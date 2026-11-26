from datetime import datetime, timezone

import pytest

from app.core.time_utils import to_utc


def test_naive_local_time_is_localized_before_writing_to_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_TIMEZONE", "Europe/Minsk")

    result = to_utc(datetime(2026, 11, 29, 13, 0))

    assert result is not None
    assert result.tzinfo is not None
    assert result == datetime(2026, 11, 29, 10, 0, tzinfo=timezone.utc)


def test_aware_and_empty_values_are_not_changed() -> None:
    aware = datetime(2026, 11, 29, 10, 0, tzinfo=timezone.utc)

    assert to_utc(None) is None
    assert to_utc(aware) == aware
