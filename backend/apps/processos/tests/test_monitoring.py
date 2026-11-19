from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.processos import monitoring
from apps.processos.models import CaseMovement, LegalCase
from apps.processos.sources import SourceError
from apps.processos.tests.factories import make_cnj
from apps.processos.tests.fixtures import movement

URL = "/api/v1/cases/"


def _movements(tenant, case):
    with tenant_context(tenant.tenant.id):
        return list(CaseMovement.objects.filter(case=case).order_by("occurred_at"))


def _case(tenant, case):
    with tenant_context(tenant.tenant.id):
        return LegalCase.objects.get(pk=case.pk)


def test_first_sync_is_baseline_and_fills_blank_fields(tenant_a, monitored_case, sync):
    assert sync(monitored_case) == "baseline:1"

    case = _case(tenant_a, monitored_case)
    assert case.sync_status == LegalCase.SyncStatus.OK
    assert case.baseline_at is not None
    assert case.last_checked_at is not None
    assert case.classe == "Procedimento Comum Cível"
    assert case.assunto == "Indenização por Dano Moral"
    assert case.orgao_julgador == "1ª Vara Cível de Nova Iguaçu"
    [only] = _movements(tenant_a, monitored_case)
    assert only.notification == CaseMovement.Notification.BASELINE


def test_baseline_does_not_overwrite_office_data(tenant_a, monitored_case, sync):
    with tenant_context(tenant_a.tenant.id):
        LegalCase.objects.filter(pk=monitored_case.pk).update(classe="Ação de indenização")
    sync(monitored_case)
    assert _case(tenant_a, monitored_case).classe == "Ação de indenização"


def test_new_movement_after_baseline_is_pending_and_audited(tenant_a, monitored_case, sync):
    sync(monitored_case)
    assert sync(monitored_case, movement("Conclusão")) == "new:1"

    pending = [
        m
        for m in _movements(tenant_a, monitored_case)
        if m.notification == CaseMovement.Notification.PENDING
    ]
    assert [m.name for m in pending] == ["Conclusão"]
    assert _case(tenant_a, monitored_case).last_movement_at == pending[0].occurred_at
    with tenant_context(tenant_a.tenant.id):
        event = AuditEvent.objects.get(action="case.movements_detected")
    assert event.data == {"count": 1, "source": "fake"}


def test_same_snapshot_twice_creates_nothing(tenant_a, monitored_case, sync):
    sync(monitored_case)
    sync(monitored_case, movement("Conclusão"))
    assert sync(monitored_case) == "unchanged"
    assert len(_movements(tenant_a, monitored_case)) == 2


def test_old_movement_seen_late_is_history_not_notification(tenant_a, monitored_case, sync):
    sync(monitored_case)
    late = movement("Juntada de Petição", timezone.now() - timedelta(days=90))
    assert sync(monitored_case, late) == "unchanged"
    names = {m.name: m.notification for m in _movements(tenant_a, monitored_case)}
    assert names["Juntada de Petição"] == CaseMovement.Notification.BASELINE


def test_same_name_different_complement_is_a_new_movement(tenant_a, monitored_case, sync):
    sync(monitored_case)
    when = timezone.now() - timedelta(days=1)
    sync(
        monitored_case,
        movement("Juntada", when, complements=("tipo de documento: Petição",)),
        movement("Juntada", when, complements=("tipo de documento: Laudo",)),
    )
    assert len(_movements(tenant_a, monitored_case)) == 3


def test_not_found(tenant_a, monitored_case, fake_source, sync):
    fake_source.snapshots[monitored_case.cnj_number] = None
    assert sync(monitored_case) == "not_found"
    case = _case(tenant_a, monitored_case)
    assert case.sync_status == LegalCase.SyncStatus.NOT_FOUND
    assert case.baseline_at is None


def test_retryable_source_error_is_recorded_and_raised(tenant_a, monitored_case, fake_source):
    fake_source.fail_next = SourceError("http_429", retryable=True)
    with pytest.raises(monitoring.RetryableSyncError):
        monitoring.sync_case(tenant_a.tenant.id, monitored_case.pk)
    case = _case(tenant_a, monitored_case)
    assert (case.sync_status, case.sync_error) == (LegalCase.SyncStatus.ERROR, "http_429")


