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
