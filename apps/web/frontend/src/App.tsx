import { useEffect, useMemo, useState, type ChangeEvent } from 'react';

import { createTask as createTaskApi, getTasks, updateTaskStatus } from './api/tasks';
import type { ApiTask, ApiTaskCreate } from './types/api';

type Page = 'dashboard' | 'tasks' | 'calendar' | 'projects' | 'analytics' | 'settings';
type TaskPriority = 'High' | 'Medium' | 'Low';
type ImportMode = 'smart' | 'classes' | 'exams';

type Task = {
  id: string;
  title: string;
  course: string;
  deadline: string;
  priority: TaskPriority;
  customTag: string;
  completed: boolean;
};

type ScheduleItemType = 'lecture' | 'lab' | 'practice' | 'exam';

type ScheduleItem = {
  time: string;
  title: string;
  room: string;
  teacher?: string;
  type: ScheduleItemType;
};

type DayDetails = {
  date: Date;
  items: ScheduleItem[];
  cycleWeek: number | null;
  inSemester: boolean;
};

const navItems: Array<{ id: Page; label: string }> = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'projects', label: 'Projects' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'settings', label: 'Settings' },
];

const initialTasks: Task[] = [
  {
    id: 'demo-1',
    title: 'Finish database report',
    course: 'Databases',
    deadline: 'Today, 18:00',
    priority: 'High',
    customTag: 'Report',
    completed: false,
  },
  {
    id: 'demo-2',
    title: 'Read AI lecture notes',
    course: 'Artificial Intelligence',
    deadline: 'Tomorrow, 11:00',
    priority: 'Medium',
    customTag: 'Lecture',
    completed: false,
  },
  {
    id: 'demo-3',
    title: 'Prepare web project structure',
    course: 'Web Development',
    deadline: 'Friday, 14:00',
    priority: 'High',
    customTag: 'Project',
    completed: true,
  },
  {
    id: 'demo-4',
    title: 'Review math homework',
    course: 'Discrete Math',
    deadline: 'Saturday, 09:00',
    priority: 'Low',
    customTag: 'Homework',
    completed: false,
  },
];

const semesterStartDate = new Date(2026, 1, 9);
const semesterEndDate = new Date(2026, 5, 30);

const semesterMonths = [
  { year: 2026, month: 1, label: 'February 2026' },
  { year: 2026, month: 2, label: 'March 2026' },
  { year: 2026, month: 3, label: 'April 2026' },
  { year: 2026, month: 4, label: 'May 2026' },
  { year: 2026, month: 5, label: 'June 2026' },
];

