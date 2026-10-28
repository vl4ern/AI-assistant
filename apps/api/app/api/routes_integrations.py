from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.container import container
from app.modules.integrations.models import (
    CurrentGroupInfo,
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
    """Занятия расписания текущей группы (последней синхронизации/импорта)."""
    return container.integration_service.list_lessons()


@router.get("/week", response_model=WeekInfo)
def get_current_week() -> WeekInfo:
    """Текущая учебная неделя (1–4)."""
    return container.integration_service.get_week_info()


@router.get("/current-group", response_model=CurrentGroupInfo)
def get_current_group() -> CurrentGroupInfo:
    """Группа, расписание которой сейчас показывается."""
    return CurrentGroupInfo(
        group_number=container.integration_service.get_current_group()
    )


@router.post("/import-file", response_model=IntegrationSyncResult)
async def import_schedule_file(
    file: UploadFile = File(...),
    group_number: str = Form(""),
) -> IntegrationSyncResult:
    """
    Импорт расписания из XLSX-файла (выгрузка расписания группы).
    Импортированное расписание заменяет прежнее и становится текущим.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")
    try:
        return container.integration_service.import_schedule_file(
            content, group_hint=group_number
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync-group", response_model=IntegrationSyncResult)
def sync_group(data: dict) -> IntegrationSyncResult:
    """Синхронизация расписания группы, введённой пользователем ({"group_number": "..."})."""
    group_number = str(data.get("group_number", "") or "")
    try:
        return container.integration_service.sync_group(group_number)
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
