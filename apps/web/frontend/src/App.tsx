import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { clearToken, getToken, setToken } from './api/client';
import { getCurrentUser, login as loginApi, register as registerApi } from './api/auth';
import type { AuthUser } from './api/auth';
import { getEvents, createEvent as createEventApi } from './api/events';
import type { ApiEvent } from './api/events';
import {
  getCurrentGroup,
  getLessons,
  getWeekInfo,
  importScheduleFile,
  syncGroup,
  syncIntegration,
} from './api/integrations';
import type { CurrentGroupInfo, Lesson, WeekInfo } from './api/integrations';
import { rebuildSchedule } from './api/schedule';
import type { SchedulePlan } from './api/schedule';
import { createTask as createTaskApi, getTasks, updateTaskStatus } from './api/tasks';
import type { ApiTask, ApiTaskStatus } from './types/api';
import { SettingsProvider } from './settings-provider';
import { useSettings } from './settings';
import type { TFunc } from './settings';

type Page = 'overview' | 'tasks' | 'timetable' | 'calendar' | 'plan' | 'history';

const IDLE_TIMEOUT_MINUTES = 30;

const navItems: Array<{ id: Page; labelKey: string }> = [
  { id: 'overview', labelKey: 'nav.overview' },
  { id: 'tasks', labelKey: 'nav.tasks' },
  { id: 'timetable', labelKey: 'nav.timetable' },
  { id: 'calendar', labelKey: 'nav.calendar' },
  { id: 'plan', labelKey: 'nav.plan' },
  { id: 'history', labelKey: 'nav.history' },
];

const WEEK_DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
const WEEK_DAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const statusLabelKeys: Record<ApiTaskStatus, string> = {
  todo: 'status.todo',
  in_progress: 'status.in_progress',
  completed: 'status.completed',
  cancelled: 'status.cancelled',
  blocked: 'status.blocked',
};

const priorityLabelKeys: Record<number, string> = {
  1: 'tasks.priority.1',
  2: 'tasks.priority.2',
  3: 'tasks.priority.3',
  4: 'tasks.priority.4',
};

const XLSX_ACCEPT = '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function formatDateTime(value: string | null, locale: string): string {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleString(locale, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatClock(value: string | null, locale: string): string {
  if (!value) return '—';
  const date = new Date(value);
  return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

