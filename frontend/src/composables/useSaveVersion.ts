import { type Ref, ref } from 'vue'
import type { GraphRunner } from '@/composables/queries/useProjectsQuery'
import { useSaveVersionMutation } from '@/composables/queries/useStudioQuery'
import { logger } from '@/utils/logger'

export interface SaveVersionOptions {
  projectId: string | Ref<string>
  currentGraphRunner: Ref<GraphRunner | null>
  onBeforeSave?: () => Promise<void> | void
  onAfterSave?: (response: unknown) => Promise<void> | void
  onError?: (error: unknown) => void
}

export interface SaveVersionResult {
  validationStatus: Ref<'valid' | 'invalid' | 'saving' | 'just_saved'>
  saveError: Ref<string | null>
  isSaving: Ref<boolean>
  saveVersion: (options?: { skipValidation?: boolean }) => Promise<void>
}

/**
 * Shared composable for save version logic used by both Studio and Agents
 * Handles common validation status, error handling, and refresh logic
 */
export function useSaveVersion(options: SaveVersionOptions): SaveVersionResult {
  const { projectId, currentGraphRunner, onBeforeSave, onAfterSave, onError } = options

  const saveVersionMutation = useSaveVersionMutation()
  const validationStatus = ref<'valid' | 'invalid' | 'saving' | 'just_saved'>('valid')
  const saveError = ref<string | null>(null)
  const isSaving = ref(false)

  let validationResetTimeout: ReturnType<typeof setTimeout> | null = null

  /**
   * Extract error message from various error structures (ofetch, axios, etc.)
   */
  const extractErrorMessage = (error: unknown): string => {
    if (error && typeof error === 'object') {
      // ofetch structure
      if ('data' in error && error.data && typeof error.data === 'object' && 'detail' in error.data) {
        return String(error.data.detail)
      }
      // axios structure
      if ('response' in error && error.response && typeof error.response === 'object') {
        const response = error.response as { data?: { detail?: unknown } }
        if (response.data && typeof response.data === 'object' && 'detail' in response.data) {
          return String(response.data.detail)
        }
      }
      // statusMessage
      if ('statusMessage' in error) {
        return String(error.statusMessage)
      }
      // message
      if ('message' in error) {
        return String(error.message)
      }
    }
    if (error instanceof Error) {
      return error.message
    }
    return 'Failed to save version. Please try again.'
  }

  /**
   * Save version (create snapshot)
   */
  const saveVersion = async (options?: { skipValidation?: boolean }) => {
    const effectiveProjectId = typeof projectId === 'string' ? projectId : projectId.value

    if (!currentGraphRunner.value?.graph_runner_id) {
      const errorMsg = 'Cannot save version: No graph runner selected.'

      saveError.value = errorMsg
      validationStatus.value = 'invalid'
      if (onError) onError(new Error(errorMsg))
      return
    }

    isSaving.value = true
    validationStatus.value = 'saving'
    saveError.value = null

    try {
      // Call optional before-save hook
      if (onBeforeSave) {
        await onBeforeSave()
      }

      // Execute save version mutation
      const response = await saveVersionMutation.mutateAsync({
        projectId: effectiveProjectId,
        graphRunnerId: currentGraphRunner.value.graph_runner_id,
      })

      // Call optional after-save hook (e.g., refresh data)
      if (onAfterSave) {
        await onAfterSave(response)
      }

      // Update validation status
      validationStatus.value = 'just_saved'
      saveError.value = null

      // Reset to valid after delay
      if (validationResetTimeout) clearTimeout(validationResetTimeout)
      validationResetTimeout = setTimeout(() => {
        if (validationStatus.value === 'just_saved') {
          validationStatus.value = 'valid'
        }
      }, 2000)
    } catch (error: unknown) {
      logger.error('[useSaveVersion] Error saving version', { error })

      const errorMessage = extractErrorMessage(error)

      saveError.value = errorMessage
      validationStatus.value = 'invalid'

      if (onError) {
        onError(error)
      }
    } finally {
      isSaving.value = false
    }
  }

  return {
    validationStatus,
    saveError,
    isSaving,
    saveVersion,
  }
}
