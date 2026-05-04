from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IntegrationProvider:
    name: str

    def sync(self) -> int:
        """Run provider sync and return number of imported items."""
        return 0


class MockProvider(IntegrationProvider):
    def __init__(self) -> None:
        super().__init__(name="mock")

    def sync(self) -> int:
        return 3


def default_providers() -> list[IntegrationProvider]:
    return [MockProvider()]
