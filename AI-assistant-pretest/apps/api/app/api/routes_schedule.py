from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.container import container
from app.modules.auth.models import UserPublic
from app.modules.intelligence.models import (
    ReorderFeedbackRequest,
    ReorderFeedbackResult,
    SchedulePlan,
    TodayView,
)

router = APIRouter(prefix="/v1/schedule", tags=["schedule"])


@router.post("/rebuild", response_model=SchedulePlan)
def rebuild_schedule(user: UserPublic = Depends(get_current_user)) -> SchedulePlan:
    return container.scheduler_service.rebuild(user.id)


@router.get("/today", response_model=TodayView)
def get_today(user: UserPublic = Depends(get_current_user)) -> TodayView:
    return container.scheduler_service.today(user.id)


@router.post("/reorder-feedback", response_model=ReorderFeedbackResult)
def reorder_feedback(
    payload: ReorderFeedbackRequest,
    user: UserPublic = Depends(get_current_user),
) -> ReorderFeedbackResult:
    try:
        return container.scheduler_service.record_reorder_feedback(payload, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
