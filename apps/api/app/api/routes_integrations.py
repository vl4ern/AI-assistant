from fastapi import APIRouter, HTTPException

from app.container import container
from app.modules.integrations.models import IntegrationSyncResult

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[str])
def list_integrations() -> list[str]:
    return container.integration_service.list_providers()


@router.post("/{provider_name}/sync", response_model=IntegrationSyncResult)
def sync_provider(provider_name: str) -> IntegrationSyncResult:
    try:
        return container.integration_service.sync(provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
