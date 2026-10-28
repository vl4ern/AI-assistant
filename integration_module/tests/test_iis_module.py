import pytest
from datetime import datetime, timezone
from models.iis_models import IisScheduleItem
from models.task import SourceType


@pytest.fixture
def sample_lesson():
    # Пара "ООП", понедельник, 09:00, идёт на 1 и 3 неделях
    return IisScheduleItem.from_dict(
        {
            "weekNumber": [1, 3],
            "numSubgroup": 0,
            "auditories": ["111-4 к."],
            "startLessonTime": "09:00",
            "endLessonTime": "10:20",
            "subject": "ООП",
            "subjectFullName": "Объектно-ориентированное программирование",
            "lessonTypeAbbrev": "ЛР",
            "startLessonDate": "14.02.2022",
            "endLessonDate": "06.06.2022",
        },
        day_of_week="Понедельник",
    )


def test_iis_schedule_date_calculation(sample_lesson):
    # Понедельник, 28 сентября 2026 (представим, что сегодня)
    base_date = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)

    # Если позиция в цикле = 1 (1-я неделя), пара должна попасть на СЕГОДНЯ (28.09)
    # так как время пары 09:00, а base_date 08:00 — время ещё не прошло
    task1 = sample_lesson.to_task(
        base_date=base_date,
        position_in_cycle=1,
        group_number="421701",
        week_cycle=4,
        is_exam=False,
    )
    assert task1 is not None
    assert task1.due_date.day == 28
    assert task1.due_date.hour == 9

    # Если позиция в цикле = 2 (2-я неделя), пара не идёт.
    # Ближайшая будущая — 3-я неделя, то есть через 1 неделю (5 октября)
    task2 = sample_lesson.to_task(
        base_date=base_date,
        position_in_cycle=2,
        group_number="421701",
        week_cycle=4,
        is_exam=False,
    )
    assert task2 is not None
    assert task2.due_date.day == 5
    assert task2.due_date.month == 10

    # Проверка группировки external_id (влияет ли группа на ID)
    task_other_group = sample_lesson.to_task(
        base_date=base_date,
        position_in_cycle=1,
        group_number="999999",  # другая группа
        week_cycle=4,
        is_exam=False,
    )
    assert task1.external_id != task_other_group.external_id
