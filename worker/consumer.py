import json
import uuid

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.enums import NotificationStatus, Priority
from app.repositories.notification_repository import NotificationRepository
from app.services.providers import ProviderError, get_provider
from app.services.queue_client import (
    QUEUE_NAME,
    declare_topology,
    get_connection,
    publish_dead_letter,
    publish_retry,
)
from app.services.retry_policy import compute_backoff_delay_ms, has_retries_remaining

configure_logging()
logger = get_logger("worker")


def process_message(notification_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        notification = repo.get_by_id(notification_id)
        if notification is None:
            logger.warning("notification_not_found", notification_id=str(notification_id))
            return

        if notification.status in (NotificationStatus.SENT.value, NotificationStatus.DELIVERED.value):
            logger.info("notification_already_processed", notification_id=str(notification_id))
            return

        attempt_number = notification.retry_count + 1
        provider = get_provider(notification.channel)

        # Send the notification
        try:
            provider_message_id = provider.send(
                user_id=notification.user_id,
                subject=notification.subject,
                body=notification.body,
            )
        except ProviderError as exc:
            _handle_failure(db, repo, notification, attempt_number, str(exc))
            return

        repo.update_status(notification, NotificationStatus.SENT)
        repo.record_attempt(notification, attempt_number, NotificationStatus.SENT)
        db.commit()
        logger.info(
            "notification_sent",
            notification_id=str(notification_id),
            channel=notification.channel,
            provider_message_id=provider_message_id,
            attempt_number=attempt_number,
        )

        # Delivery confirmation is not modeled by the mock providers, so we
        # optimistically mark DELIVERED here; a real integration would move
        # this to an async provider webhook/callback instead.
        repo.update_status(notification, NotificationStatus.DELIVERED)
        db.commit()
    finally:
        db.close()


def _handle_failure(db, repo: NotificationRepository, notification, attempt_number: int, error_message: str) -> None:
    repo.record_attempt(notification, attempt_number, NotificationStatus.FAILED, error_message)
    repo.increment_retry_count(notification)

    if has_retries_remaining(notification.retry_count):
        repo.update_status(notification, NotificationStatus.PENDING, error_message)
        db.commit()
        delay_ms = compute_backoff_delay_ms(notification.retry_count - 1)
        publish_retry(notification.id, Priority(notification.priority), delay_ms)
        logger.warning(
            "notification_retry_scheduled",
            notification_id=str(notification.id),
            retry_count=notification.retry_count,
            delay_ms=delay_ms,
            error=error_message,
        )
    else:
        repo.update_status(notification, NotificationStatus.FAILED, error_message)
        db.commit()
        publish_dead_letter(notification.id)
        logger.error(
            "notification_failed_permanently",
            notification_id=str(notification.id),
            retry_count=notification.retry_count,
            error=error_message,
        )


def _on_message(
    channel: BlockingChannel,
    method: Basic.Deliver,
    properties: BasicProperties,
    body: bytes,
) -> None:
    try:
        payload = json.loads(body)
        notification_id = uuid.UUID(payload["notification_id"])
        process_message(notification_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("worker_message_processing_error")
        # Requeue=False: bad/poison messages go to the DLQ setup via retry
        # exhaustion logic above rather than looping forever on the same message.
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    connection = get_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=_on_message)

    logger.info("worker_started", queue=QUEUE_NAME)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
