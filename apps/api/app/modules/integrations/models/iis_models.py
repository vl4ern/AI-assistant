import uuid
import hashlib
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from app.modules.integrations.models.task import Task, SourceType, TaskStatus


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

    def _generate_external_id(self) -> str:
        """Создаём уникальный идентификатор для сопоставления"""
        base = f"{self.subject}_{self.startLessonTime}_{self.dayOfWeek}_{self.weekNumber}_{self.numSubgroup}"
        # Добавим дату экзамена, если есть
        if self.dateLesson:
            base += f"_{self.dateLesson}"
        return hashlib.md5(base.encode()).hexdigest()

    def _format_employee(self) -> str:
        if not self.employees:
            return ""
        emp = self.employees[0]
        return f"{emp.lastName} {emp.firstName} {emp.middleName}".strip()

    def to_task(self, base_date: datetime, is_exam: bool = False) -> Task:
        """
        Преобразуем занятие в универсальную Task.
        base_date — дата, относительно которой вычисляется дата занятия.
        Для экзаменов используется dateLesson.
        """
        # Формируем описание
        desc_parts = []
        if self.subjectFullName:
            desc_parts.append(f"📘 {self.subjectFullName}")
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

        description = "\n".join(desc_parts)
        title = (
            self.subject
            or self.subjectFullName
            or self.lessonTypeAbbrev
            or "Без названия"
        )
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
            # Регулярное занятие: определяем ближайший день недели, попадающий в семестр
            # Упростим: берём сегодняшний день + смещение до нужного дня недели
            day_names = [
                "Понедельник",
                "Вторник",
                "Среда",
                "Четверг",
                "Пятница",
                "Суббота",
            ]
            if self.dayOfWeek in day_names:
                target_weekday = day_names.index(
                    self.dayOfWeek
                )  # 0 = Пн, ... 6 = Вс (нет)
                today = base_date.date()
                # Вычисляем разницу до ближайшего целевого дня (вперёд)
                days_until = (target_weekday - today.weekday()) % 7
                if days_until == 0:
                    # Сегодня — этот день, но если время уже прошло, берём следующую неделю
                    # Для простоты всегда берём следующий подходящий день, начиная с завтра
                    days_until = 7
                next_day = today + timedelta(days=days_until)
                # Время пары
                try:
                    time_part = datetime.strptime(self.startLessonTime, "%H:%M").time()
                    due_date = datetime.combine(next_day, time_part)
                except ValueError:
                    due_date = base_date
            else:
                due_date = base_date

        external_id = self._generate_external_id()

        return Task(
            id=str(
                uuid.uuid4()
            ),  # новый ID для каждой синхронизации (перезапишется по external_id)
            external_id=external_id,
            source_type=SourceType.IIS,
            title=title,
            description=description,
            due_date=due_date,
            labels=[self.lessonTypeAbbrev],
            # остальные поля оставим по умолчанию
        )
