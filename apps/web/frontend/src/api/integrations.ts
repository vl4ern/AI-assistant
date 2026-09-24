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

export function getIntegrations(): Promise<IntegrationAdapterStatus[]> {
  return apiRequest<IntegrationAdapterStatus[]>('/v1/integrations');
}

export function syncAllIntegrations(): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>('/v1/integrations/sync', {
    method: 'POST',
  });
}

export function syncIntegration(providerName: string): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>(
    `/v1/integrations/${providerName}/sync`,
    {
      method: 'POST',
    }
  );
}
