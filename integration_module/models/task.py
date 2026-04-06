from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json


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
    """Внутреннее представление задачи (единый формат)"""

    id: str
    external_id: str
    source_type: SourceType
    title: str
    description: str = ""
    due_date: Optional[datetime] = None
    duration_minutes: int = 30
    priority: int = 3  # 1-наивысший, 4-низший
    status: TaskStatus = TaskStatus.PENDING
    project_id: str = ""
    labels: List[str] = field(default_factory=list)
    last_modified: datetime = field(default_factory=datetime.now)
    version: int = 1

    def to_json(self) -> str:
        """Сериализация в JSON"""
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
        """Десериализация из JSON"""
        data = json.loads(json_str)
        return cls(
            id=data["id"],
            external_id=data["external_id"],
            source_type=SourceType(data["source_type"]),
            title=data["title"],
            description=data.get("description", ""),
            due_date=(
                datetime.fromisoformat(data["due_date"])
                if data.get("due_date")
                else None
            ),
            duration_minutes=data.get("duration_minutes", 30),
            priority=data.get("priority", 3),
            status=TaskStatus(data.get("status", "pending")),
            project_id=data.get("project_id", ""),
            labels=data.get("labels", []),
            last_modified=(
                datetime.fromisoformat(data["last_modified"])
                if data.get("last_modified")
                else datetime.now()
            ),
            version=data.get("version", 1),
        )
