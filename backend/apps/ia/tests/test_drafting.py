"""Minutas da Lia: sigilo (marcadores), preenchimento local, Word/PDF e falhas."""

import io
from typing import Any

import pytest
from docx import Document as DocxDocument

from apps.clientes.models import Client
from apps.core.tenancy import tenant_context
from apps.documentos import rendering
from apps.documentos.models import Document, DocumentDraft
from apps.ia import drafting
from apps.ia.llm import LlmError, get_llm_client
from apps.ia.llm.fake import FakeLlmClient
from apps.ia.models import AiGeneration
from apps.processos.models import CaseClient, LegalCase
from apps.processos.tests.factories import make_cnj

pytestmark = pytest.mark.django_db

DRAFTS = "/api/v1/document-drafts/"


@pytest.fixture
def llm() -> FakeLlmClient:
    client = get_llm_client()
    assert isinstance(client, FakeLlmClient)
    client.queue.clear()
    client.calls.clear()
    return client


@pytest.fixture
def as_a(tenant_a: Any, login: Any) -> Any:
    tenant_a.owner.full_name = "Dra. Ana Lima"
    tenant_a.owner.oab_number = "123456/RJ"
    tenant_a.owner.save()
    login(tenant_a.owner.email)
    return tenant_a


@pytest.fixture
def maria(tenant_a: Any) -> Client:
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(
            name="Maria da Silva",
            cpf_cnpj="52998224725",
            phone_e164="+5521998765432",
            email="maria@exemplo.com",
        )


def _create(api_client: Any, capture: Any, **body: Any) -> Any:
    with capture(execute=True):
        return api_client.post(DRAFTS, body, format="json")


def test_personal_data_never_reaches_the_ai_and_is_filled_locally(
    as_a, api_client, maria, llm, django_capture_on_commit_callbacks
):
    with tenant_context(as_a.tenant.id):
        case = LegalCase.objects.create(
            cnj_number=make_cnj(), classe="Procedimento Comum Cível", responsible=as_a.owner
        )
        CaseClient.objects.create(case=case, client=maria)
    response = _create(
        api_client,
        django_capture_on_commit_callbacks,
        kind="POWER",
        title="Procuração",
        instructions=(
            "Procuração para Maria da Silva, CPF 529.982.247-25, tel (21) 99876-5432, "
            "e-mail maria@exemplo.com, com poderes para receber e dar quitação."
        ),
        legal_case_id=str(case.pk),
    )
    assert response.status_code == 201, response.content
    draft_id = response.json()["id"]

    sent = llm.calls[-1]
    assert sent.purpose == "legal_draft"
    assert sent.timeout_seconds == drafting.TIMEOUT_SECONDS
    for secret in ("Maria", "529.982.247-25", "99876-5432", "maria@exemplo.com"):
        assert secret not in sent.user_content
    assert "[NOME DO CLIENTE]" in sent.user_content
    assert "Procedimento Comum Cível" in sent.user_content

    body = api_client.get(f"{DRAFTS}{draft_id}/").json()
    assert body["status"] == "DONE"
    assert body["missing_fields"] == ["[ENDEREÇO DO CLIENTE]"]
    assert body["review_notes"]

    with tenant_context(as_a.tenant.id):
        draft = DocumentDraft.objects.get(pk=draft_id)
        assert draft.client_id == maria.pk  # veio do processo
        docx = draft.docx
        assert docx is not None
        assert draft.pdf is not None
        assert docx.client_id == maria.pk
        assert docx.legal_case_id == case.pk
        assert docx.source == Document.Source.GENERATED
        assert draft.pdf.content_type == "application/pdf"
        with docx.file.open("rb") as fh:
            text = "\n".join(p.text for p in DocxDocument(io.BytesIO(fh.read())).paragraphs)
        assert "Maria da Silva" in text
        assert "529.982.247-25" in text
        assert "Dra. Ana Lima, OAB 123456/RJ" in text
        assert "[ENDEREÇO DO CLIENTE]" in text  # o que a Lia não sabe fica marcado
        assert AiGeneration.objects.get(pk=draft.ai_generation_id).kind == "DRAFT"

    docs = api_client.get("/api/v1/documents/", {"client": str(maria.pk)}).json()
    assert {d["name"].rsplit(".", 1)[1] for d in docs["results"]} >= {"docx", "pdf"}


