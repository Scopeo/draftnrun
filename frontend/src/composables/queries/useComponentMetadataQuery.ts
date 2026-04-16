import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type UpdateComponentFieldsRequest, scopeoApi } from '@/api'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

/**
 * Query: Fetch component fields options (release stages, categories)
 */
export function useComponentFieldsOptionsQuery() {
  const queryKey = ['component-fields-options']

  logQueryStart(queryKey, 'useComponentFieldsOptionsQuery')

  return useQuery({
    queryKey,
    queryFn: async () => {
      logNetworkCall(queryKey, '/components/fields/options')
      return await scopeoApi.components.getFieldsOptions()
    },
    staleTime: 1000 * 60 * 10, // 10 minutes - options rarely change
    refetchOnMount: false, // Don't refetch when components remount
  })
}

/**
 * Mutation: Update component fields (release stage, is_agent, function_callable, categories)
 */
export function useUpdateComponentFieldsMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      componentId,
      componentVersionId,
      data,
    }: {
      componentId: string
      componentVersionId: string
      data: UpdateComponentFieldsRequest
    }) => {
      logNetworkCall(
        ['update-component-fields', componentId, componentVersionId],
        `/components/${componentId}/versions/${componentVersionId}/fields`
      )
      return await scopeoApi.components.updateFields(componentId, componentVersionId, data)
    },
    onSuccess: () => {
      // Invalidate component definitions queries to refetch updated data
      queryClient.invalidateQueries({ queryKey: ['component-definitions'] })
      queryClient.invalidateQueries({ queryKey: ['global-component-definitions'] })
    },
  })
}
