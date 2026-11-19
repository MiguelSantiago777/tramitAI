"""Minutas da Lia (petição, contrato, procuração...) → .docx e .pdf na pasta do cliente.

Três fases, como no resto da IA: prepara numa transação curta, chama o LLM FORA de
transação e grava numa transação curta.

Sigilo: para o provedor de IA vão só o pedido do advogado (com nome, CPF, telefone e e-mail
do cliente trocados por marcadores), o tipo de pessoa, o papel no processo e os dados públicos
do processo (classe, assunto, órgão). A Lia escreve com marcadores e os dados reais entram
aqui, no servidor, na hora de montar o Word/PDF.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.clientes.models import Client
from apps.core import audit
from apps.core.tenancy import tenant_atomic
from apps.documentos import rendering
from apps.documentos.models import Document, DocumentDraft
from apps.processos.cnj import format_cnj
from apps.processos.models import CaseClient
from apps.tenants.models import Tenant

from .llm import LlmError, LlmRefusal, LlmRequest, LlmResult, get_llm_client
from .models import AiGeneration
from .prompts import load_prompt

logger = logging.getLogger(__name__)

PROMPT = "legal_draft"
TIMEOUT_SECONDS = 150.0
MAX_INSTRUCTIONS = 6000
MAX_BODY = 60_000

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "review_notes": {"type": "string"},
    },
    "required": ["title", "body", "review_notes"],
    "additionalProperties": False,
}

CATEGORY = {
    DocumentDraft.Kind.FEE_CONTRACT: Document.Category.CONTRATO,
    DocumentDraft.Kind.POWER_OF_ATTORNEY: Document.Category.CONTRATO,
}

_MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


class RetryableDraftError(Exception):
    pass


@dataclass(frozen=True)
class _Plan:
    prompt_version: str
    system: str
    user_content: str


# ------------------------------------------------------------------------------- dados reais


def _money(value: Decimal) -> str:
    whole, cents = f"{value:.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"R$ {groups},{cents}"


def long_date(day: date) -> str:
    return f"{day.day} de {_MONTHS[day.month - 1]} de {day.year}"


def format_document(value: str) -> str:
    if len(value) == 11 and value.isdigit():
        return f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
    if len(value) == 14:
        return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
    return value


def placeholder_values(draft: DocumentDraft) -> dict[str, str]:
    """Marcador → dado real (tenant ativo). Dado vazio fica de fora (o marcador continua)."""
    values: dict[str, str] = {
        "[DATA DE HOJE]": long_date(timezone.localdate()),
        "[NOME DO ESCRITÓRIO]": Tenant.objects.get(pk=draft.tenant_id).name,
    }
    client = draft.client
    if client is not None:
        values.update(
            {
                "[NOME DO CLIENTE]": client.name,
                "[CPF/CNPJ DO CLIENTE]": format_document(client.cpf_cnpj),
                "[TELEFONE DO CLIENTE]": client.phone_e164,
                "[E-MAIL DO CLIENTE]": client.email,
            }
        )
    case = draft.legal_case
    lawyer = (case.responsible if case and case.responsible else None) or draft.created_by
    if lawyer is not None:
        values["[NOME DO ADVOGADO]"] = lawyer.full_name
        values["[OAB DO ADVOGADO]"] = lawyer.oab_number
    if case is not None:
        values["[NÚMERO DO PROCESSO]"] = format_cnj(case.cnj_number)
        values["[VARA/ÓRGÃO JULGADOR]"] = case.orgao_julgador
        values["[TRIBUNAL]"] = case.tribunal_label
    agreement = draft.fee_agreement
    if agreement is not None:
        parts = list(agreement.installments.order_by("number"))
        values["[VALOR TOTAL DOS HONORÁRIOS]"] = _money(agreement.total_amount)
        if parts:
            entry = parts[0] if len(parts) > 1 and parts[0].amount != parts[1].amount else None
            rest = parts[1:] if entry else parts
            if entry is not None:
                values["[VALOR DA ENTRADA]"] = _money(entry.amount)
            values["[NÚMERO DE PARCELAS]"] = str(len(rest))
            values["[VALOR DA PARCELA]"] = _money(rest[0].amount)
            values["[VENCIMENTO DA PRIMEIRA PARCELA]"] = rest[0].due_date.strftime("%d/%m/%Y")
    return {k: v for k, v in values.items() if v}


def fill(text: str, values: dict[str, str]) -> str:
    for marker, value in values.items():
        text = text.replace(marker, value)
    return text


_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")


def scrub(text: str, client: Client | None) -> str:
    """Tira do pedido os dados pessoais óbvios antes de mandar para a IA."""
    if client is not None and len(client.name.strip()) >= 3:
        text = re.sub(re.escape(client.name.strip()), "[NOME DO CLIENTE]", text, flags=re.I)
    text = _CNPJ.sub("[CPF/CNPJ DO CLIENTE]", text)
    text = _CPF.sub("[CPF/CNPJ DO CLIENTE]", text)
    text = _EMAIL.sub("[E-MAIL DO CLIENTE]", text)
    return _PHONE.sub("[TELEFONE DO CLIENTE]", text)


# ------------------------------------------------------------------------------- contexto


def _context(draft: DocumentDraft) -> str:
    lines = [
        "<pedido>",
        f"Tipo: {draft.get_kind_display()}",
        f"Título: {draft.title}",
        "O que o(a) advogado(a) pediu:",
        scrub(draft.instructions[:MAX_INSTRUCTIONS], draft.client),
        "</pedido>",
    ]
    case = draft.legal_case
    if case is not None:
        lines += [
            "<processo>",
            f"Classe: {case.classe or '-'}",
            f"Assunto: {case.assunto or '-'}",
            f"Órgão julgador: {case.orgao_julgador or '-'}",
            f"Tribunal: {case.tribunal_label or '-'}",
            "</processo>",
        ]
    client = draft.client
    if client is not None:
        role = ""
        if case is not None:
            link = CaseClient.objects.filter(case=case, client=client).first()
            role = link.get_role_display() if link else ""
        lines += [
            "<cliente>",
            f"Tipo: {client.get_kind_display()}",
            f"Papel no processo: {role or 'não informado'}",
            "</cliente>",
        ]
    agreement = draft.fee_agreement
    if agreement is not None:
        count = agreement.installments.count()
        lines += [
            "<honorarios>",
            f"Tipo: {agreement.get_kind_display()}",
            f"Pagamento: {count} parcela(s) cadastrada(s) no sistema",
            "</honorarios>",
        ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------- fluxo


def generate(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> str:
    """Escreve a minuta. Idempotente: minuta pronta ou com erro não é refeita."""
    from apps.cobranca.limits import ai_allowed

    with tenant_atomic(tenant_id):
        draft = (
            DocumentDraft.objects.select_related("client", "legal_case", "fee_agreement")
            .filter(pk=draft_id)
            .first()
        )
        if draft is None or draft.status != DocumentDraft.Status.PENDING:
            return "skipped"
        if not ai_allowed(tenant_id):
            _fail(draft, "ai_limit")
            return "error:ai_limit"
        prompt = load_prompt(PROMPT)
        plan = _Plan(prompt.version, prompt.text, _context(draft))

    try:
        result = get_llm_client().complete(
            LlmRequest(
                system=plan.system,
                user_content=plan.user_content,
                json_schema=SCHEMA,
                purpose=PROMPT,
                timeout_seconds=TIMEOUT_SECONDS,
            )
        )
    except LlmError as exc:
        if exc.retryable and not isinstance(exc, LlmRefusal):
            raise RetryableDraftError(exc.code) from exc
        with tenant_atomic(tenant_id):
            _record_failure(draft_id, plan, exc)
        return f"error:{exc.code}"

    with tenant_atomic(tenant_id):
        return _store(draft_id, plan, result)


def give_up(tenant_id: uuid.UUID, draft_id: uuid.UUID, code: str) -> None:
    """A task desistiu depois das novas tentativas."""
    with tenant_atomic(tenant_id):
        draft = DocumentDraft.objects.filter(
            pk=draft_id, status=DocumentDraft.Status.PENDING
        ).first()
        if draft is not None:
            _fail(draft, code)


def _fail(draft: DocumentDraft, code: str) -> None:
    draft.status = DocumentDraft.Status.ERROR
    draft.error_code = code[:64]
    draft.save(update_fields=["status", "error_code", "updated_at"])


def _record_failure(draft_id: uuid.UUID, plan: _Plan, exc: LlmError) -> None:
    draft = DocumentDraft.objects.get(pk=draft_id)
    generation = AiGeneration.objects.create(
        kind=AiGeneration.Kind.LEGAL_DRAFT,
        status=AiGeneration.Status.REFUSED
        if isinstance(exc, LlmRefusal)
        else AiGeneration.Status.ERROR,
        prompt_name=PROMPT,
        prompt_version=plan.prompt_version,
        provider=get_llm_client().provider,
        legal_case_id=draft.legal_case_id,
        error_code=exc.code[:64],
    )
    draft.ai_generation = generation
    draft.save(update_fields=["ai_generation", "updated_at"])
    _fail(draft, exc.code)


def _store(draft_id: uuid.UUID, plan: _Plan, result: LlmResult) -> str:
    draft = DocumentDraft.objects.select_related(
        "client", "legal_case__responsible", "fee_agreement", "created_by"
    ).get(pk=draft_id)
    if draft.status != DocumentDraft.Status.PENDING:
        return "skipped"
    generation = AiGeneration.objects.create(
        kind=AiGeneration.Kind.LEGAL_DRAFT,
        status=AiGeneration.Status.OK,
        prompt_name=PROMPT,
        prompt_version=plan.prompt_version,
        provider=result.provider,
        model=result.model,
        legal_case=draft.legal_case,
        output_text=result.raw_text,
        output_data=result.data,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        request_id=result.request_id[:128],
    )
    draft.ai_generation = generation
    body = str(result.data.get("body") or "").strip()[:MAX_BODY]
    blocks = rendering.parse_body(fill(body, placeholder_values(draft)))
    if not blocks:
        generation.status = AiGeneration.Status.ERROR
        generation.error_code = "invalid_output"
        generation.save(update_fields=["status", "error_code", "updated_at"])
        draft.save(update_fields=["ai_generation", "updated_at"])
        _fail(draft, "invalid_output")
        return "error:invalid_output"

    title = str(result.data.get("title") or draft.title).strip()[:150] or draft.title
    category = CATEGORY.get(draft.kind, Document.Category.PECA)
    draft.docx = _save_file(
        draft,
        f"{title}.docx",
        rendering.to_docx(blocks),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        category,
    )
    draft.pdf = _save_file(
        draft, f"{title}.pdf", rendering.to_pdf(blocks), "application/pdf", category
    )
    draft.missing_fields = rendering.remaining_placeholders(blocks)
    draft.review_notes = str(result.data.get("review_notes") or "").strip()[:2000]
    draft.status = DocumentDraft.Status.DONE
    draft.save()
    audit.record(
        "draft.generated",
        draft,
        actor_type=audit.Actor.AI,
        data={"kind": draft.kind, "missing": len(draft.missing_fields)},
    )
    return "done"


def _save_file(
    draft: DocumentDraft, name: str, content: bytes, content_type: str, category: str
) -> Document:
    from apps.documentos.services import _hash, safe_filename

    name = safe_filename(name.replace("/", "-").replace("\\", "-"), "minuta")
    upload = ContentFile(content, name=name)
    document = Document(
        name=name,
        content_type=content_type,
        size=len(content),
        sha256=_hash(upload),
        category=category,
        description="Minuta escrita pela Lia: revise antes de usar.",
        source=Document.Source.GENERATED,
        client=draft.client,
        legal_case=draft.legal_case,
        uploaded_by=draft.created_by,
    )
    document.file.save(name, upload, save=False)
    document.save()
    return document
