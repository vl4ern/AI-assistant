import uuid
import hashlib
import json
from datetime import date, datetime, time, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from app.modules.integrations.models.task import Task, SourceType, TaskStatus

WEEK_CYCLE = 4


def academic_week(day: date, semester_start: date) -> int:
    """
    Учебная неделя БГУИР (1–4) для указанной даты.

    Недели отсчитываются от даты начала семестра и циклятся по 4:
    первая неделя семестра — учебная неделя 1, пятая — снова 1 и т.д.
    """
    delta_days = (day - semester_start).days
    if delta_days < 0:
        return 1
    return (delta_days // 7) % WEEK_CYCLE + 1


@dataclass
class IisEmployee:
    firstName: str
    lastName: str
    middleName: str
    degree: str
    degreeAbbrev: str
    rank: Optional[str]
    photoLink: str
    calendarId: str
    id: int
    urlId: str
    email: Optional[str]
    jobPositions: Optional[List] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict) -> "IisEmployee":
        return IisEmployee(
            firstName=data.get("firstName", ""),
            lastName=data.get("lastName", ""),
            middleName=data.get("middleName", ""),
            degree=data.get("degree", ""),
            degreeAbbrev=data.get("degreeAbbrev", ""),
            rank=data.get("rank"),
            photoLink=data.get("photoLink", ""),
            calendarId=data.get("calendarId", ""),
            id=data.get("id", 0),
            urlId=data.get("urlId", ""),
            email=data.get("email"),
            jobPositions=data.get("jobPositions"),
        )


@dataclass
class IisStudentGroup:
    specialityName: str
    specialityCode: str
    numberOfStudents: int
    name: str
    educationDegree: int

    @staticmethod
    def from_dict(data: dict) -> "IisStudentGroup":
        return IisStudentGroup(
            specialityName=data.get("specialityName", ""),
            specialityCode=data.get("specialityCode", ""),
            numberOfStudents=data.get("numberOfStudents", 0),
            name=data.get("name", ""),
            educationDegree=data.get("educationDegree", 0),
        )


