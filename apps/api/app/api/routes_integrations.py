from fastapi import APIRouter, HTTPException

from app.container import container
from app.modules.integrations.models import IntegrationAdapterStatus, IntegrationSyncResult

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationAdapterStatus])
def list_integrations() -> list[IntegrationAdapterStatus]:
    return container.integration_service.list_adapters()


@router.post("/sync", response_model=IntegrationSyncResult)
def sync_all_integrations() -> IntegrationSyncResult:
    return container.integration_service.sync_all()


@router.post("/{provider_name}/sync", response_model=IntegrationSyncResult)
def sync_provider(provider_name: str) -> IntegrationSyncResult:
    try:
        return container.integration_service.sync_adapter(provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
