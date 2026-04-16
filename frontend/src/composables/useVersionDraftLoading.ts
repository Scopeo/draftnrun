import { useQueryClient } from '@tanstack/vue-query'
import { type Ref, ref } from 'vue'
import { scopeoApi } from '@/api'
import { logger } from '@/utils/logger'

/**
 * Composable for managing loading a version as draft.
 */
export function useVersionDraftLoading(
  projectId: Ref<string | undefined>,
  onLoadDraftSuccess?: (graphRunnerId: string) => void
) {
  const queryClient = useQueryClient()

  // State
  const isLoadingDraft = ref(false)
  const showConfirmDialog = ref(false)
  const pendingLoadDraft = ref<{ graphRunnerId: string } | null>(null)
  const errorMessage = ref('')
  const showError = ref(false)

  // Load version as draft - shows confirmation dialog
  const loadAsDraft = async (graphRunnerId: string) => {
    // Show confirmation before loading as draft
    pendingLoadDraft.value = { graphRunnerId }
    showConfirmDialog.value = true
  }

  // Perform the actual load as draft
  const performLoadAsDraft = async (graphRunnerId: string) => {
    if (!projectId.value) return

    isLoadingDraft.value = true

    try {
      await scopeoApi.studio.loadVersionAsDraft(projectId.value, graphRunnerId)

      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      await queryClient.invalidateQueries({ queryKey: ['project', projectId.value] })

      // Call success callback immediately after API succeeds
      if (onLoadDraftSuccess) {
        onLoadDraftSuccess(graphRunnerId)
      }
    } catch (error: unknown) {
      logger.error('Error loading version as draft', { error })
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load version as draft.'
      showError.value = true
    } finally {
      isLoadingDraft.value = false
    }
  }

  // Handle load draft confirmation dialog
  const confirmLoadDraft = async () => {
    showConfirmDialog.value = false
    if (pendingLoadDraft.value) {
      await performLoadAsDraft(pendingLoadDraft.value.graphRunnerId)
      pendingLoadDraft.value = null
    }
  }

  const cancelLoadDraft = () => {
    showConfirmDialog.value = false
    pendingLoadDraft.value = null
  }

  return {
    isLoadingDraft,
    showConfirmDialog,
    pendingLoadDraft,
    errorMessage,
    showError,
    loadAsDraft,
    confirmLoadDraft,
    cancelLoadDraft,
  }
}
