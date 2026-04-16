<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed, onUnmounted, ref, watchEffect } from 'vue'
import { logger } from '@/utils/logger'
import SaveDeployButtons from '@/components/shared/SaveDeployButtons.vue'
import { type Agent, type GraphRunner, useCurrentAgent } from '@/composables/queries/useAgentsQuery'
import { useSavingState } from '@/composables/useSavingState'
import { scopeoApi } from '@/api'

interface Props {
  agent: (Agent & { graph_runners?: GraphRunner[] }) | null
  onSave?: (create_snapshot?: boolean) => Promise<void>
  showStatusIndicator?: boolean
  isLoading?: boolean
  projectId?: string
  isSavingVersion?: Ref<boolean>
  saveVersionValidationStatus?: Ref<'valid' | 'invalid' | 'saving' | 'just_saved'>
  saveVersionError?: Ref<string | null>
}

const props = withDefaults(defineProps<Props>(), {
  showStatusIndicator: true,
  isLoading: false,
})

const emit = defineEmits(['change', 'deployed', 'openCronModal'])
const { currentGraphRunner, setCurrentGraphRunner } = useCurrentAgent()
const queryClient = useQueryClient()

const hasUnsavedChanges = ref(false)
const savingState = ref(false)
const isDeploying = ref(false)
// Local validation state (for regular saves)
const localValidationStatus = ref<'valid' | 'invalid' | 'saving' | 'just_saved'>('valid')
const localSaveError = ref<string | null>(null)

// Track agent ID to detect changes (TanStack Query pattern - using watchEffect for reactive side effects)
// This is more aligned with TanStack Query's reactive patterns than watch()
const currentAgentId = computed(() => props.agent?.id ?? null)
const previousAgentId = ref<string | null>(null)

// Use watchEffect (reactive effect) instead of watch - more aligned with TanStack Query patterns
// This automatically tracks dependencies and runs when agent ID changes
watchEffect(() => {
  const currentId = currentAgentId.value
  const prevId = previousAgentId.value

  // If agent ID changed (and we had a previous ID), reset unsaved changes
  if (currentId !== prevId && prevId !== null && currentId !== null) {
    hasUnsavedChanges.value = false
  }

  // Update previous ID for next comparison
  previousAgentId.value = currentId
})

// Computed validation status: prefer shared composable status, fallback to local
const validationStatus = computed(() => {
  return props.saveVersionValidationStatus?.value ?? localValidationStatus.value
})

const saveError = computed(() => {
  return props.saveVersionError?.value ?? localSaveError.value
})

// Shared saving state helper - same pattern as StudioFlow
const isSaving = useSavingState(props.isSavingVersion, savingState)

let saveTimeout: ReturnType<typeof setTimeout> | null = null
let validationResetTimeout: ReturnType<typeof setTimeout> | null = null

// Clean up timeouts on unmount
onUnmounted(() => {
  if (saveTimeout) clearTimeout(saveTimeout)
  if (validationResetTimeout) clearTimeout(validationResetTimeout)
})

const autoSave = async () => {
  const isDraftMode = currentGraphRunner.value?.env === 'draft'
  if (!isDraftMode || props.isLoading) return

  if (saveTimeout) {
    clearTimeout(saveTimeout)
  }

  saveTimeout = setTimeout(async () => {
    await saveChanges()
  }, 1000)
}

// Check if production deployment exists
const hasProductionDeployment = computed(() => {
  if (!props.agent?.graph_runners) return false
  return props.agent.graph_runners.some((runner: { env: string | null }) => runner.env === 'production')
})

const saveChanges = async (create_snapshot = false) => {
  if (!props.agent) {
    return
  }

  // Only manage local state if shared composable is not provided
  const useLocalState = !props.saveVersionValidationStatus

  // For save version (create_snapshot), also set local savingState to ensure loading animation shows
  // even when using shared composable (the shared composable's isSavingVersion will update via saveVersionAction)
  if (create_snapshot && !useLocalState) {
    savingState.value = true
  }

  if (useLocalState) {
    savingState.value = true
    localValidationStatus.value = 'saving'
    localSaveError.value = null
  }

  try {
    if (props.onSave) {
      await props.onSave(create_snapshot)
      hasUnsavedChanges.value = false

      if (useLocalState) {
        localValidationStatus.value = 'just_saved'
        localSaveError.value = null
        // Reset to valid after delay
        if (validationResetTimeout) clearTimeout(validationResetTimeout)
        validationResetTimeout = setTimeout(() => {
          if (localValidationStatus.value === 'just_saved') {
            localValidationStatus.value = 'valid'
          }
        }, 2000)
      }
    } else {
      if (useLocalState) {
        localValidationStatus.value = 'invalid'
        localSaveError.value = 'No save function provided'
      }
    }
  } catch (error: unknown) {
    logger.error('Error saving agent', { error })
    if (useLocalState) {
      localValidationStatus.value = 'invalid'
      localSaveError.value = error instanceof Error ? error.message : 'Failed to save agent'
    }
  } finally {
    if (useLocalState) {
      savingState.value = false
    } else if (create_snapshot) {
      // Reset local savingState after save version completes (shared composable will handle its own state)
      savingState.value = false
    }
  }
}

const onSaveVersion = async () => {
  if (!props.agent || !currentGraphRunner.value || hasUnsavedChanges.value) return

  // If already saving (from either shared composable or local state), don't proceed
  if (isSaving.value) return

  await saveChanges(true)
}

const handleDeployConfirm = async () => {
  if (!props.agent || !currentGraphRunner.value) return

  isDeploying.value = true
  try {
    const draftGraphRunnerId = currentGraphRunner.value.graph_runner_id
    const deployResponse = await scopeoApi.agents.deploy(props.agent.id, draftGraphRunnerId)

    logger.info('Deploy response', { data: deployResponse })

    // The backend creates a new draft graph runner when deploying
    // We need to switch to this new draft to continue editing
    if (deployResponse.draft_graph_runner_id) {
      // Invalidate agents query to refresh the list
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      await queryClient.invalidateQueries({ queryKey: ['agent', props.agent?.id] })

      // Small delay to ensure cache is updated
      await new Promise(resolve => setTimeout(resolve, 100))

      // Now switch to the new draft graph runner
      setCurrentGraphRunner({
        graph_runner_id: deployResponse.draft_graph_runner_id,
        env: 'draft',
        tag_name: null,
      })

      // Emit deployed event so parent components can refresh
      emit('deployed', deployResponse)
      return deployResponse
    } else {
      throw new Error('Deploy response missing draft_graph_runner_id')
    }
  } finally {
    isDeploying.value = false
  }
}

const markAsChanged = () => {
  hasUnsavedChanges.value = true
  emit('change')
  autoSave()
}

const markAsSaved = () => {
  hasUnsavedChanges.value = false
}

defineExpose({
  markAsChanged,
  markAsSaved,
  hasUnsavedChanges,
  validationStatus,
  saveError,
})
</script>

<template>
  <SaveDeployButtons
    :current-graph-runner="currentGraphRunner"
    :has-unsaved-changes="hasUnsavedChanges"
    :is-saving="isSaving"
    :is-deploying="isDeploying"
    :validation-status="validationStatus"
    :save-error="saveError"
    :has-production-deployment="hasProductionDeployment"
    :show-status-indicator="showStatusIndicator"
    :on-save-version="onSaveVersion"
    :on-deploy="handleDeployConfirm"
    :on-schedule-click="() => emit('openCronModal')"
    @deployed="emit('deployed', $event)"
  />
</template>
