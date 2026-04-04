from fastapi import FastAPI

from app.api.router import router
from app.core.settings import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(router)
