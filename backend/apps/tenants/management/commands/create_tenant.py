import getpass
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.tenants.services import create_tenant


class Command(BaseCommand):
    help = "Cria um escritório (tenant) com o usuário OWNER. Onboarding manual do piloto."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--name", required=True)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--owner-name", default="")
        parser.add_argument("--slug", default=None)

    def handle(self, *args: Any, **options: Any) -> None:
        password = getpass.getpass("Senha do OWNER (vazio se o usuário já existe): ") or None
        try:
            created = create_tenant(
                name=options["name"],
                slug=options["slug"],
                owner_email=options["owner_email"],
                owner_full_name=options["owner_name"],
                owner_password=password,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Escritório criado: {created.tenant.id}"))
