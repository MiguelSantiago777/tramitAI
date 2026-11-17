"""Interface de fonte de andamentos. O resto do sistema só conhece isto, nunca o DataJud."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Movement:
    name: str
    occurred_at: datetime
    code: int | None = None
    # Complementos tabelados já em texto, ex.: "tipo de documento: Petição".
    complements: tuple[str, ...] = ()
    # Grau/instância de onde veio (G1, G2, JE...). Um processo pode ter registro em mais de um.
    grau: str = ""


@dataclass(frozen=True)
class CaseSnapshot:
    cnj_number: str
    classe: str = ""
    assuntos: tuple[str, ...] = ()
    orgao_julgador: str = ""
    # Quando a fonte atualizou o registro pela última vez (pode ser None).
    source_updated_at: datetime | None = None
    movements: tuple[Movement, ...] = field(default_factory=tuple)


class SourceError(Exception):
    """Falha ao consultar a fonte. retryable=True: vale tentar de novo (rede, 429, 5xx)."""

    def __init__(self, code: str, *, retryable: bool, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.detail = detail[:255]


class ProcessSource(Protocol):
    name: str

    def fetch(self, cnj_number: str, tribunal_alias: str) -> CaseSnapshot | None:
        """Snapshot do processo, ou None se a fonte não conhece o número."""
        ...
