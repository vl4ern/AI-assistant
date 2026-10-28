from datetime import date
from pathlib import Path

import io

import openpyxl
import pytest

from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

SEMESTER_START = date(2026, 9, 1)


def build_service(tmp_path: Path) -> IntegrationService:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    return IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        semester_start_date="2026-09-01",
    )


def make_xlsx(rows: list[list[str]], group: str | None = None) -> bytes:
    """Собирает простой XLSX: каждая строка — список ячеек."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    if group is not None:
        sheet.append([f"Группа {group}"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_import_file_parses_table_layout(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    content = make_xlsx(
        [
            ["Понедельник", "10:00-11:20", "ООП", "ЛК", "202-1", "Иванов И. И.", "1,3 нед."],
            ["Вторник", "13:30-14:55", "ЛОИС", "ПЗ", "101-3", "Петров П. П.", "2 нед."],
        ],
        group="123456",
    )

    result = service.import_schedule_file(content)

    assert result.status == "ok"
    assert result.provider == "123456"
    assert service.get_current_group() == "123456"

    lessons = service.list_lessons()
    subjects = {lesson.subject for lesson in lessons}
    assert subjects == {"ООП", "ЛОИС"}
    assert all(lesson.group_number == "123456" for lesson in lessons)

    by_subject = {lesson.subject: lesson for lesson in lessons}
    assert by_subject["ООП"].auditory == "202-1"
    assert by_subject["ООП"].lesson_type == "ЛК"
    assert by_subject["ООП"].teacher == "Иванов И. И."
    assert by_subject["ООП"].week_numbers == [1, 3]
    assert by_subject["ЛОИС"].week_numbers == [2]


def test_import_file_replaces_previous_group(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    first = make_xlsx(
        [["Понедельник", "10:00-11:20", "ООП", "ЛК"]],
        group="111111",
    )
    service.import_schedule_file(first)
    assert {lesson.subject for lesson in service.list_lessons()} == {"ООП"}
    assert service.get_current_group() == "111111"

    second = make_xlsx(
        [
            ["Среда", "09:00-10:20", "БД", "ЛР"],
            ["Четверг", "15:20-16:40", "КСИС", "ЛК"],
        ],
        group="222222",
    )
    result = service.import_schedule_file(second)

    assert result.provider == "222222"
    assert service.get_current_group() == "222222"

    lessons = service.list_lessons()
    # Расписание прошлой группы полностью заменено, ничего не смешалось
    assert {lesson.subject for lesson in lessons} == {"БД", "КСИС"}


def test_import_file_uses_group_hint_when_file_has_no_group(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    content = make_xlsx([["Пятница", "10:00-11:20", "Философия", "ЛК"]])

    result = service.import_schedule_file(content, group_hint="950505")

    assert result.provider == "950505"
    assert service.get_current_group() == "950505"
    assert all(lesson.group_number == "950505" for lesson in service.list_lessons())


def test_import_file_with_day_headers(tmp_path: Path) -> None:
    """День недели отдельной строкой-заголовком, занятия ниже."""
    service = build_service(tmp_path)
    content = make_xlsx(
        [
            ["Понедельник"],
            ["10:00-11:20", "МА", "ЛК", "ауд. 301-1"],
            ["11:40-13:00", "Физика", "ЛР", "ауд. 105-2"],
            ["Вторник"],
            ["09:00-10:20", "История", "ПЗ"],
        ],
    )

    result = service.import_schedule_file(content, group_hint="100503")

    assert result.status == "ok"
    days = {lesson.subject: lesson.day_of_week for lesson in service.list_lessons()}
    assert days["МА"] == "Понедельник"
    assert days["Физика"] == "Понедельник"
    assert days["История"] == "Вторник"


def test_import_file_rejects_unrecognized_content(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValueError):
        service.import_schedule_file(b"not an xlsx at all")

    empty = make_xlsx([["Просто текст без расписания"]])
    with pytest.raises(ValueError):
        service.import_schedule_file(empty)


def test_import_file_rejects_empty_file(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValueError):
        service.import_schedule_file(b"")


def test_lessons_without_weeks_shown_every_week(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    content = make_xlsx([["Суббота", "10:00-11:20", "Английский", "ПЗ"]], group="111111")

    service.import_schedule_file(content)

    lessons = service.list_lessons()
    assert len(lessons) > 0
    assert all(set(lesson.week_numbers) == {1, 2, 3, 4} for lesson in lessons)
