import { apiRequest } from './client';
import type { ApiTask } from '../types/api';

export type ScheduledSlot = {
  task_id: string;
  title: string;
  start_at: string;
  end_at: string;
  score: number;
};

export type SchedulePlan = {
  generated_at: string;
  slots: ScheduledSlot[];
  unscheduled_task_ids: string[];
  prime_task_id: string | null;
};

export type TodayView = {
  date: string;
  prime_task_id: string | null;
  tasks: ApiTask[];
  schedule_dirty: boolean;
};

export function rebuildSchedule(): Promise<SchedulePlan> {
  return apiRequest<SchedulePlan>('/v1/schedule/rebuild', {
    method: 'POST',
  });
}

export function getTodayView(): Promise<TodayView> {
  return apiRequest<TodayView>('/v1/schedule/today');
}