from fastapi import APIRouter

from app.api.routes_health import router as health_router
from app.api.routes_integrations import router as integrations_router
from app.api.routes_schedule import router as schedule_router
from app.api.routes_tasks import router as tasks_router

router = APIRouter()
router.include_router(health_router)
router.include_router(tasks_router)
router.include_router(schedule_router)
router.include_router(integrations_router)
