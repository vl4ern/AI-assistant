import { createContext, useContext } from 'react';

export type Theme = 'dark' | 'light';
export type Lang = 'ru' | 'en';
export type FontSize = 'sm' | 'md' | 'lg';

export type AppSettings = {
  theme: Theme;
  lang: Lang;
  fontSize: FontSize;
};

const STORAGE_KEY = 'assistant-settings';

const DEFAULT_SETTINGS: AppSettings = { theme: 'dark', lang: 'ru', fontSize: 'md' };

const ru: Record<string, string> = {
  // Навигация и каркас
  'nav.overview': 'Обзор',
  'nav.tasks': 'Задачи',
  'nav.timetable': 'Расписание',
  'nav.calendar': 'Календарь',
  'nav.plan': 'План',
  'nav.history': 'История',
  'action.logout': 'Выйти',
  'loading': 'Загрузка…',
  'error.unknown': 'Неизвестная ошибка',
  'notice.idle': 'Вы давно не были активны — войдите заново.',
  'state.updating': 'Обновляем…',

  // Настройки (шестерёнка)
  'settings.title': 'Настройки',
  'settings.theme': 'Тема',
  'settings.theme.dark': 'Тёмная',
  'settings.theme.light': 'Светлая',
  'settings.language': 'Язык интерфейса',
  'settings.language.ru': 'Русский',
  'settings.language.en': 'English',
  'settings.fontSize': 'Размер шрифта',
  'settings.fontSize.sm': 'Мелкий',
  'settings.fontSize.md': 'Обычный',
  'settings.fontSize.lg': 'Крупный',

  // Вход
  'auth.subtitle': 'Личные задачи, дедлайны и расписание в одном месте.',
  'auth.login': 'Вход',
  'auth.register': 'Регистрация',
  'auth.name': 'Имя',
  'auth.namePlaceholder': 'Как вас зовут',
  'auth.password': 'Пароль',
  'auth.passwordPlaceholder': 'Минимум 4 символа',
  'auth.submit.login': 'Войти',
  'auth.submit.register': 'Создать аккаунт',
  'auth.submitting': 'Подождите…',
  'auth.demo': 'Есть демо-аккаунт: demo / demo',

  // Обзор
  'overview.hello': 'Привет, {name}',
  'overview.today': 'Сегодня {date}.',
  'overview.activeTasks': 'Активные задачи',
  'overview.overdue': 'Просрочено: {count}',
  'overview.allGood': 'Всё под контролем',
  'overview.lessonsToday': 'Занятий сегодня',
  'overview.planned': 'Запланировано',
  'overview.slotsHint': 'слотов в плане',
  'overview.todayLessons': 'Сегодня в расписании',
  'overview.noLessons': 'Занятий сегодня нет.',
  'overview.openTimetable': 'Открыть расписание',
  'overview.plannedTasks': 'Запланированные задачи',
  'overview.noPlan': 'План ещё не построен.',
  'overview.addTask': 'Добавить задачу',

  // Задачи
  'tasks.title': 'Задачи',
  'tasks.subtitle': 'Ваши личные дедлайны и работы. Завершённые попадают в историю.',
  'tasks.new': 'Новая задача',
  'tasks.what': 'Что нужно сделать',
  'tasks.whatPlaceholder': 'Например: доделать отчёт',
  'tasks.priority': 'Важность',
  'tasks.priority.1': 'Высокая',
  'tasks.priority.2': 'Повышенная',
  'tasks.priority.3': 'Обычная',
  'tasks.priority.4': 'Низкая',
  'tasks.estimate': 'Оценка, минут',
  'tasks.deadlineDate': 'Дедлайн — дата',
  'tasks.time': 'Время',
  'tasks.note': 'Заметка',
  'tasks.create': 'Добавить задачу',
  'tasks.creating': 'Добавляем…',
  'tasks.active': 'Активные · {count}',
  'tasks.empty': 'Пока нет активных задач — самое время отдохнуть.',
  'tasks.complete': 'Выполнено',
  'tasks.start': 'В работу',
  'tasks.cancel': 'Отменить',
  'task.noDeadline': 'Без дедлайна',
  'task.overdue': 'просрочено',
  'task.today': 'сегодня',
  'task.tomorrow': 'завтра',
  'task.minutes': 'мин',
  'status.todo': 'К выполнению',
  'status.in_progress': 'В работе',
  'status.completed': 'Выполнено',
  'status.cancelled': 'Отменено',
  'status.blocked': 'Заблокировано',

  // Расписание
  'timetable.title': 'Расписание',
  'timetable.subtitle': 'Занятия по учебным неделям.',
  'timetable.weekNow': 'Сейчас неделя {week}.',
  'timetable.group': 'Группа: {group}',
  'timetable.groupUnknown': 'Группа не выбрана — введите номер или загрузите файл.',
  'timetable.groupPlaceholder': 'Номер группы',
  'timetable.groupHint': 'Введите номер группы — расписание загрузится с портала БГУИР',
  'timetable.loadGroup': 'Загрузить группу',
  'timetable.importFile': 'Загрузить из файла',
  'timetable.sync': 'Обновить с портала',
  'timetable.syncing': 'Обновляем…',
  'timetable.week': 'Неделя {week}',
  'timetable.allWeeks': 'Все недели',
  'timetable.now': 'сейчас',
  'timetable.lessons': 'Пары:',
  'timetable.subgroupAll': 'Все',
  'timetable.subgroupCommon': 'Общие',
  'timetable.subgroup1': '1 подгруппа',
  'timetable.subgroup2': '2 подгруппа',
  'timetable.empty': 'Расписание на выбранную неделю пустое. Можно обновить его с портала или загрузить файл с расписанием группы.',
  'timetable.free': 'свободно',
  'timetable.today': 'сегодня',
  'timetable.dated': 'Экзамены и события по датам',
  'timetable.datedNote': 'Записи с конкретной датой: экзамены, консультации и объявления — они не привязаны к дню недели.',
  'timetable.weeks': 'недели: {weeks}',
  'timetable.auditory': 'ауд. {auditory}',
  'timetable.subgroupBadge': '{n} подгр.',
  'lesson.ЛК': 'Лекция',
  'lesson.ПЗ': 'Практика',
  'lesson.ЛР': 'Лабораторная',
  'timetable.updated': 'Расписание обновлено.',
  'timetable.updateFailed': 'Не удалось обновить расписание: {error}',
  'timetable.imported': 'Файл загружен: занятий — {count}.',
  'timetable.importFailed': 'Не удалось загрузить файл: {error}',
  'timetable.groupLoaded': 'Расписание группы {group} загружено: занятий — {count}.',
  'timetable.groupFailed': 'Не удалось загрузить расписание группы: {error}',

  // Календарь
  'calendar.title': 'Календарь',
  'calendar.subtitle': 'Месяц целиком: расписание университета, запланированные задачи и дедлайны.',
  'calendar.clickDay': 'Нажмите на день, чтобы раскрыть подробности.',
  'calendar.lessons': 'пар нет',
  'calendar.university': 'Расписание университета',
  'calendar.personal': 'Личные задачи',
  'calendar.noPlanned': 'запланированных задач нет',
  'calendar.deadlines': 'Дедлайны',
  'calendar.noDeadlines': 'дедлайнов нет',
  'calendar.weekShort': '{week} нед.',
  'calendar.academicWeek': 'учебная неделя {week}',
  'calendar.pairs': '{count} пар',
  'calendar.pair': '{count} пара',
  'calendar.pairsFew': '{count} пары',
  'calendar.tasksShort': '{count} зад.',
  'calendar.deadlinesShort': '{count} дедл.',

  // План
  'plan.title': 'План',
  'plan.subtitle': 'Ассистент раскладывает задачи по свободным окнам между занятиями и делами.',
  'plan.build': 'Построить план',
  'plan.building': 'Строим…',
  'plan.upcoming': 'План на ближайшие дни',
  'plan.empty': 'Нажмите «Построить план» — подберём время для каждой задачи.',
  'plan.noTasks': 'Задач для планирования нет. Добавьте их на странице «Задачи».',
  'plan.prime': 'главная задача',
  'plan.addBusy': 'Добавить занятое время',
  'plan.busyNote': 'Встречи, консультации, дорога — всё, что нельзя двигать.',
  'plan.name': 'Название',
  'plan.namePlaceholder': 'Например: консультация',
  'plan.date': 'Дата',
  'plan.start': 'Начало',
  'plan.end': 'Конец',
  'plan.add': 'Добавить',
  'plan.adding': 'Добавляем…',
  'plan.next': 'Ближайшие дела',
  'plan.noEvents': 'Занятых интервалов нет.',
  'plan.ready': 'План готов.',
  'plan.failed': 'Не удалось построить план: {error}',

  // История
  'history.title': 'История',
  'history.subtitle': 'Выполненные и отменённые задачи.',
  'history.empty': 'История пока пуста.',
  'history.restore': 'Вернуть',

  // Дни недели
  'day.Понедельник': 'Понедельник',
  'day.Вторник': 'Вторник',
  'day.Среда': 'Среда',
  'day.Четверг': 'Четверг',
  'day.Пятница': 'Пятница',
  'day.Суббота': 'Суббота',
  'day.Воскресенье': 'Воскресенье',
  'dayShort.Пн': 'Пн',
  'dayShort.Вт': 'Вт',
  'dayShort.Ср': 'Ср',
  'dayShort.Чт': 'Чт',
  'dayShort.Пт': 'Пт',
  'dayShort.Сб': 'Сб',
  'dayShort.Вс': 'Вс',
};

