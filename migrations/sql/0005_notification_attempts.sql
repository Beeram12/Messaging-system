-- 0005_notification_attempts.sql
-- References notifications(id), so must run after 0002_notifications.sql.
CREATE TABLE notification_attempts (
    id               UUID PRIMARY KEY,
    notification_id  UUID NOT NULL REFERENCES notifications (id) ON DELETE CASCADE,
    attempt_number   INTEGER NOT NULL,
    status           VARCHAR(16) NOT NULL,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
