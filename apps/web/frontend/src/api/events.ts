import { apiRequest } from './client';

export type ApiEvent = {
  id: string;
  title: string;
  start_at: string;
  end_at: string;
  source: string;
};

export type ApiEventCreate = {
  title: string;
  start_at: string;
  end_at: string;
  source?: string;
};

export function getEvents(): Promise<ApiEvent[]> {
  return apiRequest<ApiEvent[]>('/v1/events');
}

export function createEvent(payload: ApiEventCreate): Promise<ApiEvent> {
  return apiRequest<ApiEvent>('/v1/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}