from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
import json


def utc_now() -> datetime:
    """Единая точка получения текущего времени (aware UTC)."""
    return datetime.now(timezone.utc)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Приводит datetime к aware UTC. Naive считается UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SourceType(Enum):
    IIS = "IIS"
    GOOGLE_CALENDAR = "google_calendar"
    MANUAL = "manual"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class Task:
    id: str
    external_id: str
    source_type: SourceType
    title: str
    description: str = ""
    due_date: Optional[datetime] = None
    duration_minutes: int = 30
    priority: int = 3
    status: TaskStatus = TaskStatus.PENDING
    project_id: str = ""
    labels: List[str] = field(default_factory=list)
    last_modified: datetime = field(default_factory=utc_now)
    version: int = 1

    def to_json(self) -> str:
        data = {
            "id": self.id,
            "external_id": self.external_id,
            "source_type": self.source_type.value,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "duration_minutes": self.duration_minutes,
            "priority": self.priority,
            "status": self.status.value,
            "project_id": self.project_id,
            "labels": self.labels,
            "last_modified": self.last_modified.isoformat(),
            "version": self.version,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Task":
        data = json.loads(json_str)
        due_date = (
            ensure_aware(datetime.fromisoformat(data["due_date"]))
            if data.get("due_date")
            else None
        )
        last_modified = (
            ensure_aware(datetime.fromisoformat(data["last_modified"]))
            if data.get("last_modified")
            else utc_now()
        )
        return cls(
            id=data["id"],
            external_id=data["external_id"],
            source_type=SourceType(data["source_type"]),
            title=data["title"],
            description=data.get("description", ""),
            due_date=due_date,
            duration_minutes=data.get("duration_minutes", 30),
            priority=data.get("priority", 3),
            status=TaskStatus(data.get("status", "pending")),
            project_id=data.get("project_id", ""),
            labels=data.get("labels", []),
            last_modified=last_modified,
            version=data.get("version", 1),
        )