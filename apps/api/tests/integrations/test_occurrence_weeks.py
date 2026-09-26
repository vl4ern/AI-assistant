from datetime import date, datetime
from pathlib import Path

from app.modules.integrations.models.iis_models import academic_week
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

SEMESTER_START = date(2026, 9, 1)


def build_service_with_two_fridays(tmp_path: Path) -> IntegrationService:
    """
    Занятие «Физика» по пятницам недель 1 и 3.
    В горизонте 28 дней таких пятниц две — должно быть два появления,
    каждое со своей собственной учебной неделей (1 и 3).
    """
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    payload = {
        "schedules": {
            "Пятница": [
                {
                    "weekNumber": [1, 3],
                    "studentGroups": [],
                    "numSubgroup": 0,
                    "auditories": ["303-1"],
                    "startLessonTime": "10:00",
                    "endLessonTime": "11:20",
                    "subject": "Физика",
                    "subjectFullName": "Физика",
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
    assert result.status == "ok"
    return service


def test_each_occurrence_carries_its_own_week(tmp_path: Path) -> None:
    service = build_service_with_two_fridays(tmp_path)

    lessons = [lesson for lesson in service.list_lessons() if lesson.subject == "Физика"]

    # Ровно два появления — по одному на каждую подходящую пятницу
    assert len(lessons) == 2

    dates = sorted(lesson.next_date.date().isoformat() for lesson in lessons)
    assert dates == ["2026-10-02", "2026-10-16"]

    # Появление недели 1 имеет week=1, появления недели 3 — week=3
    weeks_by_date = {
        lesson.next_date.date().isoformat(): lesson.week for lesson in lessons
    }
    assert weeks_by_date == {"2026-10-02": 1, "2026-10-16": 3}

    # Шаблон недель у обоих появлений одинаков — это одно занятие цикла
    assert all(lesson.week_numbers == [1, 3] for lesson in lessons)


def test_week_filter_yields_single_physical_week(tmp_path: Path) -> None:
    service = build_service_with_two_fridays(tmp_path)
    lessons = service.list_lessons()

    # Фильтр «неделя 1» по собственной неделе появления — как в интерфейсе:
    # одна физическая неделя, клонов из других недель нет
    week_one = [lesson for lesson in lessons if lesson.week == 1]
    assert len(week_one) == 1
    assert week_one[0].next_date.date().isoformat() == "2026-10-02"

    week_three = [lesson for lesson in lessons if lesson.week == 3]
    assert len(week_three) == 1
    assert week_three[0].next_date.date().isoformat() == "2026-10-16"


def test_academic_week_of_occurrences_is_consistent() -> None:
    assert academic_week(date(2026, 10, 2), SEMESTER_START) == 1
    assert academic_week(date(2026, 10, 16), SEMESTER_START) == 3


def test_subgroup_lessons_parse_and_stay_separate(tmp_path: Path) -> None:
    """
    Пары по подгруппам: одно время — два разных предмета (1-я и 2-я
    подгруппы). Появления не должны склеиваться, а поле subgroup —
    отличать общую пару от подгрупповой.
    """
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    def lesson_payload(subject: str, num_subgroup: int) -> dict:
        return {
            "weekNumber": [1],
            "studentGroups": [],
            "numSubgroup": num_subgroup,
            "auditories": ["401-1"],
            "startLessonTime": "19:00",
            "endLessonTime": "20:25",
            "subject": subject,
            "subjectFullName": subject,
            "lessonTypeAbbrev": "ЛР",
            "announcement": False,
            "split": False,
            "employees": [],
        }

    payload = {
        "schedules": {
            "Вторник": [
                lesson_payload("ИГИСиТ", 1),
                lesson_payload("СтатОИВ", 2),
                lesson_payload("ЛОИС", 0),
            ]
        },
        "exams": [],
    }
    result = service.import_schedule(payload)
    assert result.status == "ok"

    lessons = [
        lesson
        for lesson in service.list_lessons()
        if (lesson.next_date or "") and lesson.day_of_week == "Вторник"
    ]
    by_subject = {lesson.subject: lesson for lesson in lessons}

    # Подгрупповые пары различаются
    assert by_subject["ИГИСиТ"].subgroup == 1
    assert by_subject["СтатОИВ"].subgroup == 2
    # Общая пара имеет subgroup == 0
    assert by_subject["ЛОИС"].subgroup == 0

    # У всех своя запись в кэше (не склеились в одну)
    assert len({lesson.id for lesson in lessons}) == 3
