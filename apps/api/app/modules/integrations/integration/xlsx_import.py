"""
Парсер XLSX-файлов с расписанием занятий.

Заменяет прежний импорт JSON: пользователь выгружает расписание группы
в Excel и загружает файл — парсер превращает его в payload того же
формата, что отдаёт портал iis.bsuir.by/api/v1/schedule, дальше
работает обычный конвейер импорта (учебные недели, кэш, база знаний).

Поддерживаются два макета листа:
  * табличный — строка = занятие, ячейки с днём/временем/предметом;
  * «список» — день недели указывается отдельной строкой-заголовком,
    ниже идут строки занятий этого дня.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

WEEKDAYS = {
    "пн": "Понедельник",
    "понедельник": "Понедельник",
    "вт": "Вторник",
    "вторник": "Вторник",
    "ср": "Среда",
    "среда": "Среда",
    "чт": "Четверг",
    "четверг": "Четверг",
    "пт": "Пятница",
    "пятница": "Пятница",
    "сб": "Суббота",
    "суббота": "Суббота",
    "вс": "Воскресенье",
    "воскресенье": "Воскресенье",
}

DAY_NAMES_SET = set(WEEKDAYS.values())

TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
GROUP_RE = re.compile(r"\b(\d{6,8}[а-яa-z]?)\b", re.IGNORECASE)
AUDITORY_RE = re.compile(r"\b\d{2,4}-\d{1,3}[а-яa-z]?\b")
TEACHER_RE = re.compile(r"^[А-ЯЁ][а-яё]+(\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?)?\s*$")

LESSON_TYPE_MAP = {
    "лк": "ЛК",
    "лекция": "ЛК",
    "пз": "ПЗ",
    "практика": "ПЗ",
    "практ": "ПЗ",
    "лр": "ЛР",
    "лаб": "ЛР",
    "лабораторная": "ЛР",
    "лабораторная работа": "ЛР",
}

ALL_WEEKS = [1, 2, 3, 4]


def _norm(cell: Any) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def _detect_weekday(cells: List[str]) -> Optional[str]:
    """Ищет день недели среди ячеек строки (полное имя или сокращение)."""
    for cell in cells:
        key = cell.lower().strip(" .,:;")
        if key in WEEKDAYS:
            return WEEKDAYS[key]
    return None


def _detect_group(cells: List[str]) -> str:
    """Ищет номер группы (6–8 цифр, возможно с буквой) в ячейках строки."""
    for cell in cells:
        low = cell.lower()
        # «группа», «группы», «группу» — проверяем по основе
        if "групп" in low or low.startswith("гр."):
            match = GROUP_RE.search(cell)
            if match:
                return match.group(1)
    for cell in cells:
        if re.fullmatch(r"\d{6,8}[а-яa-z]?", cell.lower()):
            return cell
    return ""


def _weeks_from_cell(cell: str) -> List[int]:
    """«1,3 нед.» или «1, 3» → [1, 3]."""
    digits = [int(d) for d in re.findall(r"\d+", cell)]
    return [d for d in digits if 1 <= d <= 4]


def _employee_from_name(name: str) -> Dict[str, Any]:
    """«Иванов И. И.» → запись сотрудника в формате портала."""
    parts = name.split()
    return {
        "firstName": parts[1] if len(parts) > 1 else "",
        "lastName": parts[0] if parts else "",
        "middleName": " ".join(parts[2:]) if len(parts) > 2 else "",
        "degree": "",
        "degreeAbbrev": "",
        "rank": None,
        "photoLink": "",
        "calendarId": "",
        "id": 0,
        "urlId": "",
        "email": None,
        "jobPositions": None,
    }


def _parse_lesson_row(
    cells: List[str],
    time_cell: str,
    day_of_week: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Собирает занятие из ячеек строки, где найдено время «HH:MM–HH:MM»."""
    match = TIME_RE.search(time_cell)
    if match is None:
        return None

    start_time = match.group(1)
    end_time = match.group(2)
    if len(start_time) == 4:
        start_time = "0" + start_time
    if len(end_time) == 4:
        end_time = "0" + end_time

    weeks: List[int] = []
    auditory = ""
    lesson_type = ""
    subgroup = 0
    leftovers: List[str] = []

    for cell in cells:
        if cell == time_cell:
            continue
        low = cell.lower()

        # Ячейка дня недели — маркер, не часть занятия
        if low in WEEKDAYS:
            continue

        # Тип занятия: ЛК / ПЗ / ЛР
        if not lesson_type and low in LESSON_TYPE_MAP:
            lesson_type = LESSON_TYPE_MAP[low]
            continue

        # Подгруппа: «1 подгруппа», «2 подгр.»
        if "подгруп" in low:
            digits = re.findall(r"\d", cell)
            if digits and digits[0] in ("1", "2"):
                subgroup = int(digits[0])
            continue

        # Учебные недели: «1,3 нед.», «недели: 2», либо список «1,3,5»
        if "нед" in low or re.fullmatch(r"[\d,\s]+", cell):
            found = _weeks_from_cell(cell)
            if found:
                weeks = found
                continue
            # Не недели — цифры без значений 1–4, оставляем на остальные проверки

        # Аудитория: «ауд. 202-1», «202-1», «101»
        auditory_match = AUDITORY_RE.search(cell)
        if not auditory and ("ауд" in low or auditory_match or cell.isdigit()):
            auditory = auditory_match.group(0) if auditory_match else cell
            continue

        # Номер группы и прочие служебные ячейки пропускаем
        if "групп" in low or re.fullmatch(r"\d{6,8}[а-яa-z]?", low):
            continue

        leftovers.append(cell)

    subject = ""
    teacher = ""
    if leftovers:
        # Предмет — первая текстовая ячейка, преподаватель — ячейка
        # с фамилией («Иванов И. И.»)
        subject = leftovers[0]
        for cell in leftovers[1:]:
            if TEACHER_RE.match(cell):
                teacher = cell
                break

    if not subject:
        return None

    if not weeks:
        weeks = ALL_WEEKS

    return {
        "weekNumber": weeks,
        "studentGroups": [],
        "numSubgroup": subgroup,
        "auditories": [auditory] if auditory else [],
        "startLessonTime": start_time,
        "endLessonTime": end_time,
        "subject": subject,
        "subjectFullName": subject,
        "note": None,
        "lessonTypeAbbrev": lesson_type,
        "dateLesson": None,
        "startLessonDate": None,
        "endLessonDate": None,
        "announcement": False,
        "split": False,
        "employees": [_employee_from_name(teacher)] if teacher else [],
        "dayOfWeek": day_of_week,
    }


