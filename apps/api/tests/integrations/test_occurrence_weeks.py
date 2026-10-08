from datetime import date, datetime
from pathlib import Path

from app.modules.integrations.models.iis_models import IisScheduleItem, academic_week
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

SEMESTER_START = date(2026, 9, 1)


def make_lesson(weeks: list[int]) -> IisScheduleItem:
    """Занятие «Физика» по пятницам в 10:00 на указанных учебных неделях."""
    return IisScheduleItem.from_dict(
        {
            "weekNumber": weeks,
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
        },
        day_of_week="Пятница",
    )


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


def test_each_occurrence_carries_its_own_week() -> None:
    item = make_lesson([1, 3])
    # Фиксированная дата генерации — тест не зависит от дня запуска
    base = datetime(2026, 10, 8, 8, 0)

    tasks = item.to_tasks(base, semester_start=SEMESTER_START, horizon_days=28)

    # Пятницы в окне: 16.10 (нед. 3) и 30.10 (нед. 1) → два появления
    assert sorted(t.due_date.date().isoformat() for t in tasks) == [
        "2026-10-16",
        "2026-10-30",
    ]

    # У каждого появления — своя учебная неделя по его дате
    for task in tasks:
        expected_week = academic_week(task.due_date.date(), SEMESTER_START)
        assert expected_week in (1, 3)

    # Шаблон недель у обоих появлений одинаков — это одно занятие цикла
    assert all("Недели: 1, 3" in t.description for t in tasks)

    # У появлений разные идентификаторы — недели не склеиваются
    assert len({t.external_id for t in tasks}) == 2


def test_week_filter_yields_single_physical_week() -> None:
    item = make_lesson([1, 3])
    base = datetime(2026, 10, 8, 8, 0)

    tasks = item.to_tasks(base, semester_start=SEMESTER_START, horizon_days=28)

    by_week: dict[int, list] = {}
    for task in tasks:
        by_week.setdefault(academic_week(task.due_date.date(), SEMESTER_START), []).append(task)

    # В каждой учебной неделе — ровно одно появление, без клонов
    assert len(by_week.get(1, [])) == 1
    assert len(by_week.get(3, [])) == 1
    assert 2 not in by_week and 4 not in by_week


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


def test_sync_purges_past_occurrences(tmp_path: Path) -> None:
    """Прошедшие появления удаляются из кэша при синхронизации."""
    from datetime import datetime, timedelta

    from app.modules.integrations.integration.interfaces import IServiceAdapter
    from app.modules.integrations.models.task import SourceType, Task
    from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
    from app.modules.knowledge.service import KnowledgeService

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    now = datetime.now()
    past = Task(
        id="old-1",
        external_id="old-lesson",
        source_type=SourceType.IIS,
        title="Старая пара",
        due_date=now - timedelta(days=10),
        duration_minutes=90,
    )
    future = Task(
        id="new-1",
        external_id="new-lesson",
        source_type=SourceType.IIS,
        title="Новая пара",
        due_date=now + timedelta(days=3),
        duration_minutes=90,
    )

    class MixedAdapter(IServiceAdapter):
        def authenticate(self, token=None):
            return True

        def fetch_changes(self, since=None):
            return [past, future]

        def push_update(self, task):
            return True

        def delete_task(self, external_id):
            return True

    service._scheduler.register_adapter("Fake", MixedAdapter(), sync_interval=3600)
    service.sync_all()

    lessons = service.list_lessons()
    titles = {lesson.subject for lesson in lessons}
    assert "Старая пара" not in titles
    assert "Новая пара" in titles


def test_list_lessons_skips_past_even_without_sync(tmp_path: Path) -> None:
    """Чтение расписания не показывает прошедшие появления,
    даже если синхронизация давно не запускалась."""
    from datetime import datetime, timedelta

    from app.modules.integrations.models.task import SourceType, Task
    from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
    from app.modules.knowledge.service import KnowledgeService

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    now = datetime.now()
    stale = Task(
        id="stale-1",
        external_id="stale-lesson",
        source_type=SourceType.IIS,
        title="Прошедшая пара",
        due_date=now - timedelta(days=3),
        duration_minutes=90,
    )
    service._scheduler.cache.save_task(stale)

    lessons = service.list_lessons()
    assert all(lesson.subject != "Прошедшая пара" for lesson in lessons)


