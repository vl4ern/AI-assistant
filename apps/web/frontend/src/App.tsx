import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { clearToken, getToken, setToken } from './api/client';
import { getCurrentUser, login as loginApi, register as registerApi } from './api/auth';
import type { AuthUser } from './api/auth';
import { getEvents, createEvent as createEventApi } from './api/events';
import type { ApiEvent } from './api/events';
import { getLessons, getWeekInfo, importSchedule, syncIntegration } from './api/integrations';
import type { Lesson, WeekInfo } from './api/integrations';
import { rebuildSchedule } from './api/schedule';
import type { SchedulePlan } from './api/schedule';
import { createTask as createTaskApi, getTasks, updateTaskStatus } from './api/tasks';
import type { ApiTask, ApiTaskStatus } from './types/api';

type Page = 'overview' | 'tasks' | 'timetable' | 'plan' | 'history';

const IDLE_TIMEOUT_MINUTES = 30;

const navItems: Array<{ id: Page; label: string }> = [
  { id: 'overview', label: 'Обзор' },
  { id: 'tasks', label: 'Задачи' },
  { id: 'timetable', label: 'Расписание' },
  { id: 'plan', label: 'План' },
  { id: 'history', label: 'История' },
];

const WEEK_DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

const statusLabels: Record<ApiTaskStatus, string> = {
  todo: 'К выполнению',
  in_progress: 'В работе',
  completed: 'Выполнено',
  cancelled: 'Отменено',
  blocked: 'Заблокировано',
};

const priorityLabels: Record<number, string> = {
  1: 'Высокий',
  2: 'Повышенный',
  3: 'Обычный',
  4: 'Низкий',
};

