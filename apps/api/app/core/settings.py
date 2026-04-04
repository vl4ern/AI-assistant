from __future__ import annotations

import os
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    app_name: str = "AI Assistant API"
    app_version: str = "0.1.0"
    schedule_horizon_days: int = Field(
        default=int(os.getenv("SCHEDULE_HORIZON_DAYS", "7")), ge=1, le=30
    )
    schedule_slot_minutes: int = Field(
        default=int(os.getenv("SCHEDULE_SLOT_MINUTES", "30")), ge=15, le=120
    )
    wake_start_hour: int = Field(default=int(os.getenv("WAKE_START_HOUR", "8")), ge=0, le=23)
    wake_end_hour: int = Field(default=int(os.getenv("WAKE_END_HOUR", "23")), ge=1, le=24)


settings = AppSettings()