def test_source_edit_does_not_create_visible_duplicate(tmp_path: Path) -> None:
    """
    Портал иногда правит записи (список недель), от чего меняется
    external_id и в кэше зависает дубль с той же датой и временем.
    Отображение обязано сворачивать такие записи в одну.
    """
    from datetime import datetime, timedelta

    from app.modules.integrations.models.task import SourceType, Task

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    due = datetime.now() + timedelta(days=5)
    base = dict(
        source_type=SourceType.IIS,
        title="Консультация по курсовому проекту",
        due_date=due,
        duration_minutes=90,
        description="Тип: \nАудитория: 609-5 к.\n",
    )

    # Та же пара до и после правки портала — разные external_id
    service._scheduler.cache.save_task(Task(id="a", external_id="old-id", **base))
    service._scheduler.cache.save_task(Task(id="b", external_id="new-id", **base))

    lessons = service.list_lessons()
    same_slot = [
        lesson
        for lesson in lessons
        if lesson.subject == "Консультация по курсовому проекту"
    ]
    assert len(same_slot) == 1


def test_announcement_title_comes_from_note() -> None:
    """Анонсы без предмета получают название из примечания, а не «Без названия»."""
    from app.modules.integrations.models.iis_models import IisScheduleItem

    item = IisScheduleItem.from_dict(
        {
            "weekNumber": [4],
            "studentGroups": [],
            "numSubgroup": 0,
            "auditories": ["609-5 к."],
            "startLessonTime": "17:00",
            "endLessonTime": "18:00",
            "subject": "",
            "subjectFullName": "",
            "note": "Консультация по курсовому проекту 2.10",
            "lessonTypeAbbrev": None,
            "dateLesson": None,
            "startLessonDate": None,
            "endLessonDate": None,
            "announcement": True,
            "split": False,
            "employees": [],
        },
        day_of_week="Вторник",
    )

    tasks = item.to_tasks(
        datetime(2026, 10, 8, 8, 0),
        semester_start=SEMESTER_START,
        horizon_days=28,
    )
    assert tasks, "анонс недели 4 должен попасть в окно"
    assert tasks[0].title == "Консультация по курсовому проекту 2.10"


def test_sync_reconciles_orphaned_future_occurrences(tmp_path: Path) -> None:
    """
    Появления, которых больше нет в данных портала (запись поправили —
    сменился идентификатор), удаляются из кэша при следующей синхронизации.
    """
    from datetime import datetime, timedelta

    from app.modules.integrations.integration.interfaces import IServiceAdapter
    from app.modules.integrations.models.task import SourceType, Task

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )

    # «Сирота»: будущее появление, которое портал больше не отдаёт
    orphan = Task(
        id="orphan-1",
        external_id="portal-removed-this-id",
        source_type=SourceType.IIS,
        title="Устаревшая пара",
        due_date=datetime.now() + timedelta(days=2),
        duration_minutes=90,
    )
    service._scheduler.cache.save_task(orphan)

    alive = Task(
        id="alive-1",
        external_id="portal-keeps-this-id",
        source_type=SourceType.IIS,
        title="Живая пара",
        due_date=datetime.now() + timedelta(days=3),
        duration_minutes=90,
    )

    class FreshAdapter(IServiceAdapter):
        def authenticate(self, token=None):
            return True

        def fetch_changes(self, since=None):
            return [alive]

        def push_update(self, task):
            return True

        def delete_task(self, external_id):
            return True

    service._scheduler.register_adapter("IIS", FreshAdapter(), sync_interval=3600)
    service.sync_adapter("IIS")

    titles = {lesson.subject for lesson in service.list_lessons()}
    assert "Устаревшая пара" not in titles
    assert "Живая пара" in titles