def test_permanent_source_error_is_not_raised(tenant_a, monitored_case, fake_source):
    fake_source.fail_next = SourceError("http_401", retryable=False)
    assert monitoring.sync_case(tenant_a.tenant.id, monitored_case.pk) == "error:http_401"


def test_task_retries_on_temporary_error(tenant_a, monitored_case, fake_source):
    from apps.processos.tasks import sync_case_task

    fake_source.fail_next = SourceError("http_503", retryable=True)
    result = sync_case_task.apply(
        args=[str(tenant_a.tenant.id), str(monitored_case.pk)], throw=False
    )
    # Eager: o retry roda na hora e a segunda tentativa encontra a fonte de pé.
    assert result.get(propagate=False) == "baseline:1"


def test_disabled_and_archived_cases_are_skipped(tenant_a, monitored_case, fake_source):
    with tenant_context(tenant_a.tenant.id):
        LegalCase.objects.filter(pk=monitored_case.pk).update(monitoring_enabled=False)
    assert monitoring.sync_case(tenant_a.tenant.id, monitored_case.pk) == "disabled"
    assert fake_source.calls == []


def test_schedule_picks_only_due_cases(tenant_a, tenant_b, monitored_case):
    with tenant_context(tenant_a.tenant.id):
        fresh = LegalCase.objects.create(cnj_number=make_cnj(sequence=11))
        LegalCase.objects.filter(pk=fresh.pk).update(last_checked_at=timezone.now())
        stale = LegalCase.objects.create(cnj_number=make_cnj(sequence=12))
        LegalCase.objects.filter(pk=stale.pk).update(
            last_checked_at=timezone.now() - timedelta(days=1)
        )
        LegalCase.objects.create(cnj_number=make_cnj(sequence=13), monitoring_enabled=False)
        LegalCase.objects.create(cnj_number=make_cnj(sequence=14), status=LegalCase.Status.ARCHIVED)
    with tenant_context(tenant_b.tenant.id):
        other = LegalCase.objects.create(cnj_number=make_cnj(sequence=15))

    with mock.patch("apps.processos.tasks.sync_case_task.apply_async") as apply_async:
        assert monitoring.schedule_due_checks() == 3

    scheduled = {call.kwargs["args"][1] for call in apply_async.call_args_list}
    assert scheduled == {str(monitored_case.pk), str(stale.pk), str(other.pk)}
    countdowns = sorted(call.kwargs["countdown"] for call in apply_async.call_args_list)
    assert countdowns == [0, 15, 30]


# --------------------------------------------------------------------------- API


def test_api_lists_movements_and_sync_status(tenant_a, monitored_case, sync, login, api_client):
    sync(monitored_case)
    sync(monitored_case, movement("Conclusão"))
    login(tenant_a.owner.email)

    detail = api_client.get(f"{URL}{monitored_case.pk}/").json()
    assert detail["sync_status"] == "OK"
    assert detail["pending_movements"] == 1

    listing = api_client.get(URL).json()["results"]
    assert listing[0]["pending_movements"] == 1

    body = api_client.get(f"{URL}{monitored_case.pk}/movements/").json()
    assert [m["name"] for m in body["results"]] == ["Conclusão", "Distribuição"]
    assert body["results"][0]["notification"] == "PENDING"


def test_api_check_now_queues_and_has_cooldown(
    tenant_a, monitored_case, fake_source, login, api_client, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(f"{URL}{monitored_case.pk}/check/")
    assert response.status_code == 202
    assert fake_source.calls == [monitored_case.cnj_number]

    again = api_client.post(f"{URL}{monitored_case.pk}/check/")
    assert again.status_code == 429
    assert again.json()["error"]["code"] == "checked_recently"


def test_api_check_requires_monitoring(tenant_a, monitored_case, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        LegalCase.objects.filter(pk=monitored_case.pk).update(monitoring_enabled=False)
    login(tenant_a.owner.email)
    response = api_client.post(f"{URL}{monitored_case.pk}/check/")
    assert response.status_code == 409


def test_api_other_tenant_cannot_see_movements(
    tenant_a, tenant_b, monitored_case, sync, login, api_client
):
    sync(monitored_case)
    login(tenant_b.owner.email)
    assert api_client.get(f"{URL}{monitored_case.pk}/movements/").status_code == 404
    assert api_client.post(f"{URL}{monitored_case.pk}/check/").status_code == 404
