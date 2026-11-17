"""Dev: simula um andamento novo chegando da fonte, sem chamar o DataJud.

    python manage.py simulate_movement --tenant escritorio-demo \\
        --cnj 0801234-56.2024.8.19.0001 --name "Conclusão"

Passa pelo mesmo caminho da consulta real (ingest_snapshot → sinal → IA → rascunho).
"""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.tenancy import tenant_atomic
from apps.processos import monitoring
from apps.processos.cnj import normalize_cnj
from apps.processos.models import LegalCase
from apps.processos.sources import CaseSnapshot, Movement
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Simula um andamento novo num processo (dev)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant", required=True, help="slug do escritório")
        parser.add_argument("--cnj", required=True)
        parser.add_argument("--name", required=True, help='Ex.: "Conclusão"')
        parser.add_argument("--complement", action="append", default=[])

    def handle(self, *args: Any, **options: Any) -> None:
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            raise CommandError("Escritório não encontrado.")
        cnj = normalize_cnj(options["cnj"])
        with tenant_atomic(tenant.id):
            case = LegalCase.objects.filter(cnj_number=cnj).first()
            if case is None:
                raise CommandError("Processo não cadastrado neste escritório.")
            if case.baseline_at is None:
                # Sem linha de base, o andamento seria tratado como histórico.
                monitoring.ingest_snapshot(case.pk, CaseSnapshot(cnj_number=cnj), source="dev")
            new = Movement(
                name=options["name"],
                occurred_at=timezone.now(),
                complements=tuple(options["complement"]),
            )
            outcome = monitoring.ingest_snapshot(
                case.pk, CaseSnapshot(cnj_number=cnj, movements=(new,)), source="dev"
            )
        self.stdout.write(self.style.SUCCESS(f"Processo {case.cnj_formatted}: {outcome}"))
