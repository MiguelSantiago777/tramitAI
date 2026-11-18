"""Complementa o escritório de demonstração para os manuais (equipe, respostas prontas,
etiquetas). Rodar depois do seed_demo.py. Idempotente."""

from apps.accounts.models import Membership, User
from apps.clientes.models import Client, ClientTag, Tag
from apps.core.tenancy import tenant_atomic
from apps.tenants.models import Tenant
from apps.whatsapp.models import QuickReply

tenant = Tenant.objects.get(name="Silva & Lima Advocacia")
owner = Membership.objects.get(tenant=tenant, role=Membership.Role.OWNER).user

for email, name, role in [
    ("carla.mendes@silvalima.test", "Dra. Carla Mendes", Membership.Role.LAWYER),
    ("paula.secretaria@silvalima.test", "Paula Souza", Membership.Role.STAFF),
]:
    user = User.objects.filter(email=email).first() or User.objects.create_user(
        email=email, password=None, full_name=name
    )
    Membership.objects.get_or_create(user=user, tenant=tenant, defaults={"role": role})

with tenant_atomic(tenant.id):
    for title, body in [
        ("Documentos para aposentadoria", "Olá, {nome}! Para analisarmos sua aposentadoria, "
         "precisamos do RG, CPF, carteira de trabalho e do extrato do CNIS."),
        ("Horário de atendimento", "Nosso atendimento é de segunda a sexta, das 9h às 18h."),
        ("Endereço do escritório", "Estamos na Av. Rio Branco, 100, sala 1201, Centro."),
    ]:
        QuickReply.objects.get_or_create(title=title, defaults={"body": body, "created_by": owner})
    tags = {}
    for name, color in [("Previdenciário", "teal"), ("Trabalhista", "amber"), ("VIP", "pink")]:
        tags[name], _ = Tag.objects.get_or_create(name=name, defaults={"color": color})
    for client_name, tag in [
        ("Maria Aparecida Oliveira", "Previdenciário"),
        ("Maria Aparecida Oliveira", "VIP"),
        ("Carlos Eduardo Santos", "Trabalhista"),
        ("João Batista Pereira", "Trabalhista"),
    ]:
        client = Client.objects.get(name=client_name)
        ClientTag.objects.get_or_create(client=client, tag=tags[tag])
print("ok")
