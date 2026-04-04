from __future__ import annotations

from app.modules.integrations.models import IntegrationSyncResult
from app.modules.integrations.providers import IntegrationProvider


class IntegrationService:
    def __init__(self, providers: dict[str, IntegrationProvider]) -> None:
        self.providers = providers

    def list_providers(self) -> list[str]:
        return sorted(self.providers.keys())

    def sync(self, provider_name: str) -> IntegrationSyncResult:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unsupported provider: {provider_name}")
        return provider.sync()
