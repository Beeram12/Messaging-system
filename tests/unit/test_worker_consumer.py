import uuid

import pytest

from app.models.enums import Channel, NotificationStatus, Priority
from app.models.notification import Notification
from app.services.providers import ProviderError
from worker import consumer as consumer_module


@pytest.fixture
def make_notification(db_session):
    def _make(**overrides):
        defaults = dict(
            id=uuid.uuid4(),
            user_id="user-1",
            channel=Channel.EMAIL.value,
            priority=Priority.NORMAL.value,
            status=NotificationStatus.QUEUED.value,
            body="hello",
            payload={},
        )
        defaults.update(overrides)
        notification = Notification(**defaults)
        db_session.add(notification)
        db_session.flush()
        db_session.commit()
        return notification

    return _make


@pytest.fixture(autouse=True)
def _stub_session_local(db_session, monkeypatch):
    monkeypatch.setattr(consumer_module, "SessionLocal", lambda: db_session)
    # prevent the fixture's outer rollback from closing a session we reuse
    monkeypatch.setattr(db_session, "close", lambda: None)


def test_process_message_success_marks_delivered(db_session, make_notification, monkeypatch):
    notification = make_notification()
    monkeypatch.setattr(
        consumer_module, "get_provider", lambda channel: _StubProvider(succeed=True)
    )

    consumer_module.process_message(notification.id)

    db_session.refresh(notification)
    assert notification.status == NotificationStatus.DELIVERED.value
    assert notification.sent_at is not None
    assert len(notification.attempts) == 1
    assert notification.attempts[0].status == NotificationStatus.SENT.value


def test_process_message_failure_schedules_retry(db_session, make_notification, monkeypatch):
    notification = make_notification()
    monkeypatch.setattr(consumer_module, "get_provider", lambda channel: _StubProvider(succeed=False))

    retried = []
    monkeypatch.setattr(
        consumer_module, "publish_retry", lambda notif_id, priority, delay_ms: retried.append((notif_id, delay_ms))
    )

    consumer_module.process_message(notification.id)

    db_session.refresh(notification)
    assert notification.status == NotificationStatus.PENDING.value
    assert notification.retry_count == 1
    assert len(retried) == 1
    assert retried[0][1] == 5000  # first retry delay


def test_process_message_exhausts_retries_and_dead_letters(db_session, make_notification, monkeypatch):
    notification = make_notification(retry_count=3)  # already at max
    monkeypatch.setattr(consumer_module, "get_provider", lambda channel: _StubProvider(succeed=False))

    dead_lettered = []
    monkeypatch.setattr(
        consumer_module, "publish_dead_letter", lambda notif_id: dead_lettered.append(notif_id)
    )

    consumer_module.process_message(notification.id)

    db_session.refresh(notification)
    assert notification.status == NotificationStatus.FAILED.value
    assert dead_lettered == [notification.id]


def test_process_message_skips_already_delivered(db_session, make_notification, monkeypatch):
    notification = make_notification(status=NotificationStatus.DELIVERED.value)
    calls = []
    monkeypatch.setattr(consumer_module, "get_provider", lambda channel: calls.append(channel) or _StubProvider(succeed=True))

    consumer_module.process_message(notification.id)

    assert calls == []  # provider never invoked


class _StubProvider:
    def __init__(self, succeed: bool):
        self.succeed = succeed

    def send(self, *, user_id, subject, body):
        if not self.succeed:
            raise ProviderError("simulated failure")
        return "stub-message-id"
