import json
import time
import uuid
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from apps.whatsapp.signature import sign


def build_payload(*, phone_number_id: str, wa_id: str, name: str, text: str) -> dict[str, Any]:
    """Payload no formato do webhook da Meta para uma mensagem de texto."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5521000000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": f"wamid.sim.{uuid.uuid4().hex}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


class Command(BaseCommand):
    help = "DEV: simula uma mensagem recebida, passando pelo webhook real (com assinatura)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--phone-number-id", required=True)
        parser.add_argument("--from", dest="wa_id", required=True, help="Ex.: 5521998765432")
        parser.add_argument("--name", default="Contato de teste")
        parser.add_argument("--text", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("Só em desenvolvimento (DEBUG=True).")
        if not settings.WHATSAPP_APP_SECRET:
            raise CommandError("Defina WHATSAPP_APP_SECRET no .env.")
        body = json.dumps(
            build_payload(
                phone_number_id=options["phone_number_id"],
                wa_id=options["wa_id"],
                name=options["name"],
                text=options["text"],
            )
        ).encode()
        response = Client().post(
            "/api/webhooks/whatsapp/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sign(body, settings.WHATSAPP_APP_SECRET)},
            SERVER_NAME="localhost",
        )
        self.stdout.write(f"Webhook respondeu {response.status_code}.")
