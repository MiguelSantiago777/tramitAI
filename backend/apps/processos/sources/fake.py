"""Fonte falsa para dev e testes: nada sai da máquina."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .base import CaseSnapshot, Movement, SourceError


def default_snapshot(cnj_number: str) -> CaseSnapshot:
    """Histórico fixo para qualquer número (dev): distribuição e conclusão."""
    return CaseSnapshot(
        cnj_number=cnj_number,
        classe="Procedimento Comum Cível",
        assuntos=("Indenização por Dano Moral",),
        orgao_julgador="1ª Vara Cível",
        movements=(
            Movement(
                name="Distribuição", code=26, occurred_at=datetime(2024, 3, 4, 13, tzinfo=UTC)
            ),
            Movement(name="Conclusão", code=51, occurred_at=datetime(2024, 3, 6, 15, tzinfo=UTC)),
        ),
    )


@dataclass
class FakeProcessSource:
    name: str = "fake"
    # cnj → snapshot (None = não encontrado). Número sem entrada: default_snapshot.
    snapshots: dict[str, CaseSnapshot | None] = field(default_factory=dict)
    fail_next: SourceError | None = None
    calls: list[str] = field(default_factory=list)

    def fetch(self, cnj_number: str, tribunal_alias: str) -> CaseSnapshot | None:
        self.calls.append(cnj_number)
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        if cnj_number in self.snapshots:
            return self.snapshots[cnj_number]
        return default_snapshot(cnj_number)
