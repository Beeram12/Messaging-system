import pytest

from app.models.enums import Channel, NotificationStatus, Priority
from app.models.template import Template
from app.schemas.notification import NotificationCreateRequest
from app.services import notification_service as notification_service_module
from app.services.notification_service import NotificationService, TemplateNotFoundError
from app.services.rate_limiter import RateLimitExceededError
from app.services.template_engine import TemplateRenderError


@pytest.fixture(autouse=True)
def _stub_publish(monkeypatch):
    published = []
    monkeypatch.setattr(
        notification_service_module, "publish_notification", lambda notif_id, priority: published.append((notif_id, priority))
    )
    return published


def test_create_notification_with_raw_body(db_session):
    service = NotificationService(db_session)
    request = NotificationCreateRequest(
        user_id="user-1", channel=Channel.EMAIL, priority=Priority.NORMAL, body="Hi there"
    )
    notification, created = service.create_notification(request)
    assert created is True
    assert notification.status == NotificationStatus.QUEUED.value
    assert notification.body == "Hi there"


def test_create_notification_with_template_renders_variables(db_session):
    db_session.add(Template(id="welcome", subject="Hi {{name}}", body="Welcome, {{name}}!"))
    db_session.flush()

    service = NotificationService(db_session)
    request = NotificationCreateRequest(
        user_id="user-1",
        channel=Channel.EMAIL,
        template_id="welcome",
        variables={"name": "Ada"},
    )
    notification, _ = service.create_notification(request)
    assert notification.subject == "Hi Ada"
    assert notification.body == "Welcome, Ada!"


def test_create_notification_unknown_template_raises(db_session):
    service = NotificationService(db_session)
    request = NotificationCreateRequest(user_id="user-1", channel=Channel.EMAIL, template_id="missing")
    with pytest.raises(TemplateNotFoundError):
        service.create_notification(request)


def test_create_notification_missing_template_variable_raises(db_session):
    db_session.add(Template(id="welcome", body="Welcome, {{name}}!"))
    db_session.flush()

    service = NotificationService(db_session)
    request = NotificationCreateRequest(user_id="user-1", channel=Channel.EMAIL, template_id="welcome")
    with pytest.raises(TemplateRenderError):
        service.create_notification(request)


def test_duplicate_idempotency_key_returns_existing_without_recreating(db_session, _stub_publish):
    service = NotificationService(db_session)
    request = NotificationCreateRequest(
        user_id="user-1", channel=Channel.EMAIL, body="Hi", idempotency_key="key-1"
    )
    first, created_first = service.create_notification(request)
    second, created_second = service.create_notification(request)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert len(_stub_publish) == 1  # only published once


def test_opted_out_channel_is_skipped_not_queued(db_session, _stub_publish):
    from app.repositories.preference_repository import PreferenceRepository

    PreferenceRepository(db_session).upsert("user-1", Channel.SMS, enabled=False)
    db_session.flush()

    service = NotificationService(db_session)
    request = NotificationCreateRequest(user_id="user-1", channel=Channel.SMS, body="Hi")
    notification, created = service.create_notification(request)

    assert created is True
    assert notification.status == NotificationStatus.SKIPPED.value
    assert _stub_publish == []


def test_rate_limit_exceeded_raises(db_session, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1")
    get_settings.cache_clear()

    service = NotificationService(db_session)
    request = NotificationCreateRequest(user_id="user-rl", channel=Channel.EMAIL, body="Hi")
    service.create_notification(request)

    with pytest.raises(RateLimitExceededError):
        service.create_notification(request)

    monkeypatch.delenv("RATE_LIMIT_PER_HOUR", raising=False)
    get_settings.cache_clear()