def parse_schedule_xlsx(content: bytes, group_hint: str = "") -> Tuple[Dict[str, Any], str]:
    """
    Разбирает XLSX-файл в payload формата iis.bsuir.by и номер группы.

    Возвращает (payload, group). Бросает ValueError, если файл не открыт
    или в нём не найдено ни одного занятия.
    """
    try:
        import openpyxl
    except ImportError as e:
        raise ValueError("Библиотека openpyxl не установлена") from e

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Не удалось открыть XLSX-файл: {e}") from e

    group = group_hint.strip()
    current_day: Optional[str] = None
    schedules: Dict[str, List[Dict[str, Any]]] = {}
    exams: List[Dict[str, Any]] = []

    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                cells = [_norm(cell) for cell in row]
                non_empty = [cell for cell in cells if cell]
                if not non_empty:
                    continue

                if not group:
                    group = _detect_group(non_empty)

                day = _detect_weekday(non_empty)
                if day is not None:
                    current_day = day

                time_cell = next((c for c in non_empty if TIME_RE.search(c)), None)
                if time_cell is None:
                    continue

                lesson = _parse_lesson_row(non_empty, time_cell, current_day)
                if lesson is None:
                    continue

                date_match = DATE_RE.search(" ".join(non_empty))
                if date_match is not None:
                    lesson["dateLesson"] = date_match.group(0)
                    lesson["dayOfWeek"] = None
                    exams.append(lesson)
                    continue

                day_name = lesson["dayOfWeek"]
                if day_name is None:
                    continue
                schedules.setdefault(day_name, []).append(lesson)
    finally:
        workbook.close()

    if not schedules and not exams:
        raise ValueError(
            "Не удалось распознать расписание: в файле нет строк с занятиями "
            "(нужны день недели и время вида «10:00–11:20»)"
        )

    payload: Dict[str, Any] = {"schedules": schedules, "exams": exams}
    if group:
        payload["studentGroup"] = {"name": group}
    return payload, group
