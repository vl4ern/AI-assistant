from datetime import datetime, timezone
from app.modules.intelligence.utils.time_utils import build_working_windows


def test_build_working_windows_typical_day() -> None:
    start = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    end   = datetime(2026, 5, 3, 23, 0, tzinfo=timezone.utc)
    windows = build_working_windows(start, end, wake_start_hour=8, wake_end_hour=22)

    assert len(windows) == 1
    assert windows[0][0] == start
    assert windows[0][1] == datetime(2026, 5, 3, 22, 0, tzinfo=timezone.utc)


def test_build_working_windows_wake_end_24() -> None:
    start = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    end   = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    windows = build_working_windows(start, end, wake_start_hour=8, wake_end_hour=24)

    assert len(windows) == 1
    assert windows[0][0] == start
    assert windows[0][1] == datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)  # конец дня бодрствования


def test_build_working_windows_span_multiple_days() -> None:
    start = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    end   = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)
    windows = build_working_windows(start, end, wake_start_hour=8, wake_end_hour=22)

    assert len(windows) == 3
    assert windows[0] == (start, datetime(2026, 5, 3, 22, 0, tzinfo=timezone.utc))
    assert windows[1] == (datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc), datetime(2026, 5, 4, 22, 0, tzinfo=timezone.utc))
    assert windows[2] == (datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc), end)


def test_build_working_windows_no_overlap() -> None:
    start = datetime(2026, 5, 3, 23, 0, tzinfo=timezone.utc)
    end   = datetime(2026, 5, 3, 23, 30, tzinfo=timezone.utc)
    windows = build_working_windows(start, end, wake_start_hour=8, wake_end_hour=22)
    assert len(windows) == 0
