-- 0004_user_preferences.sql
CREATE TABLE user_preferences (
    user_id    VARCHAR(128) NOT NULL,
    channel    VARCHAR(16) NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, channel)
);

CREATE INDEX ix_user_preferences_user_id ON user_preferences (user_id);
