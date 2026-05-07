import { useEffect, useMemo, useState } from 'react';

import { apiRequest } from './api/client';
import {
  createTask as createTaskApi,
  deleteTask as deleteTaskApi,
  getTasks,
  updateTask as updateTaskApi,
  updateTaskStatus,
} from './api/tasks';
import type { ApiTask, ApiTaskCreate, ApiTaskStatus, ApiTaskUpdate } from './types/api';

type Page = 'dashboard' | 'tasks' | 'history' | 'calendar' | 'integrations' | 'intelligence' | 'docs';
type ActiveTaskFilter = 'all' | 'high' | 'blocked' | 'without_deadline';
type HistoryFilter = 'all' | 'completed' | 'cancelled';

type ApiEvent = {
  id: string;
  title: string;
  start_at: string;
  end_at: string;
  source: string;
};

type ApiEventCreate = {
  title: string;
  start_at: string;
  end_at: string;
  source: string;
};

type IntegrationSyncResult = {
  provider: string;
  synced_items: number;
  status: string;
  message: string;
};

type ScheduleSlot = {
  task_id: string;
  title: string;
  start_at: string;
  end_at: string;
  score: number;
};

type SchedulePlan = {
  generated_at: string;
  slots: ScheduleSlot[];
  unscheduled_task_ids: string[];
  prime_task_id: string | null;
};

type TodayView = {
  date: string;
  prime_task_id: string | null;
  tasks: ApiTask[];
  schedule_dirty: boolean;
};

type TaskForm = {
  title: string;
  description: string;
  estimatedMinutes: string;
  priority: string;
  deadlineDate: string;
  deadlineTime: string;
  workspaceId: string;
  projectId: string;
  dependsOnTaskId: string;
};

type EventForm = {
  title: string;
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
  source: string;
};

const initialTaskForm: TaskForm = {
  title: '',
  description: '',
  estimatedMinutes: '60',
  priority: '2',
  deadlineDate: '',
  deadlineTime: '',
  workspaceId: 'study',
  projectId: '',
  dependsOnTaskId: '',
};

const initialEventForm: EventForm = {
  title: '',
  startDate: '',
  startTime: '',
  endDate: '',
  endTime: '',
  source: 'manual',
};

const pinnedStorageKey = 'ai-assistant-pinned-task-ids';

const navItems: Array<{ id: Page; label: string }> = [
  { id: 'dashboard', label: 'База знаний' },
  { id: 'tasks', label: 'Задачи' },
  { id: 'history', label: 'История' },
  { id: 'calendar', label: 'События' },
  { id: 'integrations', label: 'Интеграции' },
  { id: 'intelligence', label: 'Интеллект' },
  { id: 'docs', label: 'Документация' },
];

const statusLabels: Record<ApiTaskStatus, string> = {
  todo: 'К выполнению',
  in_progress: 'В работе',
  completed: 'Выполнена',
  cancelled: 'Удалена',
  blocked: 'Заблокирована',
};

const statusOptions: ApiTaskStatus[] = [
  'todo',
  'in_progress',
  'blocked',
  'completed',
  'cancelled',
];

function getEvents(): Promise<ApiEvent[]> {
  return apiRequest<ApiEvent[]>('/v1/events');
}

