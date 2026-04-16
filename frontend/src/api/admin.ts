import { $api } from '@/utils/api'

export interface ComponentFieldsOptionsResponse {
  release_stages: string[]
  categories: Array<{
    id: string
    name: string
    description: string | null
    icon: string | null
    display_order: number
  }>
}

export interface UpdateComponentFieldsRequest {
  is_agent?: boolean
  function_callable?: boolean
  category_ids?: string[]
  release_stage?: string
}

export const adminToolsApi = {
  createSpecificApiTool: (data: {
    tool_display_name: string
    endpoint: string
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' | string
    headers?: Record<string, any> | null
    timeout?: number | null
    fixed_parameters?: Record<string, any> | null
    tool_description_name: string
    tool_description?: string | null
    tool_properties?: Record<string, any> | null
    required_tool_properties?: string[] | null
  }) =>
    $api('/admin-tools/api-tools', {
      method: 'POST',
      body: data,
    }),
}

export const settingsSecretsApi = {
  list: () => $api('/admin-tools/settings-secrets/', { method: 'GET' }),
  upsert: (data: { key: string; secret: string }) =>
    $api('/admin-tools/settings-secrets/', { method: 'POST', body: data }),
  delete: (key: string) => $api(`/admin-tools/settings-secrets/${encodeURIComponent(key)}`, { method: 'DELETE' }),
}

export const componentsApi = {
  getAll: (organizationId: string, releaseStage?: 'beta' | 'early_access' | 'public' | 'internal') => {
    const params: Record<string, any> = {}
    if (releaseStage) params.release_stage = releaseStage

    return $api(`/components/${organizationId}`, { query: params })
  },

  getAllGlobal: (releaseStage?: 'beta' | 'early_access' | 'public' | 'internal') => {
    const params: Record<string, any> = {}
    if (releaseStage) params.release_stage = releaseStage

    return $api('/components', { query: params })
  },

  getFieldsOptions: (): Promise<ComponentFieldsOptionsResponse> => $api('/components/fields/options'),

  updateFields: (
    componentId: string,
    componentVersionId: string,
    data: UpdateComponentFieldsRequest
  ): Promise<{ status: string }> =>
    $api(`/components/${componentId}/versions/${componentVersionId}/fields`, {
      method: 'PUT',
      body: data,
    }),

  deleteVersion: (componentId: string, componentVersionId: string) =>
    $api(`/components/${componentId}/versions/${componentVersionId}`, { method: 'DELETE' }),

  deleteComponent: (componentId: string) => $api(`/components/${componentId}`, { method: 'DELETE' }),

  updateCosts: (
    organizationId: string,
    componentVersionId: string,
    costs: {
      credits_per_call?: number | null
      credits_per?: Record<string, number> | null
    }
  ) =>
    $api(`/organizations/${organizationId}/component-version-costs/${componentVersionId}`, {
      method: 'PATCH',
      body: costs,
    }),

  deleteCosts: (organizationId: string, componentVersionId: string) =>
    $api(`/organizations/${organizationId}/component-version-costs/${componentVersionId}`, {
      method: 'DELETE',
    }),
}

export const categoriesApi = {
  getAll: () => $api('/categories'),
}
