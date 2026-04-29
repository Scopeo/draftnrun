import type {
  ComponentCreateV2Data,
  ComponentGetV2Response,
  ComponentUpdateV2Data,
  ComponentV2Response,
  GraphData,
  GraphUpdateResponse,
  GraphV2Response,
  TopologyUpdateV2Data,
} from '@/components/studio/types/graph.types'
import type { FieldExpressionAutocompleteSuggestion } from '@/types/fieldExpressions'
import { $api } from '@/utils/api'

export const studioApi = {
  // ─── V1 (full graph read — TODO: migrate to V2 once all component data is available) ──
  getGraph: (projectId: string, graphRunnerId: string): Promise<GraphData> =>
    $api<GraphData>(`/projects/${projectId}/graph/${graphRunnerId}`),

  // ─── V2 (granular graph API) ───────────────────────────────────────
  getGraphV2: (projectId: string, graphRunnerId: string): Promise<GraphV2Response> =>
    $api<GraphV2Response>(`/v2/projects/${projectId}/graph/${graphRunnerId}`),

  updateGraphTopologyV2: (
    projectId: string,
    graphRunnerId: string,
    data: TopologyUpdateV2Data
  ): Promise<GraphUpdateResponse> =>
    $api<GraphUpdateResponse>(`/v2/projects/${projectId}/graph/${graphRunnerId}/map`, {
      method: 'PUT',
      body: data,
    }),

  createComponentV2: (
    projectId: string,
    graphRunnerId: string,
    data: ComponentCreateV2Data
  ): Promise<ComponentV2Response> =>
    $api<ComponentV2Response>(`/v2/projects/${projectId}/graph/${graphRunnerId}/components`, {
      method: 'POST',
      body: data,
    }),

  updateComponentV2: (
    projectId: string,
    graphRunnerId: string,
    instanceId: string,
    data: ComponentUpdateV2Data
  ): Promise<ComponentV2Response> =>
    $api<ComponentV2Response>(`/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`, {
      method: 'PUT',
      body: data,
    }),

  getComponentV2: (projectId: string, graphRunnerId: string, instanceId: string): Promise<ComponentGetV2Response> =>
    $api<ComponentGetV2Response>(`/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`),

  deleteComponentV2: (projectId: string, graphRunnerId: string, instanceId: string): Promise<void> =>
    $api<void>(`/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`, {
      method: 'DELETE',
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
