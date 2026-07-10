-- 0003_templates.sql
CREATE TABLE templates (
    id         VARCHAR(128) PRIMARY KEY,
    subject    VARCHAR(255),
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
