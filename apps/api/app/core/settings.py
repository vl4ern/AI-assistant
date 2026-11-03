from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


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
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ai_assistant",
    )
    postgres_auto_init_schema: bool = os.getenv("POSTGRES_AUTO_INIT_SCHEMA", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    iis_group_number: str = os.getenv("IIS_GROUP_NUMBER", "")
    integration_cache_path: str = os.getenv("INTEGRATION_CACHE_PATH", "data/integration_cache.db")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "google_token.pickle")
    integrations_background_sync_enabled: bool = os.getenv(
        "INTEGRATIONS_BACKGROUND_SYNC_ENABLED", "true"
    ).lower() in {"1", "true", "yes", "on"}
    auth_token_secret: str = os.getenv(
        "AUTH_TOKEN_SECRET",
        "dev-secret-change-me-in-production",
    )
    semester_start_date: str = os.getenv("SEMESTER_START_DATE", "2026-09-01")
    iis_horizon_days: int = Field(
        default=int(os.getenv("IIS_HORIZON_DAYS", "28")), ge=7, le=60
    )

    # Локальная модель (llama-server, OpenAI-совместимый API).
    local_llm_enabled: bool = os.getenv("LOCAL_LLM_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:8080")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "qwen3.5-4b")
    local_llm_api_key: str = os.getenv("LOCAL_LLM_API_KEY", "")
    local_llm_timeout_seconds: int = Field(
        default=int(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "180")), ge=5, le=600
    )
    local_llm_max_tokens: int = Field(
        default=int(os.getenv("LOCAL_LLM_MAX_TOKENS", "1024")), ge=64, le=8192
    )
    local_llm_temperature: float = Field(
        default=float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.1")), ge=0, le=2
    )
    local_llm_disable_thinking: bool = os.getenv(
        "LOCAL_LLM_DISABLE_THINKING", "true"
    ).lower() in {"1", "true", "yes", "on"}
    local_llm_vision_enabled: bool = os.getenv(
        "LOCAL_LLM_VISION_ENABLED", "true"
    ).lower() in {"1", "true", "yes", "on"}
    local_llm_max_text_kb: int = Field(
        default=int(os.getenv("LOCAL_LLM_MAX_TEXT_KB", "256")), ge=1, le=4096
    )
    local_llm_max_image_mb: int = Field(
        default=int(os.getenv("LOCAL_LLM_MAX_IMAGE_MB", "10")), ge=1, le=50
    )


settings = AppSettings()