def test_fee_contract_values_come_from_finance(
    as_a, api_client, maria, llm, django_capture_on_commit_callbacks
):
    agreement = api_client.post(
        "/api/v1/fee-agreements/",
        {
            "client_id": str(maria.pk),
            "title": "Ação trabalhista",
            "total_amount": "3500.00",
            "installments_count": 3,
            "first_due": "2026-12-10",
            "entry_amount": "500.00",
        },
        format="json",
    ).json()
    llm.queue.append(
        {
            "title": "Contrato",
            "body": "# CONTRATO\n\nTotal [VALOR TOTAL DOS HONORÁRIOS], entrada [VALOR DA ENTRADA], "
            "[NÚMERO DE PARCELAS] parcelas de [VALOR DA PARCELA] a partir de "
            "[VENCIMENTO DA PRIMEIRA PARCELA].",
            "review_notes": "",
        }
    )
    response = _create(
        api_client,
        django_capture_on_commit_callbacks,
        kind="FEE_CONTRACT",
        title="Contrato de honorários",
        instructions="Contrato padrão de honorários.",
        fee_agreement_id=agreement["id"],
    )
    assert response.status_code == 201, response.content
    assert "3500" not in llm.calls[-1].user_content
    with tenant_context(as_a.tenant.id):
        draft = DocumentDraft.objects.get(pk=response.json()["id"])
        assert draft.client_id == maria.pk
        assert draft.docx is not None
        assert draft.docx.category == Document.Category.CONTRATO
        with draft.docx.file.open("rb") as fh:
            text = DocxDocument(io.BytesIO(fh.read())).paragraphs[1].text
    assert "Total R$ 3.500,00, entrada R$ 500,00" in text
    assert "parcelas de R$ 1.000,00" in text


def test_needs_client_or_case(as_a, api_client, llm):
    response = api_client.post(
        DRAFTS, {"kind": "PETITION", "title": "x", "instructions": "y"}, format="json"
    )
    assert response.status_code == 400
    assert "client_id" in response.json()["error"]["details"]


def test_ai_failure_marks_draft(as_a, api_client, maria, llm, django_capture_on_commit_callbacks):
    llm.queue.append(LlmError("http_400", retryable=False))
    response = _create(
        api_client,
        django_capture_on_commit_callbacks,
        kind="PETITION",
        title="Inicial",
        instructions="Petição inicial.",
        client_id=str(maria.pk),
    )
    body = api_client.get(f"{DRAFTS}{response.json()['id']}/").json()
    assert body["status"] == "ERROR"
    assert body["error_code"] == "http_400"
    assert body["docx_id"] is None


def test_overloaded_ai_retries_then_gives_up(as_a, api_client, maria, llm):
    response = api_client.post(
        DRAFTS,
        {
            "kind": "PETITION",
            "title": "Inicial",
            "instructions": "Petição inicial.",
            "client_id": str(maria.pk),
        },
        format="json",
    )
    draft_id = response.json()["id"]
    llm.queue.append(LlmError("rate_limited", retryable=True))
    with pytest.raises(drafting.RetryableDraftError):
        drafting.generate(as_a.tenant.id, draft_id)
    assert api_client.get(f"{DRAFTS}{draft_id}/").json()["status"] == "PENDING"
    drafting.give_up(as_a.tenant.id, draft_id, "rate_limited")
    body = api_client.get(f"{DRAFTS}{draft_id}/").json()
    assert body["status"] == "ERROR"
    assert body["error_code"] == "rate_limited"


def test_other_tenant_cannot_use_my_client(tenant_b, login, api_client, maria, llm):
    login(tenant_b.owner.email)
    response = api_client.post(
        DRAFTS,
        {"kind": "PETITION", "title": "x", "instructions": "y", "client_id": str(maria.pk)},
        format="json",
    )
    assert response.status_code == 400


def test_parse_and_render():
    blocks = rendering.parse_body(
        "# TÍTULO\n\n## DOS FATOS\n\nPrimeira linha\ncontinua aqui com **negrito**.\n\n"
        "> Rio de Janeiro, [DATA]\n\nTexto “aspas” — travessão."
    )
    assert [b.kind for b in blocks] == ["title", "heading", "paragraph", "center", "paragraph"]
    assert blocks[2].text == "Primeira linha continua aqui com negrito."
    assert rendering.remaining_placeholders(blocks) == ["[DATA]"]
    docx = DocxDocument(io.BytesIO(rendering.to_docx(blocks)))
    highlighted = [r.text for p in docx.paragraphs for r in p.runs if r.font.highlight_color]
    assert highlighted == ["[DATA]"]
    assert rendering.to_pdf(blocks).startswith(b"%PDF")


def test_scrub_and_formatting():
    client = Client(name="João Souza")
    text = drafting.scrub(
        "joão souza, cnpj 12.345.678/0001-95, fone +55 21 99876-5432, j@x.com.br", client
    )
    assert text == (
        "[NOME DO CLIENTE], cnpj [CPF/CNPJ DO CLIENTE], fone [TELEFONE DO CLIENTE], "
        "[E-MAIL DO CLIENTE]"
    )
    assert drafting.format_document("12345678000195") == "12.345.678/0001-95"


def test_signature_line_is_kept():
    blocks = rendering.parse_body("> ______________________________\n> Maria da Silva")
    assert [b.text for b in blocks] == ["______________________________", "Maria da Silva"]
