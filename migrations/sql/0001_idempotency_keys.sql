-- 0001_idempotency_keys.sql
CREATE TABLE idempotency_keys (
    key             VARCHAR(255) PRIMARY KEY,
    notification_id UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
