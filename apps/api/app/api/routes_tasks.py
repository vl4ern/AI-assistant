from fastapi import APIRouter, HTTPException, Response, status

from app.container import container
from app.modules.knowledge.models import (
    Event,
    EventCreate,
    Task,
    TaskCreate,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.modules.knowledge.rules import KnowledgeRuleViolation

router = APIRouter(prefix="/v1", tags=["tasks"])


@router.get("/tasks", response_model=list[Task])
def list_tasks() -> list[Task]:
    return container.knowledge_service.list_tasks()


@router.post("/tasks", response_model=Task, status_code=201)
def create_task(payload: TaskCreate) -> Task:
    try:
        return container.knowledge_service.create_task(payload)
    except KnowledgeRuleViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: str, payload: TaskUpdate) -> Task:
    try:
        item = container.knowledge_service.update_task(task_id, payload)
    except KnowledgeRuleViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return item


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str) -> Response:
    deleted = container.knowledge_service.delete_task(task_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/tasks/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    item = container.knowledge_service.update_task_status(task_id, payload.status)

    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")

    container.scheduler_service.on_task_status_updated(item)
    return item


@router.get("/events", response_model=list[Event])
def list_events() -> list[Event]:
    return container.knowledge_service.list_events()


@router.post("/events", response_model=Event, status_code=201)
def create_event(payload: EventCreate) -> Event:
    try:
        return container.knowledge_service.create_event(payload)
    except KnowledgeRuleViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
