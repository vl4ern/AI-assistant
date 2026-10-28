import uuid
import hashlib
from datetime import datetime, time, timedelta, timezone
from dataclasses import dataclass, field
from typing import List, Optional

from models.task import Task, SourceType, TaskStatus, utc_now


WEEKDAY_NAMES = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]


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
    dateLesson: Optional[str]
    startLessonDate: Optional[str]
    endLessonDate: Optional[str]
    announcement: bool
    split: bool
    employees: List[IisEmployee] = field(default_factory=list)
    dayOfWeek: Optional[str] = None

    @staticmethod
    def from_dict(data: dict, day_of_week: Optional[str] = None) -> "IisScheduleItem":
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

    # --- вспомогательные ---

    def _parse_time(self, raw: str) -> Optional[time]:
        try:
            return datetime.strptime(raw, "%H:%M").time()
        except (ValueError, TypeError):
            return None

    def _duration_minutes(self) -> int:
        start = self._parse_time(self.startLessonTime)
        end = self._parse_time(self.endLessonTime)
        if not start or not end:
            return 90
        delta = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        return max(delta, 0) or 90

    def _format_employee(self) -> str:
        """Форматирует ФИО преподавателя."""
        if not self.employees:
            return ""
        emp = self.employees[0]
        return f"{emp.lastName} {emp.firstName} {emp.middleName}".strip()

    def _generate_external_id(self, group_number: str = "") -> str:
        base = (
            f"g{group_number}_{self.subject}_{self.startLessonTime}_{self.dayOfWeek}_"
            f"{sorted(self.weekNumber)}_{self.numSubgroup}_"
            f"{','.join(sorted(self.auditories))}"
        )
        if self.dateLesson:
            base += f"_{self.dateLesson}"
        if self.employees:
            base += f"_{self.employees[0].id}"
        return hashlib.md5(base.encode()).hexdigest()

    def to_task(
        self,
        base_date: datetime,
        position_in_cycle: int,
        group_number: str,
        week_cycle: int = 4,
        is_exam: bool = False,
    ) -> Optional[Task]:
        """
        position_in_cycle — позиция текущей недели в цикле (1..week_cycle),
                            полученная от API БГУИР.
        week_cycle        — длина цикла (по умолчанию 4).
        """
        # --- описание ---
        desc_parts = []
        if self.subjectFullName:
            desc_parts.append(self.subjectFullName)
        if self.lessonTypeAbbrev:
            desc_parts.append(f"Тип: {self.lessonTypeAbbrev}")
        if self.auditories:
            desc_parts.append(f"Аудитория: {', '.join(self.auditories)}")
        teacher = self._format_employee()
        if teacher:
            desc_parts.append(f"Преподаватель: {teacher}")
        if self.note:
            desc_parts.append(f"Примечание: {self.note}")
        if self.numSubgroup and self.numSubgroup > 0:
            desc_parts.append(f"Подгруппа: {self.numSubgroup}")
        description = "\n".join(desc_parts)

        title = (
            self.subject
            or self.subjectFullName
            or self.lessonTypeAbbrev
            or "Без названия"
        )

        # --- due_date ---
        if is_exam:
            if not self.dateLesson:
                return None
            try:
                date_part = datetime.strptime(self.dateLesson, "%d.%m.%Y").date()
            except ValueError:
                return None
            time_part = self._parse_time(self.startLessonTime) or time(0, 0)
            due_date = datetime.combine(date_part, time_part, tzinfo=timezone.utc)
        else:
            if self.dayOfWeek not in WEEKDAY_NAMES:
                return None

            cycle = max(week_cycle, 1)
            day_index = WEEKDAY_NAMES.index(self.dayOfWeek)
            today = base_date.date()

            if not self.weekNumber:
                # Пара идёт каждую неделю — берём ближайший будущий день недели.
                days_until = (day_index - today.weekday()) % 7
                if days_until == 0:
                    t = self._parse_time(self.startLessonTime) or time(0, 0)
                    if t <= base_date.time():
                        days_until = 7
                target_date = today + timedelta(days=days_until)
            else:
                # Позиции в цикле, отфильтрованные по допустимому диапазону.
                weeks = sorted(w for w in self.weekNumber if 1 <= w <= cycle)
                if not weeks:
                    return None

                future = [w for w in weeks if w >= position_in_cycle]
                if future:
                    target_position = future[0]
                    weeks_ahead = target_position - position_in_cycle
                else:
                    # Все позиции текущего цикла прошли — берём первую следующего.
                    target_position = weeks[0]
                    weeks_ahead = (cycle - position_in_cycle) + target_position

                target_date = today + timedelta(weeks=weeks_ahead)
                # Выравниваем на нужный день недели в той же неделе.
                target_date = (
                    target_date
                    - timedelta(days=target_date.weekday())
                    + timedelta(days=day_index)
                )

                # Если попали на сегодня, но время пары уже прошло — на цикл вперёд.
                if target_date == today:
                    t = self._parse_time(self.startLessonTime) or time(0, 0)
                    if t <= base_date.time():
                        target_date += timedelta(weeks=cycle)

            time_part = self._parse_time(self.startLessonTime) or time(0, 0)
            due_date = datetime.combine(target_date, time_part, tzinfo=timezone.utc)

        external_id = self._generate_external_id(group_number)

        return Task(
            id=f"iis_{external_id}",
            external_id=external_id,
            source_type=SourceType.IIS,
            title=title,
            description=description,
            due_date=due_date,
            duration_minutes=self._duration_minutes(),
            labels=[self.lessonTypeAbbrev] if self.lessonTypeAbbrev else [],
            last_modified=utc_now(),
            version=1,
        )
