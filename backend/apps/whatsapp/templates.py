"""Modelos (templates) da Meta usados pelo TramitAI.

Fora da janela de 24h, o WhatsApp só aceita template aprovado. O texto abaixo precisa ser
cadastrado igual (categoria UTILITY, idioma pt_BR) na WABA de cada escritório; o nome fica em
WhatsAppAccount.movement_template_name. Aqui ele serve para mostrar a prévia no inbox.

Regra: variáveis curtas e sem dado sensível. Detalhe do andamento só vai em texto livre,
depois que o cliente responder (janela aberta).
"""

import re
from dataclasses import dataclass

_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")
# A Meta rejeita parâmetro com quebra de linha, tab ou mais de 4 espaços seguidos.
_BAD_SPACING = re.compile(r"[\n\t]| {5,}")


@dataclass(frozen=True)
class TemplateSpec:
    default_name: str
    body: str

    def render(self, params: list[str]) -> str:
        return _PLACEHOLDER.sub(lambda m: params[int(m.group(1)) - 1], self.body)


MOVEMENT_UPDATE = TemplateSpec(
    default_name="atualizacao_processo",
    body=(
        "Olá, {{1}}! Há uma atualização no seu processo nº {{2}}. "
        "Responda esta mensagem para receber os detalhes."
    ),
)


def clean_param(value: str, *, max_length: int = 60) -> str:
    return _BAD_SPACING.sub(" ", value).strip()[:max_length]
