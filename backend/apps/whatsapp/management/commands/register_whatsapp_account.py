import getpass
import os
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Tenant
from apps.whatsapp.services import register_account


class Command(BaseCommand):
    help = (
        "Cadastra o número de WhatsApp de um escritório (onboarding manual do piloto). "
        "O token vem de WHATSAPP_ACCESS_TOKEN ou é pedido no terminal; nunca por argumento."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument("--phone-number-id", required=True)
        parser.add_argument("--waba-id", required=True)
        parser.add_argument("--display-phone", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError("Escritório não encontrado.")
        token = os.environ.get("WHATSAPP_ACCESS_TOKEN") or getpass.getpass("Token da Cloud API: ")
        if not token:
            raise CommandError("Token vazio.")
        account = register_account(
            tenant=tenant,
            phone_number_id=options["phone_number_id"],
            waba_id=options["waba_id"],
            display_phone=options["display_phone"],
            access_token=token,
        )
        self.stdout.write(self.style.SUCCESS(f"Conta cadastrada: {account.id}"))
