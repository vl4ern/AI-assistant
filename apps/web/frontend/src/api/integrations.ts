import { apiRequest } from './client';

export type IntegrationSyncResult = {
  provider: string;
  imported_items: number;
  updated_items: number;
  warnings: string[];
};

export function getIntegrations(): Promise<string[]> {
  return apiRequest<string[]>('/v1/integrations');
}

export function syncIntegration(providerName: string): Promise<IntegrationSyncResult> {
  return apiRequest<IntegrationSyncResult>(
    `/v1/integrations/${providerName}/sync`,
    {
      method: 'POST',
    }
  );
}