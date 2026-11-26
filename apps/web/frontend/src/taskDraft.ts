import type { ApiTaskCreate, ApiTaskDraft } from './types/api';

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/**
 * Приводит дедлайн из ответа модели к значениям полей date/time.
 * Дедлайн без часового пояса трактуем как локальное время пользователя.
 */
export function splitDraftDeadline(value: string | null): { date: string; time: string } {
  if (!value) {
    return { date: '', time: '' };
  }

  if (/(?:z|[+-]\d{2}:?\d{2})$/i.test(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return {
        date: `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
        time: `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`,
      };
    }
  }

  const match = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(value);
  if (match) {
    return { date: match[1], time: match[2] ?? '23:59' };
  }

  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return {
      date: `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
      time: `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`,
    };
  }

  return { date: '', time: '' };
}

export function draftToTaskPayload(draft: ApiTaskDraft): ApiTaskCreate {
  const { date, time } = splitDraftDeadline(draft.deadline);

  let deadline: string | null = null;
  if (date) {
    const parsed = new Date(`${date}T${time || '23:59'}:00`);
    if (!Number.isNaN(parsed.getTime())) {
      deadline = parsed.toISOString();
    }
  }

  return {
    title: draft.title.trim(),
    description: draft.description?.trim() || null,
    estimated_minutes: draft.estimated_minutes,
    priority: draft.priority,
    deadline,
    workspace_id: draft.workspace_id,
    project_id: draft.project_id,
  };
}
