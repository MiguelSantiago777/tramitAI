"""Agenda da Vera: expediente, horários livres, pré-reserva pelo WhatsApp e confirmação."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.agenda import scheduling
from apps.agenda.models import Event
from apps.aprovacoes.models import OutboundDraft
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.ia.context import build_triage_context
from apps.tenants.models import TenantSettings
from apps.whatsapp.models import Conversation

TZ = ZoneInfo("America/Sao_Paulo")
AI = OutboundDraft.Origin.AI_REPLY
TERM = OutboundDraft.Origin.TERM_REQUEST
# Segunda-feira, 23/11/2026, 08:00 em Brasília.
MONDAY_8H = datetime(2026, 11, 23, 8, 0, tzinfo=TZ)


def _cfg(tenant_a, **changes):
    with tenant_atomic(tenant_a.tenant.id):
        TenantSettings.objects.update(**changes)
        return TenantSettings.objects.select_related("scheduling_user").get()


def test_hours_text_open_and_validation(tenant_a):
    cfg = _cfg(tenant_a)
    with tenant_context(tenant_a.tenant.id):
        assert scheduling.hours_text(cfg) == "segunda a sexta, 09:00 às 12:00 e 13:00 às 18:00"
        assert scheduling.is_open(cfg, MONDAY_8H) is False
        assert scheduling.is_open(cfg, MONDAY_8H + timedelta(hours=2)) is True
        assert (
            scheduling.is_open(cfg, MONDAY_8H + timedelta(hours=4, minutes=30)) is False
        )  # almoço
        assert scheduling.is_open(cfg, MONDAY_8H + timedelta(days=5, hours=2)) is False  # sábado
    with pytest.raises(ValueError, match="fim precisa ser depois"):
        scheduling.validate_business_hours({"0": [["18:00", "09:00"]]})
    with pytest.raises(ValueError, match="sobrepõem"):
        scheduling.validate_business_hours({"0": [["09:00", "12:00"], ["11:00", "13:00"]]})


def test_free_slots_skip_busy_lead_time_and_spread(tenant_a):
    cfg = _cfg(tenant_a, scheduling_enabled=True, consult_minutes=60)
    with tenant_atomic(tenant_a.tenant.id):
        Event.objects.create(
            title="Audiência",
            starts_at=datetime(2026, 11, 23, 10, 0, tzinfo=TZ),
            ends_at=datetime(2026, 11, 23, 11, 30, tzinfo=TZ),
            responsible=tenant_a.owner,
        )
        slots = scheduling.free_slots(cfg, now=MONDAY_8H)
    labels = [s.astimezone(TZ).strftime("%a %H:%M") for s in slots]
    # 08h + 2h de antecedência = 10h; 10h-11h30 ocupado; 11h30 bateria no almoço;
    # no máximo 2 por dia, espaçados.
    assert labels == ["Mon 13:00", "Mon 15:00", "Tue 09:00"]


def test_context_has_hours_and_offered_slots(tenant_a, account_a, monkeypatch):
    _cfg(tenant_a, scheduling_enabled=True)
    monkeypatch.setattr(timezone, "now", lambda: MONDAY_8H)
    with tenant_atomic(tenant_a.tenant.id):
        conversation = Conversation.objects.create(account=account_a, wa_id="5521911112222")
        text = build_triage_context(conversation)
        conversation.refresh_from_db()
    assert "fora do horário agora" in text
    assert "H1: segunda, 23/11 às 10:00" in text
    assert [o["id"] for o in conversation.offered_slots] == ["H1", "H2", "H3"]


def _llm(reply, **extra):
    data = {
        "intent": "new_matter",
        "needs_lawyer": False,
        "triage_complete": True,
        "scheduling_step": "none",
        "booking_slot": "",
        "booking_mode": "",
        "urgency": "normal",
        "summary_for_lawyer": "João, demitido sem receber verbas.",
        "reply": reply,
    }
    data.update(extra)
    return data


@pytest.fixture
def scheduling_on(tenant_a):
    _cfg(tenant_a, scheduling_enabled=True, auto_send_simple_replies=True)


def test_lia_offers_books_and_lawyer_confirms(
    tenant_a,
    account_a,
    scheduling_on,
    inbound,
    approve,
    drafts,
    fake_llm,
    fake_gateway,
    login,
    api_client,
    django_capture_on_commit_callbacks,
):
    inbound("Oi, fui demitido")
    fake_llm.queue.append(
        _llm("Posso marcar com a advogada: H1, H2 ou H3?", scheduling_step="offer")
    )
    inbound("Aceito")
    offer = drafts(origin=AI)[-1]
    assert offer.auto_sent is True  # oferecer horário sai sozinho
    with tenant_context(tenant_a.tenant.id):
        h2 = next(o for o in Conversation.objects.get().offered_slots if o["id"] == "H2")

    fake_llm.queue.append(
        _llm(
            "Pré-reservei! A advogada confirma por aqui.",
            scheduling_step="book",
            booking_slot="H2",
            booking_mode="online",
        )
    )
    inbound("Pode ser a segunda opção, online")
    with tenant_context(tenant_a.tenant.id):
        event = Event.objects.get(status=Event.Status.PENDING)
        assert Conversation.objects.get().offered_slots == []  # reservado: oferta zerada
    assert event.starts_at == datetime.fromisoformat(h2["start"])
    assert event.location.startswith("Online")
    assert "demitido" in event.notes
    assert drafts(origin=AI)[-1].auto_sent is True

    login(tenant_a.owner.email)
    sent_before = len(fake_gateway.sent)
    with django_capture_on_commit_callbacks(execute=True):
        confirmed = api_client.post(f"/api/v1/events/{event.pk}/confirm/")
    assert confirmed.json()["status"] == "SCHEDULED"
    assert "está confirmada" in fake_gateway.sent[sent_before].body
    assert api_client.post(f"/api/v1/events/{event.pk}/confirm/").status_code == 409


def test_taken_slot_goes_to_lawyer(
    tenant_a, account_a, scheduling_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    inbound("Oi")
    fake_llm.queue.append(_llm("H1, H2 ou H3?", scheduling_step="offer"))
    inbound("Aceito")
    with tenant_context(tenant_a.tenant.id):
        h1 = Conversation.objects.get().offered_slots[0]
    with tenant_atomic(tenant_a.tenant.id):
        start = datetime.fromisoformat(h1["start"])
        Event.objects.create(title="Outro", starts_at=start, ends_at=start + timedelta(hours=1))
    fake_llm.queue.append(
        _llm("Pré-reservei!", scheduling_step="book", booking_slot="H1", booking_mode="presencial")
    )
    inbound("A primeira, presencial")
    pending = drafts(origin=AI, status=OutboundDraft.Status.DRAFT)
    assert len(pending) == 1
    assert pending[0].needs_lawyer is True
    assert pending[0].summary.startswith("O horário escolhido não está mais livre")
    with tenant_context(tenant_a.tenant.id):
        assert not Event.objects.filter(status=Event.Status.PENDING).exists()


def test_decline_and_settings_api(tenant_a, login, api_client):
    with tenant_atomic(tenant_a.tenant.id):
        event = Event.objects.create(
            title="Consulta", status=Event.Status.PENDING, starts_at=MONDAY_8H + timedelta(days=1)
        )
    login(tenant_a.owner.email)
    assert api_client.post(f"/api/v1/events/{event.pk}/decline/").json()["status"] == "CANCELED"

    url = "/api/v1/tenant/settings/"
    bad = api_client.patch(url, {"business_hours": {"0": [["18:00", "08:00"]]}}, format="json")
    assert bad.status_code == 400
    hours = {str(d): ([["08:00", "17:00"]] if d < 5 else []) for d in range(7)}
    ok = api_client.patch(
        url,
        {"business_hours": hours, "scheduling_enabled": True, "consult_minutes": 30},
        format="json",
    ).json()
    assert ok["business_hours"]["0"] == [["08:00", "17:00"]]
    assert ok["scheduling_enabled"] is True
    assert ok["consult_minutes"] == 30


def test_only_mode_does_not_book_first_slot(
    tenant_a, account_a, scheduling_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    """Cliente responde só "online": a IA chuta H1, mas o sistema pergunta o horário."""
    inbound("Oi")
    fake_llm.queue.append(_llm("H1, H2 ou H3? Presencial ou online?", scheduling_step="offer"))
    inbound("Aceito")
    fake_llm.queue.append(
        _llm("Pré-reservei!", scheduling_step="book", booking_slot="H1", booking_mode="online")
    )
    inbound("Online")
    reply = drafts(origin=AI)[-1]
    assert reply.generated_body.startswith("Combinado, online! Qual destes horários fica melhor")
    assert reply.auto_sent is True  # pergunta de agendamento sai sozinha
    with tenant_context(tenant_a.tenant.id):
        assert not Event.objects.exists()
        assert len(Conversation.objects.get().offered_slots) == 3  # oferta continua valendo


def _say(conversation, direction, body, minute):
    from apps.whatsapp.models import Message

    msg = Message.objects.create(
        conversation=conversation,
        direction=direction,
        body=body,
        status=Message.Status.RECEIVED if direction == "IN" else Message.Status.SENT,
    )
    Message.objects.filter(pk=msg.pk).update(created_at=MONDAY_8H + timedelta(minutes=minute))


def test_booking_check_reads_what_client_said(tenant_a, account_a, monkeypatch):
    from apps.ia.booking_check import check

    _cfg(tenant_a, scheduling_enabled=True, consult_minutes=60)
    monkeypatch.setattr(timezone, "now", lambda: MONDAY_8H)
    with tenant_atomic(tenant_a.tenant.id):
        conv = Conversation.objects.create(account=account_a, wa_id="5521911113333")
        build_triage_context(conv)
        conv.refresh_from_db()
        labels = [
            scheduling.slot_label(datetime.fromisoformat(o["start"])) for o in conv.offered_slots
        ]
        assert labels == [
            "segunda, 23/11 às 10:00",
            "segunda, 23/11 às 13:00",
            "terça, 24/11 às 09:00",
        ]
        _say(conv, "IN", "Fui demitido na segunda passada", 1)
        _say(conv, "OUT", f"Tenho {', '.join(labels)}. Presencial ou online?", 2)

        _say(conv, "IN", "online", 3)
        only_mode = check(conv, "H1", "online")
        assert (only_mode.ok, only_mode.slot_id, only_mode.mode) == (False, None, "online")
        assert "Qual destes horários" in only_mode.reply

        _say(conv, "IN", "segunda", 4)  # dois horários na segunda: ambíguo
        assert check(conv, "H1", "online").slot_id is None

        _say(conv, "IN", "terça às 9h", 5)
        assert check(conv, "H3", "online").ok is True
        wrong = check(conv, "H1", "online")  # a IA escolheu outro
        assert wrong.ok is False
        assert wrong.reply == (
            "Só para confirmar: posso pré-reservar terça, 24/11 às 09:00, online?"
        )

        _say(conv, "OUT", wrong.reply, 6)
        _say(conv, "IN", "Sim", 7)
        assert check(conv, "H3", "online").ok is True

        _say(conv, "OUT", "Tenho as mesmas opções de antes: 10:00, 13:00 ou 09:00.", 8)
        _say(conv, "IN", "a segunda opção, vou no escritório", 9)
        second = check(conv, "H2", "presencial")
        assert (second.ok, second.slot_id, second.mode) == (True, "H2", "presencial")