const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const schedulePattern: Record<number, Record<number, ScheduleItem[]>> = {
  1: {
    1: [
      { time: '08:30', title: 'ППОИС (ЛК)', room: '214-4', teacher: 'Садовский М. Е.', type: 'lecture' },
      { time: '10:05', title: 'ВОВСНВМВ (ЛК)', room: '214-4', teacher: 'Николаева Л. В.', type: 'lecture' },
      { time: '12:00', title: 'ФизК (ПЗ)', room: '—', type: 'practice' },
      { time: '13:35', title: 'Инф. час (ПЗ)', room: '612а-5', teacher: 'Пакутник Д. В.', type: 'practice' },
    ],
    2: [
      { time: '12:00', title: 'СПЭ (ЛК)', room: '218-4', teacher: 'Макеева Е. Н.', type: 'lecture' },
      { time: '13:35', title: 'Философия (ЛК)', room: '218-4', teacher: 'Бархатков А. И.', type: 'lecture' },
      { time: '15:30', title: 'МППиУ (ПЗ)', room: '420-4', teacher: 'Слюсарь Т. Л.', type: 'practice' },
      { time: '17:05', title: 'ЛОИС (ЛР)', room: '607-5', teacher: 'Ивашенко В. П.', type: 'lab' },
    ],
    3: [
      { time: '12:00', title: 'ИГИСиТ / МаОсИС (ЛР)', room: '607-5 / 612-5', type: 'lab' },
      { time: '15:30', title: 'ОУИС (ЛК)', room: '209-3', teacher: 'Смирнова Н. А.', type: 'lecture' },
    ],
    4: [
      { time: '08:30', title: 'ИГИСиТ (ЛК)', room: '214-4', teacher: 'Самодумкин С. А.', type: 'lecture' },
      { time: '10:05', title: 'МаОсИС (ЛК)', room: '214-4', teacher: 'Шункевич Д. В.', type: 'lecture' },
      { time: '12:00', title: 'ВОВСНВМВ (ПЗ)', room: '427-4', teacher: 'Галицкая Е. М.', type: 'practice' },
      { time: '13:35', title: 'ЛОИС (ЛР)', room: '607-5', teacher: 'Ивашенко В. П.', type: 'lab' },
    ],
    5: [
      { time: '12:00', title: 'ЛОИС (ЛК)', room: '218-4', teacher: 'Ивашенко В. П.', type: 'lecture' },
      { time: '13:35', title: 'АОИС (ЛК)', room: '218-4', teacher: 'Захаров В. В.', type: 'lecture' },
      { time: '15:30', title: 'ППОИС (ЛР)', room: '612-5', teacher: 'Гуменный Н. А.', type: 'lab' },
      { time: '17:05', title: 'СПЭ (ПЗ)', room: '419-4', teacher: 'Пшонко Е. С.', type: 'practice' },
    ],
    6: [
      { time: '08:30', title: 'АОИС (ЛР)', room: '607-5', teacher: 'Жук А. А.', type: 'lab' },
      { time: '12:00', title: 'АОИС (ЛР)', room: '607-5', teacher: 'Жук А. А.', type: 'lab' },
    ],
  },
  2: {
    1: [
      { time: '08:30', title: 'ППОИС (ЛК)', room: '214-4', teacher: 'Садовский М. Е.', type: 'lecture' },
      { time: '10:05', title: 'МППиУ (ЛК)', room: '214-4', teacher: 'Шкор О. Н.', type: 'lecture' },
      { time: '12:00', title: 'ФизК (ПЗ)', room: '—', type: 'practice' },
    ],
    2: [
      { time: '08:30', title: 'МаОсИС / ППОИС (ЛР)', room: '612а-5 / 607-5', type: 'lab' },
      { time: '10:05', title: 'ППОИС / МаОсИС (ЛР)', room: '607-5 / 612а-5', type: 'lab' },
      { time: '13:35', title: 'Философия (ЛК)', room: '218-4', teacher: 'Бархатков А. И.', type: 'lecture' },
      { time: '15:30', title: 'К.Ч. (ПЗ)', room: '612-5', teacher: 'Пакутник Д. В.', type: 'practice' },
    ],
    3: [{ time: '13:35', title: 'ИГИСиТ (ЛР)', room: '607-5', teacher: 'Самодумкин С. А.', type: 'lab' }],
    4: [
      { time: '08:30', title: 'ИГИСиТ (ЛК)', room: '214-4', teacher: 'Самодумкин С. А.', type: 'lecture' },
      { time: '10:05', title: 'МаОсИС (ЛК)', room: '214-4', teacher: 'Шункевич Д. В.', type: 'lecture' },
      { time: '12:00', title: 'МаОсИС (ЛР)', room: '612а-5', teacher: 'Зотов Н. В.', type: 'lab' },
      { time: '13:35', title: 'ЛОИС (ЛР)', room: '607-5', teacher: 'Ивашенко В. П.', type: 'lab' },
    ],
    5: [
      { time: '10:05', title: 'Философия (ПЗ)', room: '414-4', teacher: 'Шкундич А. О.', type: 'practice' },
      { time: '12:00', title: 'ЛОИС (ЛК)', room: '218-4', teacher: 'Ивашенко В. П.', type: 'lecture' },
      { time: '13:35', title: 'АОИС (ЛК)', room: '218-4', teacher: 'Захаров В. В.', type: 'lecture' },
      { time: '15:30', title: 'СПЭ (ПЗ)', room: '417-4', teacher: 'Пшонко Е. С.', type: 'practice' },
    ],
    6: [],
  },
  3: {
    1: [
      { time: '09:55', title: 'ППОИС (ЛК)', room: '214-4', teacher: 'Садовский М. Е.', type: 'lecture' },
      { time: '11:30', title: 'ВОВСНВМВ (ЛК)', room: '214-4', teacher: 'Николаева Л. В.', type: 'lecture' },
      { time: '13:25', title: 'ФизК (ПЗ)', room: '—', type: 'practice' },
      { time: '15:00', title: 'Инф. час (ПЗ)', room: '612а-5', teacher: 'Пакутник Д. В.', type: 'practice' },
    ],
    2: [
      { time: '13:25', title: 'СПЭ (ЛК)', room: '218-4', teacher: 'Макеева Е. Н.', type: 'lecture' },
      { time: '15:00', title: 'Философия (ЛК)', room: '218-4', teacher: 'Бархатков А. И.', type: 'lecture' },
      { time: '16:55', title: 'МППиУ (ПЗ)', room: '420-4', teacher: 'Слюсарь Т. Л.', type: 'practice' },
    ],
    3: [
      { time: '13:25', title: 'МаОсИС / ИГИСиТ (ЛР)', room: '612-5 / 607-5', type: 'lab' },
      { time: '16:55', title: 'ОУИС (ЛК)', room: '209-3', teacher: 'Смирнова Н. А.', type: 'lecture' },
    ],
    4: [
      { time: '09:55', title: 'ИГИСиТ (ЛК)', room: '214-4', teacher: 'Самодумкин С. А.', type: 'lecture' },
      { time: '11:30', title: 'МаОсИС (ЛК)', room: '214-4', teacher: 'Шункевич Д. В.', type: 'lecture' },
      { time: '13:25', title: 'ВОВСНВМВ (ПЗ)', room: '427-4', teacher: 'Галицкая Е. М.', type: 'practice' },
    ],
    5: [
      { time: '12:00', title: 'ЛОИС (ЛК)', room: '218-4', teacher: 'Ивашенко В. П.', type: 'lecture' },
      { time: '13:25', title: 'АОИС (ЛК)', room: '218-4', teacher: 'Захаров В. В.', type: 'lecture' },
      { time: '16:55', title: 'ППОИС (ЛР)', room: '612-5', teacher: 'Гуменный Н. А.', type: 'lab' },
    ],
    6: [
      { time: '09:55', title: 'АОИС (ЛР)', room: '607-5', teacher: 'Жук А. А.', type: 'lab' },
      { time: '13:25', title: 'АОИС (ЛР)', room: '607-5', teacher: 'Жук А. А.', type: 'lab' },
    ],
  },
  4: {
    1: [
      { time: '09:55', title: 'ППОИС (ЛК)', room: '214-4', teacher: 'Садовский М. Е.', type: 'lecture' },
      { time: '11:30', title: 'МППиУ (ЛК)', room: '214-4', teacher: 'Шкор О. Н.', type: 'lecture' },
      { time: '15:00', title: 'Инф. час (ПЗ)', room: '612а-5', teacher: 'Пакутник Д. В.', type: 'practice' },
    ],
    2: [
      { time: '09:55', title: 'ППОИС / МаОсИС (ЛР)', room: '607-5 / 612а-5', type: 'lab' },
      { time: '11:30', title: 'ППОИС / МаОсИС (ЛР)', room: '607-5 / 612а-5', type: 'lab' },
      { time: '15:00', title: 'Философия (ЛК)', room: '218-4', teacher: 'Бархатков А. И.', type: 'lecture' },
      { time: '16:55', title: 'К.Ч. (ПЗ)', room: '612-5', teacher: 'Пакутник Д. В.', type: 'practice' },
    ],
    3: [
      { time: '15:00', title: 'ИГИСиТ (ЛР)', room: '607-5', teacher: 'Самодумкин С. А.', type: 'lab' },
      { time: '16:55', title: 'Философия (ПЗ)', room: '301-4', teacher: 'Шкундич А. О.', type: 'practice' },
    ],
    4: [
      { time: '09:55', title: 'ИГИСиТ (ЛК)', room: '214-4', teacher: 'Самодумкин С. А.', type: 'lecture' },
      { time: '11:30', title: 'МаОсИС (ЛК)', room: '214-4', teacher: 'Шункевич Д. В.', type: 'lecture' },
      { time: '15:00', title: 'МаОсИС (ЛР)', room: '612а-5', teacher: 'Зотов Н. В.', type: 'lab' },
    ],
    5: [
      { time: '10:05', title: 'Философия (ПЗ)', room: '414-4', teacher: 'Шкундич А. О.', type: 'practice' },
      { time: '13:25', title: 'ЛОИС (ЛК)', room: '218-4', teacher: 'Ивашенко В. П.', type: 'lecture' },
      { time: '15:00', title: 'АОИС (ЛК)', room: '218-4', teacher: 'Захаров В. В.', type: 'lecture' },
    ],
    6: [],
  },
};

