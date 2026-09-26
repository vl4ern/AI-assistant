from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.modules.auth.models import User

from .models import Event, EventCreate, Task, TaskCreate, TaskStatus
from .models import SHARED_USER_ID
from .repository import KnowledgeRepository

try:
    import psycopg
except ImportError:  # pragma: no cover - runtime dependency guard
    psycopg = None


class PostgresKnowledgeRepository(KnowledgeRepository):
    def __init__(self, dsn: str, *, auto_init_schema: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgresKnowledgeRepository")
        self._dsn = dsn
        self._schedule_dirty = True
        self._lock = Lock()
        if auto_init_schema:
            self._init_schema()

    def _connect(self) -> Any:
        return psycopg.connect(self._dsn)

    def _init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(schema_sql)
            conn.commit()

        migrations_dir = Path(__file__).with_name("migrations")
        migration_files = sorted(migrations_dir.glob("*.sql"))
        with self._connect() as conn, conn.cursor() as cur:
            for migration_file in migration_files:
                cur.execute(migration_file.read_text(encoding="utf-8"))
            conn.commit()

    @staticmethod
    def _task_from_row(row: Any) -> Task:
        depends_on = list(row[13]) if row[13] else []
        return Task(
            id=row[0],
            title=row[1],
            description=row[2],
            estimated_minutes=row[3],
            priority=row[4],
            deadline=row[5],
            workspace_id=row[6],
            project_id=row[7],
            auto_reschedule=row[8],
            allow_split=row[9],
            min_chunk_minutes=row[10],
            status=row[11],
            created_at=row[12],
            depends_on=depends_on,
            updated_at=row[14],
            scheduled_start=row[15],
            scheduled_end=row[16],
            user_id=row[17],
        )

    @staticmethod
    def _task_query(where_clause: str = "") -> str:
        return f"""
            SELECT
                t.id,
                t.title,
                t.description,
                t.estimated_minutes,
                t.priority,
                t.deadline,
                t.workspace_id,
                t.project_id,
                t.auto_reschedule,
                t.allow_split,
                t.min_chunk_minutes,
                t.status,
                t.created_at,
                COALESCE(
                    ARRAY_AGG(td.depends_on_task_id) FILTER (WHERE td.depends_on_task_id IS NOT NULL),
                    '{{}}'
                ) AS depends_on,
                t.updated_at,
                t.scheduled_start,
                t.scheduled_end,
                t.user_id
            FROM tasks t
            LEFT JOIN task_dependencies td ON td.task_id = t.id
            {where_clause}
            GROUP BY t.id
            ORDER BY t.created_at ASC
        """

    def list_tasks(self, user_id: str | None = None) -> list[Task]:
        query = self._task_query()
        params: tuple[Any, ...] = ()
        if user_id is not None:
            query = self._task_query("WHERE t.user_id = ANY(%s)")
            params = ([user_id, SHARED_USER_ID],)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._task_from_row(row) for row in rows]

    def get_task(self, task_id: str) -> Task | None:
        query = self._task_query("WHERE t.id = %s")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, (task_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._task_from_row(row)

    def create_task(self, payload: TaskCreate) -> Task:
        item = Task(**payload.model_dump())
        insert_task = """
            INSERT INTO tasks (
                id,
                title,
                description,
                estimated_minutes,
                priority,
                deadline,
                workspace_id,
                project_id,
                auto_reschedule,
                allow_split,
                min_chunk_minutes,
                status,
                created_at,
                updated_at,
                scheduled_start,
                scheduled_end,
                user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        insert_dep = """
            INSERT INTO task_dependencies (task_id, depends_on_task_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                insert_task,
                (
                    item.id,
                    item.title,
                    item.description,
                    item.estimated_minutes,
                    item.priority,
                    item.deadline,
                    item.workspace_id,
                    item.project_id,
                    item.auto_reschedule,
                    item.allow_split,
                    item.min_chunk_minutes,
                    item.status,
                    item.created_at,
                    item.updated_at,
                    item.scheduled_start,
                    item.scheduled_end,
                    item.user_id,
                ),
            )
            for dependency_id in item.depends_on:
                cur.execute(insert_dep, (item.id, dependency_id))
            conn.commit()
        with self._lock:
            self._schedule_dirty = True
        return item

    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        query = """
            UPDATE tasks
            SET status = %s, updated_at = %s
            WHERE id = %s
            RETURNING id
        """
        updated_at = datetime.now(timezone.utc)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, (status, updated_at, task_id))
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        with self._lock:
            self._schedule_dirty = True
        return self.get_task(task_id)

    def update_task_schedule(
        self,
        task_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> Task | None:
        query = """
            UPDATE tasks
            SET scheduled_start = %s, scheduled_end = %s, updated_at = %s
            WHERE id = %s
            RETURNING id
        """
        updated_at = datetime.now(timezone.utc)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, (start_at, end_at, updated_at, task_id))
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return self.get_task(task_id)

    def list_events(self, user_id: str | None = None) -> list[Event]:
        query = """
            SELECT id, title, start_at, end_at, source, user_id
            FROM events
        """
        params: tuple[Any, ...] = ()
        if user_id is not None:
            query += " WHERE user_id = ANY(%s)"
            params = ([user_id, SHARED_USER_ID],)
        query += " ORDER BY start_at ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [
            Event(
                id=row[0],
                title=row[1],
                start_at=row[2],
                end_at=row[3],
                source=row[4],
                user_id=row[5],
            )
            for row in rows
        ]

    def create_event(self, payload: EventCreate) -> Event:
        item = Event(**payload.model_dump())
        query = """
            INSERT INTO events (id, title, start_at, end_at, source, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                query,
                (item.id, item.title, item.start_at, item.end_at, item.source, item.user_id),
            )
            conn.commit()
        with self._lock:
            self._schedule_dirty = True
        return item

    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        user_id: str | None = None,
    ) -> User:
        user_data: dict[str, str] = {
            "username": username,
            "password_hash": password_hash,
            "salt": salt,
        }
        if user_id:
            user_data["id"] = user_id
        user = User(**user_data)
        query = """
            INSERT INTO users (id, username, password_hash, salt, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                query,
                (user.id, user.username, user.password_hash, user.salt, user.created_at),
            )
            conn.commit()
        return user

    def get_user_by_username(self, username: str) -> User | None:
        query = """
            SELECT id, username, password_hash, salt, created_at
            FROM users
            WHERE username = %s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, (username,))
            row = cur.fetchone()
        if row is None:
            return None
        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            salt=row[3],
            created_at=row[4],
        )

    def is_schedule_dirty(self) -> bool:
        with self._lock:
            return self._schedule_dirty

    def set_schedule_dirty(self, value: bool) -> None:
        with self._lock:
            self._schedule_dirty = value
