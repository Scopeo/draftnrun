import { useMutation, useQueryClient } from '@tanstack/vue-query'
import type {
  ComponentCreateV2Data,
  ComponentGetV2Response,
  ComponentUpdateV2Data,
  ComponentV2Response,
  GraphUpdateResponse,
  GraphV2Response,
  TopologyUpdateV2Data,
} from '@/components/studio/types/graph.types'
import { studioApi } from '@/api'
import { logNetworkCall } from '@/utils/queryLogger'

export const graphV2QueryKey = (projectId: string, graphRunnerId: string) =>
  ['graph-v2', projectId, graphRunnerId] as const

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
      return await studioApi.saveVersion(projectId, graphRunnerId)
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
 * Mutation: Update graph topology (V2 — edges, relationships, node metadata only)
 */
export function useUpdateGraphTopologyV2Mutation() {
  const queryClient = useQueryClient()

  return useMutation<
    GraphUpdateResponse,
    Error,
    { projectId: string; graphRunnerId: string; data: TopologyUpdateV2Data }
  >({
    mutationFn: async ({ projectId, graphRunnerId, data }) => {
      logNetworkCall(
        ['update-topology-v2', projectId, graphRunnerId],
        `/v2/projects/${projectId}/graph/${graphRunnerId}/map`
      )
      return await studioApi.updateGraphTopologyV2(projectId, graphRunnerId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}

/**
 * Imperative fetch for graph V2 topology.
 * Uses queryClient.fetchQuery for deduplication and cache coherence
 * with the reactive useGraphQueryV2 (same query key).
 */
export function useFetchGraphV2() {
  const queryClient = useQueryClient()

  return {
    fetchGraphV2: (projectId: string, graphRunnerId: string): Promise<GraphV2Response> => {
      const key = graphV2QueryKey(projectId, graphRunnerId)
      logNetworkCall(key, `/v2/projects/${projectId}/graph/${graphRunnerId}`)
      return queryClient.fetchQuery<GraphV2Response>({
        queryKey: key,
        queryFn: () => studioApi.getGraphV2(projectId, graphRunnerId),
        staleTime: 0,
      })
    },
  }
}

/**
 * Imperative fetch for a single component instance V2.
 * Uses queryClient.fetchQuery for deduplication and cache coherence.
 */
export function useFetchComponentV2() {
  const queryClient = useQueryClient()

  return {
    fetchComponentV2: (
      projectId: string,
      graphRunnerId: string,
      instanceId: string
    ): Promise<ComponentGetV2Response> => {
      const key = ['get-component-v2', projectId, graphRunnerId, instanceId] as const
      logNetworkCall(
        key,
        `/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`
      )
      return queryClient.fetchQuery<ComponentGetV2Response>({
        queryKey: key,
        queryFn: () => studioApi.getComponentV2(projectId, graphRunnerId, instanceId),
        staleTime: 0,
      })
    },
  }
}

/**
 * Mutation: Create a single component instance (V2)
 */
export function useCreateComponentV2Mutation() {
  const queryClient = useQueryClient()

  return useMutation<
    ComponentV2Response,
    Error,
    { projectId: string; graphRunnerId: string; data: ComponentCreateV2Data }
  >({
    mutationFn: async ({ projectId, graphRunnerId, data }) => {
      logNetworkCall(
        ['create-component-v2', projectId, graphRunnerId],
        `/v2/projects/${projectId}/graph/${graphRunnerId}/components`
      )
      return await studioApi.createComponentV2(projectId, graphRunnerId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: graphV2QueryKey(variables.projectId, variables.graphRunnerId),
      })
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}

/**
 * Mutation: Update a single component instance (V2)
 */
export function useUpdateComponentV2Mutation() {
  const queryClient = useQueryClient()

  return useMutation<
    ComponentV2Response,
    Error,
    { projectId: string; graphRunnerId: string; instanceId: string; data: ComponentUpdateV2Data }
  >({
    mutationFn: async ({ projectId, graphRunnerId, instanceId, data }) => {
      logNetworkCall(
        ['update-component-v2', projectId, graphRunnerId, instanceId],
        `/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`
      )
      return await studioApi.updateComponentV2(projectId, graphRunnerId, instanceId, data)
    },
    onSuccess: (data, variables) => {
      const key = graphV2QueryKey(variables.projectId, variables.graphRunnerId)
      queryClient.setQueryData<GraphV2Response>(key, (old) => {
        if (!old) return old
        return {
          ...old,
          last_edited_time: data.last_edited_time ?? old.last_edited_time,
          last_edited_user_id: data.last_edited_user_id ?? old.last_edited_user_id,
          graph_map: {
            ...old.graph_map,
            nodes: old.graph_map.nodes.map((node) =>
              node.instance_id === variables.instanceId
                ? { ...node, label: data.label ?? node.label, is_start_node: data.is_start_node ?? node.is_start_node }
                : node
            ),
          },
        }
      })
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}

/**
 * Mutation: Delete a single component instance (V2)
 */
export function useDeleteComponentV2Mutation() {
  const queryClient = useQueryClient()

  return useMutation<
    void,
    Error,
    { projectId: string; graphRunnerId: string; instanceId: string }
  >({
    mutationFn: async ({ projectId, graphRunnerId, instanceId }) => {
      logNetworkCall(
        ['delete-component-v2', projectId, graphRunnerId, instanceId],
        `/v2/projects/${projectId}/graph/${graphRunnerId}/components/${instanceId}`
      )
      return await studioApi.deleteComponentV2(projectId, graphRunnerId, instanceId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: graphV2QueryKey(variables.projectId, variables.graphRunnerId),
      })
      queryClient.invalidateQueries({
        queryKey: ['modification-history', variables.projectId, variables.graphRunnerId],
      })
    },
  })
}