function formatDeadline(value: string | null, t: TFunc, locale: string): string {
  if (!value) return t('task.noDeadline');
  const date = new Date(value);
  const today = new Date();
  const daysLeft = Math.ceil((date.getTime() - today.getTime()) / 86_400_000);
  const base = date.toLocaleString(locale, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
  if (daysLeft < 0) return `${base} · ${t('task.overdue')}`;
  if (daysLeft === 0) return `${base} · ${t('task.today')}`;
  if (daysLeft === 1) return `${base} · ${t('task.tomorrow')}`;
  return base;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Неизвестная ошибка';
}

function App() {
  return (
    <SettingsProvider>
      <AppInner />
    </SettingsProvider>
  );
}

function AppInner() {
  const { t, locale } = useSettings();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthChecking, setIsAuthChecking] = useState(true);
  const [logoutNotice, setLogoutNotice] = useState('');

  const [activePage, setActivePage] = useState<Page>('overview');
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [weekInfo, setWeekInfo] = useState<WeekInfo | null>(null);
  const [currentGroup, setCurrentGroup] = useState<CurrentGroupInfo | null>(null);
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
      const [loadedTasks, loadedEvents, loadedLessons, loadedWeek, loadedGroup] =
        await Promise.all([
          getTasks(),
          getEvents(),
          getLessons().catch(() => []),
          getWeekInfo().catch(() => null),
          getCurrentGroup().catch(() => null),
        ]);
      setTasks(loadedTasks);
      setEvents(loadedEvents);
      setLessons(loadedLessons);
      setWeekInfo(loadedWeek);
      setCurrentGroup(loadedGroup);
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
    setCurrentGroup(null);
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
        handleLogout(t('notice.idle'));
      }
    }, 30_000);

    return () => {
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, updateActivity);
      });
      window.clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, locale]);

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
      setMessage(t('timetable.updated'));
    } catch (syncError) {
      setError(t('timetable.updateFailed', { error: getErrorMessage(syncError) }));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleImportSchedule(file: File, groupNumber: string) {
    try {
      setIsLoading(true);
      setError('');
      const result = await importScheduleFile(file, groupNumber);
      await refreshData();
      const provider = result.provider && result.provider !== 'import' ? result.provider : '';
      setMessage(
        provider
          ? t('timetable.groupLoaded', { group: provider, count: result.synced_items })
          : t('timetable.imported', { count: result.synced_items })
      );
    } catch (importError) {
      setError(t('timetable.importFailed', { error: getErrorMessage(importError) }));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSyncGroup(group: string) {
    try {
      setIsLoading(true);
      setError('');
      const result = await syncGroup(group);
      await refreshData();
      setMessage(
        t('timetable.groupLoaded', { group: result.provider, count: result.synced_items })
      );
    } catch (groupError) {
      setError(t('timetable.groupFailed', { error: getErrorMessage(groupError) }));
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
      setMessage(t('plan.ready'));
    } catch (planError) {
      setError(t('plan.failed', { error: getErrorMessage(planError) }));
    } finally {
      setIsLoading(false);
    }
  }

  if (isAuthChecking) {
    return <div className="auth-checking">{t('loading')}</div>;
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
                {t(item.labelKey)}
              </button>
            ))}
          </nav>
          <div className="user-box">
            <SettingsGear />
            <span className="user-name">{user.username}</span>
            <button className="link-button" onClick={() => handleLogout()}>
              {t('action.logout')}
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
            currentGroup={currentGroup}
            isLoading={isLoading}
            onSync={() => void handleSyncTimetable()}
            onImport={(file, group) => void handleImportSchedule(file, group)}
            onSyncGroup={(group) => void handleSyncGroup(group)}
          />
        )}

        {activePage === 'calendar' && (
          <CalendarPage lessons={lessons} tasks={tasks} weekInfo={weekInfo} />
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

function SettingsGear() {
  const { t, theme, setTheme, lang, setLang, fontSize, setFontSize } = useSettings();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onDocClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [isOpen]);

  return (
    <div className="settings-root" ref={rootRef}>
      <button
        type="button"
        className={`gear-button ${isOpen ? 'open' : ''}`}
        title={t('settings.title')}
        aria-label={t('settings.title')}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((previous) => !previous)}
      >
        <svg
          className="gear-icon"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58 c0.18-0.14,0.23-0.41,0.12-0.61l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81 c-0.04-0.24-0.24-0.41-0.48-0.41h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33 c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87C2.62,9.08,2.66,9.34,2.86,9.49l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12 s0.02,0.64,0.07,0.94l-2.03,1.58c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96 c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54 c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z" />
        </svg>
      </button>

      {isOpen && (
        <div className="settings-panel">
          <h3 className="settings-panel-title">{t('settings.title')}</h3>

          <div className="settings-section">
            <span className="settings-label">{t('settings.theme')}</span>
            <div className="settings-options">
              <button
                type="button"
                className={`settings-chip ${theme === 'dark' ? 'active' : ''}`}
                onClick={() => setTheme('dark')}
              >
                {t('settings.theme.dark')}
              </button>
              <button
                type="button"
                className={`settings-chip ${theme === 'light' ? 'active' : ''}`}
                onClick={() => setTheme('light')}
              >
                {t('settings.theme.light')}
              </button>
            </div>
          </div>

          <div className="settings-section">
            <span className="settings-label">{t('settings.language')}</span>
            <div className="settings-options">
              <button
                type="button"
                className={`settings-chip ${lang === 'ru' ? 'active' : ''}`}
                onClick={() => setLang('ru')}
              >
                {t('settings.language.ru')}
              </button>
              <button
                type="button"
                className={`settings-chip ${lang === 'en' ? 'active' : ''}`}
                onClick={() => setLang('en')}
              >
                {t('settings.language.en')}
              </button>
            </div>
          </div>

          <div className="settings-section">
            <span className="settings-label">{t('settings.fontSize')}</span>
            <div className="settings-options">
              {(['sm', 'md', 'lg'] as const).map((size) => (
                <button
                  key={size}
                  type="button"
                  className={`settings-chip ${fontSize === size ? 'active' : ''}`}
                  onClick={() => setFontSize(size)}
                >
                  {t(`settings.fontSize.${size}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AuthScreen({ notice, onSuccess }: { notice?: string; onSuccess: (user: AuthUser) => void }) {
  const { t } = useSettings();
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
        <p className="auth-subtitle">{t('auth.subtitle')}</p>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
          >
            {t('auth.login')}
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
          >
            {t('auth.register')}
          </button>
        </div>

        <label className="field">
          <span>{t('auth.name')}</span>
          <input
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder={t('auth.namePlaceholder')}
          />
        </label>

        <label className="field">
          <span>{t('auth.password')}</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            placeholder={t('auth.passwordPlaceholder')}
          />
        </label>

        {error && <div className="notice error">{error}</div>}

        <button className="button primary full" type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? t('auth.submitting')
            : mode === 'login'
              ? t('auth.submit.login')
              : t('auth.submit.register')}
        </button>

        <p className="auth-hint">
          {t('auth.demo')}: <strong>demo / demo</strong>
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
  const { t, locale } = useSettings();
  const dateToday = new Date().toLocaleDateString(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  return (
    <section className="page">
      <h1 className="page-title">{t('overview.hello', { name: username })}</h1>
      <p className="page-subtitle">{t('overview.today', { date: dateToday })}</p>

      <div className="stats-row">
        <StatCard
          label={t('overview.activeTasks')}
          value={tasksCount}
          hint={
            overdueCount > 0 ? t('overview.overdue', { count: overdueCount }) : t('overview.allGood')
          }
        />
        <StatCard label={t('overview.lessonsToday')} value={lessonsToday.length} />
        <StatCard
          label={t('overview.planned')}
          value={plan ? plan.slots.length : 0}
          hint={t('overview.slotsHint')}
        />
      </div>

      <div className="two-columns">
        <div className="card">
          <h3 className="card-title">{t('overview.todayLessons')}</h3>
          {lessonsToday.length === 0 ? (
            <div className="empty">
              {t('overview.noLessons')}{' '}
              <button className="link-button" onClick={onGoToTimetable}>
                {t('overview.openTimetable')}
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
          <h3 className="card-title">{t('overview.plannedTasks')}</h3>
          {todayTasks.length === 0 ? (
            <div className="empty">
              {t('overview.noPlan')}{' '}
              <button className="link-button" onClick={onGoToTasks}>
                {t('overview.addTask')}
              </button>
            </div>
          ) : (
            <ul className="task-list">
              {todayTasks.map((task) => (
                <li key={task.id} className="task-row">
                  <div>
                    <strong>{task.title}</strong>
                    <span className="task-meta">
                      {formatClock(task.scheduled_start, locale)} —{' '}
                      {formatClock(task.scheduled_end, locale)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {isLoading && <div className="empty">{t('state.updating')}</div>}
        </div>
      </div>
    </section>
  );
}

function LessonRow({ lesson, showWeeks = false }: { lesson: Lesson; showWeeks?: boolean }) {
  const { t } = useSettings();

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
              {t('timetable.subgroupBadge', { n: lesson.subgroup })}
            </span>
          )}
        </strong>
        <span className="lesson-meta">
          {[
            t(`lesson.${lesson.lesson_type}`) !== `lesson.${lesson.lesson_type}`
              ? t(`lesson.${lesson.lesson_type}`)
              : lesson.lesson_type || null,
            lesson.auditory && t('timetable.auditory', { auditory: lesson.auditory }),
            lesson.teacher,
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
        {showWeeks && lesson.week_numbers.length > 0 && (
          <span className="lesson-weeks">
            {t('timetable.weeks', { weeks: lesson.week_numbers.join(', ') })}
          </span>
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
  const { t, locale } = useSettings();
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
      <h1 className="page-title">{t('tasks.title')}</h1>
      <p className="page-subtitle">{t('tasks.subtitle')}</p>

      <div className="card">
        <h3 className="card-title">{t('tasks.new')}</h3>
        <div className="form-grid">
          <label className="field span-2">
            <span>{t('tasks.what')}</span>
            <input
              className="input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t('tasks.whatPlaceholder')}
            />
          </label>
          <label className="field">
            <span>{t('tasks.priority')}</span>
            <select className="input" value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="1">{t('tasks.priority.1')}</option>
              <option value="2">{t('tasks.priority.2')}</option>
              <option value="3">{t('tasks.priority.3')}</option>
              <option value="4">{t('tasks.priority.4')}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('tasks.estimate')}</span>
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
            <span>{t('tasks.deadlineDate')}</span>
            <input
              className="input"
              type="date"
              value={deadlineDate}
              onChange={(event) => setDeadlineDate(event.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('tasks.time')}</span>
            <input
              className="input"
              type="time"
              value={deadlineTime}
              onChange={(event) => setDeadlineTime(event.target.value)}
            />
          </label>
          <label className="field span-2">
            <span>{t('tasks.note')}</span>
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
          {isSubmitting ? t('tasks.creating') : t('tasks.create')}
        </button>
      </div>

      <div className="card">
        <h3 className="card-title">{t('tasks.active', { count: activeTasks.length })}</h3>
        {activeTasks.length === 0 ? (
          <div className="empty">{t('tasks.empty')}</div>
        ) : (
          <ul className="task-list">
            {activeTasks.map((task) => (
              <li key={task.id} className="task-row">
                <div className="task-main">
                  <strong>{task.title}</strong>
                  {task.description && <span className="task-description">{task.description}</span>}
                  <span className="task-meta">
                    {formatDeadline(task.deadline, t, locale)} · {t(priorityLabelKeys[task.priority] ?? 'tasks.priority.3')} · ~
                    {task.estimated_minutes} {t('task.minutes')}
                  </span>
                </div>
                <div className="task-actions">
                  <button className="button small success" onClick={() => onStatusChange(task.id, 'completed')}>
                    {t('tasks.complete')}
                  </button>
                  <button className="button small" onClick={() => onStatusChange(task.id, 'in_progress')}>
                    {t('tasks.start')}
                  </button>
                  <button className="button small" onClick={() => onStatusChange(task.id, 'cancelled')}>
                    {t('tasks.cancel')}
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
  currentGroup,
  isLoading,
  onSync,
  onImport,
  onSyncGroup,
}: {
  lessons: Lesson[];
  weekInfo: WeekInfo | null;
  currentGroup: CurrentGroupInfo | null;
  isLoading: boolean;
  onSync: () => void;
  onImport: (file: File, groupNumber: string) => void;
  onSyncGroup: (group: string) => void;
}) {
  const { t } = useSettings();
  const [selectedWeek, setSelectedWeek] = useState<number | 'all' | null>(null);
  const [subgroupFilter, setSubgroupFilter] = useState<'all' | 0 | 1 | 2>('all');
  const [groupNumber, setGroupNumber] = useState('');
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
      // Без дня недели (экзамены, консультации) — не подмешиваем в воскресенье,
      // собираем в отдельную секцию «По дате».
      const day = lesson.day_of_week ?? '__by_date__';
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day)!.push(lesson);
    }
    return byDay;
  }, [visibleLessons]);

  const datedLessons = useMemo(
    () =>
      (grouped.get('__by_date__') ?? [])
        .slice()
        .sort((a, b) => (a.next_date ?? '').localeCompare(b.next_date ?? '')),
    [grouped]
  );

  const hasLessons = visibleLessons.length > 0;
  const currentWeek = weekInfo?.current_week ?? null;
  const groupName = currentGroup?.group_number ?? '';

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('timetable.title')}</h1>
          <p className="page-subtitle group-subtitle">
            {groupName
              ? t('timetable.group', { group: groupName })
              : t('timetable.groupUnknown')}
          </p>
          <p className="page-subtitle">
            {t('timetable.subtitle')}{' '}
            {currentWeek && <>{t('timetable.weekNow', { week: currentWeek })}</>}
          </p>
        </div>
        <div className="head-actions">
          <div className="group-input">
            <input
              className="input"
              value={groupNumber}
              onChange={(event) => setGroupNumber(event.target.value)}
              placeholder={t('timetable.groupPlaceholder')}
              title={t('timetable.groupHint')}
            />
            <button
              className="button"
              disabled={isLoading || groupNumber.trim().length === 0}
              onClick={() => onSyncGroup(groupNumber.trim())}
            >
              {t('timetable.loadGroup')}
            </button>
          </div>
          <button
            className="button"
            disabled={isLoading}
            onClick={() => fileInputRef.current?.click()}
            title="XLSX"
          >
            {t('timetable.importFile')}
          </button>
          <button className="button primary" disabled={isLoading} onClick={onSync}>
            {isLoading ? t('timetable.syncing') : t('timetable.sync')}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={XLSX_ACCEPT}
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                onImport(file, groupNumber.trim());
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
            {t('timetable.week', { week })}
            {currentWeek === week && <span className="chip-now">{t('timetable.now')}</span>}
          </button>
        ))}
        <button
          className={`week-chip ${effectiveWeek === 'all' ? 'active' : ''}`}
          onClick={() => setSelectedWeek('all')}
        >
          {t('timetable.allWeeks')}
        </button>
      </div>

      <div className="subgroup-switcher">
        <span className="switcher-label">{t('timetable.lessons')}</span>
        {([
          ['all', 'timetable.subgroupAll'],
          [0, 'timetable.subgroupCommon'],
          [1, 'timetable.subgroup1'],
          [2, 'timetable.subgroup2'],
        ] as Array<['all' | 0 | 1 | 2, string]>).map(([value, labelKey]) => (
          <button
            key={String(value)}
            className={`subgroup-chip ${subgroupFilter === value ? 'active' : ''}`}
            onClick={() => setSubgroupFilter(value)}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>

      {!hasLessons && <div className="empty card">{t('timetable.empty')}</div>}

      <div className="week-grid">
        {WEEK_DAYS.map((day) => {
          const dayLessons = grouped.get(day) ?? [];
          const isToday = WEEK_DAYS[(new Date().getDay() + 6) % 7] === day;
          return (
            <div key={day} className={`day-card ${isToday ? 'today' : ''} ${dayLessons.length === 0 ? 'empty-day' : ''}`}>
              <h4 className="day-name">
                {t(`day.${day}`)} {isToday && <span className="today-badge">{t('timetable.today')}</span>}
              </h4>
              {dayLessons.length === 0 ? (
                <span className="day-off">{t('timetable.free')}</span>
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

      {datedLessons.length > 0 && (
        <div className="card">
          <h3 className="card-title">{t('timetable.dated')}</h3>
          <p className="card-note">{t('timetable.datedNote')}</p>
          <ul className="lesson-list dated">
            {datedLessons.map((lesson) => (
              <DatedLessonRow key={lesson.id} lesson={lesson} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function DatedLessonRow({ lesson }: { lesson: Lesson }) {
  const { t, locale } = useSettings();

  return (
    <li className="lesson-row dated">
      <span className="lesson-time">
        {(lesson.next_date ?? '').slice(8, 10)}.{(lesson.next_date ?? '').slice(5, 7)}
      </span>
      <div className="lesson-body">
        <strong className="lesson-subject">
          {lesson.subject}
          {lesson.subgroup > 0 && (
            <span className={`subgroup-badge ${lesson.subgroup === 1 ? 's1' : 's2'}`}>
              {t('timetable.subgroupBadge', { n: lesson.subgroup })}
            </span>
          )}
        </strong>
        <span className="lesson-meta">
          {[
            lesson.next_date ? formatClock(lesson.next_date, locale) : null,
            t(`lesson.${lesson.lesson_type}`) !== `lesson.${lesson.lesson_type}`
              ? t(`lesson.${lesson.lesson_type}`)
              : lesson.lesson_type || null,
            lesson.auditory && t('timetable.auditory', { auditory: lesson.auditory }),
            lesson.teacher,
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </div>
    </li>
  );
}

function academicWeekOf(dateISO: string, semesterStartISO: string | null | undefined): number | null {
  if (!semesterStartISO) return null;
  const day = new Date(`${dateISO}T00:00:00`);
  const start = new Date(`${semesterStartISO.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(day.getTime()) || Number.isNaN(start.getTime())) return null;
  // Учебные недели меняются по понедельникам: отсчёт от понедельника
  // недели начала семестра, иначе понедельник попадал бы в прошлую неделю
  const mondayOffset = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - mondayOffset);
  const diffDays = Math.floor((day.getTime() - start.getTime()) / 86_400_000);
  if (diffDays < 0) return 1;
  return (Math.floor(diffDays / 7) % 4) + 1;
}

function CalendarPage({
  lessons,
  tasks,
  weekInfo,
}: {
  lessons: Lesson[];
  tasks: ApiTask[];
  weekInfo: WeekInfo | null;
}) {
  const { t, locale } = useSettings();
  const now = new Date();
  const [monthCursor, setMonthCursor] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const days = useMemo(() => {
    const year = monthCursor.getFullYear();
    const month = monthCursor.getMonth();
    const first = new Date(year, month, 1);
    const mondayOffset = (first.getDay() + 6) % 7;
    const result: Date[] = [];
    const start = new Date(year, month, 1 - mondayOffset);
    for (let i = 0; i < 42; i += 1) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      result.push(day);
    }
    return result;
  }, [monthCursor]);

  const byDate = useMemo(() => {
    const lessonsByDate = new Map<string, Lesson[]>();
    for (const lesson of lessons) {
      const key = (lesson.next_date ?? '').slice(0, 10);
      if (!key) continue;
      if (!lessonsByDate.has(key)) lessonsByDate.set(key, []);
      lessonsByDate.get(key)!.push(lesson);
    }

    const plannedByDate = new Map<string, ApiTask[]>();
    const deadlinesByDate = new Map<string, ApiTask[]>();
    for (const task of tasks) {
      if (task.status === 'cancelled') continue;
      if (task.scheduled_start) {
        const key = task.scheduled_start.slice(0, 10);
        if (!plannedByDate.has(key)) plannedByDate.set(key, []);
        plannedByDate.get(key)!.push(task);
      }
      if (task.deadline) {
        const key = task.deadline.slice(0, 10);
        if (!deadlinesByDate.has(key)) deadlinesByDate.set(key, []);
        deadlinesByDate.get(key)!.push(task);
      }
    }
    return { lessonsByDate, plannedByDate, deadlinesByDate };
  }, [lessons, tasks]);

  const monthTitle = monthCursor.toLocaleDateString(locale, {
    month: 'long',
    year: 'numeric',
  });
  const todayISO = new Date().toISOString().slice(0, 10);
  const cursorMonth = monthCursor.getMonth();

  const selected = selectedDate
    ? {
        lessons: byDate.lessonsByDate.get(selectedDate) ?? [],
        planned: byDate.plannedByDate.get(selectedDate) ?? [],
        deadlines: byDate.deadlinesByDate.get(selectedDate) ?? [],
      }
    : null;

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('calendar.title')}</h1>
          <p className="page-subtitle">
            {t('calendar.subtitle')} {t('calendar.clickDay')}
          </p>
        </div>
        <div className="month-nav">
          <button
            className="button small"
            onClick={() => setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1))}
          >
            ←
          </button>
          <span className="month-title">{monthTitle}</span>
          <button
            className="button small"
            onClick={() => setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1))}
          >
            →
          </button>
        </div>
      </div>

      <div className="month-grid">
        {WEEK_DAYS_SHORT.map((weekday) => (
          <div key={weekday} className="month-weekday">{t(`dayShort.${weekday}`)}</div>
        ))}

        {days.map((day) => {
          const iso = day.toISOString().slice(0, 10);
          const isoLocal = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
          const outside = day.getMonth() !== cursorMonth;
          const week = academicWeekOf(isoLocal, weekInfo?.semester_start);
          const dayLessons = byDate.lessonsByDate.get(isoLocal) ?? [];
          const dayPlanned = byDate.plannedByDate.get(isoLocal) ?? [];
          const dayDeadlines = byDate.deadlinesByDate.get(isoLocal) ?? [];

          return (
            <button
              key={iso}
              className={[
                'cal-cell',
                outside ? 'outside' : '',
                isoLocal === todayISO ? 'today' : '',
                selectedDate === isoLocal ? 'selected' : '',
                dayLessons.length + dayPlanned.length + dayDeadlines.length > 0 ? 'has-items' : '',
              ].filter(Boolean).join(' ')}
              onClick={() => setSelectedDate(selectedDate === isoLocal ? null : isoLocal)}
            >
              <span className="cal-top">
                {week !== null && (
                  <span className="cal-week-badge">{t('calendar.weekShort', { week })}</span>
                )}
                <span className="cal-day-num">{day.getDate()}</span>
              </span>

              {(dayLessons.length > 0 || dayPlanned.length > 0 || dayDeadlines.length > 0) && (
                <span className="cal-summary">
                  {dayLessons.length > 0 && (
                    <span>
                      {dayLessons.length === 1
                        ? t('calendar.pair', { count: dayLessons.length })
                        : t('calendar.pairs', { count: dayLessons.length })}
                    </span>
                  )}
                  {dayPlanned.length > 0 && (
                    <span>{t('calendar.tasksShort', { count: dayPlanned.length })}</span>
                  )}
                  {dayDeadlines.length > 0 && (
                    <span className="has-deadline">
                      {t('calendar.deadlinesShort', { count: dayDeadlines.length })}
                    </span>
                  )}
                </span>
              )}
              {dayLessons.length > 0 && <span className="cal-hint">{dayLessons[0].subject}</span>}
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="cal-detail card">
          <div className="cal-detail-head">
            <strong className="cal-detail-day">{Number(selectedDate!.slice(8, 10))}</strong>
            <div className="cal-detail-sub">
              <span className="cal-detail-weekday">
                {new Date(`${selectedDate}T00:00:00`).toLocaleDateString(locale, { weekday: 'long' })}
              </span>
              <span className="cal-detail-month">
                {new Date(`${selectedDate}T00:00:00`).toLocaleDateString(locale, { month: 'long' })}
                {(() => {
                  const week = academicWeekOf(selectedDate!, weekInfo?.semester_start);
                  return week !== null ? ` · ${t('calendar.academicWeek', { week })}` : '';
                })()}
              </span>
            </div>
          </div>

          <div className="cal-section">
            <h4 className="cal-section-title">{t('calendar.university')}</h4>
            {selected.lessons.length === 0 ? (
              <span className="cal-section-empty">{t('calendar.lessons')}</span>
            ) : (
              <ul className="lesson-list">
                {selected.lessons
                  .slice()
                  .sort((a, b) => a.start_time.localeCompare(b.start_time))
                  .map((lesson) => (
                    <LessonRow key={lesson.id} lesson={lesson} />
                  ))}
              </ul>
            )}
          </div>

          <div className="cal-section">
            <h4 className="cal-section-title">{t('calendar.personal')}</h4>
            {selected.planned.length === 0 ? (
              <span className="cal-section-empty">{t('calendar.noPlanned')}</span>
            ) : (
              <ul className="task-list">
                {selected.planned.map((task) => (
                  <li key={task.id} className="task-row">
                    <div className="task-main">
                      <strong>{task.title}</strong>
                      <span className="task-meta">
                        {formatClock(task.scheduled_start, locale)} —{' '}
                        {formatClock(task.scheduled_end, locale)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="cal-section">
            <h4 className="cal-section-title">{t('calendar.deadlines')}</h4>
            {selected.deadlines.length === 0 ? (
              <span className="cal-section-empty">{t('calendar.noDeadlines')}</span>
            ) : (
              <ul className="task-list">
                {selected.deadlines.map((task) => (
                  <li key={task.id} className="task-row deadline">
                    <div className="task-main">
                      <strong>{task.title}</strong>
                      <span className="task-meta">
                        {formatClock(task.deadline, locale)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
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
  const { t, locale } = useSettings();
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
          <h1 className="page-title">{t('plan.title')}</h1>
          <p className="page-subtitle">{t('plan.subtitle')}</p>
        </div>
        <button className="button primary" disabled={isLoading} onClick={onBuild}>
          {isLoading ? t('plan.building') : t('plan.build')}
        </button>
      </div>

      <div className="card">
        <h3 className="card-title">{t('plan.upcoming')}</h3>
        {!plan && <div className="empty">{t('plan.empty')}</div>}
        {plan && plan.slots.length === 0 && <div className="empty">{t('plan.noTasks')}</div>}
        {plan && plan.slots.length > 0 && (
          <ul className="timeline">
            {plan.slots.map((slot) => (
              <li
                key={`${slot.task_id}-${slot.start_at}`}
                className={`timeline-item ${slot.task_id === plan.prime_task_id ? 'prime' : ''}`}
              >
                <span className="timeline-time">
                  {formatDateTime(slot.start_at, locale)} — {formatClock(slot.end_at, locale)}
                </span>
                <div className="timeline-body">
                  <strong>{slot.title}</strong>
                  {slot.task_id === plan.prime_task_id && (
                    <span className="prime-badge">{t('plan.prime')}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="two-columns">
        <div className="card">
          <h3 className="card-title">{t('plan.addBusy')}</h3>
          <p className="card-note">{t('plan.busyNote')}</p>
          <div className="form-grid">
            <label className="field span-2">
              <span>{t('plan.name')}</span>
              <input
                className="input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t('plan.namePlaceholder')}
              />
            </label>
            <label className="field">
              <span>{t('plan.date')}</span>
              <input className="input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
            <label className="field">
              <span>{t('plan.start')}</span>
              <input className="input" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
            </label>
            <label className="field">
              <span>{t('plan.end')}</span>
              <input className="input" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
            </label>
          </div>
          {error && <div className="notice error">{error}</div>}
          <button
            className="button primary"
            disabled={isSubmitting || !title.trim() || !date || !startTime || !endTime}
            onClick={() => void handleCreateEvent()}
          >
            {isSubmitting ? t('plan.adding') : t('plan.add')}
          </button>
        </div>

        <div className="card">
          <h3 className="card-title">{t('plan.next')}</h3>
          {upcomingEvents.length === 0 ? (
            <div className="empty">{t('plan.noEvents')}</div>
          ) : (
            <ul className="event-list">
              {upcomingEvents.map((event) => (
                <li key={event.id} className="event-row">
                  <div>
                    <strong>{event.title}</strong>
                    <span className="task-meta">
                      {formatDateTime(event.start_at, locale)} — {formatClock(event.end_at, locale)}
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
  const { t, locale } = useSettings();

  return (
    <section className="page">
      <h1 className="page-title">{t('history.title')}</h1>
      <p className="page-subtitle">{t('history.subtitle')}</p>

      <div className="card">
        {tasks.length === 0 ? (
          <div className="empty">{t('history.empty')}</div>
        ) : (
          <ul className="task-list">
            {tasks.map((task) => (
              <li key={task.id} className="task-row">
                <div className="task-main">
                  <strong>{task.title}</strong>
                  <span className="task-meta">
                    {t(statusLabelKeys[task.status])} · {formatDeadline(task.deadline, t, locale)}
                  </span>
                </div>
                <div className="task-actions">
                  {task.status === 'cancelled' && (
                    <button className="button small" onClick={() => onStatusChange(task.id, 'todo')}>
                      {t('history.restore')}
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
