from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.integrations.models import IntegrationSyncResult


class IntegrationProvider(ABC):
    name: str

    @abstractmethod
    def sync(self) -> IntegrationSyncResult:
        raise NotImplementedError


class GoogleCalendarProvider(IntegrationProvider):
    name = "google-calendar"

    def sync(self) -> IntegrationSyncResult:
        return IntegrationSyncResult(
            provider=self.name,
            imported_items=3,
            updated_items=1,
            warnings=[],
        )


class GithubProvider(IntegrationProvider):
    name = "github"

    def sync(self) -> IntegrationSyncResult:
        return IntegrationSyncResult(
            provider=self.name,
            imported_items=2,
            updated_items=0,
            warnings=[],
        )


class BsuirLmsProvider(IntegrationProvider):
    name = "bsuir-lms"

    def sync(self) -> IntegrationSyncResult:
        return IntegrationSyncResult(
            provider=self.name,
            imported_items=4,
            updated_items=1,
            warnings=["Running in demo mode: manual credentials are not configured."],
        )


def default_providers() -> dict[str, IntegrationProvider]:
    return {
        provider.name: provider
        for provider in [GoogleCalendarProvider(), GithubProvider(), BsuirLmsProvider()]
    }
