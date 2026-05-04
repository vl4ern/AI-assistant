export type ApiTaskStatus =
  | 'todo'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'blocked';

export type ApiTask = {
  id: string;
  title: string;
  description: string | null;
  estimated_minutes: number;
  priority: number;
  deadline: string | null;
  workspace_id: string;
  project_id: string | null;
  auto_reschedule: boolean;
  depends_on: string[];
  allow_split: boolean;
  min_chunk_minutes: number | null;
  status: ApiTaskStatus;
  created_at: string;
  updated_at: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
};

export type ApiTaskCreate = {
  title: string;
  description?: string | null;
  estimated_minutes?: number;
  priority?: number;
  deadline?: string | null;
  workspace_id?: string;
  project_id?: string | null;
  auto_reschedule?: boolean;
  depends_on?: string[];
  allow_split?: boolean;
  min_chunk_minutes?: number | null;
};