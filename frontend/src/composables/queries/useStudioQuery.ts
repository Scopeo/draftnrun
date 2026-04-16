import { useMutation, useQueryClient } from '@tanstack/vue-query'
import type {
  ApiComponentInstance,
  ApiEdge,
  ApiRelationship,
  GraphUpdateResponse,
} from '@/components/studio/types/graph.types'
import { scopeoApi } from '@/api'
import { logNetworkCall } from '@/utils/queryLogger'

export interface UpdateGraphData {
  component_instances: ApiComponentInstance[]
  relationships: ApiRelationship[]
  edges: ApiEdge[]
}

/**
 * Mutation: Save version (create snapshot)
 */
export function useSaveVersionMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ projectId, graphRunnerId }: { projectId: string; graphRunnerId: string }) => {
      logNetworkCall(
        ['save-version', projectId, graphRunnerId],
        `/projects/${projectId}/graph/${graphRunnerId}/save-version`
      )
      return await scopeoApi.studio.saveVersion(projectId, graphRunnerId)
    },
    onSuccess: (_data, variables) => {
      // Invalidate project and agents queries to refresh graph_runners list
      queryClient.invalidateQueries({ queryKey: ['project', variables.projectId] })
      queryClient.invalidateQueries({ queryKey: ['agent', variables.projectId] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}

/**
 * Mutation: Update graph
 */
export function useUpdateGraphMutation() {
  const queryClient = useQueryClient()

  return useMutation<GraphUpdateResponse, Error, { projectId: string; graphRunnerId: string; data: UpdateGraphData }>({
    mutationFn: async ({ projectId, graphRunnerId, data }) => {
      logNetworkCall(['update-graph', projectId, graphRunnerId], `/projects/${projectId}/graph/${graphRunnerId}`)
      return await scopeoApi.studio.updateGraph(projectId, graphRunnerId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}
