import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import Channel, NotificationStatus
from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.repositories.preference_repository import PreferenceRepository
from app.repositories.rate_limit_repository import RateLimitRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.notification import NotificationCreateRequest
from app.services.queue_client import publish_notification
from app.services.rate_limiter import RateLimiter
from app.services.template_engine import render_template

logger = get_logger(__name__)


class TemplateNotFoundError(Exception):
    pass


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.preference_repo = PreferenceRepository(db)
        self.template_repo = TemplateRepository(db)
        self.rate_limiter = RateLimiter(RateLimitRepository(db))

    def create_notification(self, request: NotificationCreateRequest) -> tuple[Notification, bool]:
        """Returns (notification, was_created). was_created=False means an
        existing notification was returned due to a duplicate idempotency key."""

        if request.idempotency_key:
            existing = self.notification_repo.get_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                logger.info(
                    "idempotent_replay",
                    idempotency_key=request.idempotency_key,
                    notification_id=str(existing.id),
                )
                return existing, False

        self.rate_limiter.check(request.user_id)

        subject, body = self._resolve_content(request)

        channel_enabled = self.preference_repo.is_channel_enabled(request.user_id, request.channel)

        notification = Notification(
            id=uuid.uuid4(),
            user_id=request.user_id,
            channel=request.channel.value,
            priority=request.priority.value,
            status=NotificationStatus.PENDING.value,
            template_id=request.template_id,
            subject=subject,
            body=body,
            payload=request.variables,
            idempotency_key=request.idempotency_key,
        )

        if not channel_enabled:
            notification.status = NotificationStatus.SKIPPED.value
            notification.error_message = "User has opted out of this channel"
            self.notification_repo.create(notification)
            logger.info(
                "notification_skipped_opt_out",
                user_id=request.user_id,
                channel=request.channel.value,
            )
            return notification, True

        self.notification_repo.create(notification)
        notification.status = NotificationStatus.QUEUED.value
        self.db.flush()

        publish_notification(notification.id, request.priority)
        logger.info(
            "notification_queued",
            notification_id=str(notification.id),
            user_id=request.user_id,
            channel=request.channel.value,
            priority=request.priority.value,
        )

        return notification, True

    def _resolve_content(self, request: NotificationCreateRequest) -> tuple[str | None, str]:
        if request.template_id:
            template = self.template_repo.get_by_id(request.template_id)
            if template is None:
                raise TemplateNotFoundError(f"Template '{request.template_id}' not found")
            subject = render_template(template.subject, request.variables) if template.subject else None
            body = render_template(template.body, request.variables)
            return subject, body

        return request.subject, request.body

    def get_notification(self, notification_id: uuid.UUID) -> Notification | None:
        return self.notification_repo.get_by_id(notification_id)

    def list_user_notifications(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[Notification], int]:
        return self.notification_repo.list_for_user(user_id, limit, offset)