function toMidnight(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function getDayDifference(from: Date, to: Date): number {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.floor((toMidnight(to).getTime() - toMidnight(from).getTime()) / millisecondsPerDay);
}

function getMondayIndex(date: Date): number {
  const raw = date.getDay();
  return raw === 0 ? 7 : raw;
}

function isDateInSemester(date: Date): boolean {
  const current = toMidnight(date).getTime();
  return current >= toMidnight(semesterStartDate).getTime() && current <= toMidnight(semesterEndDate).getTime();
}

function getCycleWeek(date: Date): number | null {
  if (!isDateInSemester(date)) return null;
  const diff = getDayDifference(semesterStartDate, date);
  const weekIndex = Math.floor(diff / 7);
  return (weekIndex % 4) + 1;
}

function getScheduleForDate(date: Date): ScheduleItem[] {
  const cycleWeek = getCycleWeek(date);
  const weekday = getMondayIndex(date);
  if (!cycleWeek || weekday === 7) return [];
  return schedulePattern[cycleWeek]?.[weekday] ?? [];
}

function getMonthGrid(year: number, month: number): Array<Date | null> {
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstWeekdayIndex = getMondayIndex(firstDay);

  const cells: Array<Date | null> = [];
  for (let i = 1; i < firstWeekdayIndex; i += 1) cells.push(null);
  for (let day = 1; day <= daysInMonth; day += 1) cells.push(new Date(year, month, day));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function getDaySummary(date: Date): { line1: string; line2: string } {
  const inSemester = isDateInSemester(date);
  const weekday = getMondayIndex(date);
  const items = getScheduleForDate(date);

  if (!inSemester) return { line1: 'Semester off', line2: 'No study cycle yet' };
  if (weekday === 7) return { line1: 'Weekend', line2: 'No classes' };
  if (items.length === 0) return { line1: 'No classes', line2: 'Free study day' };

  return {
    line1: `${items[0].time}–${items[items.length - 1].time}`,
    line2: `${items.length} class${items.length > 1 ? 'es' : ''} • study`,
  };
}


function mapApiPriorityToUiPriority(priority: number): TaskPriority {
  if (priority <= 1) {
    return 'High';
  }

  if (priority === 2) {
    return 'Medium';
  }

  return 'Low';
}

function mapUiPriorityToApiPriority(priority: TaskPriority): number {
  if (priority === 'High') {
    return 1;
  }

  if (priority === 'Medium') {
    return 2;
  }

  return 3;
}

function formatDeadline(deadline: string | null): string {
  if (!deadline) {
    return 'No deadline';
  }

  const date = new Date(deadline);

  if (Number.isNaN(date.getTime())) {
    return 'Invalid deadline';
  }

  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function buildDeadlineIso(day: string, time: string): string | null {
  if (!day || !time) {
    return null;
  }

  const date = new Date(`${day}T${time}:00`);

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toISOString();
}

function mapApiTaskToUiTask(task: ApiTask): Task {
  return {
    id: task.id,
    title: task.title,
    course: task.workspace_id || 'Study',
    deadline: formatDeadline(task.deadline),
    priority: mapApiPriorityToUiPriority(task.priority),
    customTag: task.project_id || 'Backend',
    completed: task.status === 'completed',
  };
}

function App() {
  const [activePage, setActivePage] = useState<Page>('dashboard');
  const [searchValue, setSearchValue] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isTasksLoading, setIsTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState('');
  const [currentMonthIndex, setCurrentMonthIndex] = useState(0);
  const [selectedDay, setSelectedDay] = useState<DayDetails | null>(null);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState('No schedule file selected');
  const [importMode, setImportMode] = useState<ImportMode>('smart');
  const [calendarSourceLabel, setCalendarSourceLabel] = useState('Semester template');

  // Task creation modal state
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskCourse, setNewTaskCourse] = useState('');
  const [newTaskDay, setNewTaskDay] = useState('');
  const [newTaskTime, setNewTaskTime] = useState('');
  const [newTaskPriority, setNewTaskPriority] = useState<TaskPriority>('Medium');
  const [newTaskTag, setNewTaskTag] = useState('');
  const [taskFormError, setTaskFormError] = useState('');

  const currentMonth = semesterMonths[currentMonthIndex];

  useEffect(() => {
    async function loadTasks(): Promise<void> {
      try {
        setIsTasksLoading(true);
        setTasksError('');

        const apiTasks = await getTasks();

        setTasks(apiTasks.map(mapApiTaskToUiTask));
      } catch {
        setTasksError('Failed to load tasks from backend. Check that API is running on http://localhost:8000.');
      } finally {
        setIsTasksLoading(false);
      }
    }

    loadTasks();
  }, []);


  const monthCells = useMemo(() => getMonthGrid(currentMonth.year, currentMonth.month), [currentMonth]);
  const activeTasksCount = useMemo(() => tasks.filter((task) => !task.completed).length, [tasks]);
  const completedTasksCount = useMemo(() => tasks.filter((task) => task.completed).length, [tasks]);
  const highPriorityCount = useMemo(
    () => tasks.filter((task) => task.priority === 'High' && !task.completed).length,
    [tasks]
  );

  const filteredTasks = useMemo(() => {
    const normalized = searchValue.trim().toLowerCase();
    if (!normalized) return tasks;
    return tasks.filter((task) => {
      return (
        task.title.toLowerCase().includes(normalized) ||
        task.course.toLowerCase().includes(normalized) ||
        task.deadline.toLowerCase().includes(normalized) ||
        task.customTag.toLowerCase().includes(normalized)
      );
    });
  }, [tasks, searchValue]);

  async function toggleTask(taskId: string): Promise<void> {
    const currentTask = tasks.find((task) => task.id === taskId);

    if (!currentTask) {
      return;
    }

    const nextCompleted = !currentTask.completed;
    const nextStatus = nextCompleted ? 'completed' : 'todo';

    setTasks((prevTasks) =>
      prevTasks.map((task) =>
        task.id === taskId ? { ...task, completed: nextCompleted } : task
      )
    );

    try {
      setTasksError('');

      const updatedTask = await updateTaskStatus(taskId, nextStatus);

      setTasks((prevTasks) =>
        prevTasks.map((task) =>
          task.id === taskId ? mapApiTaskToUiTask(updatedTask) : task
        )
      );
    } catch {
      setTasksError('Failed to update task status on backend.');

      setTasks((prevTasks) =>
        prevTasks.map((task) =>
          task.id === taskId ? { ...task, completed: currentTask.completed } : task
        )
      );
    }
  }

  function openTaskModal(): void {
    setIsTaskModalOpen(true);
    setTaskFormError('');
  }

  function closeTaskModal(): void {
    setIsTaskModalOpen(false);
    setNewTaskTitle('');
    setNewTaskCourse('');
    setNewTaskDay('');
    setNewTaskTime('');
    setNewTaskPriority('Medium');
    setNewTaskTag('');
    setTaskFormError('');
  }

  async function createTask(): Promise<void> {
    const title = newTaskTitle.trim();
    const course = newTaskCourse.trim() || 'study';
    const day = newTaskDay.trim();
    const time = newTaskTime.trim();
    const tag = newTaskTag.trim() || null;

    if (!title) {
      setTaskFormError('Enter task title.');
      return;
    }

    if (!day || !time) {
      setTaskFormError('Enter day and time.');
      return;
    }

    const deadline = buildDeadlineIso(day, time);

    if (!deadline) {
      setTaskFormError('Enter a valid day and time.');
      return;
    }

    const payload: ApiTaskCreate = {
      title,
      description: null,
      estimated_minutes: 60,
      priority: mapUiPriorityToApiPriority(newTaskPriority),
      deadline,
      workspace_id: course,
      project_id: tag,
      auto_reschedule: true,
      depends_on: [],
      allow_split: false,
      min_chunk_minutes: null,
    };

    try {
      setTaskFormError('');
      setTasksError('');

      const createdTask = await createTaskApi(payload);

      setTasks((prevTasks) => [mapApiTaskToUiTask(createdTask), ...prevTasks]);
      setActivePage('tasks');
      closeTaskModal();
    } catch {
      setTaskFormError('Failed to create task on backend.');
    }
  }

  function openDayDetails(date: Date): void {
    setSelectedDay({
      date,
      items: getScheduleForDate(date),
      cycleWeek: getCycleWeek(date),
      inSemester: isDateInSemester(date),
    });
  }

  function closeDayDetails(): void {
    setSelectedDay(null);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedFileName('No schedule file selected');
      return;
    }
    setSelectedFileName(file.name);
  }

  function applyImportPreview(): void {
    const modeLabel =
      importMode === 'smart'
        ? 'Smart import'
        : importMode === 'classes'
        ? 'Classes only'
        : 'Exams only';

    setCalendarSourceLabel(`${modeLabel} • ${selectedFileName}`);
    setIsImportModalOpen(false);
    setActivePage('calendar');
  }

  return (
    <>
      <style>{`
        * { box-sizing: border-box; }
        :root {
          color-scheme: dark;
          --bg: #081120;
          --panel: rgba(20,31,58,0.9);
          --border: rgba(255,255,255,0.07);
          --text: #f8fafc;
          --muted: #94a3b8;
          --blue: #2563eb;
          --blue-hover: #1d4ed8;
          --shadow: 0 20px 60px rgba(0,0,0,0.25);
        }
        body {
          margin: 0;
          font-family: Inter, Arial, sans-serif;
          background:
            radial-gradient(circle at top right, rgba(37,99,235,0.12), transparent 18%),
            linear-gradient(180deg, #06101f 0%, #081120 100%);
          color: var(--text);
        }
        button, input, select { font: inherit; }
        button { border: none; cursor: pointer; }
        .app-shell { min-height: 100vh; display: flex; }
        .sidebar {
          width: 280px; min-width: 280px; padding: 28px 18px;
          background: linear-gradient(180deg, rgba(8,17,32,0.98), rgba(10,23,48,0.98));
          border-right: 1px solid rgba(255,255,255,0.07); position: sticky; top: 0; height: 100vh;
        }
        .brand { display: flex; flex-direction: column; gap: 6px; margin-bottom: 28px; }
        .brand-title { margin: 0; font-size: 2rem; font-weight: 800; letter-spacing: -0.04em; }
        .brand-subtitle { margin: 0; color: var(--muted); font-size: 0.95rem; }
        .nav { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }
        .nav-button {
          width: 100%; display: flex; align-items: center; justify-content: flex-start;
          padding: 14px 16px; border-radius: 16px; background: transparent; color: #dbe6f5;
          transition: background-color 0.2s ease, transform 0.15s ease, color 0.2s ease;
        }
        .nav-button:hover { background: rgba(255,255,255,0.05); transform: translateX(2px); }
        .nav-button.active {
          background: linear-gradient(90deg, rgba(37,99,235,0.24), rgba(255,255,255,0.04));
          color: white; border: 1px solid rgba(255,255,255,0.06);
        }
        .sidebar-card {
          margin-top: 24px; padding: 18px; border-radius: 20px; background: var(--panel);
          border: 1px solid var(--border); box-shadow: var(--shadow);
        }
        .sidebar-card-title { margin: 0 0 8px 0; font-size: 1rem; font-weight: 700; }
        .sidebar-card-text { margin: 0 0 14px 0; color: var(--muted); line-height: 1.55; font-size: 0.92rem; }
        .sidebar-card-button {
          width: 100%; padding: 12px 14px; border-radius: 14px; background: var(--blue); color: white; font-weight: 600;
        }
        .sidebar-card-button:hover { background: var(--blue-hover); }
        .page { flex: 1; padding: 28px 34px 40px; }
        .topbar {
          display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 28px; flex-wrap: wrap;
        }
        .search-input {
          width: min(460px, 100%); background: var(--panel); border: 1px solid var(--border); color: var(--text);
          padding: 14px 18px; border-radius: 18px; outline: none;
        }
        .search-input::placeholder { color: var(--muted); }
        .topbar-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        .ghost-button, .primary-button, .secondary-button, .month-nav-button {
          padding: 12px 16px; border-radius: 14px; transition: transform 0.15s ease, background-color 0.2s ease; white-space: nowrap;
        }
        .ghost-button {
          background: var(--panel); border: 1px solid var(--border); color: var(--text);
        }
        .ghost-button:hover, .month-nav-button:hover { background: rgba(255,255,255,0.08); transform: translateY(-1px); }
        .primary-button { background: var(--blue); color: white; font-weight: 600; }
        .primary-button:hover { background: var(--blue-hover); transform: translateY(-1px); }
        .secondary-button, .month-nav-button {
          background: rgba(255,255,255,0.05); color: white; border: 1px solid var(--border);
        }
        .avatar {
          width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center;
          background: linear-gradient(135deg, #2563eb, #60a5fa); font-weight: 800; color: white; flex-shrink: 0;
        }
        .page-header { margin-bottom: 28px; }
        .page-title { margin: 0 0 10px 0; font-size: clamp(2.5rem, 5vw, 4rem); line-height: 1; letter-spacing: -0.05em; }
        .page-subtitle { margin: 0; color: var(--muted); font-size: 1.05rem; }
        .overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin-bottom: 28px; }
        .stat-card {
          background: var(--panel); border: 1px solid var(--border); border-radius: 22px; padding: 22px; box-shadow: var(--shadow);
        }
        .stat-label { margin: 0 0 10px 0; color: var(--muted); font-size: 0.92rem; }
        .stat-value { margin: 0; font-size: 2rem; font-weight: 800; letter-spacing: -0.03em; }
        .dashboard-grid { display: grid; grid-template-columns: 1.6fr 1fr; gap: 22px; }
        .stack { display: flex; flex-direction: column; gap: 22px; }
        .panel {
          background: var(--panel); border: 1px solid var(--border); border-radius: 24px; padding: 24px; box-shadow: var(--shadow);
        }
        .panel-header {
          display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; flex-wrap: wrap;
        }
        .panel-title { margin: 0 0 6px 0; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.03em; }
        .panel-subtitle { margin: 0; color: var(--muted); font-size: 0.95rem; }
        .calendar-header {
          display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
        }
        .calendar-month-title { margin: 0; font-size: 1.4rem; font-weight: 800; letter-spacing: -0.03em; }
        .calendar-meta { margin: 8px 0 0 0; color: var(--muted); font-size: 0.92rem; line-height: 1.5; }
        .calendar-header-right { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .calendar-weekdays { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
        .weekday-cell { padding: 0 6px; color: var(--muted); font-size: 0.84rem; font-weight: 700; text-transform: uppercase; }
        .calendar-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 12px; }
        .calendar-empty { min-height: 144px; border-radius: 20px; background: rgba(255,255,255,0.015); border: 1px dashed rgba(255,255,255,0.03); }
        .calendar-day-button {
          min-height: 144px; border-radius: 20px; padding: 14px; text-align: left; background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.04); display: flex; flex-direction: column; gap: 12px; color: var(--text);
        }
        .calendar-day-button:hover { background: rgba(255,255,255,0.05); transform: translateY(-1px); }
        .calendar-day-button.outside-semester { opacity: 0.55; }
        .calendar-day-button.weekend { background: rgba(255,255,255,0.02); }
        .calendar-day-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
        .calendar-day-number { margin: 0; font-size: 1rem; font-weight: 800; }
        .cycle-badge {
          padding: 5px 8px; border-radius: 999px; background: rgba(37,99,235,0.18); color: #bfdbfe; font-size: 0.75rem; font-weight: 700;
        }
        .calendar-summary { display: flex; flex-direction: column; gap: 6px; }
        .calendar-summary-line1 { margin: 0; font-size: 0.9rem; font-weight: 700; color: #e2e8f0; }
        .calendar-summary-line2 { margin: 0; font-size: 0.82rem; color: var(--muted); }
        .calendar-preview-list { display: flex; flex-direction: column; gap: 6px; margin-top: auto; }
        .calendar-preview-chip {
          display: inline-flex; align-items: center; width: fit-content; padding: 5px 9px; border-radius: 999px; font-size: 0.76rem; font-weight: 700;
        }
        .chip-lecture { background: rgba(37,99,235,0.18); color: #bfdbfe; }
        .chip-lab { background: rgba(34,197,94,0.18); color: #bbf7d0; }
        .chip-practice { background: rgba(245,158,11,0.18); color: #fde68a; }
        .chip-exam { background: rgba(239,68,68,0.18); color: #fecaca; }
        .task-list { display: flex; flex-direction: column; gap: 14px; }
        .task-card {
          display: flex; justify-content: space-between; gap: 16px; padding: 18px; border-radius: 18px;
          background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.04);
        }
        .task-card.completed { opacity: 0.7; }
        .task-left { display: flex; align-items: flex-start; gap: 14px; min-width: 0; }
        .task-check { margin-top: 4px; width: 18px; height: 18px; accent-color: var(--blue); flex-shrink: 0; }
        .task-title { margin: 0 0 8px 0; font-size: 1rem; font-weight: 700; }
        .task-meta { display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 0.9rem; }
        .task-tag {
          display: inline-flex; align-items: center; padding: 5px 10px; border-radius: 999px; background: rgba(37,99,235,0.16);
          color: #bfdbfe; font-size: 0.78rem; font-weight: 700;
        }
        .priority-badge { display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; }
        .priority-high { background: rgba(239,68,68,0.16); color: #fecaca; }
        .priority-medium { background: rgba(245,158,11,0.16); color: #fde68a; }
        .priority-low { background: rgba(34,197,94,0.16); color: #bbf7d0; }
        .feature-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
        .feature-card {
          background: var(--panel); border: 1px solid var(--border); border-radius: 22px; padding: 22px; min-height: 180px; box-shadow: var(--shadow);
        }
        .feature-label {
          display: inline-flex; padding: 7px 10px; border-radius: 999px; background: rgba(37,99,235,0.15); color: #bfdbfe;
          font-size: 0.78rem; font-weight: 700; margin-bottom: 14px;
        }
        .feature-title { margin: 0 0 10px 0; font-size: 1.2rem; font-weight: 800; }
        .feature-text { margin: 0; color: var(--muted); line-height: 1.65; }
        .empty-note { margin: 0; color: var(--muted); line-height: 1.6; }
        .modal-overlay {
          position: fixed; inset: 0; background: rgba(2,6,23,0.72); display: flex; align-items: center; justify-content: center;
          padding: 20px; z-index: 1000; backdrop-filter: blur(6px);
        }
        .details-modal {
          width: min(720px, 100%); background: linear-gradient(180deg, #0c1730 0%, #101c38 100%);
          border: 1px solid var(--border); border-radius: 24px; padding: 24px; box-shadow: 0 30px 80px rgba(0,0,0,0.45);
          max-height: 90vh; overflow: auto;
        }
        .modal-header {
          display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px;
        }
        .modal-title { margin: 0 0 8px 0; font-size: 1.4rem; font-weight: 800; }
        .modal-subtitle { margin: 0; color: var(--muted); font-size: 0.95rem; line-height: 1.5; }
        .modal-close-button {
          width: 38px; height: 38px; border-radius: 12px; background: rgba(255,255,255,0.06); color: white; font-size: 1rem;
        }
        .modal-close-button:hover { background: rgba(255,255,255,0.1); }
        .details-stack, .import-form, .task-form { display: flex; flex-direction: column; gap: 14px; }
        .details-card {
          padding: 18px; border-radius: 18px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.05);
        }
        .details-time { margin: 0 0 8px 0; color: #bfdbfe; font-size: 0.88rem; font-weight: 700; }
        .details-title { margin: 0 0 8px 0; font-size: 1rem; font-weight: 800; }
        .details-meta { margin: 0; color: var(--muted); line-height: 1.6; font-size: 0.92rem; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .form-group { display: flex; flex-direction: column; gap: 8px; }
        .form-label { font-size: 0.9rem; color: #dbe6f5; font-weight: 600; }
        .form-input {
          width: 100%; background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--text);
          padding: 13px 14px; border-radius: 14px; outline: none;
        }
        .form-input::placeholder { color: var(--muted); }
        .form-error {
          margin: 0; padding: 12px 14px; border-radius: 14px; background: rgba(239,68,68,0.12);
          border: 1px solid rgba(239,68,68,0.24); color: #fecaca; font-size: 0.9rem;
        }
        .import-status { margin: 0; color: var(--muted); line-height: 1.5; }
        .option-row { display: flex; gap: 12px; flex-wrap: wrap; }
        .option-button {
          padding: 12px 14px; border-radius: 14px; background: rgba(255,255,255,0.04); color: var(--text); border: 1px solid var(--border);
        }
        .option-button.active {
          background: rgba(37,99,235,0.18); border-color: rgba(37,99,235,0.6); color: #dbeafe;
        }
        .modal-actions {
          display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; flex-wrap: wrap;
        }
        @media (max-width: 1300px) {
          .overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .dashboard-grid { grid-template-columns: 1fr; }
          .feature-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 1050px) {
          .calendar-weekdays, .calendar-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 980px) {
          .sidebar { display: none; }
          .page { padding: 22px; }
          .topbar { flex-direction: column; align-items: stretch; }
          .topbar-right { justify-content: flex-start; }
        }
        @media (max-width: 640px) {
          .overview-grid { grid-template-columns: 1fr; }
          .calendar-weekdays, .calendar-grid { grid-template-columns: 1fr; }
          .page-title { font-size: 2.4rem; }
          .form-row { grid-template-columns: 1fr; }
        }
      `}</style>

      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <h1 className="brand-title">AI Assistant</h1>
            <p className="brand-subtitle">Student planning workspace</p>
          </div>

          <nav className="nav">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={`nav-button ${activePage === item.id ? 'active' : ''}`}
                onClick={() => setActivePage(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="sidebar-card">
            <h3 className="sidebar-card-title">Quick action</h3>
            <p className="sidebar-card-text">
              Add a custom study task with title, subject, day, time, priority and tag.
            </p>
            <button className="sidebar-card-button" onClick={openTaskModal}>
              Add task
            </button>
          </div>
        </aside>

        <main className="page">
          <header className="topbar">
            <input
              className="search-input"
              type="text"
              placeholder="Search tasks, classes, days..."
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
            />

            <div className="topbar-right">
              <button className="ghost-button" onClick={() => setActivePage('calendar')}>
                Calendar
              </button>
              <button className="secondary-button" onClick={() => setIsImportModalOpen(true)}>
                Import schedule
              </button>
              <button className="primary-button" onClick={openTaskModal}>
                New Task
              </button>
              <div className="avatar">X</div>
            </div>
          </header>

          {activePage === 'dashboard' && (
            <>
              <section className="page-header">
                <h2 className="page-title">Dashboard</h2>
                <p className="page-subtitle">
                  Clean dashboard with task creation, separate schedule import and stable semester calendar.
                </p>
              </section>

              <section className="overview-grid">
                <div className="stat-card">
                  <p className="stat-label">Tasks Today</p>
                  <p className="stat-value">{activeTasksCount}</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">Completed Tasks</p>
                  <p className="stat-value">{completedTasksCount}</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">High Priority</p>
                  <p className="stat-value">{highPriorityCount}</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">Calendar Source</p>
                  <p className="stat-value" style={{ fontSize: '1.05rem' }}>{calendarSourceLabel}</p>
                </div>
              </section>

              <section className="dashboard-grid">
                <div className="stack">
                  <section className="panel">
                    <div className="panel-header">
                      <div>
                        <h3 className="panel-title">Today's Tasks</h3>
                        <p className="panel-subtitle">Task preview for the current frontend shell</p>
                      </div>
                      <button className="primary-button" onClick={openTaskModal}>
                        Add task
                      </button>
                    </div>

                    <div className="task-list">
                      {isTasksLoading && (
                        <p className="empty-note">Loading tasks from backend...</p>
                      )}

                      {tasksError && (
                        <p className="form-error">{tasksError}</p>
                      )}

                      {filteredTasks.map((task) => (
                        <article
                          key={task.id}
                          className={`task-card ${task.completed ? 'completed' : ''}`}
                        >
                          <div className="task-left">
                            <input
                              className="task-check"
                              type="checkbox"
                              checked={task.completed}
                              onChange={() => toggleTask(task.id)}
                            />

                            <div>
                              <p className="task-title">{task.title}</p>
                              <div className="task-meta">
                                <span>{task.course}</span>
                                <span>{task.deadline}</span>
                                <span className="task-tag">{task.customTag}</span>
                              </div>
                            </div>
                          </div>

                          <div
                            className={`priority-badge ${
                              task.priority === 'High'
                                ? 'priority-high'
                                : task.priority === 'Medium'
                                ? 'priority-medium'
                                : 'priority-low'
                            }`}
                          >
                            {task.priority}
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>

                  <section className="panel">
                    <div className="panel-header">
                      <div>
                        <h3 className="panel-title">Calendar Integration</h3>
                        <p className="panel-subtitle">Import from external sources without changing dashboard structure</p>
                      </div>
                      <button className="secondary-button" onClick={() => setIsImportModalOpen(true)}>
                        Import schedule
                      </button>
                    </div>

                    <p className="empty-note">
                      Month grid, clickable day cells and detailed popup remain on the calendar page.
                      Import is handled in a separate modal and does not replace dashboard blocks.
                    </p>
                  </section>
                </div>

                <div className="stack">
                  <section className="panel">
                    <div className="panel-header">
                      <div>
                        <h3 className="panel-title">AI Recommendations</h3>
                        <p className="panel-subtitle">Visual placeholder for future recommendation logic</p>
                      </div>
                    </div>

                    <div className="task-list">
                      <article className="task-card">
                        <div>
                          <p className="task-title">Start with the hardest task first</p>
                          <p className="empty-note">
                            Later backend can use imported schedule density and deadlines to build these suggestions.
                          </p>
                        </div>
                      </article>

                      <article className="task-card">
                        <div>
                          <p className="task-title">Keep tasks and classes in one workspace</p>
                          <p className="empty-note">
                            Newly created tasks now appear immediately in Dashboard and Tasks.
                          </p>
                        </div>
                      </article>
                    </div>
                  </section>
                </div>
              </section>
            </>
          )}

          {activePage === 'calendar' && (
            <>
              <section className="page-header">
                <h2 className="page-title">Calendar</h2>
                <p className="page-subtitle">
                  Month grid stays the same. User import only updates source status for now, while the calendar view remains stable.
                </p>
              </section>

              <section className="overview-grid">
                <div className="stat-card">
                  <p className="stat-label">Semester Start</p>
                  <p className="stat-value">09 Feb</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">Cycle Length</p>
                  <p className="stat-value">4 weeks</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">Active Month</p>
                  <p className="stat-value" style={{ fontSize: '1.15rem' }}>{currentMonth.label}</p>
                </div>

                <div className="stat-card">
                  <p className="stat-label">Imported Source</p>
                  <p className="stat-value" style={{ fontSize: '1.05rem' }}>{calendarSourceLabel}</p>
                </div>
              </section>

              <section className="panel">
                <div className="calendar-header">
                  <div>
                    <h3 className="calendar-month-title">{currentMonth.label}</h3>
                    <p className="calendar-meta">
                      Semester months: February 2026 → June 2026. Start point: 09.02.2026 (Monday).
                      Current source: {calendarSourceLabel}.
                    </p>
                  </div>

                  <div className="calendar-header-right">
                    <button
                      className="month-nav-button"
                      onClick={() => setCurrentMonthIndex((prev) => Math.max(prev - 1, 0))}
                      disabled={currentMonthIndex === 0}
                    >
                      ← Previous
                    </button>

                    <button className="secondary-button" onClick={() => setIsImportModalOpen(true)}>
                      Import schedule
                    </button>

                    <button
                      className="month-nav-button"
                      onClick={() =>
                        setCurrentMonthIndex((prev) => Math.min(prev + 1, semesterMonths.length - 1))
                      }
                      disabled={currentMonthIndex === semesterMonths.length - 1}
                    >
                      Next →
                    </button>
                  </div>
                </div>

                <div className="calendar-weekdays">
                  {weekdayLabels.map((label) => (
                    <div key={label} className="weekday-cell">{label}</div>
                  ))}
                </div>

                <div className="calendar-grid">
                  {monthCells.map((cell, index) => {
                    if (!cell) return <div key={`empty-${index}`} className="calendar-empty" />;

                    const daySummary = getDaySummary(cell);
                    const cycleWeek = getCycleWeek(cell);
                    const dayItems = getScheduleForDate(cell);
                    const inSemester = isDateInSemester(cell);
                    const weekday = getMondayIndex(cell);
                    const weekend = weekday === 7;

                    return (
                      <button
                        key={cell.toISOString()}
                        className={`calendar-day-button ${!inSemester ? 'outside-semester' : ''} ${weekend ? 'weekend' : ''}`}
                        onClick={() => openDayDetails(cell)}
                      >
                        <div className="calendar-day-top">
                          <p className="calendar-day-number">{cell.getDate()}</p>
                          {cycleWeek ? <span className="cycle-badge">W{cycleWeek}</span> : <span className="cycle-badge">Off</span>}
                        </div>

                        <div className="calendar-summary">
                          <p className="calendar-summary-line1">{daySummary.line1}</p>
                          <p className="calendar-summary-line2">{daySummary.line2}</p>
                        </div>

                        <div className="calendar-preview-list">
                          {dayItems.slice(0, 2).map((item) => (
                            <span
                              key={`${cell.toISOString()}-${item.time}-${item.title}`}
                              className={`calendar-preview-chip ${
                                item.type === 'lecture'
                                  ? 'chip-lecture'
                                  : item.type === 'lab'
                                  ? 'chip-lab'
                                  : item.type === 'practice'
                                  ? 'chip-practice'
                                  : 'chip-exam'
                              }`}
                            >
                              {item.time} • {item.title}
                            </span>
                          ))}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            </>
          )}

          {activePage === 'tasks' && (
            <>
              <section className="page-header">
                <h2 className="page-title">Tasks</h2>
                <p className="page-subtitle">Create, review and complete your study tasks.</p>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <h3 className="panel-title">Task List</h3>
                    <p className="panel-subtitle">New tasks are added locally and displayed immediately.</p>
                  </div>

                  <button className="primary-button" onClick={openTaskModal}>
                    Add task
                  </button>
                </div>

                <div className="task-list">
                  {isTasksLoading && (
                    <p className="empty-note">Loading tasks from backend...</p>
                  )}

                  {tasksError && (
                    <p className="form-error">{tasksError}</p>
                  )}

                  {filteredTasks.map((task) => (
                    <article
                      key={task.id}
                      className={`task-card ${task.completed ? 'completed' : ''}`}
                    >
                      <div className="task-left">
                        <input
                          className="task-check"
                          type="checkbox"
                          checked={task.completed}
                          onChange={() => toggleTask(task.id)}
                        />

                        <div>
                          <p className="task-title">{task.title}</p>
                          <div className="task-meta">
                            <span>{task.course}</span>
                            <span>{task.deadline}</span>
                            <span className="task-tag">{task.customTag}</span>
                          </div>
                        </div>
                      </div>

                      <div
                        className={`priority-badge ${
                          task.priority === 'High'
                            ? 'priority-high'
                            : task.priority === 'Medium'
                            ? 'priority-medium'
                            : 'priority-low'
                        }`}
                      >
                        {task.priority}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}

          {(activePage === 'projects' || activePage === 'analytics' || activePage === 'settings') && (
            <>
              <section className="page-header">
                <h2 className="page-title">{activePage.charAt(0).toUpperCase() + activePage.slice(1)}</h2>
                <p className="page-subtitle">Frontend placeholder page.</p>
              </section>

              <section className="feature-grid">
                <article className="feature-card">
                  <span className="feature-label">Feature in development</span>
                  <h3 className="feature-title">Semester-aware workspace</h3>
                  <p className="feature-text">
                    This block can later use the same calendar logic and imported timetable data.
                  </p>
                </article>

                <article className="feature-card">
                  <span className="feature-label">Feature in development</span>
                  <h3 className="feature-title">Task + calendar sync</h3>
                  <p className="feature-text">
                    Import flow and task creation are separated, so the dashboard stays stable.
                  </p>
                </article>
              </section>
            </>
          )}
        </main>
      </div>

      {isTaskModalOpen && (
        <div className="modal-overlay" onClick={closeTaskModal}>
          <div className="details-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">Create new task</h3>
                <p className="modal-subtitle">
                  Add a study task. It will appear in Dashboard and Tasks immediately.
                </p>
              </div>

              <button className="modal-close-button" onClick={closeTaskModal}>✕</button>
            </div>

            <div className="task-form">
              {taskFormError && <p className="form-error">{taskFormError}</p>}

              <div className="form-group">
                <label className="form-label">Task title</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Например: закончить отчёт по базе данных"
                  value={newTaskTitle}
                  onChange={(event) => setNewTaskTitle(event.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Subject / course</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Например: Databases"
                  value={newTaskCourse}
                  onChange={(event) => setNewTaskCourse(event.target.value)}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Day</label>
                  <input
                    className="form-input"
                    type="date"
                    value={newTaskDay}
                    onChange={(event) => setNewTaskDay(event.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Time</label>
                  <input
                    className="form-input"
                    type="time"
                    value={newTaskTime}
                    onChange={(event) => setNewTaskTime(event.target.value)}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Priority</label>
                  <select
                    className="form-input"
                    value={newTaskPriority}
                    onChange={(event) => setNewTaskPriority(event.target.value as TaskPriority)}
                  >
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Custom tag</label>
                  <input
                    className="form-input"
                    type="text"
                    placeholder="Lab / Exam / Report"
                    value={newTaskTag}
                    onChange={(event) => setNewTaskTag(event.target.value)}
                  />
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button className="ghost-button" onClick={closeTaskModal}>
                Cancel
              </button>
              <button className="primary-button" onClick={createTask}>
                Create task
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedDay && (
        <div className="modal-overlay" onClick={closeDayDetails}>
          <div className="details-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">
                  {selectedDay.date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
                </h3>
                <p className="modal-subtitle">
                  {selectedDay.inSemester
                    ? selectedDay.cycleWeek
                      ? `Semester day • cycle week ${selectedDay.cycleWeek}`
                      : 'Semester off day'
                    : 'Outside semester range'}
                </p>
              </div>

              <button className="modal-close-button" onClick={closeDayDetails}>✕</button>
            </div>

            <div className="details-stack">
              {!selectedDay.inSemester && (
                <div className="details-card">
                  <p className="details-title">Semester has not started yet</p>
                  <p className="details-meta">Semester logic starts from 9 February 2026.</p>
                </div>
              )}

              {selectedDay.inSemester && selectedDay.items.length === 0 && (
                <div className="details-card">
                  <p className="details-title">No scheduled classes</p>
                  <p className="details-meta">This day is currently free in the 4-week cycle or falls on Sunday.</p>
                </div>
              )}

              {selectedDay.items.map((item) => (
                <div key={`${selectedDay.date.toISOString()}-${item.time}-${item.title}`} className="details-card">
                  <p className="details-time">{item.time}</p>
                  <p className="details-title">{item.title}</p>
                  <p className="details-meta">
                    Room: {item.room}
                    {item.teacher ? ` • Teacher: ${item.teacher}` : ''}
                    {` • Type: ${item.type}`}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {isImportModalOpen && (
        <div className="modal-overlay" onClick={() => setIsImportModalOpen(false)}>
          <div className="details-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">Import schedule</h3>
                <p className="modal-subtitle">
                  Upload a schedule file. Current frontend only stores the selected source label.
                </p>
              </div>

              <button className="modal-close-button" onClick={() => setIsImportModalOpen(false)}>✕</button>
            </div>

            <div className="import-form">
              <div className="form-group">
                <label className="form-label">Choose schedule file</label>
                <input className="form-input" type="file" accept=".xlsx,.xls,.csv" onChange={handleFileChange} />
                <p className="import-status">Selected file: {selectedFileName}</p>
              </div>

              <div className="form-group">
                <label className="form-label">How should the system read it?</label>
                <div className="option-row">
                  <button className={`option-button ${importMode === 'smart' ? 'active' : ''}`} onClick={() => setImportMode('smart')}>
                    Smart import
                  </button>
                  <button className={`option-button ${importMode === 'classes' ? 'active' : ''}`} onClick={() => setImportMode('classes')}>
                    Classes only
                  </button>
                  <button className={`option-button ${importMode === 'exams' ? 'active' : ''}`} onClick={() => setImportMode('exams')}>
                    Exams only
                  </button>
                </div>
              </div>

              <div className="details-card">
                <p className="details-title">Current stage</p>
                <p className="details-meta">
                  Later backend will parse the uploaded workbook and replace the semester template with real classes.
                </p>
              </div>
            </div>

            <div className="modal-actions">
              <button className="ghost-button" onClick={() => setIsImportModalOpen(false)}>
                Cancel
              </button>
              <button className="primary-button" onClick={applyImportPreview}>
                Apply import source
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default App;