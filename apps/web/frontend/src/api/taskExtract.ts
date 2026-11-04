import { apiRequest } from './client';
import type { ApiTaskDrafts } from '../types/api';

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
