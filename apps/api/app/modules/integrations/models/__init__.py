from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationSyncResult(BaseModel):
    provider: str = Field(..., description="Integration provider name")
    synced_items: int = Field(ge=0, default=0)
    conflicts_detected: int = Field(ge=0, default=0)
    errors: list[str] = Field(default_factory=list)
    status: str = Field(default="ok")
    message: str = Field(default="Synchronization completed")

    @property
    def success(self) -> bool:
        return not self.errors


class IntegrationAdapterStatus(BaseModel):
    name: str = Field(..., description="Adapter name")
    source: str = Field(..., description="External source type")
    sync_interval_seconds: int = Field(ge=0)
    last_sync_at: datetime | None = None
    running: bool = False


class Lesson(BaseModel):
    """Одно занятие расписания, восстановленное из кэша синхронизации."""

    id: str = Field(..., description="Внешний идентификатор занятия")
    subject: str = Field(..., description="Название предмета")
    subject_full_name: str = ""
    day_of_week: str | None = None
    start_time: str = Field(..., description="Время начала, HH:MM")
    end_time: str = Field(..., description="Время окончания, HH:MM")
    lesson_type: str = ""
    teacher: str = ""
    auditory: str = ""
    weeks: str = ""
    week_numbers: list[int] = Field(default_factory=list)
    week: int | None = Field(
        default=None,
        description="Учебная неделя этого появления (по его дате), 1–4",
    )
    subgroup: int = Field(
        default=0,
        description="Подгруппа: 0 — общая пара, 1 — первая подгруппа, 2 — вторая",
    )
    next_date: datetime | None = Field(
        default=None, description="Ближайшая дата занятия"
    )


class WeekInfo(BaseModel):
    """Информация об учебной неделе."""

    current_week: int = Field(ge=1, le=4)
    semester_start: datetime
    today: datetime
