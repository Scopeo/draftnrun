import { useQueryClient } from '@tanstack/vue-query'
import { type Ref, ref } from 'vue'
import { scopeoApi } from '@/api'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { GraphRunner } from '@/types/version'
import { logger } from '@/utils/logger'

/**
 * Composable for refreshing graph runners after deployment or draft loading.
 * Handles context-aware query invalidation (agent vs project).
 */
export function useVersionRefresh(projectId: Ref<string>, context: Ref<'agent' | 'project'>) {
  const isRefreshing = ref(false)
  const queryClient = useQueryClient()
  const { selectedOrgId } = useSelectedOrg()

  const refreshAfterDeployment = async (
    graphRunnerId: string,
    env: 'production' | 'draft'
  ): Promise<GraphRunner[] | null> => {
    if (isRefreshing.value) return null

    isRefreshing.value = true

    try {
      // Invalidate appropriate queries based on context
      await queryClient.invalidateQueries({ queryKey: ['project', projectId.value] })

      if (context.value === 'agent') {
        await queryClient.invalidateQueries({ queryKey: ['agents', selectedOrgId.value] })
      }

      // Refetch the project
      const updatedProject = await queryClient.fetchQuery({
        queryKey: ['project', projectId.value],
        queryFn: async () => {
          const data = await scopeoApi.projects.getById(projectId.value)
          if (!data) {
            logger.error('[useVersionRefresh] Project not found', { error: projectId.value })
            throw new Error('Project not found')
          }
          return data
        },
      })

      return updatedProject.graph_runners || []
    } finally {
      isRefreshing.value = false
    }
  }

  return {
    isRefreshing,
    refreshAfterDeployment,
  }
}
