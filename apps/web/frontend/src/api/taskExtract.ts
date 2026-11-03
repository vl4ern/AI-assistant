import { apiRequest } from './client';
import type { ApiTaskDraft } from '../types/api';

export function extractTaskDraft(
  text: string,
  file: File | null
): Promise<ApiTaskDraft> {
  const form = new FormData();
  if (text.trim()) {
    form.append('text', text);
  }
  if (file) {
    form.append('file', file);
  }

  return apiRequest<ApiTaskDraft>('/v1/tasks/extract', {
    method: 'POST',
    body: form,
  });
}
