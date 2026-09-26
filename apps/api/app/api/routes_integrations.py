from typing import Any

from fastapi import APIRouter, HTTPException

from app.container import container
from app.modules.integrations.models import (
    IntegrationAdapterStatus,
    IntegrationSyncResult,
    Lesson,
    WeekInfo,
)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationAdapterStatus])
def list_integrations() -> list[IntegrationAdapterStatus]:
    return container.integration_service.list_adapters()


@router.get("/lessons", response_model=list[Lesson])
def list_lessons() -> list[Lesson]:
    """Занятия расписания из последней синхронизации (IIS БГУИР)."""
    return container.integration_service.list_lessons()


@router.get("/week", response_model=WeekInfo)
def get_current_week() -> WeekInfo:
    """Текущая учебная неделя (1–4)."""
    return container.integration_service.get_week_info()


@router.post("/import", response_model=IntegrationSyncResult)
def import_schedule(data: dict[str, Any]) -> IntegrationSyncResult:
    """
    Импорт расписания из JSON-файла портала БГУИР
    (формат ответа iis.bsuir.by/api/v1/schedule).
    """
    try:
        return container.integration_service.import_schedule(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync", response_model=IntegrationSyncResult)
def sync_all_integrations() -> IntegrationSyncResult:
    return container.integration_service.sync_all()


@router.post("/{provider_name}/sync", response_model=IntegrationSyncResult)
def sync_provider(provider_name: str) -> IntegrationSyncResult:
    try:
        return container.integration_service.sync_adapter(provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
