from django.db import migrations


def unlimit(apps, schema_editor):
    """Escritório e Equipe: Lia liberada (só o Essencial tem limite mensal)."""
    Plan = apps.get_model("cobranca", "Plan")
    Plan.objects.filter(code__in=["escritorio", "equipe"]).update(monthly_ai_limit=None)


class Migration(migrations.Migration):
    dependencies = [("cobranca", "0004_plan_ai_limit_and_tiers")]

    operations = [migrations.RunPython(unlimit, migrations.RunPython.noop)]
