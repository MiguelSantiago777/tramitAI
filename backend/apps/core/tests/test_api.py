import pytest

from apps.core import views

pytestmark = pytest.mark.django_db


def test_health_ok(api_client, monkeypatch):
    monkeypatch.setattr(views, "_check_redis", lambda: True)
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "redis": True}


def test_health_degraded_returns_503(api_client, monkeypatch):
    monkeypatch.setattr(views, "_check_redis", lambda: False)
    response = api_client.get("/api/health/")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_openapi_schema_is_served(api_client):
    response = api_client.get("/api/schema/")
    assert response.status_code == 200
    assert b"/api/v1/auth/login/" in response.content


def test_unknown_route_uses_standard_error_body(api_client):
    response = api_client.get("/api/v1/nao-existe/")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Não encontrado."}}