@dataclass
class IisScheduleItem:
    """Одно занятие (расписание или экзамен)"""

    # Поля из JSON
    weekNumber: List[int]
    studentGroups: List[IisStudentGroup]
    numSubgroup: int
    auditories: List[str]
    startLessonTime: str
    endLessonTime: str
    subject: str
    subjectFullName: str
    note: Optional[str]
    lessonTypeAbbrev: str
    dateLesson: Optional[str]  # только для экзаменов
    startLessonDate: Optional[str]  # для регулярных занятий
    endLessonDate: Optional[str]
    announcement: bool
    split: bool
    employees: List[IisEmployee] = field(default_factory=list)

    # Дополнительно: день недели (для расписания)
    dayOfWeek: Optional[str] = None

    @staticmethod
    def from_dict(data: dict, day_of_week: Optional[str] = None) -> "IisScheduleItem":
        """Фабрика из JSON-объекта, day_of_week — только для регулярных занятий"""
        employees = [IisEmployee.from_dict(e) for e in data.get("employees", [])]
        student_groups = [
            IisStudentGroup.from_dict(g) for g in data.get("studentGroups", [])
        ]
        return IisScheduleItem(
            weekNumber=data.get("weekNumber", []),
            studentGroups=student_groups,
            numSubgroup=data.get("numSubgroup", 0),
            auditories=data.get("auditories", []),
            startLessonTime=data.get("startLessonTime", ""),
            endLessonTime=data.get("endLessonTime", ""),
            subject=data.get("subject", ""),
            subjectFullName=data.get("subjectFullName", ""),
            note=data.get("note"),
            lessonTypeAbbrev=data.get("lessonTypeAbbrev", ""),
            dateLesson=data.get("dateLesson"),
            startLessonDate=data.get("startLessonDate"),
            endLessonDate=data.get("endLessonDate"),
            announcement=data.get("announcement", False),
            split=data.get("split", False),
            employees=employees,
            dayOfWeek=day_of_week,
        )

    def _generate_external_id(self, occurrence_date: Optional[date] = None) -> str:
        """Создаём уникальный идентификатор для сопоставления (по дате появления)."""
        base = f"{self.subject}_{self.startLessonTime}_{self.dayOfWeek}_{self.weekNumber}_{self.numSubgroup}"
        # Добавим дату экзамена, если есть
        if self.dateLesson:
            base += f"_{self.dateLesson}"
        # И дату появления, чтобы занятия разных учебных недель не склеивались
        if occurrence_date is not None:
            base += f"_{occurrence_date.strftime('%d.%m.%Y')}"
        return hashlib.md5(base.encode()).hexdigest()

    def _format_employee(self) -> str:
        if not self.employees:
            return ""
        emp = self.employees[0]
        return f"{emp.lastName} {emp.firstName} {emp.middleName}".strip()

    def to_task(self, base_date: datetime, is_exam: bool = False) -> Task:
        """
        Преобразуем занятие в универсальную Task (одиночное появление).

        Используется для экзаменов и как запасной вариант, когда учебные
        недели неизвестны. Для регулярных занятий по неделям см. to_tasks.
        """
        description = self._build_description()
        title = self._title()

        # Вычисляем due_date
        if is_exam and self.dateLesson:
            # Экзамен — конкретная дата + время
            try:
                date_part = datetime.strptime(self.dateLesson, "%d.%m.%Y").date()
                time_part = datetime.strptime(self.startLessonTime, "%H:%M").time()
                due_date = datetime.combine(date_part, time_part)
            except ValueError:
                due_date = base_date  # фолбэк
        else:
            # Ближайший следующий подходящий день недели
            due_date = self._next_occurrence(base_date)

        return self._build_task(
            due_date=due_date,
            description=description,
            title=title,
            external_id=self._generate_external_id(),
        )

    def to_tasks(
        self,
        base_date: datetime,
        *,
        semester_start: Optional[date] = None,
        horizon_days: int = 28,
    ) -> List[Task]:
        """
        Все появления занятия в пределах горизонта с учётом учебных недель.

        В БГУИР расписание циклично: неделя 1 — один набор занятий, неделя 2 —
        другой, всего 4 варианта. Для каждого дня в горизонте проверяем,
        попадает ли его учебная неделя в weekNumber занятия, и если да —
        создаём появление с датой. Так планировщик видит реальные даты
        занятий, а не «ближайший вторник».

        Без semester_start или без дня недели — одиночное появление.
        """
        description = self._build_description()
        title = self._title()

        day_names = [
            "Понедельник",
            "Вторник",
            "Среда",
            "Четверг",
            "Пятница",
            "Суббота",
        ]
        if semester_start is None or self.dayOfWeek not in day_names:
            return [
                self._build_task(
                    due_date=self._next_occurrence(base_date),
                    description=description,
                    title=title,
                    external_id=self._generate_external_id(),
                )
            ]

        target_weekday = day_names.index(self.dayOfWeek)
        start_time = self._parse_time(self.startLessonTime)
        tasks: List[Task] = []

        for offset in range(0, horizon_days + 1):
            candidate = base_date + timedelta(days=offset)

            if candidate.weekday() != target_weekday:
                continue
            # Сегодняшнее занятие, время которого уже прошло, пропускаем.
            if candidate.date() == base_date.date():
                if start_time is None or start_time <= base_date.time():
                    continue

            academic = academic_week(candidate.date(), semester_start)
            if academic not in self.weekNumber:
                continue

            due_date = (
                datetime.combine(candidate.date(), start_time)
                if start_time is not None
                else candidate
            )
            tasks.append(
                self._build_task(
                    due_date=due_date,
                    description=description,
                    title=title,
                    external_id=self._generate_external_id(candidate.date()),
                )
            )

        # Занятие с пустым weekNumber или без попаданий — хотя бы одно появление.
        if not tasks:
            tasks.append(
                self._build_task(
                    due_date=self._next_occurrence(base_date),
                    description=description,
                    title=title,
                    external_id=self._generate_external_id(),
                )
            )
        return tasks

    def _build_description(self) -> str:
        desc_parts = []
        if self.subjectFullName:
            desc_parts.append(f"📘 {self.subjectFullName}")
        if self.dayOfWeek:
            desc_parts.append(f"День недели: {self.dayOfWeek}")
        desc_parts.append(f"Тип: {self.lessonTypeAbbrev}")
        if self.auditories:
            desc_parts.append(f"Аудитория: {', '.join(self.auditories)}")
        teacher = self._format_employee()
        if teacher:
            desc_parts.append(f"Преподаватель: {teacher}")
        if self.note:
            desc_parts.append(f"Примечание: {self.note}")
        if self.weekNumber:
            desc_parts.append(f"Недели: {', '.join(map(str, self.weekNumber))}")
        if self.numSubgroup and self.numSubgroup > 0:
            desc_parts.append(f"Подгруппа: {self.numSubgroup}")
        return "\n".join(desc_parts)

    def _title(self) -> str:
        return (
            self.subject
            or self.subjectFullName
            or self.lessonTypeAbbrev
            or "Без названия"
        )

    def _duration_minutes(self) -> int:
        try:
            start_time = datetime.strptime(self.startLessonTime, "%H:%M")
            end_time = datetime.strptime(self.endLessonTime, "%H:%M")
            return max(30, int((end_time - start_time).total_seconds() / 60))
        except (ValueError, TypeError):
            return 90

    @staticmethod
    def _parse_time(value: Optional[str]) -> Optional[time]:
        try:
            return datetime.strptime(value, "%H:%M").time()
        except (ValueError, TypeError):
            return None

    def _next_occurrence(self, base_date: datetime) -> datetime:
        day_names = [
            "Понедельник",
            "Вторник",
            "Среда",
            "Четверг",
            "Пятница",
            "Суббота",
        ]
        start_time = self._parse_time(self.startLessonTime)

        if self.dayOfWeek in day_names:
            target_weekday = day_names.index(self.dayOfWeek)
            today = base_date.date()
            days_until = (target_weekday - today.weekday()) % 7
            if days_until == 0:
                days_until = 7
            next_day = today + timedelta(days=days_until)
            if start_time is not None:
                return datetime.combine(next_day, start_time)
            return base_date + timedelta(days=days_until)

        if self.dayOfWeek in day_names or (self.dateLesson and start_time):
            try:
                date_part = datetime.strptime(self.dateLesson, "%d.%m.%Y").date()
                return datetime.combine(date_part, start_time)
            except ValueError:
                pass
        return base_date

    def _build_task(
        self,
        due_date: datetime,
        description: str,
        title: str,
        external_id: str,
    ) -> Task:
        return Task(
            id=str(
                uuid.uuid4()
            ),  # новый ID для каждой синхронизации (перезапишется по external_id)
            external_id=external_id,
            source_type=SourceType.IIS,
            title=title,
            description=description,
            due_date=due_date,
            duration_minutes=self._duration_minutes(),
            labels=[self.lessonTypeAbbrev],
            version=2,
            # остальные поля оставим по умолчанию
        )
