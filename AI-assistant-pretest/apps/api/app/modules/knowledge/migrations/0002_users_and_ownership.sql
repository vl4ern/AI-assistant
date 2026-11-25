BEGIN;

-- Пользователи и принадлежность задач/событий.
-- Идемпотентно: безопасно запускать на существующей базе.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'shared';
ALTER TABLE events ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'shared';

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);

COMMIT;
