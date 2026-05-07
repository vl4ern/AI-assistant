import { apiRequest } from './client';
import type { ApiTask, ApiTaskCreate, ApiTaskStatus, ApiTaskUpdate } from '../types/api';

export function getTasks(): Promise<ApiTask[]> {
  return apiRequest<ApiTask[]>('/v1/tasks');
}

export function createTask(payload: ApiTaskCreate): Promise<ApiTask> {
  return apiRequest<ApiTask>('/v1/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTask(taskId: string, payload: ApiTaskUpdate): Promise<ApiTask> {
  return apiRequest<ApiTask>(`/v1/tasks/${taskId}`, {
    method: 'PUT',
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

export function deleteTask(taskId: string): Promise<void> {
  return apiRequest<void>(`/v1/tasks/${taskId}`, {
    method: 'DELETE',
  });
}
