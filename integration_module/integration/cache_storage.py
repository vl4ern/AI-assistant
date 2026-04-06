import sqlite3
import json
from typing import Optional, List
from datetime import datetime
from models.task import Task, SourceType, TaskStatus
from integration.interfaces import ICacheStorage


class SQLiteCacheStorage(ICacheStorage):
    """Реализация кэш-хранилища на SQLite"""

    def __init__(self, db_path: str = "cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Инициализация таблиц"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    external_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    due_date TEXT,
                    duration_minutes INTEGER,
                    priority INTEGER,
                    status TEXT,
                    project_id TEXT,
                    labels TEXT,
                    last_modified TEXT,
                    version INTEGER,
                    data TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_external_id 
                ON tasks(external_id, source_type)
            """
            )

    def get_task(self, task_id: str) -> Optional[Task]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT data FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return Task.from_json(row[0])
        return None

    def get_task_by_external_id(
        self, external_id: str, source_type: str
    ) -> Optional[Task]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM tasks WHERE external_id = ? AND source_type = ?",
                (external_id, source_type),
            )
            row = cursor.fetchone()
            if row:
                return Task.from_json(row[0])
        return None

    def save_task(self, task: Task) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks 
                    (id, external_id, source_type, title, description, due_date, 
                     duration_minutes, priority, status, project_id, labels, last_modified, version, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        task.id,
                        task.external_id,
                        task.source_type.value,
                        task.title,
                        task.description,
                        task.due_date.isoformat() if task.due_date else None,
                        task.duration_minutes,
                        task.priority,
                        task.status.value,
                        task.project_id,
                        json.dumps(task.labels),
                        task.last_modified.isoformat(),
                        task.version,
                        task.to_json(),
                    ),
                )
            return True
        except Exception as e:
            print(f"Error saving task: {e}")
            return False

    def delete_task(self, task_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return True

    def get_version(self, task_id: str) -> int:
        task = self.get_task(task_id)
        return task.version if task else 0
