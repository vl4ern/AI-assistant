from __future__ import annotations

import os
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    app_name: str = "AI Assistant API"
    app_version: str = "0.1.0"
    schedule_horizon_days: int = Field(
        default=int(os.getenv("SCHEDULE_HORIZON_DAYS", "30")), ge=1, le=30
    )
    schedule_slot_minutes: int = Field(
        default=int(os.getenv("SCHEDULE_SLOT_MINUTES", "30")), ge=15, le=120
    )
    wake_start_hour: int = Field(default=int(os.getenv("WAKE_START_HOUR", "8")), ge=0, le=23)
    wake_end_hour: int = Field(default=int(os.getenv("WAKE_END_HOUR", "23")), ge=1, le=24)
    ml_retrain_batch_size: int = Field(
        default=int(os.getenv("ML_RETRAIN_BATCH_SIZE", "20")), ge=1, le=1000
    )
    ml_overdue_bonus: float = Field(
        default=float(os.getenv("ML_OVERDUE_BONUS", "10")), ge=0, le=10000
    )


settings = AppSettings()
