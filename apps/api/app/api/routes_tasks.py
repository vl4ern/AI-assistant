from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.container import container
from app.modules.auth.models import UserPublic
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate, TaskStatusUpdate
from app.modules.knowledge.rules import KnowledgeRuleViolation

router = APIRouter(prefix="/v1", tags=["tasks"])


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
