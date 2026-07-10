-- 0002_notifications.sql
CREATE TABLE notifications (
    id               UUID PRIMARY KEY,
    user_id          VARCHAR(128) NOT NULL,
    channel          VARCHAR(16) NOT NULL,
    priority         VARCHAR(16) NOT NULL,
    status           VARCHAR(16) NOT NULL,
    template_id      VARCHAR(128),
    subject          VARCHAR(255),
    body             TEXT NOT NULL,
    payload          JSONB NOT NULL,
    idempotency_key  VARCHAR(255),
    retry_count      INTEGER NOT NULL DEFAULT 0,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at          TIMESTAMPTZ,
    delivered_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX ix_notifications_idempotency_key ON notifications (idempotency_key);
CREATE INDEX ix_notifications_status ON notifications (status);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);
