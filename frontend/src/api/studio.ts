import type { GraphUpdateResponse } from '@/components/studio/types/graph.types'
import type { FieldExpressionAutocompleteSuggestion } from '@/types/fieldExpressions'
import { $api } from '@/utils/api'

export const studioApi = {
  getGraph: (projectId: string, graphRunnerId: string) => $api(`/projects/${projectId}/graph/${graphRunnerId}`),

  updateGraph: (projectId: string, graphRunnerId: string, data: any): Promise<GraphUpdateResponse> =>
    $api<GraphUpdateResponse>(`/projects/${projectId}/graph/${graphRunnerId}`, {
      method: 'PUT',
      body: data,
    }),

  deployGraph: (projectId: string, graphRunnerId: string) =>
    $api(`/projects/${projectId}/graph/${graphRunnerId}/deploy`, {
      method: 'POST',
    }),

  deployGraphToEnv: (projectId: string, graphRunnerId: string, env: 'production' | 'draft') =>
    $api(`/projects/${projectId}/graph/${graphRunnerId}/env/${env}`, {
      method: 'PUT',
    }),

  loadVersionAsDraft: (projectId: string, graphRunnerId: string) =>
    $api(`/projects/${projectId}/graph/${graphRunnerId}/load-as-draft`, {
      method: 'POST',
    }),

  getModificationHistory: (projectId: string, graphRunnerId: string) =>
    $api(`/projects/${projectId}/graph/${graphRunnerId}/modification-history`),

  saveVersion: (projectId: string, graphRunnerId: string) =>
    $api(`/projects/${projectId}/graph/${graphRunnerId}/save-version`, {
      method: 'POST',
    }),

  autocompleteFieldExpression: async (
    projectId: string,
    graphRunnerId: string,
    query: string,
    targetInstanceId: string
  ): Promise<FieldExpressionAutocompleteSuggestion[]> => {
    const response = await $api<{ suggestions: FieldExpressionAutocompleteSuggestion[] }>(
      `/projects/${projectId}/graph/${graphRunnerId}/field-expressions/autocomplete`,
      { query: { query, target_instance_id: targetInstanceId } }
    )

    return response?.suggestions ?? []
  },
}
