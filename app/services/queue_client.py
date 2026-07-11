import json
import uuid

import pika

from app.core.config import get_settings
from app.models.enums import Priority

# RabbitMQ priority queues need an explicit max priority declared up front.
MAX_QUEUE_PRIORITY = 10
# Higher number = delivered first. Map our "lower is more urgent" weight to that.
_PRIORITY_TO_MQ_PRIORITY = {
    Priority.CRITICAL: 10,
    Priority.HIGH: 7,
    Priority.NORMAL: 4,
    Priority.LOW: 1,
}

QUEUE_NAME = "notifications.delivery"
DEAD_LETTER_QUEUE_NAME = "notifications.delivery.dead_letter"
RETRY_EXCHANGE_NAME = "notifications.retry"


def _connection_params() -> pika.URLParameters:
    return pika.URLParameters(get_settings().rabbitmq_url)


def get_connection() -> pika.BlockingConnection:
    return pika.BlockingConnection(_connection_params())


def declare_topology(channel: "pika.adapters.blocking_connection.BlockingChannel") -> None:
    """Idempotent declaration of the exchange/queue topology.

    notifications.delivery: main work queue, priority-enabled, consumed by workers.
    notifications.retry: delayed-retry exchange; messages land back on the main
        queue after their per-message TTL expires (poor-man's delayed retry
        without needing the delayed-message-exchange plugin).
    notifications.delivery.dead_letter: terminal failures after max retries.
    """
    settings = get_settings()

    channel.exchange_declare(exchange=settings.rabbitmq_exchange, exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=RETRY_EXCHANGE_NAME, exchange_type="direct", durable=True)

    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True,
        arguments={"x-max-priority": MAX_QUEUE_PRIORITY},
    )
    channel.queue_bind(queue=QUEUE_NAME, exchange=settings.rabbitmq_exchange, routing_key=QUEUE_NAME)
    channel.queue_bind(queue=QUEUE_NAME, exchange=RETRY_EXCHANGE_NAME, routing_key=QUEUE_NAME)

    channel.queue_declare(queue=DEAD_LETTER_QUEUE_NAME, durable=True)
    channel.queue_bind(
        queue=DEAD_LETTER_QUEUE_NAME, exchange=settings.rabbitmq_exchange, routing_key=DEAD_LETTER_QUEUE_NAME
    )


def publish_notification(notification_id: uuid.UUID, priority: Priority) -> None:
    settings = get_settings()
    connection = get_connection()
    try:
        channel = connection.channel()
        declare_topology(channel)
        channel.basic_publish(
            exchange=settings.rabbitmq_exchange,
            routing_key=QUEUE_NAME,
            body=json.dumps({"notification_id": str(notification_id)}),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                priority=_PRIORITY_TO_MQ_PRIORITY[priority],
            ),
        )
    finally:
        connection.close()


def publish_retry(notification_id: uuid.UUID, priority: Priority, delay_ms: int) -> None:
    """Publish to a per-message TTL queue that dead-letters back into the main queue after delay_ms."""
    settings = get_settings()
    connection = get_connection()
    try:
        channel = connection.channel()
        declare_topology(channel)

        delay_queue_name = f"notifications.retry.{delay_ms}ms"
        channel.queue_declare(
            queue=delay_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": delay_ms,
                "x-dead-letter-exchange": settings.rabbitmq_exchange,
                "x-dead-letter-routing-key": QUEUE_NAME,
            },
        )
        channel.queue_bind(queue=delay_queue_name, exchange=RETRY_EXCHANGE_NAME, routing_key=delay_queue_name)

        channel.basic_publish(
            exchange=RETRY_EXCHANGE_NAME,
            routing_key=delay_queue_name,
            body=json.dumps({"notification_id": str(notification_id)}),
            properties=pika.BasicProperties(
                delivery_mode=2,
                priority=_PRIORITY_TO_MQ_PRIORITY[priority],
            ),
        )
    finally:
        connection.close()


def publish_dead_letter(notification_id: uuid.UUID) -> None:
    settings = get_settings()
    connection = get_connection()
    try:
        channel = connection.channel()
        declare_topology(channel)
        channel.basic_publish(
            exchange=settings.rabbitmq_exchange,
            routing_key=DEAD_LETTER_QUEUE_NAME,
            body=json.dumps({"notification_id": str(notification_id)}),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    finally:
        connection.close()
