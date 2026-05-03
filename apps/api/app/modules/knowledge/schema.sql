CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    estimated_minutes INTEGER NOT NULL CHECK (estimated_minutes >= 15 AND estimated_minutes <= 1440),
    priority INTEGER NOT NULL CHECK (priority >= 1 AND priority <= 4),
    deadline TIMESTAMPTZ NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT NULL,
    auto_reschedule BOOLEAN NOT NULL DEFAULT TRUE,
    allow_split BOOLEAN NOT NULL DEFAULT FALSE,
    min_chunk_minutes INTEGER NULL CHECK (min_chunk_minutes >= 15 AND min_chunk_minutes <= 1440),
    status TEXT NOT NULL CHECK (status IN ('todo', 'in_progress', 'completed', 'cancelled', 'blocked')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    scheduled_start TIMESTAMPTZ NULL,
    scheduled_end TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_task_id),
    CHECK (task_id <> depends_on_task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_events_start_at ON events(start_at);
