import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { type CreateWidgetData, type UpdateWidgetData, scopeoApi } from '@/api'

/**
 * Query: Fetch widget for a specific project
 */
export function useWidgetByProjectQuery(projectId: Ref<string | undefined>) {
  const queryKey = computed(() => ['widget', 'project', projectId.value])

  return useQuery({
    queryKey,
    queryFn: async () => {
      if (!projectId.value) throw new Error('No project ID provided')
      try {
        return await scopeoApi.widget.getByProject(projectId.value)
      } catch (error: unknown) {
        // Return null if widget not found (404)
        const err = error as { response?: { status?: number }; statusCode?: number }
        if (err?.response?.status === 404 || err?.statusCode === 404) {
          return null
        }
        throw error
      }
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 5000,
  })
}

/**
 * Query: Fetch all widgets for an organization
 */
export function useWidgetsByOrgQuery(organizationId: Ref<string | undefined>) {
  const queryKey = computed(() => ['widgets', 'org', organizationId.value])

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!organizationId.value) throw new Error('No organization ID provided')
      return scopeoApi.widget.listByOrg(organizationId.value)
    },
    enabled: computed(() => !!organizationId.value),
    staleTime: 5000,
  })
}

/**
 * Mutation: Create a new widget
 */
export function useCreateWidgetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ organizationId, data }: { organizationId: string; data: CreateWidgetData }) =>
      scopeoApi.widget.create(organizationId, data),
    onSuccess: newWidget => {
      // Invalidate widget queries
      queryClient.invalidateQueries({ queryKey: ['widget'] })
      queryClient.invalidateQueries({ queryKey: ['widgets'] })
      // Optionally set the new widget directly in cache
      queryClient.setQueryData(['widget', 'project', newWidget.project_id], newWidget)
    },
  })
}

/**
 * Mutation: Update an existing widget
 */
export function useUpdateWidgetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ widgetId, data }: { widgetId: string; data: UpdateWidgetData }) =>
      scopeoApi.widget.update(widgetId, data),
    onSuccess: updatedWidget => {
      // Invalidate and update cache
      queryClient.invalidateQueries({ queryKey: ['widget'] })
      queryClient.invalidateQueries({ queryKey: ['widgets'] })
      queryClient.setQueryData(['widget', 'project', updatedWidget.project_id], updatedWidget)
    },
  })
}

/**
 * Mutation: Regenerate widget key
 */
export function useRegenerateWidgetKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (widgetId: string) => scopeoApi.widget.regenerateKey(widgetId),
    onSuccess: updatedWidget => {
      queryClient.invalidateQueries({ queryKey: ['widget'] })
      queryClient.invalidateQueries({ queryKey: ['widgets'] })
      queryClient.setQueryData(['widget', 'project', updatedWidget.project_id], updatedWidget)
    },
  })
}

/**
 * Mutation: Delete a widget
 */
export function useDeleteWidgetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (widgetId: string) => scopeoApi.widget.delete(widgetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['widget'] })
      queryClient.invalidateQueries({ queryKey: ['widgets'] })
    },
  })
}
