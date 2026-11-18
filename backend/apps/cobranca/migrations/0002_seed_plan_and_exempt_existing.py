from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    Plan = apps.get_model("cobranca", "Plan")
    Subscription = apps.get_model("cobranca", "Subscription")
    Tenant = apps.get_model("tenants", "Tenant")

    # Preço inicial: ajuste no admin (Planos) antes de abrir as vendas.
    Plan.objects.get_or_create(
        code="escritorio",
        defaults={
            "name": "TramitAI Escritório",
            "price": Decimal("197.00"),
            "description": "WhatsApp com a Lia, processos, agenda, funil, documentos e financeiro.",
        },
    )
    # Escritórios criados antes da assinatura existir não são bloqueados.
    for tenant in Tenant.objects.all():
        Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={"status": "EXEMPT", "notes": "Criado antes da assinatura (isento)."},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cobranca", "0001_initial"),
        ("tenants", "0003_tenantsettings_ai_triage_enabled"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
