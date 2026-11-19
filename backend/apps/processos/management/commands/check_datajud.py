"""Diagnóstico do DataJud: chave, tempo de resposta e o que ele tem de um processo.

    docker compose -f docker-compose.prod.yml exec backend \\
        python manage.py check_datajud 0801234-56.2024.8.19.0001

Não mostra a chave (só se está preenchida) e não grava nada no banco.
"""

import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.processos.cnj import is_valid_cnj, normalize_cnj, tribunal_alias
from apps.processos.sources import SourceError
from apps.processos.sources.datajud import DataJudSource


class Command(BaseCommand):
    help = "Testa a API do DataJud com um número de processo (não grava nada)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("cnj", help="Número CNJ do processo (com ou sem pontuação)")

    def handle(self, *args: Any, **options: Any) -> None:
        cnj = normalize_cnj(options["cnj"])
        if not is_valid_cnj(cnj):
            raise CommandError("Número CNJ inválido.")
        alias = tribunal_alias(cnj)
        if not alias:
            raise CommandError("Tribunal desconhecido para esse número.")

        key = settings.DATAJUD_API_KEY
        self.stdout.write(f"PROCESS_SOURCE = {settings.PROCESS_SOURCE}")
        self.stdout.write(
            f"Chave DataJud: {'preenchida' if key else 'VAZIA'} ({len(key)} caracteres)"
        )
        self.stdout.write(f"Timeout: {settings.DATAJUD_TIMEOUT:.0f} s · tribunal: {alias.upper()}")

        started = time.monotonic()
        try:
            snapshot = DataJudSource().fetch(cnj, alias)
        except SourceError as exc:
            took = time.monotonic() - started
            hint = {
                "http_401": "chave errada ou vencida: copie a atual da wiki do CNJ",
                "http_403": "chave errada ou vencida: copie a atual da wiki do CNJ",
                "http_429": "DataJud sobrecarregado agora; o sistema tenta de novo sozinho",
                "network": "sem resposta a tempo (lentidão do DataJud ou rede)",
                "http_504": "o próprio DataJud estourou o tempo; instabilidade do CNJ",
                "http_503": "DataJud fora do ar agora; o sistema tenta de novo sozinho",
                "not_configured": "preencha DATAJUD_API_KEY no .env",
            }.get(exc.code, "")
            raise CommandError(f"Falhou em {took:.1f} s: {exc.code} {hint}") from exc
        took = time.monotonic() - started

        if snapshot is None:
            self.stdout.write(
                self.style.WARNING(
                    f"Respondeu em {took:.1f} s, mas o DataJud NÃO tem este processo "
                    "(muito novo, segredo de justiça ou o tribunal ainda não enviou)."
                )
            )
            return
        latest = max((m.occurred_at for m in snapshot.movements), default=None)
        self.stdout.write(self.style.SUCCESS(f"OK em {took:.1f} s"))
        self.stdout.write(f"Classe: {snapshot.classe} · órgão: {snapshot.orgao_julgador}")
        updated = snapshot.source_updated_at
        self.stdout.write(
            f"DataJud atualizou este processo em: {updated:%d/%m/%Y %H:%M}" if updated else ""
        )
        self.stdout.write(
            f"{len(snapshot.movements)} andamento(s); o mais recente em {latest:%d/%m/%Y}"
            if latest
            else "Nenhum andamento."
        )
        for m in sorted(snapshot.movements, key=lambda m: m.occurred_at, reverse=True)[:5]:
            self.stdout.write(f"  {m.occurred_at:%d/%m/%Y} {m.name}")
