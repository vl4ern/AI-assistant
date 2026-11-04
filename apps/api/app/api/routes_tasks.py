from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.container import container
from app.core.settings import settings
from app.modules.auth.models import UserPublic
from app.modules.integrations.integration.task_extraction import (
    TaskExtractFile,
    TaskExtractionError,
)
from app.modules.integrations.models import TaskDrafts
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate, TaskStatusUpdate
from app.modules.knowledge.rules import KnowledgeRuleViolation

router = APIRouter(prefix="/v1", tags=["tasks"])

UPLOAD_CHUNK_BYTES = 1024 * 1024


def _upload_limit() -> int:
    """Максимальный размер загружаемого файла с небольшим запасом."""
    return max(
        settings.local_llm_max_image_mb * 1024 * 1024,
        settings.local_llm_max_text_kb * 1024,
    ) + 1


async def _read_upload_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Файл слишком большой. Увеличьте LOCAL_LLM_MAX_IMAGE_MB "
                    "или загрузите файл меньшего размера."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _ensure_can_access(item: Task, user: UserPublic) -> None:
    if item.user_id != user.id and item.user_id != "shared":
        raise HTTPException(status_code=404, detail="Task not found")


@router.get("/tasks", response_model=list[Task])
def list_tasks(user: UserPublic = Depends(get_current_user)) -> list[Task]:
    return container.knowledge_service.list_tasks(user.id)


@router.post("/tasks", response_model=Task, status_code=201)
def create_task(
    payload: TaskCreate,
    user: UserPublic = Depends(get_current_user),
) -> Task:
    payload.user_id = user.id
    try:
        return container.knowledge_service.create_task(payload)
    except KnowledgeRuleViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/extract", response_model=TaskDrafts)
async def extract_task_draft(
    text: str = Form(""),
    file: Optional[list[UploadFile]] = File(default=None),
    user: UserPublic = Depends(get_current_user),
) -> TaskDrafts:
    """
    Распознать черновики задач из текста и файлов (локальная LLM).

    Модель возвращает один черновик (одна задача) или несколько
    (несколько независимых задач — например, несколько лабораторных).
    Черновики не сохраняются: пользователь проверяет/правирует их и
    отправляет обычный POST /v1/tasks. Так данные по-прежнему принадлежат
    knowledge.
    """
    del user  # зависимость нужна только для проверки токена

    upload_files: list[TaskExtractFile] = []
    if file:
        for upload in file:
            upload_files.append(
                TaskExtractFile(
                    filename=upload.filename or "",
                    content_type=upload.content_type or "",
                    content=await _read_upload_limited(upload, _upload_limit()),
                )
            )

    try:
        return container.integration_service.extract_task_draft(
            text=text,
            files=upload_files,
        )
    except TaskExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/status", response_model=Task)
def update_task_status(
    task_id: str,
    payload: TaskStatusUpdate,
    user: UserPublic = Depends(get_current_user),
) -> Task:
    existing = container.knowledge_service.get_task(task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_can_access(existing, user)

    item = container.knowledge_service.update_task_status(task_id, payload.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")
    container.scheduler_service.on_task_status_updated(item)
    return item


@router.get("/events", response_model=list[Event])
def list_events(user: UserPublic = Depends(get_current_user)) -> list[Event]:
    return container.knowledge_service.list_events(user.id)


@router.post("/events", response_model=Event, status_code=201)
def create_event(
    payload: EventCreate,
    user: UserPublic = Depends(get_current_user),
) -> Event:
    payload.user_id = user.id
    try:
        return container.knowledge_service.create_event(payload)
    except KnowledgeRuleViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=Task)
def get_task(
    task_id: str,
    user: UserPublic = Depends(get_current_user),
) -> Task:
    item = container.knowledge_service.get_task(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_can_access(item, user)
    return item
