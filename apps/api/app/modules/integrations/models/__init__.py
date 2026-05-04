from pydantic import BaseModel, Field


class IntegrationSyncResult(BaseModel):
    provider: str = Field(..., description="Integration provider name")
    synced_items: int = Field(ge=0, default=0)
    status: str = Field(default="ok")
    message: str = Field(default="Synchronization completed")
