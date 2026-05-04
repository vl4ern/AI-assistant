from fastapi import APIRouter, HTTPException

from app.container import container
from app.modules.intelligence.models import (
    ReorderFeedbackRequest,
    ReorderFeedbackResult,
    SchedulePlan,
    TodayView,
)

router = APIRouter(prefix="/v1/schedule", tags=["schedule"])


@router.post("/rebuild", response_model=SchedulePlan)
def rebuild_schedule() -> SchedulePlan:
    return container.scheduler_service.rebuild()


@router.get("/today", response_model=TodayView)
def get_today() -> TodayView:
    return container.scheduler_service.today()


@router.post("/reorder-feedback", response_model=ReorderFeedbackResult)
def reorder_feedback(payload: ReorderFeedbackRequest) -> ReorderFeedbackResult:
    try:
        return container.scheduler_service.record_reorder_feedback(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
