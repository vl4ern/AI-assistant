from fastapi import APIRouter

from app.container import container
from app.modules.intelligence.models import SchedulePlan, TodayView

router = APIRouter(prefix="/v1/schedule", tags=["schedule"])


@router.post("/rebuild", response_model=SchedulePlan)
def rebuild_schedule() -> SchedulePlan:
    return container.scheduler_service.rebuild()


@router.get("/today", response_model=TodayView)
def get_today() -> TodayView:
    return container.scheduler_service.today()