const lessonTypeLabels: Record<string, string> = {
  ЛК: 'Лекция',
  ПЗ: 'Практика',
  ЛР: 'Лабораторная',
};

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatClock(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function formatDeadline(value: string | null): string {
  if (!value) return 'Без дедлайна';
  const date = new Date(value);
  const today = new Date();
  const daysLeft = Math.ceil((date.getTime() - today.getTime()) / 86_400_000);
  const base = date.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  if (daysLeft < 0) return `${base} · просрочено`;
  if (daysLeft === 0) return `${base} · сегодня`;
  if (daysLeft === 1) return `${base} · завтра`;
  return base;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Неизвестная ошибка';
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthChecking, setIsAuthChecking] = useState(true);
  const [logoutNotice, setLogoutNotice] = useState('');

  const [activePage, setActivePage] = useState<Page>('overview');
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [weekInfo, setWeekInfo] = useState<WeekInfo | null>(null);
  const [plan, setPlan] = useState<SchedulePlan | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const activeTasks = useMemo(
    () => tasks.filter((task) => ['todo', 'in_progress', 'blocked'].includes(task.status)),
    [tasks]
  );
  const historyTasks = useMemo(
    () => tasks.filter((task) => ['completed', 'cancelled'].includes(task.status)),
    [tasks]
  );
  const overdueTasks = useMemo(
    () =>
      activeTasks.filter(
        (task) => task.deadline !== null && new Date(task.deadline) < new Date()
      ),
    [activeTasks]
  );
  const lessonsToday = useMemo(() => {
    const todayISO = new Date().toISOString().slice(0, 10);
    return lessons.filter((lesson) => (lesson.next_date ?? '').slice(0, 10) === todayISO);
  }, [lessons]);

  const refreshData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [loadedTasks, loadedEvents, loadedLessons, loadedWeek] = await Promise.all([
        getTasks(),
        getEvents(),
        getLessons().catch(() => []),
        getWeekInfo().catch(() => null),
      ]);
      setTasks(loadedTasks);
      setEvents(loadedEvents);
      setLessons(loadedLessons);
      setWeekInfo(loadedWeek);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setIsAuthChecking(false);
      return;
    }

    getCurrentUser()
      .then((currentUser) => {
        setUser(currentUser);
        return refreshData();
      })
      .catch(() => {
        clearToken();
        setUser(null);
      })
      .finally(() => setIsAuthChecking(false));
  }, [refreshData]);

  function handleLogout(notice: string = '') {
    clearToken();
    setUser(null);
    setTasks([]);
    setEvents([]);
    setLessons([]);
    setPlan(null);
    setLogoutNotice(notice);
  }

  // Авто-выход после длительного бездействия
  useEffect(() => {
    if (!user) return;

    let lastActivity = Date.now();

    const updateActivity = () => {
      lastActivity = Date.now();
    };

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'keydown',
      'click',
      'scroll',
      'touchstart',
    ];
    activityEvents.forEach((eventName) => {
      window.addEventListener(eventName, updateActivity, { passive: true });
    });

    const interval = window.setInterval(() => {
      const idleMs = Date.now() - lastActivity;
      if (idleMs > IDLE_TIMEOUT_MINUTES * 60_000) {
        handleLogout('Вы давно не были активны — войдите заново.');
      }
    }, 30_000);

    return () => {
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, updateActivity);
      });
      window.clearInterval(interval);
    };
  }, [user]);

  async function changeTaskStatus(taskId: string, status: ApiTaskStatus) {
    try {
      const updated = await updateTaskStatus(taskId, status);
      setTasks((previous) => previous.map((task) => (task.id === taskId ? updated : task)));
    } catch (statusError) {
      setError(getErrorMessage(statusError));
    }
  }

  async function handleSyncTimetable() {
    try {
      setIsLoading(true);
      setError('');
      await syncIntegration('IIS');
      await refreshData();
      setMessage('Расписание обновлено.');
    } catch (syncError) {
      setError(`Не удалось обновить расписание: ${getErrorMessage(syncError)}`);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleImportSchedule(file: File) {
    try {
      setIsLoading(true);
      setError('');
      const text = await file.text();
      const data: unknown = JSON.parse(text);
      const result = await importSchedule(data);
      await refreshData();
      setMessage(`Файл загружен: занятий — ${result.synced_items}.`);
    } catch (importError) {
      setError(`Не удалось загрузить файл: ${getErrorMessage(importError)}`);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleBuildPlan() {
    try {
      setIsLoading(true);
      setError('');
      const builtPlan = await rebuildSchedule();
      setPlan(builtPlan);
      setMessage('План готов.');
    } catch (planError) {
      setError(`Не удалось построить план: ${getErrorMessage(planError)}`);
    } finally {
      setIsLoading(false);
    }
  }

  if (isAuthChecking) {
    return <div className="auth-checking">Загрузка…</div>;
  }

  if (!user) {
    return (
      <AuthScreen
        notice={logoutNotice}
        onSuccess={(authUser) => {
          setUser(authUser);
          setLogoutNotice('');
          void refreshData();
        }}
      />
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">Ассистент</div>
          <nav className="nav">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={`nav-link ${activePage === item.id ? 'active' : ''}`}
                onClick={() => {
                  setActivePage(item.id);
                  setMessage('');
                  setError('');
                }}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="user-box">
            <span className="user-name">{user.username}</span>
            <button className="link-button" onClick={() => handleLogout()}>
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="app-content">
        {(message || error) && (
          <div className="notices">
            {message && <div className="notice">{message}</div>}
            {error && <div className="notice error">{error}</div>}
          </div>
        )}

        {activePage === 'overview' && (
          <OverviewPage
            username={user.username}
            tasksCount={activeTasks.length}
            overdueCount={overdueTasks.length}
            lessonsToday={lessonsToday}
            todayTasks={activeTasks.filter((task) => task.scheduled_start !== null)}
            plan={plan}
            isLoading={isLoading}
            onGoToTasks={() => setActivePage('tasks')}
            onGoToTimetable={() => setActivePage('timetable')}
          />
        )}

        {activePage === 'tasks' && (
          <TasksPage
            tasks={tasks}
            onStatusChange={changeTaskStatus}
            onCreate={async (payload) => {
              const created = await createTaskApi(payload);
              setTasks((previous) => [...previous, created]);
            }}
          />
        )}

        {activePage === 'timetable' && (
          <TimetablePage
            lessons={lessons}
            weekInfo={weekInfo}
            isLoading={isLoading}
            onSync={() => void handleSyncTimetable()}
            onImport={(file) => void handleImportSchedule(file)}
          />
        )}

        {activePage === 'plan' && (
          <PlanPage
            plan={plan}
            events={events}
            isLoading={isLoading}
            onBuild={() => void handleBuildPlan()}
            onCreateEvent={async (payload) => {
              const created = await createEventApi(payload);
              setEvents((previous) => [...previous, created]);
            }}
          />
        )}

        {activePage === 'history' && (
          <HistoryPage tasks={historyTasks} onStatusChange={changeTaskStatus} />
        )}
      </main>
    </div>
  );
}

function AuthScreen({ notice, onSuccess }: { notice?: string; onSuccess: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(notice ?? '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit() {
    try {
      setIsSubmitting(true);
      setError('');
      const response =
        mode === 'login'
          ? await loginApi(username.trim(), password)
          : await registerApi(username.trim(), password);
      setToken(response.token);
      onSuccess(response.user);
    } catch (submitError) {
      setError(getErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-screen">
      <form
        className="auth-card"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSubmit();
        }}
      >
        <div className="brand auth-brand">Ассистент</div>
        <p className="auth-subtitle">Личные задачи, дедлайны и расписание в одном месте.</p>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
          >
            Вход
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
          >
            Регистрация
          </button>
        </div>

        <label className="field">
          <span>Имя</span>
          <input
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="Как вас зовут"
          />
        </label>

        <label className="field">
          <span>Пароль</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            placeholder="Минимум 4 символа"
          />
        </label>

        {error && <div className="notice error">{error}</div>}

        <button className="button primary full" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
        </button>

        <p className="auth-hint">
          Есть демо-аккаунт: <strong>demo / demo</strong>
        </p>
      </form>
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

function OverviewPage({
  username,
  tasksCount,
  overdueCount,
  lessonsToday,
  todayTasks,
  plan,
  isLoading,
  onGoToTasks,
  onGoToTimetable,
}: {
  username: string;
  tasksCount: number;
  overdueCount: number;
  lessonsToday: Lesson[];
  todayTasks: ApiTask[];
  plan: SchedulePlan | null;
  isLoading: boolean;
  onGoToTasks: () => void;
  onGoToTimetable: () => void;
}) {
  const dateToday = new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  return (
    <section className="page">
      <h1 className="page-title">Привет, {username}</h1>
      <p className="page-subtitle">Сегодня {dateToday}.</p>

      <div className="stats-row">
        <StatCard label="Активные задачи" value={tasksCount} hint={overdueCount > 0 ? `Просрочено: ${overdueCount}` : 'Всё под контролем'} />
        <StatCard label="Занятий сегодня" value={lessonsToday.length} />
        <StatCard label="Запланировано" value={plan ? plan.slots.length : 0} hint="слотов в плане" />
      </div>

      <div className="two-columns">
        <div className="card">
          <h3 className="card-title">Сегодня в расписании</h3>
          {lessonsToday.length === 0 ? (
            <div className="empty">
              Занятий сегодня нет.
              <button className="link-button" onClick={onGoToTimetable}>
                Открыть расписание
              </button>
            </div>
          ) : (
            <ul className="lesson-list compact">
              {lessonsToday.map((lesson) => (
                <LessonRow key={lesson.id} lesson={lesson} />
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h3 className="card-title">Запланированные задачи</h3>
          {todayTasks.length === 0 ? (
            <div className="empty">
              План ещё не построен.
              <button className="link-button" onClick={onGoToTasks}>
                Добавить задачу
              </button>
            </div>
          ) : (
            <ul className="task-list">
              {todayTasks.map((task) => (
                <li key={task.id} className="task-row">
                  <div>
                    <strong>{task.title}</strong>
                    <span className="task-meta">{formatClock(task.scheduled_start)} — {formatClock(task.scheduled_end)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {isLoading && <div className="empty">Обновляем…</div>}
        </div>
      </div>
    </section>
  );
}

function LessonRow({ lesson, showWeeks = false }: { lesson: Lesson; showWeeks?: boolean }) {
  return (
    <li className="lesson-row">
      <span className="lesson-time">
        {lesson.start_time}–{lesson.end_time}
      </span>
      <div className="lesson-body">
        <strong className="lesson-subject">
          {lesson.subject}
          {lesson.subgroup > 0 && (
            <span className={`subgroup-badge ${lesson.subgroup === 1 ? 's1' : 's2'}`}>
              {lesson.subgroup} подгр.
            </span>
          )}
        </strong>
        <span className="lesson-meta">
          {[
            (lessonTypeLabels[lesson.lesson_type] ?? null) || (lesson.lesson_type || null),
            lesson.auditory && `ауд. ${lesson.auditory}`,
            lesson.teacher,
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
        {showWeeks && lesson.week_numbers.length > 0 && (
          <span className="lesson-weeks">недели: {lesson.week_numbers.join(', ')}</span>
        )}
      </div>
    </li>
  );
}

function TasksPage({
  tasks,
  onStatusChange,
  onCreate,
}: {
  tasks: ApiTask[];
  onStatusChange: (taskId: string, status: ApiTaskStatus) => void;
  onCreate: (payload: { title: string; priority: number; estimated_minutes: number; deadline: string | null; description: string | null }) => Promise<void>;
}) {
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('3');
  const [estimate, setEstimate] = useState('60');
  const [deadlineDate, setDeadlineDate] = useState('');
  const [deadlineTime, setDeadlineTime] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const activeTasks = tasks.filter((task) => ['todo', 'in_progress', 'blocked'].includes(task.status));

  async function handleCreate() {
    try {
      setIsSubmitting(true);
      setError('');
      await onCreate({
        title: title.trim(),
        priority: Number(priority),
        estimated_minutes: Number(estimate),
        deadline:
          deadlineDate
            ? new Date(`${deadlineDate}T${deadlineTime || '23:59'}`).toISOString()
            : null,
        description: description.trim() || null,
      });
      setTitle('');
      setDescription('');
      setDeadlineDate('');
      setDeadlineTime('');
    } catch (createError) {
      setError(getErrorMessage(createError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="page">
      <h1 className="page-title">Задачи</h1>
      <p className="page-subtitle">Ваши личные дедлайны и работы. Завершённые попадают в историю.</p>

      <div className="card">
        <h3 className="card-title">Новая задача</h3>
        <div className="form-grid">
          <label className="field span-2">
            <span>Что нужно сделать</span>
            <input
              className="input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Например: доделать отчёт"
            />
          </label>
          <label className="field">
            <span>Важность</span>
            <select className="input" value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="1">Высокая</option>
              <option value="2">Повышенная</option>
              <option value="3">Обычная</option>
              <option value="4">Низкая</option>
            </select>
          </label>
          <label className="field">
            <span>Оценка, минут</span>
            <input
              className="input"
              type="number"
              min={15}
              step={15}
              value={estimate}
              onChange={(event) => setEstimate(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Дедлайн — дата</span>
            <input
              className="input"
              type="date"
              value={deadlineDate}
              onChange={(event) => setDeadlineDate(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Время</span>
            <input
              className="input"
              type="time"
              value={deadlineTime}
              onChange={(event) => setDeadlineTime(event.target.value)}
            />
          </label>
          <label className="field span-2">
            <span>Заметка</span>
            <textarea
              className="input"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
        </div>
        {error && <div className="notice error">{error}</div>}
        <button
          className="button primary"
          disabled={isSubmitting || title.trim().length === 0}
          onClick={() => void handleCreate()}
        >
          {isSubmitting ? 'Добавляем…' : 'Добавить задачу'}
        </button>
      </div>

      <div className="card">
        <h3 className="card-title">Активные · {activeTasks.length}</h3>
        {activeTasks.length === 0 ? (
          <div className="empty">Пока нет активных задач — самое время отдохнуть.</div>
        ) : (
          <ul className="task-list">
            {activeTasks.map((task) => (
              <li key={task.id} className="task-row">
                <div className="task-main">
                  <strong>{task.title}</strong>
                  {task.description && <span className="task-description">{task.description}</span>}
                  <span className="task-meta">
                    {formatDeadline(task.deadline)} · {priorityLabels[task.priority]} · ~{task.estimated_minutes} мин
                  </span>
                </div>
                <div className="task-actions">
                  <button className="button small success" onClick={() => onStatusChange(task.id, 'completed')}>
                    Выполнено
                  </button>
                  <button className="button small" onClick={() => onStatusChange(task.id, 'in_progress')}>
                    В работу
                  </button>
                  <button className="button small" onClick={() => onStatusChange(task.id, 'cancelled')}>
                    Отменить
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function TimetablePage({
  lessons,
  weekInfo,
  isLoading,
  onSync,
  onImport,
}: {
  lessons: Lesson[];
  weekInfo: WeekInfo | null;
  isLoading: boolean;
  onSync: () => void;
  onImport: (file: File) => void;
}) {
  const [selectedWeek, setSelectedWeek] = useState<number | 'all' | null>(null);
  const [subgroupFilter, setSubgroupFilter] = useState<'all' | 0 | 1 | 2>('all');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // По умолчанию показываем текущую учебную неделю
  const effectiveWeek: number | 'all' =
    selectedWeek ?? weekInfo?.current_week ?? 'all';

  const subgroupFiltered = useMemo(() => {
    if (subgroupFilter === 'all') {
      return lessons;
    }
    return lessons.filter((lesson) => lesson.subgroup === subgroupFilter);
  }, [lessons, subgroupFilter]);

  const visibleLessons = useMemo(() => {
    if (effectiveWeek !== 'all') {
      // Конкретная неделя — появления, чья дата попадает в эту учебную неделю.
      // Физическая неделя одна, поэтому каждое занятие встречается один раз.
      return subgroupFiltered.filter((lesson) => lesson.week === effectiveWeek);
    }

    // «Все недели» — шаблон расписания: уникальные занятия,
    // недели схлопываются в один список. Подгруппа входит в ключ,
    // чтобы пары разных подгрупп не склеились.
    const template = new Map<string, Lesson>();
    for (const lesson of subgroupFiltered) {
      const key = `${lesson.subject}|${lesson.day_of_week}|${lesson.start_time}|${lesson.end_time}|${lesson.auditory}|${lesson.subgroup}`;
      const existing = template.get(key);
      if (!existing) {
        template.set(key, { ...lesson, week_numbers: [...lesson.week_numbers] });
      } else {
        const merged = new Set([...existing.week_numbers, ...lesson.week_numbers]);
        existing.week_numbers = [...merged].sort((a, b) => a - b);
      }
    }
    return [...template.values()];
  }, [subgroupFiltered, effectiveWeek]);

  const grouped = useMemo(() => {
    const byDay = new Map<string, Lesson[]>();
    for (const day of WEEK_DAYS) {
      byDay.set(day, []);
    }
    for (const lesson of visibleLessons) {
      const day = lesson.day_of_week ?? 'Воскресенье';
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day)!.push(lesson);
    }
    return byDay;
  }, [visibleLessons]);

  const hasLessons = visibleLessons.length > 0;
  const currentWeek = weekInfo?.current_week ?? null;

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Расписание</h1>
          <p className="page-subtitle">
            Занятия по учебным неделям.
            {currentWeek && (
              <>
                {' '}
                Сейчас <strong>неделя {currentWeek}</strong>.
              </>
            )}
          </p>
        </div>
        <div className="head-actions">
          <button className="button" disabled={isLoading} onClick={() => fileInputRef.current?.click()}>
            Загрузить из файла
          </button>
          <button className="button primary" disabled={isLoading} onClick={onSync}>
            {isLoading ? 'Обновляем…' : 'Обновить с портала'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                onImport(file);
              }
              event.target.value = '';
            }}
          />
        </div>
      </div>

      <div className="week-switcher">
        {[1, 2, 3, 4].map((week) => (
          <button
            key={week}
            className={`week-chip ${effectiveWeek === week ? 'active' : ''}`}
            onClick={() => setSelectedWeek(week)}
          >
            Неделя {week}
            {currentWeek === week && <span className="chip-now">сейчас</span>}
          </button>
        ))}
        <button
          className={`week-chip ${effectiveWeek === 'all' ? 'active' : ''}`}
          onClick={() => setSelectedWeek('all')}
        >
          Все недели
        </button>
      </div>

      <div className="subgroup-switcher">
        <span className="switcher-label">Пары:</span>
        {([
          ['all', 'Все'],
          [0, 'Общие'],
          [1, '1 подгруппа'],
          [2, '2 подгруппа'],
        ] as Array<['all' | 0 | 1 | 2, string]>).map(([value, label]) => (
          <button
            key={String(value)}
            className={`subgroup-chip ${subgroupFilter === value ? 'active' : ''}`}
            onClick={() => setSubgroupFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {!hasLessons && (
        <div className="empty card">
          Расписание на выбранную неделю пустое. Можно обновить его с портала или
          загрузить файл с расписанием группы.
        </div>
      )}

      <div className="week-grid">
        {WEEK_DAYS.map((day) => {
          const dayLessons = grouped.get(day) ?? [];
          const isToday = WEEK_DAYS[(new Date().getDay() + 6) % 7] === day;
          return (
            <div key={day} className={`day-card ${isToday ? 'today' : ''} ${dayLessons.length === 0 ? 'empty-day' : ''}`}>
              <h4 className="day-name">
                {day} {isToday && <span className="today-badge">сегодня</span>}
              </h4>
              {dayLessons.length === 0 ? (
                <span className="day-off">свободно</span>
              ) : (
                <ul className="lesson-list">
                  {dayLessons.map((lesson) => (
                    <LessonRow
                      key={lesson.id}
                      lesson={lesson}
                      showWeeks={effectiveWeek === 'all'}
                    />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PlanPage({
  plan,
  events,
  isLoading,
  onBuild,
  onCreateEvent,
}: {
  plan: SchedulePlan | null;
  events: ApiEvent[];
  isLoading: boolean;
  onBuild: () => void;
  onCreateEvent: (payload: { title: string; start_at: string; end_at: string; source?: string }) => Promise<void>;
}) {
  const [title, setTitle] = useState('');
  const [date, setDate] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const upcomingEvents = useMemo(
    () =>
      events
        .filter((event) => new Date(event.end_at) >= new Date())
        .sort((a, b) => a.start_at.localeCompare(b.start_at))
        .slice(0, 8),
    [events]
  );

  async function handleCreateEvent() {
    try {
      setIsSubmitting(true);
      setError('');
      await onCreateEvent({
        title: title.trim(),
        start_at: new Date(`${date}T${startTime}`).toISOString(),
        end_at: new Date(`${date}T${endTime}`).toISOString(),
        source: 'manual',
      });
      setTitle('');
      setDate('');
      setStartTime('');
      setEndTime('');
    } catch (createError) {
      setError(getErrorMessage(createError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">План</h1>
          <p className="page-subtitle">
            Ассистент раскладывает задачи по свободным окнам между занятиями и делами.
          </p>
        </div>
        <button className="button primary" disabled={isLoading} onClick={onBuild}>
          {isLoading ? 'Строим…' : 'Построить план'}
        </button>
      </div>

      <div className="card">
        <h3 className="card-title">План на ближайшие дни</h3>
        {!plan && <div className="empty">Нажмите «Построить план» — подберём время для каждой задачи.</div>}
        {plan && plan.slots.length === 0 && (
          <div className="empty">Задач для планирования нет. Добавьте их на странице «Задачи».</div>
        )}
        {plan && plan.slots.length > 0 && (
          <ul className="timeline">
            {plan.slots.map((slot) => (
              <li
                key={`${slot.task_id}-${slot.start_at}`}
                className={`timeline-item ${slot.task_id === plan.prime_task_id ? 'prime' : ''}`}
              >
                <span className="timeline-time">
                  {formatDateTime(slot.start_at)} — {formatClock(slot.end_at)}
                </span>
                <div className="timeline-body">
                  <strong>{slot.title}</strong>
                  {slot.task_id === plan.prime_task_id && (
                    <span className="prime-badge">главная задача</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="two-columns">
        <div className="card">
          <h3 className="card-title">Добавить занятое время</h3>
          <p className="card-note">Встречи, консультации, дорога — всё, что нельзя двигать.</p>
          <div className="form-grid">
            <label className="field span-2">
              <span>Название</span>
              <input
                className="input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Например: консультация"
              />
            </label>
            <label className="field">
              <span>Дата</span>
              <input className="input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
            <label className="field">
              <span>Начало</span>
              <input className="input" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
            </label>
            <label className="field">
              <span>Конец</span>
              <input className="input" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
            </label>
          </div>
          {error && <div className="notice error">{error}</div>}
          <button
            className="button primary"
            disabled={isSubmitting || !title.trim() || !date || !startTime || !endTime}
            onClick={() => void handleCreateEvent()}
          >
            {isSubmitting ? 'Добавляем…' : 'Добавить'}
          </button>
        </div>

        <div className="card">
          <h3 className="card-title">Ближайшие дела</h3>
          {upcomingEvents.length === 0 ? (
            <div className="empty">Занятых интервалов нет.</div>
          ) : (
            <ul className="event-list">
              {upcomingEvents.map((event) => (
                <li key={event.id} className="event-row">
                  <div>
                    <strong>{event.title}</strong>
                    <span className="task-meta">
                      {formatDateTime(event.start_at)} — {formatClock(event.end_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function HistoryPage({
  tasks,
  onStatusChange,
}: {
  tasks: ApiTask[];
  onStatusChange: (taskId: string, status: ApiTaskStatus) => void;
}) {
  return (
    <section className="page">
      <h1 className="page-title">История</h1>
      <p className="page-subtitle">Выполненные и отменённые задачи.</p>

      <div className="card">
        {tasks.length === 0 ? (
          <div className="empty">История пока пуста.</div>
        ) : (
          <ul className="task-list">
            {tasks.map((task) => (
              <li key={task.id} className="task-row">
                <div className="task-main">
                  <strong>{task.title}</strong>
                  <span className="task-meta">
                    {statusLabels[task.status]} · {formatDeadline(task.deadline)}
                  </span>
                </div>
                <div className="task-actions">
                  {task.status === 'cancelled' && (
                    <button className="button small" onClick={() => onStatusChange(task.id, 'todo')}>
                      Вернуть
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default App;
