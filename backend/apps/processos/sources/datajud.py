"""API Pública do DataJud (CNJ).

Endpoint: POST {DATAJUD_URL}/api_publica_{alias}/_search, com header
`Authorization: APIKey <chave pública divulgada pelo CNJ>`. A chave fica só em variável de
ambiente (o CNJ pode trocá-la a qualquer momento).

O DataJud devolve um documento por grau/instância (G1, G2, JE...). Juntamos os movimentos de
todos. Os movimentos não têm id: a deduplicação é feita por hash do conteúdo (ver monitoring).
"""

import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings

from .base import CaseSnapshot, Movement, SourceError

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
# Datas sem fuso no DataJud são horário de Brasília.
_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
_MIN = datetime(1900, 1, 1, tzinfo=UTC)


class DataJudSource:
    name = "datajud"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=settings.DATAJUD_TIMEOUT)

    def fetch(self, cnj_number: str, tribunal_alias: str) -> CaseSnapshot | None:
        if not settings.DATAJUD_API_KEY:
            raise SourceError("not_configured", retryable=False, detail="DATAJUD_API_KEY vazio")
        url = f"{settings.DATAJUD_URL.rstrip('/')}/api_publica_{tribunal_alias}/_search"
        body = {"size": 10, "query": {"match": {"numeroProcesso": cnj_number}}}
        try:
            response = self._client.post(
                url,
                json=body,
                headers={"Authorization": f"APIKey {settings.DATAJUD_API_KEY}"},
            )
        except httpx.HTTPError as exc:
            # Consulta é só leitura: repetir não tem efeito colateral.
            raise SourceError("network", retryable=True, detail=type(exc).__name__) from exc

        if response.status_code == 404:
            # Índice do tribunal não existe no DataJud.
            raise SourceError("unknown_tribunal", retryable=False, detail=tribunal_alias)
        if not response.is_success:
            logger.warning("datajud: http %s alias=%s", response.status_code, tribunal_alias)
            raise SourceError(
                f"http_{response.status_code}",
                retryable=response.status_code in _RETRYABLE_HTTP,
            )
        try:
            hits = response.json()["hits"]["hits"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("bad_response", retryable=False) from exc
        return parse_hits(cnj_number, [h.get("_source") or {} for h in hits])


def parse_hits(cnj_number: str, sources: list[dict[str, Any]]) -> CaseSnapshot | None:
    docs = [s for s in sources if str(s.get("numeroProcesso", "")) == cnj_number]
    if not docs:
        return None
    # Documento atualizado mais recentemente primeiro: dele vêm classe, assunto e órgão.
    docs.sort(key=lambda s: _updated_at(s) or _MIN, reverse=True)
    main = docs[0]

    movements: list[Movement] = []
    for doc in docs:
        grau = str(doc.get("grau") or "")
        for raw in doc.get("movimentos") or []:
            movement = _movement(raw, grau)
            if movement is not None:
                movements.append(movement)
    movements.sort(key=lambda m: m.occurred_at)

    updated = [d for d in (_updated_at(s) for s in docs) if d is not None]
    return CaseSnapshot(
        cnj_number=cnj_number,
        classe=_name(main.get("classe")),
        assuntos=tuple(n for n in (_name(a) for a in main.get("assuntos") or []) if n),
        orgao_julgador=_name(main.get("orgaoJulgador")),
        source_updated_at=max(updated) if updated else None,
        movements=tuple(movements),
    )


def _updated_at(doc: dict[str, Any]) -> datetime | None:
    return parse_datetime(doc.get("dataHoraUltimaAtualizacao"))


def _name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("nome") or "").strip()
    if isinstance(value, list):  # alguns tribunais mandam assunto aninhado em lista
        return _name(value[0]) if value else ""
    return ""


def _movement(raw: Any, grau: str) -> Movement | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("nome") or "").strip()
    occurred_at = parse_datetime(raw.get("dataHora"))
    if not name or occurred_at is None:
        return None
    complements = []
    for c in raw.get("complementosTabelados") or []:
        if not isinstance(c, dict):
            continue
        label = str(c.get("descricao") or "").replace("_", " ").strip()
        value = str(c.get("nome") or c.get("valor") or "").strip()
        if value:
            complements.append(f"{label}: {value}" if label else value)
    code = raw.get("codigo")
    return Movement(
        name=name,
        occurred_at=occurred_at,
        code=int(str(code)) if str(code).isdigit() else None,
        complements=tuple(complements),
        grau=grau,
    )


def parse_datetime(value: Any) -> datetime | None:
    """Aceita ISO 8601 (com ou sem fuso) e o formato compacto AAAAMMDD[hhmmss]."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.isdigit() and len(text) in (8, 14):
            parsed = datetime.strptime(text, "%Y%m%d%H%M%S" if len(text) == 14 else "%Y%m%d")
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_LOCAL_TZ)
    return parsed
