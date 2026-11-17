from django.db import migrations

from apps.core.db import MakeAppendOnly


class Migration(migrations.Migration):
    dependencies = [
        ("clientes", "0001_initial"),
        ("core", "0001_initial"),
    ]

    operations = [
        MakeAppendOnly("clienttermacceptance"),
    ]
