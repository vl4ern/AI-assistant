import { apiRequest } from './client';
import type { ApiTaskDraft, ApiTaskDraftPrompt, ApiTaskDrafts } from '../types/api';

export function extractTaskDraft(
  text: string,
  files: File[] = []
): Promise<ApiTaskDrafts> {
  const form = new FormData();
  if (text.trim()) {
    form.append('text', text);
  }
  for (const file of files) {
    form.append('file', file);
  }

  return apiRequest<ApiTaskDrafts>('/v1/tasks/extract', {
    method: 'POST',
    body: form,
  });
}

export function getTaskDraftPrompt(): Promise<ApiTaskDraftPrompt> {
  return apiRequest<ApiTaskDraftPrompt>('/v1/tasks/extract/prompt', {
    method: 'GET',
  });
}

export type TaskDraftFeedbackItem = {
  task_title: string;
  user_draft: ApiTaskDraft;
  llm_draft: ApiTaskDraft;
};

export type TaskDraftFeedbackPayload = {
  items: TaskDraftFeedbackItem[];
};

/**
 * Отправляет обратную связь по всей пачке задач одним запросом.
 * Вызывается только после добавления последней задачи из пачки,
 * чтобы калибровка промпта сработала один раз по суммарной ошибке.
 */
export async function recordTaskDraftFeedbackBatch(
  items: TaskDraftFeedbackItem[]
): Promise<void> {
  if (items.length === 0) return;
  await apiRequest('/v1/tasks/extract/feedback', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
}
