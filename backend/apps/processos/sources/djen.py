"""DJEN — Diário de Justiça Eletrônico Nacional (API pública de comunicações do CNJ).

Endpoint: GET {DJEN_URL}/api/v1/comunicacao?numeroOab=&ufOab=&dataDisponibilizacaoInicio=&...
Sem chave. Limite observado: 20 requisições por janela (header X-RateLimit-*), 429 quando passa.

O texto vem em HTML. Guardamos SÓ texto puro (convertido aqui): a tela nunca renderiza HTML
de fora, então não há como entrar script por uma publicação.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx
from django.conf import settings

from .base import SourceError

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
PAGE_SIZE = 100
# Mais que isso numa consulta é escritório de massa; o resto vem na próxima rodada.
MAX_PAGES = 20
MAX_TEXT = 60_000


@dataclass(frozen=True)
class Communication:
    djen_id: int
    cnj_number: str
    tribunal: str
    kind: str
    document_type: str
    orgao: str
    classe: str
    available_on: date
    text: str
    link: str
    recipients: tuple[str, ...] = ()


class PublicationSource(Protocol):
    name: str

    def fetch(self, oab_number: str, uf: str, start: date, end: date) -> list[Communication]:
        """Comunicações disponibilizadas no período para a OAB (ativas apenas)."""
        ...


class DjenSource:
    name = "djen"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=settings.DJEN_TIMEOUT)

    def fetch(self, oab_number: str, uf: str, start: date, end: date) -> list[Communication]:
        url = f"{settings.DJEN_URL.rstrip('/')}/api/v1/comunicacao"
        found: list[Communication] = []
        for page in range(1, MAX_PAGES + 1):
            params = {
                "numeroOab": oab_number,
                "ufOab": uf,
                "dataDisponibilizacaoInicio": start.isoformat(),
                "dataDisponibilizacaoFim": end.isoformat(),
                "itensPorPagina": PAGE_SIZE,
                "pagina": page,
            }
            data = self._get(url, params)
            items = data.get("items") or []
            for raw in items:
                item = parse_item(raw)
                if item is not None:
                    found.append(item)
            total = data.get("count")
            if len(items) < PAGE_SIZE or (isinstance(total, int) and page * PAGE_SIZE >= total):
                break
        else:
            logger.warning("djen: limite de páginas atingido uf=%s", uf)
        return found

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise SourceError("network", retryable=True, detail=type(exc).__name__) from exc
        if not response.is_success:
            logger.warning("djen: http %s", response.status_code)
            raise SourceError(
                f"http_{response.status_code}",
                retryable=response.status_code in _RETRYABLE_HTTP,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise SourceError("bad_response", retryable=False) from exc
        if not isinstance(data, dict):
            raise SourceError("bad_response", retryable=False)
        return data


class FakeDjenSource:
    """Para dev/testes: devolve `items` filtrados pela OAB e período; nada sai da máquina."""

    name = "fake"

    def __init__(self) -> None:
        # (numero, uf) -> comunicações
        self.items: dict[tuple[str, str], list[Communication]] = {}
        self.calls: list[tuple[str, str, date, date]] = []
        self.fail_next: SourceError | None = None

    def fetch(self, oab_number: str, uf: str, start: date, end: date) -> list[Communication]:
        self.calls.append((oab_number, uf, start, end))
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        return [c for c in self.items.get((oab_number, uf), []) if start <= c.available_on <= end]


# ------------------------------------------------------------------------------------ parsing


def parse_item(raw: dict[str, Any]) -> Communication | None:
    if raw.get("ativo") is False or raw.get("data_cancelamento"):
        return None
    try:
        djen_id = int(raw["id"])
        available_on = date.fromisoformat(str(raw["data_disponibilizacao"])[:10])
    except KeyError, TypeError, ValueError:
        return None
    cnj = re.sub(r"\D", "", str(raw.get("numero_processo") or ""))
    recipients = tuple(
        str(d.get("nome") or "").strip()
        for d in raw.get("destinatarios") or []
        if isinstance(d, dict) and d.get("nome")
    )
    link = str(raw.get("link") or "")
    return Communication(
        djen_id=djen_id,
        cnj_number=cnj if len(cnj) == 20 else "",
        tribunal=_s(raw.get("siglaTribunal"), 20),
        kind=_s(raw.get("tipoComunicacao"), 60),
        document_type=_s(raw.get("tipoDocumento"), 120),
        orgao=_s(raw.get("nomeOrgao"), 255),
        classe=_s(raw.get("nomeClasse"), 255),
        available_on=available_on,
        text=html_to_text(str(raw.get("texto") or ""))[:MAX_TEXT],
        link=link if link.startswith("https://") and len(link) <= 1000 else "",
        recipients=recipients[:20],
    )


def _s(value: Any, size: int) -> str:
    return " ".join(str(value or "").split())[:size]


_BLOCK = {"p", "div", "br", "tr", "section", "article", "header", "li", "h1", "h2", "h3", "table"}
_SKIP = {"style", "script", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """HTML do diário → texto puro com quebras de parágrafo."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


_DEADLINE = re.compile(
    r"prazo\s+(?:comum\s+|legal\s+|sucessivo\s+)?de\s+(\d{1,3})\s*(?:\([^)]{1,40}\)\s*)?"
    r"(dias?\s+[úu]teis|dias?\s+corridos|dias?|horas?)",
    re.IGNORECASE,
)


def deadline_hints(text: str) -> list[str]:
    """Trechos "prazo de N dias" citados no texto. Só dica: o TramitAI não calcula prazo."""
    hints: list[str] = []
    for number, unit in _DEADLINE.findall(text):
        hint = f"{int(number)} {' '.join(unit.lower().split())}"
        if hint not in hints:
            hints.append(hint)
    return hints[:3]
