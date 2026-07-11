-- 0006_rate_limit_buckets.sql
-- One row per user, holding token-bucket state for rate limiting.
CREATE TABLE rate_limit_buckets (
    user_id         VARCHAR(128) PRIMARY KEY,
    tokens          DOUBLE PRECISION NOT NULL,
    last_refill_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
