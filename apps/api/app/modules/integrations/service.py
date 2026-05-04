from __future__ import annotations

from app.modules.integrations.models import IntegrationSyncResult
from app.modules.integrations.providers import IntegrationProvider


class IntegrationService:
    def __init__(self, providers: list[IntegrationProvider]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    def sync(self, provider_name: str) -> IntegrationSyncResult:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' not found")

        synced_items = provider.sync()
        return IntegrationSyncResult(
            provider=provider_name,
            synced_items=synced_items,
            status="ok",
            message="Synchronization completed",
        )
