"""Travas pós-geração: a IA nunca pode inventar processo, data, prazo ou jurisprudência.

O prompt já proíbe; isto é a segunda trava, determinística. Se o rascunho trouxer algo que
não está no contexto que a IA recebeu, ele é trocado por uma resposta segura e marcado para o
advogado (o texto original fica registrado em AiGeneration).
"""

import re

from apps.core.br import only_digits

SAFE_REPLY = (
    "Obrigado pela mensagem! Vou encaminhar para o(a) advogado(a) responsável, "
    "que vai te responder em breve."
)

_CNJ = re.compile(r"\d{7}\s*-?\s*\d{2}\s*\.?\s*\d{4}\s*\.?\s*\d\s*\.?\s*\d{2}\s*\.?\s*\d{4}")
_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_LEGAL_CITATION = re.compile(
    r"\b(art(?:igo)?s?\.?\s*\d+|lei\s*(?:n[º°o.]*\s*)?\d|s[uú]mula|jurisprud[eê]ncia|"
    r"\bresp\b|\bagrg\b|c[oó]digo\s+(?:civil|penal|de\s+processo|de\s+defesa)|"
    r"\bcpc\b|\bclt\b|\bcdc\b)",
    re.IGNORECASE,
)
_DEADLINE = re.compile(
    r"\b(prazo|vence|vencimento)\b[^.]{0,60}\b\d+\s*(dias?|horas?|semanas?|meses?)",
    re.IGNORECASE,
)


def _normalize_date(day: str, month: str) -> str:
    return f"{int(day):02d}/{int(month):02d}"


def check_reply(reply: str, context: str) -> list[str]:
    """Lista de travas violadas (vazia = ok)."""
    flags: list[str] = []

    known_cnj = {only_digits(m) for m in _CNJ.findall(context)}
    for match in _CNJ.findall(reply):
        if only_digits(match) not in known_cnj:
            flags.append("unknown_case_number")
            break

    known_dates = {_normalize_date(d, m) for d, m, _ in _DATE.findall(context)}
    for day, month, _year in _DATE.findall(reply):
        if _normalize_date(day, month) not in known_dates:
            flags.append("unknown_date")
            break

    if _LEGAL_CITATION.search(reply):
        flags.append("legal_citation")
    if _DEADLINE.search(reply):
        flags.append("deadline")
    return flags
