"""Escritório fictício para o vídeo de apresentação (rodar no dev: manage.py shell < seed_demo.py).

Tudo inventado: nomes, telefones, CPFs e processos. Idempotente: apaga e recria o escritório
"Silva & Lima Advocacia" (login: video@tramitai.local / video-senha-123).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone

from apps.accounts.models import User
from apps.agenda.models import Event, Task
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client, ClientTermAcceptance
from apps.core.tenancy import tenant_atomic
from apps.documentos.models import Document
from apps.financeiro import services as finance
from apps.funil.models import Opportunity
from apps.processos.models import CaseClient, CaseMovement, LegalCase
from apps.processos.tests.factories import make_cnj
from apps.tenants.models import Tenant, TenantSettings
from apps.tenants.services import active_term_version, create_tenant
from apps.whatsapp.models import Conversation, Message
from apps.whatsapp.services import register_account

TZ = ZoneInfo("America/Sao_Paulo")
NAME = "Silva & Lima Advocacia"
EMAIL = "video@tramitai.local"

if Tenant.objects.filter(name=NAME).exists():
    print("Escritório de demonstração já existe; usando o existente.")
    raise SystemExit

created = create_tenant(
    name=NAME,
    owner_email=EMAIL,
    owner_password="video-senha-123",
    owner_full_name="Dra. Beatriz Lima",
)
tenant, owner = created.tenant, created.owner
User.objects.filter(pk=owner.pk).update(full_name="Dra. Beatriz Lima")
account = register_account(
    tenant=tenant,
    phone_number_id=f"video-{tenant.id.hex[:8]}",
    waba_id="video",
    display_phone="+55 21 3333-4444",
    access_token="token-de-demonstracao",
)
now = timezone.now()
today = timezone.localdate()


def at(days: int, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(today + timedelta(days=days), time(hour, minute), tzinfo=TZ)


def msg(conv, direction, body, minutes_ago, *, by=None):
    m = Message.objects.create(
        conversation=conv,
        direction=direction,
        body=body,
        status="RECEIVED" if direction == "IN" else "READ",
        sent_by=by,
        wa_timestamp=now - timedelta(minutes=minutes_ago),
    )
    Message.objects.filter(pk=m.pk).update(created_at=now - timedelta(minutes=minutes_ago))
    return m


with tenant_atomic(tenant.id):
    TenantSettings.objects.update(
        auto_send_simple_replies=True, scheduling_enabled=True, consult_minutes=60
    )
    term = active_term_version()

    # ------------------------------------------------------------ clientes e processos
    maria = Client.objects.create(
        name="Maria Aparecida Oliveira",
        cpf_cnpj="52998224725",
        phone_e164="+5521998761234",
        email="maria.oliveira@exemplo.com.br",
    )
    carlos = Client.objects.create(
        name="Carlos Eduardo Santos", phone_e164="+5521987654321", cpf_cnpj="11144477735"
    )
    ana = Client.objects.create(name="Ana Paula Ferreira", phone_e164="+5521976543210")
    joao = Client.objects.create(
        name="João Batista Pereira", phone_e164="+5521965432109", status=Client.Status.LEAD
    )
    for c in (maria, carlos, ana, joao):
        ClientTermAcceptance.objects.create(
            client=c,
            term_version=term,
            channel=ClientTermAcceptance.Channel.WHATSAPP,
            accepted_at=now - timedelta(days=10),
            evidence="WhatsApp (demonstração)",
        )

    case_maria = LegalCase.objects.create(
        cnj_number=make_cnj(801234, court="19"),
        classe="Procedimento Comum Cível",
        assunto="Aposentadoria por tempo de contribuição",
        orgao_julgador="3ª Vara Federal Previdenciária",
        responsible=owner,
        last_movement_at=now - timedelta(days=2),
    )
    CaseClient.objects.create(case=case_maria, client=maria)
    for i, (name, days) in enumerate(
        [
            ("Conclusos para decisão", 2),
            ("Juntada de petição", 9),
            ("Citação expedida", 30),
        ]
    ):
        CaseMovement.objects.create(
            case=case_maria,
            source="datajud",
            fingerprint=f"demo-{i}",
            name=name,
            occurred_at=now - timedelta(days=days),
            notification=CaseMovement.Notification.NOTIFIED if i else "PENDING",
        )
    case_carlos = LegalCase.objects.create(
        cnj_number=make_cnj(507711, court="01", segment="5"),
        classe="Reclamação Trabalhista",
        assunto="Verbas rescisórias",
        orgao_julgador="45ª Vara do Trabalho",
        responsible=owner,
        last_movement_at=now - timedelta(days=5),
    )
    CaseClient.objects.create(case=case_carlos, client=carlos)

    # ------------------------------------------------------------ conversas
    conv_maria = Conversation.objects.create(
        account=account,
        wa_id="5521998761234",
        contact_name="Maria Oliveira",
        client=maria,
        last_inbound_at=now - timedelta(minutes=12),
        last_message_at=now - timedelta(minutes=12),
        unread_count=1,
        assignee=owner,
    )
    msg(conv_maria, "IN", "Bom dia, doutora! Tem alguma novidade do meu processo da aposentadoria?", 12)
    OutboundDraft.objects.create(
        conversation=conv_maria,
        client=maria,
        origin=OutboundDraft.Origin.AI_REPLY,
        generated_body=(
            "Bom dia, Maria! Seu processo teve uma movimentação há 2 dias: ele foi enviado ao "
            "juiz para decisão. Isso é uma etapa normal. Assim que houver a decisão, a doutora "
            "te avisa por aqui."
        ),
        intent="case_status",
        urgency="normal",
        summary="Cliente pergunta do processo de aposentadoria. Último andamento: conclusos para decisão.",
        legal_case=case_maria,
    )

    conv_joao = Conversation.objects.create(
        account=account,
        wa_id="5521965432109",
        contact_name="João Pereira",
        client=joao,
        last_inbound_at=now - timedelta(minutes=3),
        last_message_at=now - timedelta(minutes=2),
    )
    lia = [
        ("IN", "Boa noite! Fui demitido semana passada e não recebi nada. Vocês podem me ajudar?", 30),
        ("OUT", "Boa noite! Nosso atendimento é de segunda a sexta, das 9h às 18h, mas já vou adiantando o seu atendimento. Sinto muito pelo que aconteceu. Qual é o seu nome completo?", 29),
        ("IN", "João Batista Pereira", 26),
        ("OUT", "Obrigada, João. Me conta com suas palavras: quanto tempo você trabalhou lá e o que exatamente não foi pago?", 25),
        ("IN", "Trabalhei 4 anos numa transportadora. Não pagaram as férias, o FGTS nem a multa.", 20),
        ("OUT", "Entendi. A Dra. Beatriz pode conversar com você nestes horários: amanhã às 10:00, amanhã às 14:00 ou quinta às 09:00. Prefere presencial, no escritório, ou online?", 19),
        ("IN", "Amanhã às 14h, online", 4),
        ("OUT", "Pré-reservei amanhã às 14:00, online. A Dra. Beatriz vai confirmar por aqui.", 3),
    ]
    for direction, body, minutes in lia:
        msg(conv_joao, direction, body, minutes)

    conv_ana = Conversation.objects.create(
        account=account,
        wa_id="5521976543210",
        contact_name="Ana Paula",
        client=ana,
        last_inbound_at=now - timedelta(hours=3),
        last_message_at=now - timedelta(hours=3),
    )
    msg(conv_ana, "IN", "Segue o comprovante de residência que a doutora pediu.", 180)
    doc_msg = Message.objects.create(
        conversation=conv_ana,
        direction="IN",
        type="document",
        body="",
        status="RECEIVED",
        media_id="demo",
        wa_timestamp=now - timedelta(minutes=179),
    )
    pdf = ContentFile(b"%PDF-1.4 documento de demonstracao")
    for name, client, kind, conv, message, category in [
        ("comprovante-residencia.pdf", ana, "WHATSAPP", conv_ana, doc_msg, "WHATSAPP"),
        ("procuracao-assinada.pdf", maria, "UPLOAD", None, None, "CONTRATO"),
        ("CNIS-Maria.pdf", maria, "UPLOAD", None, None, "PESSOAL"),
    ]:
        d = Document(
            name=name,
            content_type="application/pdf",
            size=184_320,
            sha256="0" * 64,
            category=category,
            source=kind,
            client=client,
            conversation=conv,
            message=message,
            uploaded_by=owner if kind == "UPLOAD" else None,
        )
        d.file.save(name, pdf, save=False)
        d.save()

    # ------------------------------------------------------------ agenda e tarefas
    Event.objects.create(
        title="Consulta inicial - João Batista Pereira",
        kind=Event.Kind.CONSULTATION,
        status=Event.Status.PENDING,
        starts_at=at(1, 14),
        ends_at=at(1, 15),
        location="Online (vídeo ou telefone)",
        notes="Marcado pela Vera no WhatsApp. Demitido sem verbas rescisórias após 4 anos.",
        responsible=owner,
        client=joao,
        remind_client=True,
    )
    Event.objects.create(
        title="Audiência de instrução - Carlos Santos",
        kind=Event.Kind.HEARING,
        starts_at=at(2, 13, 30),
        ends_at=at(2, 15),
        location="45ª Vara do Trabalho",
        responsible=owner,
        client=carlos,
        legal_case=case_carlos,
        remind_client=True,
    )
    Event.objects.create(
        title="Reunião com Maria Oliveira",
        kind=Event.Kind.MEETING,
        starts_at=at(3, 10),
        ends_at=at(3, 11),
        location="Escritório",
        responsible=owner,
        client=maria,
    )
    for title, days, prio in [
        ("Protocolar réplica - Carlos Santos", 1, "HIGH"),
        ("Pedir CNIS atualizado da Maria", 0, "NORMAL"),
        ("Enviar contrato de honorários ao João", 2, "NORMAL"),
    ]:
        Task.objects.create(
            title=title, due_date=today + timedelta(days=days), priority=prio, assignee=owner
        )

    # ------------------------------------------------------------ funil
    for title, client, stage, value, source in [
        ("Verbas rescisórias - João Pereira", joao, "CONSULT", "6000", "WHATSAPP"),
        ("Revisão de aposentadoria - Ana Ferreira", ana, "PROPOSAL", "4500", "INDICACAO"),
        ("Pensão alimentícia - novo contato", ana, "NEW", None, "WHATSAPP"),
        ("Aposentadoria - Maria Oliveira", maria, "WON", "8000", "INDICACAO"),
    ]:
        Opportunity.objects.create(
            title=title,
            client=client,
            stage=stage,
            estimated_value=Decimal(value) if value else None,
            source=source,
            owner=owner,
            closed_at=now if stage == "WON" else None,
        )

    # ------------------------------------------------------------ financeiro
    ag1 = finance.create_agreement(
        user=owner,
        client=maria,
        legal_case=case_maria,
        title="Honorários - aposentadoria",
        total_amount=Decimal("6000.00"),
        installments=6,
        first_due=today.replace(day=10) - timedelta(days=60),
    )
    for inst in ag1.installments.order_by("number")[:2]:
        finance.settle(inst, user=owner, method="PIX")
    ag2 = finance.create_agreement(
        user=owner,
        client=carlos,
        legal_case=case_carlos,
        title="Honorários - reclamação trabalhista",
        total_amount=Decimal("3600.00"),
        installments=3,
        first_due=today + timedelta(days=5),
        entry_amount=Decimal("1200.00"),
    )
    first = ag2.installments.order_by("number").first()
    first.charge_kind = "PIX"
    first.pix_code = "00020126580014br.gov.bcb.pix0136demo"
    first.payment_url = "https://www.mercadopago.com.br/"
    first.charge_expires_at = now + timedelta(days=5)
    first.mp_payment_id = "demo"
    first.save()

connection.close()
print("Escritório de demonstração criado:", EMAIL)