const en: Record<string, string> = {
  'nav.overview': 'Overview',
  'nav.tasks': 'Tasks',
  'nav.timetable': 'Timetable',
  'nav.calendar': 'Calendar',
  'nav.plan': 'Plan',
  'nav.history': 'History',
  'action.logout': 'Log out',
  'loading': 'Loading…',
  'error.unknown': 'Unknown error',
  'notice.idle': 'You have been inactive for a while — please log in again.',
  'state.updating': 'Updating…',

  'settings.title': 'Settings',
  'settings.theme': 'Theme',
  'settings.theme.dark': 'Dark',
  'settings.theme.light': 'Light',
  'settings.language': 'Interface language',
  'settings.language.ru': 'Русский',
  'settings.language.en': 'English',
  'settings.fontSize': 'Font size',
  'settings.fontSize.sm': 'Small',
  'settings.fontSize.md': 'Medium',
  'settings.fontSize.lg': 'Large',

  'auth.subtitle': 'Personal tasks, deadlines and timetable in one place.',
  'auth.login': 'Log in',
  'auth.register': 'Sign up',
  'auth.name': 'Name',
  'auth.namePlaceholder': 'Your name',
  'auth.password': 'Password',
  'auth.passwordPlaceholder': 'At least 4 characters',
  'auth.submit.login': 'Log in',
  'auth.submit.register': 'Create account',
  'auth.submitting': 'Please wait…',
  'auth.demo': 'Demo account available: demo / demo',

  'overview.hello': 'Hi, {name}',
  'overview.today': 'Today is {date}.',
  'overview.activeTasks': 'Active tasks',
  'overview.overdue': 'Overdue: {count}',
  'overview.allGood': 'All under control',
  'overview.lessonsToday': 'Lessons today',
  'overview.planned': 'Planned',
  'overview.slotsHint': 'slots in the plan',
  'overview.todayLessons': 'Today in the timetable',
  'overview.noLessons': 'No lessons today.',
  'overview.openTimetable': 'Open the timetable',
  'overview.plannedTasks': 'Scheduled tasks',
  'overview.noPlan': 'The plan has not been built yet.',
  'overview.addTask': 'Add a task',

  'tasks.title': 'Tasks',
  'tasks.subtitle': 'Your personal deadlines and assignments. Completed ones go to history.',
  'tasks.new': 'New task',
  'tasks.what': 'What needs to be done',
  'tasks.whatPlaceholder': 'e.g. finish the report',
  'tasks.priority': 'Priority',
  'tasks.priority.1': 'High',
  'tasks.priority.2': 'Elevated',
  'tasks.priority.3': 'Normal',
  'tasks.priority.4': 'Low',
  'tasks.estimate': 'Estimate, minutes',
  'tasks.deadlineDate': 'Deadline — date',
  'tasks.time': 'Time',
  'tasks.note': 'Note',
  'tasks.create': 'Add task',
  'tasks.creating': 'Adding…',
  'tasks.active': 'Active · {count}',
  'tasks.empty': 'No active tasks yet — time to rest.',
  'tasks.complete': 'Done',
  'tasks.start': 'Start',
  'tasks.cancel': 'Cancel',
  'task.noDeadline': 'No deadline',
  'task.overdue': 'overdue',
  'task.today': 'today',
  'task.tomorrow': 'tomorrow',
  'task.minutes': 'min',
  'status.todo': 'To do',
  'status.in_progress': 'In progress',
  'status.completed': 'Completed',
  'status.cancelled': 'Cancelled',
  'status.blocked': 'Blocked',

  'timetable.title': 'Timetable',
  'timetable.subtitle': 'Lessons by academic week.',
  'timetable.weekNow': 'Current week is {week}.',
  'timetable.group': 'Group: {group}',
  'timetable.groupUnknown': 'No group selected — enter a number or upload a file.',
  'timetable.groupPlaceholder': 'Group number',
  'timetable.groupHint': 'Enter a group number — the timetable will load from BSUIR portal',
  'timetable.loadGroup': 'Load group',
  'timetable.importFile': 'Import file',
  'timetable.sync': 'Refresh from portal',
  'timetable.syncing': 'Refreshing…',
  'timetable.week': 'Week {week}',
  'timetable.allWeeks': 'All weeks',
  'timetable.now': 'now',
  'timetable.lessons': 'Lessons:',
  'timetable.subgroupAll': 'All',
  'timetable.subgroupCommon': 'Common',
  'timetable.subgroup1': 'Subgroup 1',
  'timetable.subgroup2': 'Subgroup 2',
  'timetable.empty': 'The selected week is empty. Refresh from the portal or upload a group timetable file.',
  'timetable.free': 'free',
  'timetable.today': 'today',
  'timetable.dated': 'Exams and dated events',
  'timetable.datedNote': 'Entries with a specific date: exams, consultations and announcements — not tied to a weekday.',
  'timetable.weeks': 'weeks: {weeks}',
  'timetable.auditory': 'room {auditory}',
  'timetable.subgroupBadge': 'subgr. {n}',
  'lesson.ЛК': 'Lecture',
  'lesson.ПЗ': 'Practice',
  'lesson.ЛР': 'Lab',
  'timetable.updated': 'Timetable refreshed.',
  'timetable.updateFailed': 'Failed to refresh the timetable: {error}',
  'timetable.imported': 'File imported: {count} lessons.',
  'timetable.importFailed': 'Failed to import the file: {error}',
  'timetable.groupLoaded': 'Timetable of group {group} loaded: {count} lessons.',
  'timetable.groupFailed': 'Failed to load the group timetable: {error}',

  'calendar.title': 'Calendar',
  'calendar.subtitle': 'The whole month: university timetable, planned tasks and deadlines.',
  'calendar.clickDay': 'Click a day to see details.',
  'calendar.lessons': 'no lessons',
  'calendar.university': 'University timetable',
  'calendar.personal': 'Personal tasks',
  'calendar.noPlanned': 'no planned tasks',
  'calendar.deadlines': 'Deadlines',
  'calendar.noDeadlines': 'no deadlines',
  'calendar.weekShort': 'week {week}',
  'calendar.academicWeek': 'academic week {week}',
  'calendar.pairs': '{count} lessons',
  'calendar.pair': '{count} lesson',
  'calendar.pairsFew': '{count} lessons',
  'calendar.tasksShort': '{count} tasks',
  'calendar.deadlinesShort': '{count} dl.',

  'plan.title': 'Plan',
  'plan.subtitle': 'The assistant fits tasks into free slots between lessons and events.',
  'plan.build': 'Build plan',
  'plan.building': 'Building…',
  'plan.upcoming': 'Plan for the coming days',
  'plan.empty': 'Press "Build plan" — we will find time for every task.',
  'plan.noTasks': 'Nothing to plan. Add tasks on the "Tasks" page.',
  'plan.prime': 'prime task',
  'plan.addBusy': 'Add busy time',
  'plan.busyNote': 'Meetings, consultations, commutes — anything immovable.',
  'plan.name': 'Title',
  'plan.namePlaceholder': 'e.g. consultation',
  'plan.date': 'Date',
  'plan.start': 'Start',
  'plan.end': 'End',
  'plan.add': 'Add',
  'plan.adding': 'Adding…',
  'plan.next': 'Upcoming events',
  'plan.noEvents': 'No busy intervals.',
  'plan.ready': 'The plan is ready.',
  'plan.failed': 'Failed to build the plan: {error}',

  'history.title': 'History',
  'history.subtitle': 'Completed and cancelled tasks.',
  'history.empty': 'History is empty.',
  'history.restore': 'Restore',

  'day.Понедельник': 'Monday',
  'day.Вторник': 'Tuesday',
  'day.Среда': 'Wednesday',
  'day.Четверг': 'Thursday',
  'day.Пятница': 'Friday',
  'day.Суббота': 'Saturday',
  'day.Воскресенье': 'Sunday',
  'dayShort.Пн': 'Mo',
  'dayShort.Вт': 'Tu',
  'dayShort.Ср': 'We',
  'dayShort.Чт': 'Th',
  'dayShort.Пт': 'Fr',
  'dayShort.Сб': 'Sa',
  'dayShort.Вс': 'Su',
};

const translations: Record<Lang, Record<string, string>> = { ru, en };

export type TFunc = (key: string, vars?: Record<string, string | number>) => string;

export function makeT(lang: Lang): TFunc {
  return (key, vars) => {
    let value = translations[lang][key] ?? translations.ru[key] ?? key;
    if (vars) {
      for (const [name, replacement] of Object.entries(vars)) {
        value = value.replaceAll(`{${name}}`, String(replacement));
      }
    }
    return value;
  };
}

export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return {
      theme: parsed.theme === 'light' ? 'light' : 'dark',
      lang: parsed.lang === 'en' ? 'en' : 'ru',
      fontSize:
        parsed.fontSize === 'sm' || parsed.fontSize === 'lg' ? parsed.fontSize : 'md',
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export type SettingsContextValue = {
  theme: Theme;
  lang: Lang;
  fontSize: FontSize;
  locale: string;
  setTheme: (theme: Theme) => void;
  setLang: (lang: Lang) => void;
  setFontSize: (size: FontSize) => void;
  t: TFunc;
};

export const SettingsContext = createContext<SettingsContextValue | null>(null);

export function useSettings(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used inside SettingsProvider');
  }
  return context;
}
