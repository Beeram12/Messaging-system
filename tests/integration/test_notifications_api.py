import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services import notification_service as notification_service_module

API_KEY_HEADERS = {"X-API-Key": "dev-local-api-key"}


@pytest.fixture(autouse=True)
def _stub_publish(monkeypatch):
    monkeypatch.setattr(notification_service_module, "publish_notification", lambda *a, **k: None)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_notification_requires_api_key(client):
    response = client.post("/notifications", json={"user_id": "u1", "channel": "email", "body": "hi"})
    assert response.status_code in (401, 422)


def test_create_notification_with_invalid_api_key(client):
    response = client.post(
        "/notifications",
        json={"user_id": "u1", "channel": "email", "body": "hi"},
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


def test_create_notification_success(client):
    response = client.post(
        "/notifications",
        json={"user_id": "u1", "channel": "email", "priority": "high", "body": "hello"},
        headers=API_KEY_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["channel"] == "email"
    assert body["priority"] == "high"


def test_create_notification_requires_body_or_template(client):
    response = client.post(
        "/notifications",
        json={"user_id": "u1", "channel": "email"},
        headers=API_KEY_HEADERS,
    )
    assert response.status_code == 422


def test_create_notification_invalid_channel_rejected(client):
    response = client.post(
        "/notifications",
        json={"user_id": "u1", "channel": "carrier_pigeon", "body": "hi"},
        headers=API_KEY_HEADERS,
    )
    assert response.status_code == 422


def test_get_notification_by_id(client):
    create_response = client.post(
        "/notifications",
        json={"user_id": "u2", "channel": "sms", "body": "hi"},
        headers=API_KEY_HEADERS,
    )
    notification_id = create_response.json()["id"]

    get_response = client.get(f"/notifications/{notification_id}", headers=API_KEY_HEADERS)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == notification_id
    assert "attempts" in get_response.json()


def test_get_notification_not_found(client):
    response = client.get(
        "/notifications/00000000-0000-0000-0000-000000000000", headers=API_KEY_HEADERS
    )
    assert response.status_code == 404


def test_idempotency_key_prevents_duplicate_notifications(client):
    payload = {
        "user_id": "u3",
        "channel": "email",
        "body": "hi",
        "idempotency_key": "same-key",
    }
    first = client.post("/notifications", json=payload, headers=API_KEY_HEADERS)
    second = client.post("/notifications", json=payload, headers=API_KEY_HEADERS)

    assert first.json()["id"] == second.json()["id"]

    history = client.get("/users/u3/notifications", headers=API_KEY_HEADERS)
    assert history.json()["total"] == 1


def test_list_user_notifications_pagination(client):
    for i in range(3):
        client.post(
            "/notifications",
            json={"user_id": "u4", "channel": "push", "body": f"msg {i}"},
            headers=API_KEY_HEADERS,
        )

    response = client.get("/users/u4/notifications?limit=2&offset=0", headers=API_KEY_HEADERS)
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_preferences_default_all_enabled(client):
    response = client.get("/users/new-user/preferences", headers=API_KEY_HEADERS)
    assert response.status_code == 200
    assert response.json()["preferences"] == {"email": True, "sms": True, "push": True}


def test_set_and_get_preferences(client):
    set_response = client.post(
        "/users/u5/preferences",
        json={"preferences": [{"channel": "sms", "enabled": False}]},
        headers=API_KEY_HEADERS,
    )
    assert set_response.status_code == 200
    assert set_response.json()["preferences"]["sms"] is False

    get_response = client.get("/users/u5/preferences", headers=API_KEY_HEADERS)
    assert get_response.json()["preferences"]["sms"] is False
    assert get_response.json()["preferences"]["email"] is True


def test_notification_skipped_when_channel_opted_out(client):
    client.post(
        "/users/u6/preferences",
        json={"preferences": [{"channel": "push", "enabled": False}]},
        headers=API_KEY_HEADERS,
    )
    response = client.post(
        "/notifications",
        json={"user_id": "u6", "channel": "push", "body": "hi"},
        headers=API_KEY_HEADERS,
    )
    assert response.json()["status"] == "skipped"


def test_unknown_template_returns_400(client):
    response = client.post(
        "/notifications",
        json={"user_id": "u7", "channel": "email", "template_id": "does-not-exist"},
        headers=API_KEY_HEADERS,
    )
    assert response.status_code == 400
