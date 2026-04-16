import { $api } from '@/utils/api'

export const sourcesApi = {
  getAll: (organizationId: string) => $api(`/sources/${organizationId}`),
  update: (organizationId: string, sourceId: string) =>
    $api(`/sources/${organizationId}/${sourceId}`, { method: 'POST' }),
  delete: (organizationId: string, sourceId: string) =>
    $api(`/sources/${organizationId}/${sourceId}`, { method: 'DELETE' }),
  checkUsage: (organizationId: string, sourceId: string) =>
    $api(`/organizations/${organizationId}/sources/${sourceId}/usage`),
}

export const ingestionTaskApi = {
  getAll: (organizationId: string) => $api(`/ingestion_task/${organizationId}`),
  create: (organizationId: string, data: any) =>
    $api(`/ingestion_task/${organizationId}`, { method: 'POST', body: data }),
  delete: (organizationId: string, taskId: string) =>
    $api(`/ingestion_task/${organizationId}/${taskId}`, { method: 'DELETE' }),
}
