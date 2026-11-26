from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.container import container
from app.modules.auth.models import UserPublic
from app.modules.integrations.models import (
    CurrentGroupInfo,
    GoogleCalendarStatus,
    GoogleExportResult,
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


@router.get("/google/status", response_model=GoogleCalendarStatus)
def google_status() -> GoogleCalendarStatus:
    """Состояние интеграции с Google Calendar (настроена / подключена)."""
    return container.integration_service.google_status()


@router.post("/google/connect", response_model=GoogleCalendarStatus)
def google_connect() -> GoogleCalendarStatus:
    """
    Авторизация в Google (OAuth). Браузер откроется на машине с backend.
    Запрос блокируется до завершения авторизации.
    """
    try:
        return container.integration_service.connect_google()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/google/export", response_model=GoogleExportResult)
def google_export(user: UserPublic = Depends(get_current_user)) -> GoogleExportResult:
    """Перестраивает план пользователя и переносит слоты в Google Calendar."""
    plan = container.scheduler_service.rebuild(user.id)
    try:
        return container.integration_service.export_slots_to_google(plan.slots)
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
