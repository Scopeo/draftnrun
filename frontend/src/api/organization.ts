import type {
  OrganizationLimit,
  OrganizationLimitAndUsageResponse,
  OrganizationLimitResponse,
} from '@/types/organizationLimits'
import { $api } from '@/utils/api'

export const organizationSecretsApi = {
  getAll: (organizationId: string) =>
    $api(`/org/${organizationId}/secrets`, {
      query: { organization_id: organizationId },
    }),

  addOrUpdate: (organizationId: string, secretKey: string, data: { value: string }) =>
    $api(`/org/${organizationId}/secrets/${secretKey}`, {
      method: 'PUT',
      query: {
        organization_id: organizationId,
        secret: data.value,
      },
    }),

  delete: (organizationId: string, secretKey: string) =>
    $api(`/org/${organizationId}/secrets/${secretKey}`, {
      method: 'DELETE',
      query: { organization_id: organizationId },
    }),
}

export const organizationLimitsApi = {
  getAllLimitsAndUsage: (month: number, year: number): Promise<OrganizationLimitAndUsageResponse[]> => {
    return $api('/organizations-limits-and-usage', {
      query: { month, year },
    })
  },

  create: (organizationId: string, data: OrganizationLimit): Promise<OrganizationLimitResponse> =>
    $api(`/organizations/${organizationId}/organization-limits`, {
      method: 'POST',
      body: data,
    }),

  update: (organizationId: string, limitId: string, limit: number): Promise<OrganizationLimitResponse> =>
    $api(`/organizations/${organizationId}/organization-limits`, {
      method: 'PATCH',
      query: {
        id: limitId,
        organization_limit: limit,
      },
    }),

  delete: (organizationId: string, limitId: string): Promise<void> =>
    $api(`/organizations/${organizationId}/organization-limits`, {
      method: 'DELETE',
      query: { id: limitId },
    }),
}

export const organizationCreditUsageApi = {
  getCreditUsage: (organizationId: string) => $api(`/organizations/${organizationId}/credit-usage`),
}

export const orgVariableDefinitionsApi = {
  list: (organizationId: string, params?: { type?: string }) =>
    $api(`/org/${organizationId}/variable-definitions`, { query: params }),
  upsert: (organizationId: string, name: string, data: Record<string, unknown>, projectIds?: string[]) =>
    $api(`/org/${organizationId}/variable-definitions/${name}`, {
      method: 'PUT',
      body: { ...data, ...(projectIds ? { project_ids: projectIds } : {}) },
    }),
  delete: (organizationId: string, name: string) =>
    $api(`/org/${organizationId}/variable-definitions/${name}`, {
      method: 'DELETE',
    }),
}

export const variableSetsApi = {
  list: (organizationId: string) => $api(`/org/${organizationId}/variable-sets`),
  listSetIds: (organizationId: string, projectId: string) =>
    $api(`/org/${organizationId}/set-ids`, { query: { project_id: projectId } }),
  upsert: (organizationId: string, setId: string, values: Record<string, string | null>) =>
    $api(`/org/${organizationId}/variable-sets/${setId}`, { method: 'PUT', body: { values } }),
  delete: (organizationId: string, setId: string) =>
    $api(`/org/${organizationId}/variable-sets/${setId}`, { method: 'DELETE' }),
}
