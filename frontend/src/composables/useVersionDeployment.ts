import { type Ref, ref, watch } from 'vue'
import { scopeoApi } from '@/api'
import type { GraphRunner } from '@/types/version'
import { logger } from '@/utils/logger'

/**
 * Composable for managing version deployment to production.
 */
export function useVersionDeployment(
  projectId: Ref<string | undefined>,
  onDeploymentSuccess?: (graphRunnerId: string) => void
) {
  // State
  const isDeploying = ref(false)
  const deployingGraphRunnerId = ref<string | null>(null)
  const showConfirmDialog = ref(false)
  const pendingDeployment = ref<{ graphRunnerId: string } | null>(null)
  const errorMessage = ref('')
  const showError = ref(false)

  // Deploy to production - shows confirmation dialog
  const deployToProduction = async (graphRunnerId: string) => {
    // Always show confirmation before deploying (there's always a production version)
    pendingDeployment.value = { graphRunnerId }
    showConfirmDialog.value = true
  }

  // Perform the actual deployment
  const performDeployment = async (graphRunnerId: string) => {
    if (!projectId.value) return

    isDeploying.value = true
    deployingGraphRunnerId.value = graphRunnerId

    try {
      await scopeoApi.studio.deployGraphToEnv(projectId.value, graphRunnerId, 'production')
      // Call the success callback immediately to trigger data refresh
      if (onDeploymentSuccess) {
        onDeploymentSuccess(graphRunnerId)
      }
      // The watcher will detect when the graph runner has env='production' and stop the spinner
    } catch (error: unknown) {
      logger.error('Error deploying to production', { error })
      errorMessage.value = error instanceof Error ? error.message : 'Failed to deploy to production.'
      showError.value = true
      isDeploying.value = false
      deployingGraphRunnerId.value = null
    }
  }

  // Handle confirmation dialog
  const confirmDeployment = async () => {
    showConfirmDialog.value = false
    if (pendingDeployment.value) {
      await performDeployment(pendingDeployment.value.graphRunnerId)
      pendingDeployment.value = null
    }
  }

  const cancelDeployment = () => {
    showConfirmDialog.value = false
    pendingDeployment.value = null
  }

  // Watch for deployment completion
  const watchDeploymentCompletion = (graphRunners: Ref<GraphRunner[]>, onComplete: (graphRunnerId: string) => void) => {
    watch(
      () => graphRunners.value,
      () => {
        if (deployingGraphRunnerId.value && isDeploying.value) {
          const deployedRunner = graphRunners.value.find(r => r.graph_runner_id === deployingGraphRunnerId.value)
          if (deployedRunner?.env === 'production') {
            const completedId = deployingGraphRunnerId.value

            isDeploying.value = false
            deployingGraphRunnerId.value = null
            onComplete(completedId)
          }
        }
      },
      { deep: true }
    )
  }

  return {
    isDeploying,
    deployingGraphRunnerId,
    showConfirmDialog,
    pendingDeployment,
    errorMessage,
    showError,
    deployToProduction,
    confirmDeployment,
    cancelDeployment,
    watchDeploymentCompletion,
  }
}
