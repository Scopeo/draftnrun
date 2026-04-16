import { $api } from '@/utils/api'

export const apiKeysApi = {
  getAll: (projectId: string) => $api('/auth/api-key', { query: { project_id: projectId } }),
  create: (projectId: string, data: { key_name: string; project_id: string }) =>
    $api('/auth/api-key', { method: 'POST', body: data }),
  revoke: (projectId: string, data: { key_id: string }) =>
    $api('/auth/api-key', {
      method: 'DELETE',
      query: { project_id: projectId },
      body: data,
    }),
}

export const orgApiKeysApi = {
  getAll: (organizationId: string) => $api('/auth/org-api-key', { query: { organization_id: organizationId } }),
  create: (data: { key_name: string; org_id: string }) => $api('/auth/org-api-key', { method: 'POST', body: data }),
  revoke: (organizationId: string, data: { key_id: string }) =>
    $api('/auth/org-api-key', { method: 'DELETE', query: { organization_id: organizationId }, body: data }),
}
