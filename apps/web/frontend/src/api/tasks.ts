import { apiRequest } from './client';
import type { ApiTask, ApiTaskCreate, ApiTaskStatus } from '../types/api';

export function getTasks(): Promise<ApiTask[]> {
  return apiRequest<ApiTask[]>('/v1/tasks');
}

export function createTask(payload: ApiTaskCreate): Promise<ApiTask> {
  return apiRequest<ApiTask>('/v1/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTaskStatus(
  taskId: string,
  status: ApiTaskStatus
): Promise<ApiTask> {
  return apiRequest<ApiTask>(`/v1/tasks/${taskId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}