function createEvent(payload: ApiEventCreate): Promise<ApiEvent> {
  return apiRequest<ApiEvent>('/v1/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

function getIntegrations(): Promise<string[]> {
  return apiRequest<string[]>('/v1/integrations');
}

function syncIntegration(providerName: string): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>(`/v1/integrations/${providerName}/sync`, {
    method: 'POST',
  });
}

function getTodaySchedule(): Promise<TodayView> {
  return apiRequest<TodayView>('/v1/schedule/today');
}

function rebuildSchedule(): Promise<SchedulePlan> {
  return apiRequest<SchedulePlan>('/v1/schedule/rebuild', {
    method: 'POST',
  });
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return 'не указан';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'некорректная дата';
  }

  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function buildDateTimeIso(date: string, time: string): string | null {
  if (!date || !time) {
    return null;
  }

  const result = new Date(`${date}T${time}:00`);

  if (Number.isNaN(result.getTime())) {
    return null;
  }

  return result.toISOString();
}

function splitDateTime(value: string | null): { date: string; time: string } {
  if (!value) {
    return { date: '', time: '' };
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return { date: '', time: '' };
  }

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');

  return {
    date: `${year}-${month}-${day}`,
    time: `${hours}:${minutes}`,
  };
}

function getPriorityLabel(priority: number): string {
  if (priority === 1) {
    return 'Высокий';
  }

  if (priority === 2) {
    return 'Средний';
  }

  if (priority === 3) {
    return 'Низкий';
  }

  return 'Минимальный';
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return 'Неизвестная ошибка';
}

function isPastDateTime(value: string | null): boolean {
  if (!value) {
    return false;
  }

  return new Date(value).getTime() < Date.now();
}

function loadPinnedTaskIds(): string[] {
  try {
    const rawValue = window.localStorage.getItem(pinnedStorageKey);

    if (!rawValue) {
      return [];
    }

    const parsedValue = JSON.parse(rawValue);

    if (!Array.isArray(parsedValue)) {
      return [];
    }

    return parsedValue.filter((value) => typeof value === 'string');
  } catch {
    return [];
  }
}

function savePinnedTaskIds(taskIds: string[]): void {
  window.localStorage.setItem(pinnedStorageKey, JSON.stringify(taskIds));
}

function App() {
  const [activePage, setActivePage] = useState<Page>('dashboard');
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [integrations, setIntegrations] = useState<string[]>([]);
  const [integrationResults, setIntegrationResults] = useState<Record<string, IntegrationSyncResult>>({});
  const [todayView, setTodayView] = useState<TodayView | null>(null);
  const [schedulePlan, setSchedulePlan] = useState<SchedulePlan | null>(null);
  const [pinnedTaskIds, setPinnedTaskIds] = useState<string[]>(() => loadPinnedTaskIds());
  const [activeFilter, setActiveFilter] = useState<ActiveTaskFilter>('all');
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>('all');
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [taskToDelete, setTaskToDelete] = useState<ApiTask | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isEventsLoading, setIsEventsLoading] = useState(false);
  const [isIntegrationsLoading, setIsIntegrationsLoading] = useState(false);
  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [isScheduleLoading, setIsScheduleLoading] = useState(false);
  const [isSavingTask, setIsSavingTask] = useState(false);
  const [isCreatingEvent, setIsCreatingEvent] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [taskForm, setTaskForm] = useState<TaskForm>(initialTaskForm);
  const [eventForm, setEventForm] = useState<EventForm>(initialEventForm);

  const activeTasksList = useMemo(
    () => tasks.filter((task) => ['todo', 'in_progress', 'blocked'].includes(task.status)),
    [tasks]
  );

  const filteredActiveTasks = useMemo(() => {
    if (activeFilter === 'high') {
      return activeTasksList.filter((task) => task.priority === 1);
    }

    if (activeFilter === 'blocked') {
      return activeTasksList.filter((task) => task.status === 'blocked');
    }

    if (activeFilter === 'without_deadline') {
      return activeTasksList.filter((task) => task.deadline === null);
    }

    return activeTasksList;
  }, [activeFilter, activeTasksList]);

  const historyTasks = useMemo(
    () => tasks.filter((task) => ['completed', 'cancelled'].includes(task.status)),
    [tasks]
  );

  const filteredHistoryTasks = useMemo(() => {
    if (historyFilter === 'completed') {
      return historyTasks.filter((task) => task.status === 'completed');
    }

    if (historyFilter === 'cancelled') {
      return historyTasks.filter((task) => task.status === 'cancelled');
    }

    return historyTasks;
  }, [historyFilter, historyTasks]);

  const pinnedTasks = useMemo(
    () => filteredActiveTasks.filter((task) => pinnedTaskIds.includes(task.id)),
    [filteredActiveTasks, pinnedTaskIds]
  );

  const regularActiveTasks = useMemo(
    () => filteredActiveTasks.filter((task) => !pinnedTaskIds.includes(task.id)),
    [filteredActiveTasks, pinnedTaskIds]
  );

  const totalTasks = tasks.length;
  const activeTasks = activeTasksList.length;
  const schedulableTasks = useMemo(
    () => tasks.filter((task) => ['todo', 'in_progress'].includes(task.status)).length,
    [tasks]
  );
  const completedTasks = useMemo(
    () => tasks.filter((task) => task.status === 'completed').length,
    [tasks]
  );
  const cancelledTasks = useMemo(
    () => tasks.filter((task) => task.status === 'cancelled').length,
    [tasks]
  );
  const highPriorityTasks = useMemo(
    () =>
      tasks.filter(
        (task) => task.priority === 1 && task.status !== 'completed' && task.status !== 'cancelled'
      ).length,
    [tasks]
  );
  const dependenciesCount = useMemo(
    () => tasks.reduce((count, task) => count + task.depends_on.length, 0),
    [tasks]
  );

  async function loadTasks(): Promise<void> {
    try {
      setIsLoading(true);
      setError('');

      const loadedTasks = await getTasks();
      setTasks(loadedTasks);
    } catch (loadError) {
      setError(`Не удалось загрузить задачи: ${getErrorMessage(loadError)}`);
    } finally {
      setIsLoading(false);
    }
  }

  async function loadEvents(): Promise<void> {
    try {
      setIsEventsLoading(true);
      setError('');

      const loadedEvents = await getEvents();
      setEvents(loadedEvents);
    } catch (loadError) {
      setError(`Не удалось загрузить события: ${getErrorMessage(loadError)}`);
    } finally {
      setIsEventsLoading(false);
    }
  }

  async function loadIntegrations(): Promise<void> {
    try {
      setIsIntegrationsLoading(true);
      setError('');

      const loadedIntegrations = await getIntegrations();
      setIntegrations(loadedIntegrations);
    } catch (loadError) {
      setError(`Не удалось загрузить интеграции: ${getErrorMessage(loadError)}`);
    } finally {
      setIsIntegrationsLoading(false);
    }
  }

  async function handleSyncIntegration(providerName: string): Promise<void> {
    try {
      setSyncingProvider(providerName);
      setError('');
      setMessage('');

      const result = await syncIntegration(providerName);

      setIntegrationResults((currentResults) => ({
        ...currentResults,
        [providerName]: result,
      }));
      setMessage(`Синхронизация провайдера ${providerName} завершена.`);
    } catch (syncError) {
      setError(`Не удалось синхронизировать провайдер: ${getErrorMessage(syncError)}`);
    } finally {
      setSyncingProvider(null);
    }
  }

  async function loadTodaySchedule(): Promise<void> {
    try {
      setIsScheduleLoading(true);
      setError('');

      const today = await getTodaySchedule();
      setTodayView(today);
    } catch (loadError) {
      setError(`Не удалось получить план на сегодня: ${getErrorMessage(loadError)}`);
    } finally {
      setIsScheduleLoading(false);
    }
  }

  async function handleRebuildSchedule(): Promise<void> {
    try {
      setIsScheduleLoading(true);
      setError('');
      setMessage('');

      const plan = await rebuildSchedule();
      const today = await getTodaySchedule();

      setSchedulePlan(plan);
      setTodayView(today);
      setMessage('Расписание перестроено интеллектуальным модулем.');
    } catch (rebuildError) {
      setError(`Не удалось перестроить расписание: ${getErrorMessage(rebuildError)}`);
    } finally {
      setIsScheduleLoading(false);
    }
  }

  async function loadKnowledgeBase(): Promise<void> {
    await Promise.all([loadTasks(), loadEvents(), loadIntegrations(), loadTodaySchedule()]);
  }

  useEffect(() => {
    void loadKnowledgeBase();
  }, []);

  function updateTaskFormField(field: keyof TaskForm, value: string): void {
    setTaskForm((previousForm) => ({
      ...previousForm,
      [field]: value,
    }));
  }

  function updateEventFormField(field: keyof EventForm, value: string): void {
    setEventForm((previousForm) => ({
      ...previousForm,
      [field]: value,
    }));
  }

  function resetTaskForm(): void {
    setEditingTaskId(null);
    setTaskForm(initialTaskForm);
  }

  function startEditTask(task: ApiTask): void {
    const deadline = splitDateTime(task.deadline);

    setEditingTaskId(task.id);
    setTaskForm({
      title: task.title,
      description: task.description ?? '',
      estimatedMinutes: String(task.estimated_minutes),
      priority: String(task.priority),
      deadlineDate: deadline.date,
      deadlineTime: deadline.time,
      workspaceId: task.workspace_id,
      projectId: task.project_id ?? '',
      dependsOnTaskId: task.depends_on[0] ?? '',
    });
    setActivePage('tasks');
  }

  function togglePinnedTask(taskId: string): void {
    setPinnedTaskIds((currentIds) => {
      const nextIds = currentIds.includes(taskId)
        ? currentIds.filter((id) => id !== taskId)
        : [...currentIds, taskId];

      savePinnedTaskIds(nextIds);
      return nextIds;
    });
  }

  function buildTaskPayload(): ApiTaskCreate | ApiTaskUpdate | null {
    const title = taskForm.title.trim();

    if (!title) {
      setError('Введите название задачи.');
      return null;
    }

    const estimatedMinutes = Number(taskForm.estimatedMinutes);
    const priority = Number(taskForm.priority);

    if (!Number.isFinite(estimatedMinutes) || estimatedMinutes < 15 || estimatedMinutes > 1440) {
      setError('Длительность задачи должна быть от 15 до 1440 минут.');
      return null;
    }

    if (!Number.isFinite(priority) || priority < 1 || priority > 4) {
      setError('Приоритет должен быть от 1 до 4.');
      return null;
    }

    const deadline = buildDateTimeIso(taskForm.deadlineDate, taskForm.deadlineTime);

    if ((taskForm.deadlineDate && !taskForm.deadlineTime) || (!taskForm.deadlineDate && taskForm.deadlineTime)) {
      setError('Для дедлайна нужно указать и дату, и время.');
      return null;
    }

    if (isPastDateTime(deadline)) {
      setError('Дедлайн не может быть в прошлом.');
      return null;
    }

    if (editingTaskId && taskForm.dependsOnTaskId === editingTaskId) {
      setError('Задача не может зависеть сама от себя.');
      return null;
    }

    return {
      title,
      description: taskForm.description.trim() || null,
      estimated_minutes: estimatedMinutes,
      priority,
      deadline,
      workspace_id: taskForm.workspaceId.trim() || 'study',
      project_id: taskForm.projectId.trim() || null,
      auto_reschedule: true,
      depends_on: taskForm.dependsOnTaskId ? [taskForm.dependsOnTaskId] : [],
      allow_split: false,
      min_chunk_minutes: null,
    };
  }

  async function handleSaveTask(): Promise<void> {
    const payload = buildTaskPayload();

    if (!payload) {
      return;
    }

    try {
      setIsSavingTask(true);
      setError('');
      setMessage('');

      if (editingTaskId) {
        const updatedTask = await updateTaskApi(editingTaskId, payload);

        setTasks((previousTasks) =>
          previousTasks.map((task) => (task.id === editingTaskId ? updatedTask : task))
        );
        setMessage('Задача обновлена.');
      } else {
        const createdTask = await createTaskApi(payload);

        setTasks((previousTasks) => [createdTask, ...previousTasks]);
        setMessage('Задача добавлена в базу знаний.');
      }

      resetTaskForm();
      setActivePage('tasks');
    } catch (saveError) {
      setError(`Не удалось сохранить задачу: ${getErrorMessage(saveError)}`);
    } finally {
      setIsSavingTask(false);
    }
  }

  async function handleCreateEvent(): Promise<void> {
    const title = eventForm.title.trim();

    if (!title) {
      setError('Введите название события.');
      return;
    }

    const startAt = buildDateTimeIso(eventForm.startDate, eventForm.startTime);
    const endAt = buildDateTimeIso(eventForm.endDate, eventForm.endTime);

    if (!startAt || !endAt) {
      setError('Введите корректное время начала и окончания события.');
      return;
    }

    if (isPastDateTime(startAt)) {
      setError('Событие не может начинаться в прошлом.');
      return;
    }

    if (new Date(endAt).getTime() <= new Date(startAt).getTime()) {
      setError('Событие должно заканчиваться позже, чем начинается.');
      return;
    }

    const payload: ApiEventCreate = {
      title,
      start_at: startAt,
      end_at: endAt,
      source: eventForm.source.trim() || 'manual',
    };

    try {
      setIsCreatingEvent(true);
      setError('');
      setMessage('');

      const createdEvent = await createEvent(payload);

      setEvents((previousEvents) => [createdEvent, ...previousEvents]);
      setEventForm(initialEventForm);
      setMessage('Событие добавлено в базу знаний.');
    } catch (createError) {
      setError(`Не удалось создать событие: ${getErrorMessage(createError)}`);
    } finally {
      setIsCreatingEvent(false);
    }
  }

  async function handleStatusChange(taskId: string, status: ApiTaskStatus): Promise<void> {
    const previousTasks = tasks;

    setTasks((currentTasks) =>
      currentTasks.map((task) => (task.id === taskId ? { ...task, status } : task))
    );

    if (status === 'cancelled' || status === 'completed') {
      setPinnedTaskIds((currentIds) => {
        const nextIds = currentIds.filter((id) => id !== taskId);
        savePinnedTaskIds(nextIds);
        return nextIds;
      });
    }

    try {
      setError('');
      setMessage('');

      const updatedTask = await updateTaskStatus(taskId, status);

      setTasks((currentTasks) =>
        currentTasks.map((task) => (task.id === taskId ? updatedTask : task))
      );

      setMessage(
        status === 'cancelled'
          ? 'Задача перемещена в историю как удалённая.'
          : 'Статус задачи обновлён.'
      );
    } catch (updateError) {
      setTasks(previousTasks);
      setError(`Не удалось обновить статус: ${getErrorMessage(updateError)}`);
    }
  }

  async function handleSoftDeleteTask(taskId: string): Promise<void> {
    await handleStatusChange(taskId, 'cancelled');
  }

  async function handleRestoreTask(taskId: string): Promise<void> {
    await handleStatusChange(taskId, 'todo');
  }

  function openHardDeleteModal(task: ApiTask): void {
    setTaskToDelete(task);
  }

  function closeHardDeleteModal(): void {
    setTaskToDelete(null);
  }

  async function confirmHardDeleteTask(): Promise<void> {
    if (!taskToDelete) {
      return;
    }

    const taskId = taskToDelete.id;

    try {
      setError('');
      setMessage('');

      await deleteTaskApi(taskId);

      setTasks((previousTasks) => previousTasks.filter((task) => task.id !== taskId));
      setPinnedTaskIds((currentIds) => {
        const nextIds = currentIds.filter((id) => id !== taskId);
        savePinnedTaskIds(nextIds);
        return nextIds;
      });

      if (editingTaskId === taskId) {
        resetTaskForm();
      }

      setTaskToDelete(null);
      setMessage('Задача полностью удалена из базы данных.');
    } catch (deleteError) {
      setError(`Не удалось полностью удалить задачу: ${getErrorMessage(deleteError)}`);
    }
  }

  return (
    <>
      <style>{`
        * {
          box-sizing: border-box;
        }

        :root {
          color-scheme: dark;
          --bg: #07111f;
          --sidebar: #081426;
          --panel: #111e35;
          --border: rgba(255, 255, 255, 0.09);
          --text: #f8fafc;
          --muted: #9fb0c8;
          --accent: #3b82f6;
          --accent-soft: rgba(59, 130, 246, 0.16);
          --danger: #fb7185;
          --success: #34d399;
          --warning: #fbbf24;
          --shadow: 0 22px 70px rgba(0, 0, 0, 0.28);
        }

        body {
          margin: 0;
          min-width: 1100px;
          font-family: Inter, Arial, sans-serif;
          color: var(--text);
          background:
            radial-gradient(circle at top right, rgba(59, 130, 246, 0.14), transparent 28%),
            linear-gradient(180deg, #06101d 0%, #07111f 100%);
        }

        button,
        input,
        textarea,
        select {
          font: inherit;
        }

        button {
          cursor: pointer;
        }

        .layout {
          display: grid;
          grid-template-columns: 280px 1fr;
          min-height: 100vh;
        }

        .sidebar {
          position: sticky;
          top: 0;
          height: 100vh;
          padding: 28px 18px;
          background: linear-gradient(180deg, rgba(8, 20, 38, 0.98), rgba(8, 15, 30, 0.98));
          border-right: 1px solid var(--border);
        }

        .brand {
          margin-bottom: 30px;
        }

        .brand h1 {
          margin: 0 0 8px;
          font-size: 2rem;
          letter-spacing: -0.04em;
        }

        .brand p {
          margin: 0;
          color: var(--muted);
          line-height: 1.45;
        }

        .nav {
          display: grid;
          gap: 10px;
        }

        .nav button {
          width: 100%;
          padding: 14px 16px;
          border: 1px solid transparent;
          border-radius: 16px;
          text-align: left;
          color: #dbeafe;
          background: transparent;
        }

        .nav button:hover,
        .nav button.active {
          border-color: rgba(255, 255, 255, 0.08);
          background: var(--accent-soft);
        }

        .sidebar-note {
          margin-top: 28px;
          padding: 18px;
          border: 1px solid var(--border);
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.04);
        }

        .sidebar-note strong {
          display: block;
          margin-bottom: 8px;
        }

        .sidebar-note p {
          margin: 0;
          color: var(--muted);
          line-height: 1.55;
        }

        .content {
          padding: 28px 36px 48px;
        }

        .topbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 20px;
          margin-bottom: 24px;
        }

        .topbar h2 {
          margin: 0;
          font-size: 1.2rem;
        }

        .topbar p {
          margin: 4px 0 0;
          color: var(--muted);
        }

        .actions,
        .task-actions,
        .filters {
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }

        .button {
          border: 1px solid var(--border);
          border-radius: 14px;
          padding: 12px 16px;
          color: var(--text);
          background: rgba(255, 255, 255, 0.05);
        }

        .button.primary {
          border-color: transparent;
          background: linear-gradient(135deg, #3b82f6, #2563eb);
        }

        .button.danger {
          border-color: rgba(251, 113, 133, 0.35);
          color: #fecdd3;
          background: rgba(251, 113, 133, 0.12);
        }

        .button.success {
          border-color: rgba(52, 211, 153, 0.35);
          color: #bbf7d0;
          background: rgba(52, 211, 153, 0.12);
        }

        .button.small {
          padding: 8px 11px;
          border-radius: 12px;
          font-size: 0.86rem;
        }

        .button.active {
          background: var(--accent-soft);
          border-color: rgba(59, 130, 246, 0.45);
        }

        .button:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }

        .pin-button {
          position: absolute;
          top: 14px;
          right: 14px;
          width: 36px;
          height: 36px;
          display: grid;
          place-items: center;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          color: #cbd5e1;
          background: rgba(255, 255, 255, 0.05);
        }

        .pin-button.active {
          color: #fef3c7;
          background: rgba(251, 191, 36, 0.16);
          border-color: rgba(251, 191, 36, 0.35);
        }

        .notice {
          margin-bottom: 16px;
          padding: 14px 16px;
          border-radius: 16px;
          border: 1px solid var(--border);
          color: #dbeafe;
          background: rgba(59, 130, 246, 0.12);
        }

        .notice.error {
          color: #fecdd3;
          background: rgba(251, 113, 133, 0.12);
        }

        .hero {
          padding: 28px;
          margin-bottom: 22px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 28px;
          background:
            linear-gradient(135deg, rgba(59, 130, 246, 0.18), rgba(17, 30, 53, 0.95)),
            var(--panel);
          box-shadow: var(--shadow);
        }

        .eyebrow {
          margin: 0 0 8px;
          color: #bfdbfe;
          font-size: 0.82rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .hero h1 {
          margin: 0 0 12px;
          font-size: 2.5rem;
          line-height: 1.05;
          letter-spacing: -0.05em;
        }

        .hero p {
          margin: 0;
          max-width: 920px;
          color: var(--muted);
          line-height: 1.65;
        }

        .stats-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 16px;
          margin: 20px 0 0;
        }

        .stat-card,
        .panel {
          border: 1px solid var(--border);
          border-radius: 22px;
          background: rgba(17, 30, 53, 0.82);
        }

        .stat-card {
          padding: 18px;
        }

        .stat-card span {
          display: block;
          margin-bottom: 10px;
          color: var(--muted);
          font-size: 0.9rem;
        }

        .stat-card strong {
          font-size: 2rem;
        }

        .facts {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 22px;
        }

        .fact {
          padding: 9px 13px;
          border-radius: 999px;
          color: #dbeafe;
          background: rgba(255, 255, 255, 0.08);
        }

        .grid-two {
          display: grid;
          grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
          gap: 20px;
          align-items: start;
        }

        .panel {
          padding: 22px;
        }

        .panel h3 {
          margin: 0 0 8px;
          font-size: 1.35rem;
        }

        .panel-description {
          margin: 0 0 18px;
          color: var(--muted);
          line-height: 1.55;
        }

        .form-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }

        .form-field {
          display: grid;
          gap: 8px;
        }

        .form-field.full {
          grid-column: 1 / -1;
        }

        .form-field label {
          color: #cbd5e1;
          font-size: 0.9rem;
        }

        .input,
        .textarea,
        .select {
          width: 100%;
          border: 1px solid var(--border);
          border-radius: 14px;
          padding: 12px 14px;
          color: var(--text);
          background: rgba(5, 12, 24, 0.72);
          outline: none;
        }

        .textarea {
          min-height: 86px;
          resize: vertical;
        }

        .task-list,
        .event-list,
        .section-stack,
        .doc-list {
          display: grid;
          gap: 12px;
        }

        .task-card,
        .event-card,
        .doc-card {
          position: relative;
          display: grid;
          gap: 12px;
          padding: 18px;
          border: 1px solid var(--border);
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.04);
        }

        .task-card.pinned {
          border-color: rgba(251, 191, 36, 0.55);
        }

        .task-card.cancelled {
          border-color: rgba(251, 113, 133, 0.7);
        }

        .task-card.completed {
          border-color: rgba(52, 211, 153, 0.7);
        }

        .task-card-header {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          padding-right: 44px;
        }

        .task-title,
        .event-title {
          margin: 0 0 6px;
          font-size: 1.05rem;
        }

        .task-description,
        .event-description {
          margin: 0;
          color: var(--muted);
          line-height: 1.5;
        }

        .badges {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .badge {
          padding: 7px 10px;
          border-radius: 999px;
          color: #dbeafe;
          background: rgba(255, 255, 255, 0.08);
          font-size: 0.82rem;
        }

        .badge.high {
          color: #fecdd3;
          background: rgba(251, 113, 133, 0.14);
        }

        .badge.success {
          color: #bbf7d0;
          background: rgba(52, 211, 153, 0.14);
        }

        .badge.cancelled {
          color: #fecdd3;
          background: rgba(251, 113, 133, 0.16);
        }

        .badge.pinned {
          color: #fef3c7;
          background: rgba(251, 191, 36, 0.16);
        }

        .status-select {
          min-width: 160px;
        }

        .empty {
          padding: 26px;
          border: 1px dashed var(--border);
          border-radius: 18px;
          color: var(--muted);
          text-align: center;
        }

        .module-card {
          padding: 22px;
          border: 1px solid var(--border);
          border-radius: 20px;
          background: rgba(255, 255, 255, 0.04);
        }

        .module-card h4 {
          margin: 0 0 8px;
          font-size: 1.15rem;
        }

        .module-card p {
          margin: 0;
          color: var(--muted);
          line-height: 1.55;
        }

        .module-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 14px;
        }

        .module-result {
          margin-top: 14px;
          padding: 14px;
          border: 1px solid rgba(52, 211, 153, 0.24);
          border-radius: 14px;
          background: rgba(52, 211, 153, 0.08);
        }

        .module-result p {
          margin: 0;
          color: #bbf7d0;
        }

        .schedule-list {
          display: grid;
          gap: 10px;
          margin-top: 14px;
        }

        .schedule-slot {
          padding: 14px;
          border: 1px solid var(--border);
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.04);
        }

        .schedule-slot strong {
          display: block;
          margin-bottom: 6px;
        }

        .schedule-slot span {
          display: block;
          color: var(--muted);
          font-size: 0.9rem;
          line-height: 1.5;
        }

        .doc-card strong {
          display: block;
          margin-bottom: 6px;
        }

        .doc-card code {
          color: #bfdbfe;
        }

        .modal-backdrop {
          position: fixed;
          inset: 0;
          z-index: 100;
          display: grid;
          place-items: center;
          padding: 24px;
          background: rgba(2, 6, 23, 0.72);
          backdrop-filter: blur(8px);
        }

        .modal {
          width: min(520px, 100%);
          border: 1px solid rgba(251, 113, 133, 0.32);
          border-radius: 24px;
          padding: 24px;
          background:
            linear-gradient(135deg, rgba(251, 113, 133, 0.14), rgba(17, 30, 53, 0.96)),
            var(--panel);
          box-shadow: var(--shadow);
        }

        .modal-icon {
          width: 44px;
          height: 44px;
          display: grid;
          place-items: center;
          margin-bottom: 16px;
          border-radius: 16px;
          color: #fecdd3;
          background: rgba(251, 113, 133, 0.16);
          font-size: 1.35rem;
        }

        .modal h3 {
          margin: 0 0 10px;
          font-size: 1.45rem;
        }

        .modal p {
          margin: 0;
          color: var(--muted);
          line-height: 1.6;
        }

        .modal-task {
          margin: 18px 0;
          padding: 14px 16px;
          border: 1px solid rgba(255, 255, 255, 0.09);
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.05);
        }

        .modal-task strong {
          display: block;
          margin-bottom: 4px;
        }

        .modal-task span {
          color: var(--muted);
          font-size: 0.9rem;
        }

        .modal-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 22px;
        }

        @media (max-width: 1200px) {
          body {
            min-width: 0;
          }

          .layout {
            grid-template-columns: 1fr;
          }

          .sidebar {
            position: static;
            height: auto;
          }

          .stats-grid,
          .grid-two {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <div className="layout">
        <aside className="sidebar">
          <div className="brand">
            <h1>AI Assistant</h1>
            <p>Учебный MVP базы знаний для планирования задач.</p>
          </div>

          <nav className="nav">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={activePage === item.id ? 'active' : ''}
                onClick={() => setActivePage(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="sidebar-note">
            <strong>Два типа удаления</strong>
            <p>
              Мягкое удаление переносит задачу в историю. Полное удаление удаляет
              задачу из PostgreSQL без возможности восстановления.
            </p>
          </div>
        </aside>

        <main className="content">
          <header className="topbar">
            <div>
              <h2>Интерфейс базы знаний</h2>
              <p>Frontend показывает текущее состояние знаний, сохранённых через backend.</p>
            </div>

            <div className="actions">
              <button className="button" onClick={() => void loadKnowledgeBase()}>
                Обновить
              </button>
              <button className="button primary" onClick={() => setActivePage('tasks')}>
                Добавить задачу
              </button>
            </div>
          </header>

          {message && <div className="notice">{message}</div>}
          {error && <div className="notice error">{error}</div>}

          {activePage === 'dashboard' && (
            <>
              <section className="hero">
                <p className="eyebrow">Knowledge Base MVP</p>
                <h1>База знаний ассистента планирования</h1>
                <p>
                  Система хранит структурированные знания о задачах, событиях,
                  дедлайнах, приоритетах, статусах и зависимостях. Активные задачи
                  отображаются отдельно, а выполненные и мягко удалённые переносятся в историю.
                </p>

                <div className="stats-grid">
                  <div className="stat-card">
                    <span>Всего задач</span>
                    <strong>{totalTasks}</strong>
                  </div>
                  <div className="stat-card">
                    <span>Активные</span>
                    <strong>{activeTasks}</strong>
                  </div>
                  <div className="stat-card">
                    <span>События</span>
                    <strong>{events.length}</strong>
                  </div>
                  <div className="stat-card">
                    <span>Удалённые</span>
                    <strong>{cancelledTasks}</strong>
                  </div>
                </div>

                <div className="facts">
                  <span className="fact">Task</span>
                  <span className="fact">Event</span>
                  <span className="fact">Dependency</span>
                  <span className="fact">Deadline</span>
                  <span className="fact">Priority</span>
                  <span className="fact">Status</span>
                  <span className="fact">Soft delete</span>
                  <span className="fact">Hard delete</span>
                  <span className="fact">Pinned task</span>
                </div>
              </section>

              <div className="section-stack">
                {pinnedTasks.length > 0 && (
                  <section className="panel">
                    <h3>Закреплённые задачи</h3>
                    <p className="panel-description">
                      Закрепление хранится на frontend и помогает держать важные активные
                      задачи наверху.
                    </p>
                    <TaskList
                      tasks={pinnedTasks}
                      isLoading={isLoading}
                      pinnedTaskIds={pinnedTaskIds}
                      showDeleteButton
                      showPinButton
                      onStatusChange={handleStatusChange}
                      onSoftDeleteTask={handleSoftDeleteTask}
                      onHardDeleteTask={openHardDeleteModal}
                      onRestoreTask={handleRestoreTask}
                      onEditTask={startEditTask}
                      onTogglePinned={togglePinnedTask}
                    />
                  </section>
                )}

                <section className="panel">
                  <h3>Активные задачи</h3>
                  <p className="panel-description">
                    Здесь показана текущая работа. Исторические задачи сюда не попадают.
                  </p>

                  <TaskFilters activeFilter={activeFilter} onChange={setActiveFilter} />

                  <TaskList
                    tasks={regularActiveTasks.slice(0, 6)}
                    isLoading={isLoading}
                    pinnedTaskIds={pinnedTaskIds}
                    showDeleteButton
                    showPinButton
                    onStatusChange={handleStatusChange}
                    onSoftDeleteTask={handleSoftDeleteTask}
                    onHardDeleteTask={openHardDeleteModal}
                    onRestoreTask={handleRestoreTask}
                    onEditTask={startEditTask}
                    onTogglePinned={togglePinnedTask}
                  />
                </section>
              </div>
            </>
          )}

          {activePage === 'tasks' && (
            <div className="grid-two">
              <section className="panel">
                <h3>{editingTaskId ? 'Редактировать задачу' : 'Добавить задачу'}</h3>
                <p className="panel-description">
                  {editingTaskId
                    ? 'Изменения сохраняются через PUT /v1/tasks/{id}.'
                    : 'Новая задача сохраняется как факт Task в базе знаний.'}
                </p>

                <div className="form-grid">
                  <div className="form-field full">
                    <label>Название</label>
                    <input
                      className="input"
                      value={taskForm.title}
                      onChange={(event) => updateTaskFormField('title', event.target.value)}
                      placeholder="Например: подготовить отчёт по лабораторной"
                    />
                  </div>

                  <div className="form-field full">
                    <label>Описание</label>
                    <textarea
                      className="textarea"
                      value={taskForm.description}
                      onChange={(event) => updateTaskFormField('description', event.target.value)}
                      placeholder="Кратко опиши, что нужно сделать"
                    />
                  </div>

                  <div className="form-field">
                    <label>Длительность, минут</label>
                    <input
                      className="input"
                      type="number"
                      min="15"
                      max="1440"
                      value={taskForm.estimatedMinutes}
                      onChange={(event) =>
                        updateTaskFormField('estimatedMinutes', event.target.value)
                      }
                    />
                  </div>

                  <div className="form-field">
                    <label>Приоритет</label>
                    <select
                      className="select"
                      value={taskForm.priority}
                      onChange={(event) => updateTaskFormField('priority', event.target.value)}
                    >
                      <option value="1">1 — высокий</option>
                      <option value="2">2 — средний</option>
                      <option value="3">3 — низкий</option>
                      <option value="4">4 — минимальный</option>
                    </select>
                  </div>

                  <div className="form-field">
                    <label>Дата дедлайна</label>
                    <input
                      className="input"
                      type="date"
                      value={taskForm.deadlineDate}
                      onChange={(event) => updateTaskFormField('deadlineDate', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Время дедлайна</label>
                    <input
                      className="input"
                      type="time"
                      value={taskForm.deadlineTime}
                      onChange={(event) => updateTaskFormField('deadlineTime', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Рабочая область</label>
                    <input
                      className="input"
                      value={taskForm.workspaceId}
                      onChange={(event) => updateTaskFormField('workspaceId', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Проект / дисциплина</label>
                    <input
                      className="input"
                      value={taskForm.projectId}
                      onChange={(event) => updateTaskFormField('projectId', event.target.value)}
                      placeholder="например: Базы знаний"
                    />
                  </div>

                  <div className="form-field full">
                    <label>Зависит от задачи</label>
                    <select
                      className="select"
                      value={taskForm.dependsOnTaskId}
                      onChange={(event) =>
                        updateTaskFormField('dependsOnTaskId', event.target.value)
                      }
                    >
                      <option value="">Нет зависимости</option>
                      {activeTasksList
                        .filter((task) => task.id !== editingTaskId)
                        .map((task) => (
                          <option key={task.id} value={task.id}>
                            {task.title}
                          </option>
                        ))}
                    </select>
                  </div>

                  <div className="form-field full">
                    <div className="actions">
                      <button
                        className="button primary"
                        disabled={isSavingTask}
                        onClick={() => void handleSaveTask()}
                      >
                        {isSavingTask
                          ? 'Сохранение...'
                          : editingTaskId
                            ? 'Сохранить изменения'
                            : 'Сохранить в базу знаний'}
                      </button>

                      {editingTaskId && (
                        <button className="button" onClick={resetTaskForm}>
                          Отменить редактирование
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </section>

              <section className="panel">
                <h3>Активные задачи</h3>
                <p className="panel-description">
                  Удалённые и выполненные задачи не отображаются здесь, а переносятся
                  в историю.
                </p>

                <TaskFilters activeFilter={activeFilter} onChange={setActiveFilter} />

                <TaskList
                  tasks={[...pinnedTasks, ...regularActiveTasks]}
                  isLoading={isLoading}
                  pinnedTaskIds={pinnedTaskIds}
                  showDeleteButton
                  showPinButton
                  onStatusChange={handleStatusChange}
                  onSoftDeleteTask={handleSoftDeleteTask}
                  onHardDeleteTask={openHardDeleteModal}
                  onRestoreTask={handleRestoreTask}
                  onEditTask={startEditTask}
                  onTogglePinned={togglePinnedTask}
                />
              </section>
            </div>
          )}

          {activePage === 'history' && (
            <section className="panel">
              <h3>История задач</h3>
              <p className="panel-description">
                Здесь отображаются выполненные и мягко удалённые задачи. Полностью
                удалённые задачи из истории исчезают, потому что удаляются из PostgreSQL.
              </p>

              <HistoryFilters historyFilter={historyFilter} onChange={setHistoryFilter} />

              <TaskList
                tasks={filteredHistoryTasks}
                isLoading={isLoading}
                pinnedTaskIds={pinnedTaskIds}
                isHistory
                onStatusChange={handleStatusChange}
                onSoftDeleteTask={handleSoftDeleteTask}
                onHardDeleteTask={openHardDeleteModal}
                onRestoreTask={handleRestoreTask}
                onEditTask={startEditTask}
                onTogglePinned={togglePinnedTask}
              />
            </section>
          )}

          {activePage === 'calendar' && (
            <div className="grid-two">
              <section className="panel">
                <h3>Добавить событие</h3>
                <p className="panel-description">
                  Событие сохраняется как факт Event и описывает занятый временной
                  интервал пользователя.
                </p>

                <div className="form-grid">
                  <div className="form-field full">
                    <label>Название события</label>
                    <input
                      className="input"
                      value={eventForm.title}
                      onChange={(event) => updateEventFormField('title', event.target.value)}
                      placeholder="Например: лекция по базам знаний"
                    />
                  </div>

                  <div className="form-field">
                    <label>Дата начала</label>
                    <input
                      className="input"
                      type="date"
                      value={eventForm.startDate}
                      onChange={(event) => updateEventFormField('startDate', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Время начала</label>
                    <input
                      className="input"
                      type="time"
                      value={eventForm.startTime}
                      onChange={(event) => updateEventFormField('startTime', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Дата окончания</label>
                    <input
                      className="input"
                      type="date"
                      value={eventForm.endDate}
                      onChange={(event) => updateEventFormField('endDate', event.target.value)}
                    />
                  </div>

                  <div className="form-field">
                    <label>Время окончания</label>
                    <input
                      className="input"
                      type="time"
                      value={eventForm.endTime}
                      onChange={(event) => updateEventFormField('endTime', event.target.value)}
                    />
                  </div>

                  <div className="form-field full">
                    <label>Источник</label>
                    <select
                      className="select"
                      value={eventForm.source}
                      onChange={(event) => updateEventFormField('source', event.target.value)}
                    >
                      <option value="manual">manual — ручной ввод</option>
                      <option value="university-schedule">university-schedule — расписание</option>
                      <option value="google-calendar">google-calendar — календарь</option>
                      <option value="mock">mock — тестовый источник</option>
                    </select>
                  </div>

                  <div className="form-field full">
                    <button
                      className="button primary"
                      disabled={isCreatingEvent}
                      onClick={() => void handleCreateEvent()}
                    >
                      {isCreatingEvent ? 'Сохранение...' : 'Сохранить событие'}
                    </button>
                  </div>
                </div>
              </section>

              <section className="panel">
                <h3>События базы знаний</h3>
                <p className="panel-description">
                  Список загружается из backend API /v1/events.
                </p>

                <EventList events={events} isLoading={isEventsLoading} />
              </section>
            </div>
          )}

          {activePage === 'integrations' && (
            <section className="panel">
              <h3>Интеграционный модуль</h3>
              <p className="panel-description">
                Модуль подключает внешние источники данных к базе знаний. Сейчас
                frontend получает список доступных провайдеров и может запускать их
                синхронизацию через backend.
              </p>

              <div className="actions" style={{ marginBottom: 16 }}>
                <button className="button" onClick={() => void loadIntegrations()}>
                  Обновить провайдеры
                </button>
              </div>

              {isIntegrationsLoading && <div className="empty">Загрузка провайдеров...</div>}

              {!isIntegrationsLoading && integrations.length === 0 && (
                <div className="empty">Провайдеры интеграций пока не найдены.</div>
              )}

              <div className="section-stack">
                {integrations.map((providerName) => {
                  const result = integrationResults[providerName];

                  return (
                    <div className="module-card" key={providerName}>
                      <h4>{providerName}</h4>
                      <p>
                        Провайдер интеграционного слоя. Его можно синхронизировать,
                        чтобы проверить работу модуля коллег через API.
                      </p>

                      <div className="module-meta">
                        <span className="badge">Provider: {providerName}</span>
                        <span className="badge">Endpoint: /v1/integrations/{providerName}/sync</span>
                      </div>

                      <div className="actions" style={{ marginTop: 14 }}>
                        <button
                          className="button primary"
                          disabled={syncingProvider === providerName}
                          onClick={() => void handleSyncIntegration(providerName)}
                        >
                          {syncingProvider === providerName
                            ? 'Синхронизация...'
                            : 'Синхронизировать'}
                        </button>
                      </div>

                      {result && (
                        <div className="module-result">
                          <p>
                            Статус: {result.status}. Импортировано элементов:{' '}
                            {result.synced_items}. Сообщение: {result.message}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}

                <div className="module-card">
                  <h4>Будущие источники</h4>
                  <p>
                    Слой интеграций можно расширить провайдерами расписания университета,
                    Google Calendar и других внешних сервисов. Такие данные будут
                    попадать в базу знаний как события Event.
                  </p>
                </div>
              </div>
            </section>
          )}

          {activePage === 'intelligence' && (
            <section className="panel">
              <h3>Интеллектуальный модуль</h3>
              <p className="panel-description">
                Модуль использует задачи и события базы знаний для построения расписания,
                определения prime-задачи и дальнейшего скоринга.
              </p>

              <div className="actions" style={{ marginBottom: 16 }}>
                <button
                  className="button"
                  disabled={isScheduleLoading}
                  onClick={() => void loadTodaySchedule()}
                >
                  Получить план на сегодня
                </button>
                <button
                  className="button primary"
                  disabled={isScheduleLoading}
                  onClick={() => void handleRebuildSchedule()}
                >
                  Перестроить расписание
                </button>
              </div>

              <div className="grid-two">
                <div className="module-card">
                  <h4>План на сегодня</h4>
                  <p>
                    Данные загружаются из endpoint GET /v1/schedule/today.
                  </p>

                  {isScheduleLoading && <div className="empty">Загрузка расписания...</div>}

                  {!isScheduleLoading && !todayView && (
                    <div className="empty">План на сегодня ещё не загружен.</div>
                  )}

                  {todayView && (
                    <>
                      <div className="module-meta">
                        <span className="badge">Дата: {todayView.date}</span>
                        <span className="badge">
                          Prime task: {todayView.prime_task_id || 'нет'}
                        </span>
                        <span className="badge">
                          Schedule dirty: {todayView.schedule_dirty ? 'да' : 'нет'}
                        </span>
                      </div>

                      <div className="schedule-list">
                        {todayView.tasks.length === 0 && (
                          <div className="empty">На сегодня задач не запланировано.</div>
                        )}

                        {todayView.tasks.map((task) => (
                          <div className="schedule-slot" key={task.id}>
                            <strong>{task.title}</strong>
                            <span>Статус: {statusLabels[task.status]}</span>
                            <span>
                              Интервал: {formatDateTime(task.scheduled_start)} —{' '}
                              {formatDateTime(task.scheduled_end)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <div className="module-card">
                  <h4>Результат перестроения</h4>
                  <p>
                    Данные появляются после POST /v1/schedule/rebuild.
                  </p>

                  {!schedulePlan && (
                    <div className="empty">Расписание ещё не перестраивалось.</div>
                  )}

                  {schedulePlan && (
                    <>
                      <div className="module-meta">
                        <span className="badge">
                          Сгенерировано: {formatDateTime(schedulePlan.generated_at)}
                        </span>
                        <span className="badge">
                          Слотов: {schedulePlan.slots.length}
                        </span>
                        <span className="badge">
                          Prime task: {schedulePlan.prime_task_id || 'нет'}
                        </span>
                        <span className="badge">
                          Не запланировано: {schedulePlan.unscheduled_task_ids.length}
                        </span>
                      </div>

                      <div className="schedule-list">
                        {schedulePlan.slots.length === 0 && (
                          <div className="empty">Планировщик не создал слоты.</div>
                        )}

                        {schedulePlan.slots.map((slot) => (
                          <div className="schedule-slot" key={`${slot.task_id}-${slot.start_at}`}>
                            <strong>{slot.title}</strong>
                            <span>
                              Интервал: {formatDateTime(slot.start_at)} —{' '}
                              {formatDateTime(slot.end_at)}
                            </span>
                            <span>Score: {slot.score.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </section>
          )}

          {activePage === 'docs' && (
            <section className="panel">
              <h3>Документация проекта</h3>
              <p className="panel-description">
                Эти документы описывают проект именно как MVP базы знаний для 4 семестра.
              </p>

              <div className="doc-list">
                <div className="doc-card">
                  <strong>Описание базы знаний</strong>
                  <code>docs/knowledge_base.md</code>
                </div>
                <div className="doc-card">
                  <strong>Схема PostgreSQL</strong>
                  <code>docs/database_schema.md</code>
                </div>
                <div className="doc-card">
                  <strong>Проверка и тестирование</strong>
                  <code>docs/testing.md</code>
                </div>
                <div className="doc-card">
                  <strong>Модуль правил</strong>
                  <code>apps/api/app/modules/knowledge/rules.py</code>
                </div>
                <div className="doc-card">
                  <strong>Сервис базы знаний</strong>
                  <code>apps/api/app/modules/knowledge/service.py</code>
                </div>
              </div>
            </section>
          )}
          {taskToDelete && (
            <ConfirmDeleteModal
              task={taskToDelete}
              onCancel={closeHardDeleteModal}
              onConfirm={() => void confirmHardDeleteTask()}
            />
          )}
        </main>
      </div>
    </>
  );
}

type ConfirmDeleteModalProps = {
  task: ApiTask;
  onCancel: () => void;
  onConfirm: () => void;
};

function ConfirmDeleteModal({ task, onCancel, onConfirm }: ConfirmDeleteModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-task-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-icon">!</div>

        <h3 id="delete-task-title">Полностью удалить задачу?</h3>

        <p>
          Задача будет удалена из базы данных PostgreSQL. Это действие нельзя
          отменить, и восстановить задачу из истории уже не получится.
        </p>

        <div className="modal-task">
          <strong>{task.title}</strong>
          <span>{task.description || 'Описание не указано.'}</span>
        </div>

        <div className="modal-actions">
          <button className="button" onClick={onCancel}>
            Отмена
          </button>
          <button className="button danger" onClick={onConfirm}>
            Удалить полностью
          </button>
        </div>
      </div>
    </div>
  );
}

type TaskFiltersProps = {
  activeFilter: ActiveTaskFilter;
  onChange: (filter: ActiveTaskFilter) => void;
};

function TaskFilters({ activeFilter, onChange }: TaskFiltersProps) {
  const filters: Array<{ id: ActiveTaskFilter; label: string }> = [
    { id: 'all', label: 'Все активные' },
    { id: 'high', label: 'Высокий приоритет' },
    { id: 'blocked', label: 'Заблокированные' },
    { id: 'without_deadline', label: 'Без дедлайна' },
  ];

  return (
    <div className="filters" style={{ marginBottom: 16 }}>
      {filters.map((filter) => (
        <button
          key={filter.id}
          className={activeFilter === filter.id ? 'button small active' : 'button small'}
          onClick={() => onChange(filter.id)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}

type HistoryFiltersProps = {
  historyFilter: HistoryFilter;
  onChange: (filter: HistoryFilter) => void;
};

function HistoryFilters({ historyFilter, onChange }: HistoryFiltersProps) {
  const filters: Array<{ id: HistoryFilter; label: string }> = [
    { id: 'all', label: 'Вся история' },
    { id: 'completed', label: 'Выполненные' },
    { id: 'cancelled', label: 'Удалённые' },
  ];

  return (
    <div className="filters" style={{ marginBottom: 16 }}>
      {filters.map((filter) => (
        <button
          key={filter.id}
          className={historyFilter === filter.id ? 'button small active' : 'button small'}
          onClick={() => onChange(filter.id)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}

type TaskListProps = {
  tasks: ApiTask[];
  isLoading: boolean;
  pinnedTaskIds: string[];
  showDeleteButton?: boolean;
  showPinButton?: boolean;
  isHistory?: boolean;
  onStatusChange: (taskId: string, status: ApiTaskStatus) => Promise<void>;
  onSoftDeleteTask: (taskId: string) => Promise<void>;
  onHardDeleteTask: (task: ApiTask) => void;
  onRestoreTask: (taskId: string) => Promise<void>;
  onEditTask: (task: ApiTask) => void;
  onTogglePinned: (taskId: string) => void;
};

function TaskList({
  tasks,
  isLoading,
  pinnedTaskIds,
  showDeleteButton = false,
  showPinButton = false,
  isHistory = false,
  onStatusChange,
  onSoftDeleteTask,
  onHardDeleteTask,
  onRestoreTask,
  onEditTask,
  onTogglePinned,
}: TaskListProps) {
  if (isLoading) {
    return <div className="empty">Загрузка задач из базы знаний...</div>;
  }

  if (tasks.length === 0) {
    return <div className="empty">Нет задач для отображения.</div>;
  }

  return (
    <div className="task-list">
      {tasks.map((task) => {
        const isPinned = pinnedTaskIds.includes(task.id);
        const isCancelled = task.status === 'cancelled';
        const isCompleted = task.status === 'completed';

        return (
          <article
            key={task.id}
            className={[
              'task-card',
              isPinned ? 'pinned' : '',
              isCancelled ? 'cancelled' : '',
              isCompleted ? 'completed' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {showPinButton && !isHistory && (
              <button
                className={isPinned ? 'pin-button active' : 'pin-button'}
                title={isPinned ? 'Открепить задачу' : 'Закрепить задачу'}
                onClick={() => onTogglePinned(task.id)}
              >
                ★
              </button>
            )}

            <div className="task-card-header">
              <div>
                <h4 className="task-title">{task.title}</h4>
                <p className="task-description">
                  {task.description || 'Описание не указано.'}
                </p>
              </div>

              <select
                className="select status-select"
                value={task.status}
                onChange={(event) =>
                  void onStatusChange(task.id, event.target.value as ApiTaskStatus)
                }
              >
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {statusLabels[status]}
                  </option>
                ))}
              </select>
            </div>

            <div className="badges">
              {isPinned && <span className="badge pinned">Закреплена</span>}
              <span className={task.priority === 1 ? 'badge high' : 'badge'}>
                {getPriorityLabel(task.priority)}
              </span>
              <span className="badge">{task.estimated_minutes} мин.</span>
              <span className="badge">Дедлайн: {formatDateTime(task.deadline)}</span>
              <span className="badge">Область: {task.workspace_id}</span>
              <span className="badge">Проект: {task.project_id || 'не указан'}</span>
              <span
                className={
                  task.status === 'completed'
                    ? 'badge success'
                    : task.status === 'cancelled'
                      ? 'badge cancelled'
                      : 'badge'
                }
              >
                {statusLabels[task.status]}
              </span>
              {task.depends_on.length > 0 && (
                <span className="badge">Зависимостей: {task.depends_on.length}</span>
              )}
            </div>

            <div className="task-actions">
              {!isHistory && task.status !== 'cancelled' && (
                <button className="button small" onClick={() => onEditTask(task)}>
                  Редактировать
                </button>
              )}

              {showDeleteButton && !isHistory && task.status !== 'cancelled' && (
                <button className="button danger small" onClick={() => void onSoftDeleteTask(task.id)}>
                  Удалить в историю
                </button>
              )}

              {isHistory && task.status === 'cancelled' && (
                <button className="button success small" onClick={() => void onRestoreTask(task.id)}>
                  Восстановить
                </button>
              )}

              <button className="button danger small" onClick={() => onHardDeleteTask(task)}>
                Удалить полностью
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

type EventListProps = {
  events: ApiEvent[];
  isLoading: boolean;
};

function EventList({ events, isLoading }: EventListProps) {
  if (isLoading) {
    return <div className="empty">Загрузка событий из базы знаний...</div>;
  }

  if (events.length === 0) {
    return <div className="empty">Пока нет событий.</div>;
  }

  return (
    <div className="event-list">
      {events.map((event) => (
        <article key={event.id} className="event-card">
          <div>
            <h4 className="event-title">{event.title}</h4>
            <p className="event-description">
              Событие занимает временной интервал и хранится как факт базы знаний.
            </p>
          </div>

          <div className="badges">
            <span className="badge">Начало: {formatDateTime(event.start_at)}</span>
            <span className="badge">Конец: {formatDateTime(event.end_at)}</span>
            <span className="badge">Источник: {event.source}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

export default App;
