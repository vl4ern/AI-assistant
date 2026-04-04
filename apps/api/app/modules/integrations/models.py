from __future__ import annotations

from pydantic import BaseModel, Field


class IntegrationSyncResult(BaseModel):
    provider: str
    imported_items: int
    updated_items: int
    warnings: list[str] = Field(default_factory=list)
