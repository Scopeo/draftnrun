import { useMutation } from '@tanstack/vue-query'
import { type Ref, ref, watch } from 'vue'
import { useQAEvents } from '@/composables/useQAEvents'
import { scopeoApi } from '@/api'
import { logger } from '@/utils/logger'

interface SaveToQAItem {
  traceId: string
}

interface UseSaveToQAOptions {
  projectId: Ref<string | undefined>
  getConversationData?: () => SaveToQAItem | null
}

export function useSaveToQA(options: UseSaveToQAOptions) {
  const { projectId, getConversationData } = options
  const { emitConversationSaved, emitDatasetCreated } = useQAEvents()

  // State
  const showSaveToQADialog = ref(false)
  const selectedQADataset = ref<string | null>(null)
  const qaDatasets = ref<Array<{ id: string; dataset_name: string }>>([])
  const loadingQADatasets = ref(false)
  const savingToQA = ref(false)
  const saveToQAError = ref<string | null>(null)
  const saveToQASuccess = ref(false)
  const showCreateDataset = ref(false)
  const newDatasetName = ref('')
  const creatingDataset = ref(false)
  let saveToQACloseTimer: ReturnType<typeof setTimeout> | null = null

  // Cleanup timer and reset state when dialog closes
  watch(showSaveToQADialog, newVal => {
    if (!newVal) {
      // Clear timer
      if (saveToQACloseTimer) {
        clearTimeout(saveToQACloseTimer)
        saveToQACloseTimer = null
      }

      // Reset all state
      saveToQAError.value = null
      saveToQASuccess.value = false
      savingToQA.value = false
      showCreateDataset.value = false
      newDatasetName.value = ''
    }
  })

  // Load QA datasets
  const loadQADatasets = async () => {
    if (!projectId.value) return

    // If datasets already loaded, just ensure first one is selected
    if (qaDatasets.value.length > 0) {
      if (!selectedQADataset.value) selectedQADataset.value = qaDatasets.value[0].id

      return
    }

    loadingQADatasets.value = true
    try {
      const datasets = await scopeoApi.qa.getDatasets(projectId.value)

      qaDatasets.value = datasets || []

      // Auto-select first dataset if available
      if (qaDatasets.value.length > 0 && !selectedQADataset.value) selectedQADataset.value = qaDatasets.value[0].id
    } catch (error: unknown) {
      logger.error('Failed to load QA datasets', { error })
      saveToQAError.value = 'Failed to load datasets'
    } finally {
      loadingQADatasets.value = false
    }
  }

  // Create new dataset
  const createDataset = async () => {
    if (!projectId.value || !newDatasetName.value.trim()) return

    const datasetNameToCreate = newDatasetName.value.trim()

    creatingDataset.value = true
    saveToQAError.value = null

    try {
      await scopeoApi.qa.createDatasets(projectId.value, {
        datasets_name: [datasetNameToCreate],
      })

      // Reload datasets list
      qaDatasets.value = [] // Clear cache to force reload
      loadingQADatasets.value = true

      const datasets = await scopeoApi.qa.getDatasets(projectId.value)

      qaDatasets.value = datasets || []
      loadingQADatasets.value = false

      // Auto-select the newly created dataset by name
      const newDataset = qaDatasets.value.find(d => d.dataset_name === datasetNameToCreate)
      if (newDataset) {
        selectedQADataset.value = newDataset.id
      }

      // Emit event to notify QA table that datasets list changed
      emitDatasetCreated({
        projectId: projectId.value!,
        datasetId: selectedQADataset.value!,
      })

      // Close create dataset form
      showCreateDataset.value = false
      newDatasetName.value = ''
    } catch (error: unknown) {
      logger.error('Failed to create dataset', { error })
      saveToQAError.value = error instanceof Error ? error.message : 'Failed to create dataset'
    } finally {
      creatingDataset.value = false
    }
  }

  // Open save to QA dialog
  const openSaveDialog = (traceId?: string) => {
    // If traceId is provided directly, use it
    // Otherwise, use the getConversationData function
    let dataToSave: SaveToQAItem | null = null

    if (traceId !== undefined) dataToSave = { traceId }
    else if (getConversationData) dataToSave = getConversationData()

    if (!dataToSave || !dataToSave.traceId) {
      saveToQAError.value = 'No trace ID found'
      setTimeout(() => {
        saveToQAError.value = null
      }, 3000)

      return
    }

    logger.info('[QA] Opening save dialog', {
      traceId: dataToSave.traceId,
    })
    loadQADatasets()
    showSaveToQADialog.value = true
  }

  // TanStack Query mutation for saving trace
  const saveTraceMutation = useMutation({
    mutationFn: ({ traceId, datasetId }: { traceId: string; datasetId: string }) =>
      scopeoApi.qa.saveTraceToQA(projectId.value!, traceId, datasetId),
    gcTime: 0, // No cache
    onSuccess: (_, variables) => {
      saveToQASuccess.value = true
      logger.info('[QA Debug] Save success! saveToQASuccess =', { data: saveToQASuccess.value })

      // Emit event to trigger QA table refresh
      emitConversationSaved({
        projectId: projectId.value!,
        datasetId: variables.datasetId,
        traceId: variables.traceId,
      })

      // Close dialog after 3 seconds
      saveToQACloseTimer = setTimeout(() => {
        showSaveToQADialog.value = false
        saveToQASuccess.value = false
        selectedQADataset.value = null
        saveToQACloseTimer = null
      }, 3000)
    },
    onError: (error: any) => {
      logger.error('Failed to save trace to QA', { error })
      saveToQAError.value = error.message || 'Failed to save trace to QA'
    },
  })

  // Save to QA
  const saveToQA = async () => {
    if (!selectedQADataset.value || !projectId.value || !getConversationData) return

    // Guard against concurrent saves
    if (savingToQA.value) {
      logger.info('[QA] Save already in progress, ignoring duplicate request')
      return
    }

    const conversationData = getConversationData()
    if (!conversationData || !conversationData.traceId) {
      saveToQAError.value = 'No trace ID found'
      return
    }

    // Clear any existing close timer
    if (saveToQACloseTimer) {
      clearTimeout(saveToQACloseTimer)
      saveToQACloseTimer = null
    }

    savingToQA.value = true
    saveToQAError.value = null
    saveToQASuccess.value = false

    try {
      await saveTraceMutation.mutateAsync({
        traceId: conversationData.traceId,
        datasetId: selectedQADataset.value,
      })
    } finally {
      savingToQA.value = false
    }
  }

  return {
    // State
    showSaveToQADialog,
    selectedQADataset,
    qaDatasets,
    loadingQADatasets,
    savingToQA,
    saveToQAError,
    saveToQASuccess,
    showCreateDataset,
    newDatasetName,
    creatingDataset,

    // Actions
    loadQADatasets,
    openSaveDialog,
    saveToQA,
    createDataset,
  }
}
