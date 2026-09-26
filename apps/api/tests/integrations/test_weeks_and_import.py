from datetime import date, datetime
from pathlib import Path

from app.modules.integrations.models.iis_models import IisScheduleItem, academic_week
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

SEMESTER_START = date(2026, 9, 1)


def test_academic_week_cycles_from_semester_start() -> None:
    assert academic_week(date(2026, 9, 1), SEMESTER_START) == 1
    assert academic_week(date(2026, 9, 7), SEMESTER_START) == 1
    assert academic_week(date(2026, 9, 8), SEMESTER_START) == 2
    assert academic_week(date(2026, 9, 15), SEMESTER_START) == 3
    assert academic_week(date(2026, 9, 22), SEMESTER_START) == 4
    # Пятая неделя семестра — снова учебная неделя 1
    assert academic_week(date(2026, 9, 29), SEMESTER_START) == 1
    # До начала семестра — считаем первой неделей
    assert academic_week(date(2026, 8, 20), SEMESTER_START) == 1


def make_lesson(weeks: list[int]) -> IisScheduleItem:
    return IisScheduleItem.from_dict(
        {
            "weekNumber": weeks,
            "studentGroups": [],
            "numSubgroup": 0,
            "auditories": ["101-1"],
            "startLessonTime": "10:00",
            "endLessonTime": "11:20",
            "subject": "ООП",
            "subjectFullName": "Объектно-ориентированное программирование",
            "note": None,
            "lessonTypeAbbrev": "ЛК",
            "dateLesson": None,
            "startLessonDate": None,
            "endLessonDate": None,
            "announcement": False,
            "split": False,
            "employees": [],
        },
        day_of_week="Вторник",
    )


def test_to_tasks_creates_occurrences_only_on_matching_weeks() -> None:
    item = make_lesson([1, 3])
    now = datetime(2026, 9, 26, 8, 0)  # суббота, учебная неделя 4

    tasks = item.to_tasks(now, semester_start=SEMESTER_START, horizon_days=28)

    # 28 дней = 4 учебные недели; вторники недель 1 и 3 → 2 появления
    assert len(tasks) == 2

    due_dates = [task.due_date.date().isoformat() for task in tasks]
    assert due_dates == ["2026-09-29", "2026-10-13"]

    # У каждого появления свой external_id — иначе недели склеятся в кэше
    external_ids = {task.external_id for task in tasks}
    assert len(external_ids) == 2

    # У каждого появления есть день недели и недели в описании
    for task in tasks:
        assert "День недели: Вторник" in task.description
        assert "Недели: 1, 3" in task.description


def test_to_tasks_skips_today_lesson_already_started() -> None:
    item = make_lesson([1, 2, 3, 4])
    # Вторник 10:00, а «сейчас» — вторник 12:00
    now = datetime(2026, 9, 29, 12, 0)

    tasks = item.to_tasks(now, semester_start=SEMESTER_START, horizon_days=7)

    assert all(task.due_date > now for task in tasks)
    assert "2026-09-29" not in {task.due_date.date().isoformat() for task in tasks}


def test_import_schedule_uses_one_shot_pipeline(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    payload = {
        "schedules": {
            "Вторник": [
                {
                    "weekNumber": [1],
                    "studentGroups": [],
                    "numSubgroup": 0,
                    "auditories": ["202-1"],
                    "startLessonTime": "13:30",
                    "endLessonTime": "14:55",
                    "subject": "ЛОИС",
                    "subjectFullName": "Логика и теория алгоритмов",
                    "lessonTypeAbbrev": "ЛК",
                    "announcement": False,
                    "split": False,
                    "employees": [],
                }
            ]
        },
        "exams": [],
    }

    result = service.import_schedule(payload)

    assert result.provider == "import"
    assert result.synced_items >= 1
    assert result.status == "ok"

    lessons = service.list_lessons()
    assert any(lesson.subject == "ЛОИС" for lesson in lessons)
    assert any(lesson.week_numbers == [1] for lesson in lessons)
    # У появления есть собственная учебная неделя — по его дате
    assert all(lesson.week is not None for lesson in lessons)

    # Занятие попало и в базу знаний как событие
    assert any(event.title == "ЛОИС" for event in kb.list_events())

    # Импорт не оставляет висящего адаптера в списке
    assert all(adapter.name != "import" for adapter in service.list_adapters())


def test_get_week_info_returns_current_week(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    info = service.get_week_info()

    assert 1 <= info.current_week <= 4
    assert info.semester_start.date() == SEMESTER_START
