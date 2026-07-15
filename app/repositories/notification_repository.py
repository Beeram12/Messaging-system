import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import NotificationStatus
from app.models.notification import Notification, NotificationAttempt

# NotificationRepository is responsible for interacting with the notification model and performing CRUD operations.
class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    # Create a new notification
    def create(self, notification: Notification) -> Notification:
        self.db.add(notification)
        self.db.flush()
        return notification

    # Get a notification by id
    def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        return self.db.get(Notification, notification_id)

    # Get a notification by idempotency key
    def get_by_idempotency_key(self, idempotency_key: str) -> Notification | None:
        stmt = select(Notification).where(Notification.idempotency_key == idempotency_key)
        return self.db.execute(stmt).scalar_one_or_none()

    # List notifications for a user
    def list_for_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[Notification], int]:
        base_stmt = select(Notification).where(Notification.user_id == user_id)
        total = self.db.execute(
            select(func.count()).select_from(base_stmt.subquery())
        ).scalar_one()
        items = (
            self.db.execute(
                base_stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return list(items), total

    # Update the status of the notification
    def update_status(
        self,
        notification: Notification,
        status: NotificationStatus,
        error_message: str | None = None,
    ) -> Notification:
        notification.status = status
        notification.error_message = error_message
        now = datetime.now(timezone.utc)
        if status == NotificationStatus.SENT:
            notification.sent_at = now
        elif status == NotificationStatus.DELIVERED:
            notification.delivered_at = now
        self.db.flush()
        return notification

    # Record an attempt to send the notification
    def record_attempt(
        self,
        notification: Notification,
        attempt_number: int,
        status: NotificationStatus,
        error_message: str | None = None,
    ) -> NotificationAttempt:
        attempt = NotificationAttempt(
            notification_id=notification.id,
            attempt_number=attempt_number,
            status=status,
            error_message=error_message,
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    # Increment the retry count of the notification
    def increment_retry_count(self, notification: Notification) -> Notification:
        notification.retry_count += 1
        self.db.flush()
        return notification
