import { apiRequest } from './client';

export type IntegrationAdapterStatus = {
  name: string;
  source: string;
  sync_interval_seconds: number;
  last_sync_at: string | null;
  running: boolean;
};

export type IntegrationSyncResult = {
  provider: string;
  synced_items: number;
  conflicts_detected: number;
  errors: string[];
  status: string;
  message: string;
};

export type Lesson = {
  id: string;
  subject: string;
  subject_full_name: string;
  day_of_week: string | null;
  start_time: string;
  end_time: string;
  lesson_type: string;
  teacher: string;
  auditory: string;
  weeks: string;
  week_numbers: number[];
  week: number | null;
  subgroup: number;
  group_number: string;
  next_date: string | null;
};

export type WeekInfo = {
  current_week: number;
  semester_start: string;
  today: string;
};

export type CurrentGroupInfo = {
  group_number: string;
};

export function getIntegrations(): Promise<IntegrationAdapterStatus[]> {
  return apiRequest<IntegrationAdapterStatus[]>('/v1/integrations');
}

export function getLessons(): Promise<Lesson[]> {
  return apiRequest<Lesson[]>('/v1/integrations/lessons');
}

export function getWeekInfo(): Promise<WeekInfo> {
  return apiRequest<WeekInfo>('/v1/integrations/week');
}

export function getCurrentGroup(): Promise<CurrentGroupInfo> {
  return apiRequest<CurrentGroupInfo>('/v1/integrations/current-group');
}

export function importScheduleFile(
  file: File,
  groupNumber: string
): Promise<IntegrationSyncResult> {
  const body = new FormData();
  body.append('file', file);
  body.append('group_number', groupNumber);
  return apiRequest<IntegrationSyncResult>('/v1/integrations/import-file', {
    method: 'POST',
    body,
  });
}

export function syncIntegration(providerName: string): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>(`/v1/integrations/${providerName}/sync`, {
    method: 'POST',
  });
}

export function syncGroup(groupNumber: string): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>('/v1/integrations/sync-group', {
    method: 'POST',
    body: JSON.stringify({ group_number: groupNumber }),
  });
}
