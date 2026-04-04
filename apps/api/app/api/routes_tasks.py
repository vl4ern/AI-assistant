from fastapi import APIRouter, HTTPException

from app.container import container
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate, TaskStatusUpdate

router = APIRouter(prefix="/v1", tags=["tasks"])


@router.get("/tasks", response_model=list[Task])
def list_tasks() -> list[Task]:
    return container.knowledge_repository.list_tasks()


@router.post("/tasks", response_model=Task, status_code=201)
def create_task(payload: TaskCreate) -> Task:
    return container.knowledge_repository.create_task(payload)


@router.patch("/tasks/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    item = container.knowledge_repository.update_task_status(task_id, payload.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return item


@router.get("/events", response_model=list[Event])
def list_events() -> list[Event]:
    return container.knowledge_repository.list_events()


@router.post("/events", response_model=Event, status_code=201)
def create_event(payload: EventCreate) -> Event:
    return container.knowledge_repository.create_event(payload)
