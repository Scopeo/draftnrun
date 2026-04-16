import { useQueryClient } from '@tanstack/vue-query'
import { format } from 'date-fns'
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { logger } from '@/utils/logger'
import {
  type IngestionTask,
  type Source,
  useDeleteIngestionTaskMutation,
  useDeleteSourceMutation,
  useIngestionTasksQuery,
  useSourcesQuery,
  useUpdateSourceMutation,
} from '@/composables/queries/useDataSourcesQuery'
import { useNotifications } from '@/composables/useNotifications'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { scopeoApi } from '@/api'

export const formatSourceDateTime = (value: unknown) => {
  if (typeof value !== 'string' || value.trim() === '') return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return format(date, 'MMM dd, yyyy HH:mm')
}

export const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (typeof error === 'string' && error.trim()) return error
  if (error && typeof error === 'object') {
    const e = error as { message?: string; data?: { detail?: string } }
    if (e.message) return e.message
    if (e.data?.detail) return e.data.detail
  }
  return fallbackMessage
}

export const hasTaskErrorOrWarning = (task: IngestionTask) => {
  if (!task.result_metadata) return false
  return task.result_metadata.type === 'error' || task.result_metadata.type === 'partial_success'
}

export const getStatusChipProps = (task: IngestionTask) => {
  const status = task.status
  const lowerStatus = String(status).toLowerCase()

  const hasWarning =
    task.result_metadata?.type === 'partial_success' &&
    (lowerStatus === 'done' || lowerStatus === 'completed' || status === true)

  const hasError = task.result_metadata?.type === 'error'

  if (lowerStatus === 'done' || lowerStatus === 'completed' || status === true) {
    return {
      color: 'success',
      text: lowerStatus === 'completed' ? 'Completed' : 'Done',
      showWarning: hasWarning,
      showError: false,
    }
  }
  if (lowerStatus === 'pending') {
    return { color: 'warning', text: 'Pending', showWarning: false, showError: false }
  }
  if (lowerStatus === 'failed' || lowerStatus === 'error' || status === false || hasError) {
    return { color: 'error', text: 'Failed', showWarning: false, showError: hasError }
  }
  return { color: 'grey', text: String(status) || 'Unknown', showWarning: false, showError: false }
}

export function useDataSources() {
  const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
  const router = useRouter()
  const queryClient = useQueryClient()
  const { notify } = useNotifications()

  // --- Queries ---
  const ingestionTasksQuery = useIngestionTasksQuery(selectedOrgId)
  const sourcesQuery = useSourcesQuery(selectedOrgId)

  // --- Mutations ---
  const deleteIngestionTaskMutation = useDeleteIngestionTaskMutation()
  const updateSourceMutation = useUpdateSourceMutation()
  const deleteSourceMutation = useDeleteSourceMutation()

  // --- Tab ---
  const activeTab = ref('sources')

  // --- Knowledge Explorer ---
  const selectedKnowledgeSource = ref<Source | null>(null)
  const knowledgeExplorerKey = ref(0)
  const highlightedSourceId = ref<string | null>(null)

  const openKnowledgeExplorer = (item: Source) => {
    selectedKnowledgeSource.value = item
  }

  const closeKnowledgeExplorer = () => {
    selectedKnowledgeSource.value = null
    knowledgeExplorerKey.value += 1
  }

  // --- Dialog Visibility ---
  const showFileUploadDialog = ref(false)
  const showAddFilesDialog = ref(false)
  const showDatabaseDialog = ref(false)
  const showWebsiteDialog = ref(false)
  const showGoogleDriveDialog = ref(false)

  // --- Source Table State ---
  const sourceItemsPerPage = ref(10)
  const sourcePage = ref(1)
  const sourceSortBy = ref('created_at')
  const sourceOrderBy = ref('desc')
  const sourceSearch = ref('')

  const sourceHeaders = [
    { title: 'NAME', key: 'source_name' },
    { title: 'TYPE', key: 'source_type' },
    { title: 'CREATED', key: 'created_at' },
    { title: 'ACTIONS', key: 'actions', sortable: false },
  ]

  // --- Computed Data ---
  const sourcesData = computed(() => ({
    items: sourcesQuery.data.value || [],
    total: (sourcesQuery.data.value || []).length,
    loading: sourcesQuery.isLoading.value,
    error: sourcesQuery.error.value as Error | null,
    isInitialLoad: sourcesQuery.isLoading.value && !sourcesQuery.data.value,
  }))

  const ingestionTasksData = computed(() => ({
    tasks: ingestionTasksQuery.data.value || [],
    total: (ingestionTasksQuery.data.value || []).length,
    loading: ingestionTasksQuery.isLoading.value,
    error: ingestionTasksQuery.error.value as Error | null,
    isInitialLoad: ingestionTasksQuery.isLoading.value && !ingestionTasksQuery.data.value,
  }))

  const filteredSources = computed(() => {
    let filtered = [...sourcesData.value.items]
    if (sourceSearch.value) {
      const term = sourceSearch.value.toLowerCase()

      filtered = filtered.filter(
        item => item.source_name?.toLowerCase().includes(term) || item.source_type?.toLowerCase().includes(term)
      )
    }
    if (sourceSortBy.value) {
      filtered.sort((a, b) => {
        type K = 'source_name' | 'source_type' | 'created_at'
        const aVal = a[sourceSortBy.value as K]
        const bVal = b[sourceSortBy.value as K]
        return sourceOrderBy.value === 'desc' ? (aVal > bVal ? -1 : 1) : aVal < bVal ? -1 : 1
      })
    }
    return filtered
  })

  const paginatedSources = computed(() => {
    const start = (sourcePage.value - 1) * sourceItemsPerPage.value
    return filteredSources.value.slice(start, start + sourceItemsPerPage.value)
  })

  const totalSources = computed(() => filteredSources.value.length)

  const updateSourceOptions = (options: any) => {
    sourceSortBy.value = options.sortBy[0]?.key || 'created_at'
    sourceOrderBy.value = options.sortBy[0]?.order || 'desc'
  }

  // --- Source Delete ---
  const sourceToDelete = ref<Source | null>(null)
  const showDeleteConfirmation = ref(false)
  const sourceUsage = ref<Array<{ id: string; name: string }>>([])
  const isCheckingUsage = ref(false)

  const deleteDataSource = async (item: Source) => {
    if (!selectedOrgId.value) return
    sourceToDelete.value = item
    sourceUsage.value = []
    isCheckingUsage.value = true
    try {
      const usage = await scopeoApi.sources.checkUsage(selectedOrgId.value, item.id)

      sourceUsage.value = usage || []
    } catch (error: unknown) {
      logger.error('Error checking source usage', { error })
      sourceUsage.value = []
    } finally {
      isCheckingUsage.value = false
      showDeleteConfirmation.value = true
    }
  }

  const handleDeleteConfirm = async () => {
    if (!sourceToDelete.value || !selectedOrgId.value) return
    try {
      await deleteSourceMutation.mutateAsync({
        orgId: selectedOrgId.value,
        sourceId: sourceToDelete.value.id,
      })
    } catch (error: unknown) {
      logger.error('Error deleting source', { error })
      notify.error(getErrorMessage(error, 'Failed to delete source. Please try again.'))
    } finally {
      sourceToDelete.value = null
      sourceUsage.value = []
      showDeleteConfirmation.value = false
    }
  }

  const handleDeleteCancel = () => {
    sourceToDelete.value = null
    sourceUsage.value = []
    showDeleteConfirmation.value = false
  }

  const getDeleteTitle = () => {
    if (!sourceToDelete.value) return 'Delete data source?'
    return `Delete data source "${sourceToDelete.value.source_name}"?`
  }

  const getDeleteMessage = () => {
    if (!sourceToDelete.value) return ''
    if (sourceUsage.value.length > 0) {
      const n = sourceUsage.value.length
      const list = sourceUsage.value.map(p => `- ${p.name}`).join('\n')
      return [
        `This data source is currently used by ${n} ${n === 1 ? 'project' : 'projects'}.`,
        'Deleting it will break those projects immediately.',
        '',
        'Affected projects:',
        list,
        '',
        'This action cannot be undone.',
      ].join('\n')
    }
    return ['This data source is not used by any projects.', '', 'This action cannot be undone.'].join('\n')
  }

  // --- Source Update ---
  const sourceToUpdate = ref<Source | null>(null)
  const showUpdateConfirmation = ref(false)
  const isUpdatingSource = ref(false)

  const updateDataSource = (item: Source) => {
    sourceToUpdate.value = item
    showUpdateConfirmation.value = true
  }

  const handleUpdateConfirm = async () => {
    if (!sourceToUpdate.value || !selectedOrgId.value) return
    try {
      isUpdatingSource.value = true
      await updateSourceMutation.mutateAsync({
        orgId: selectedOrgId.value,
        sourceId: sourceToUpdate.value.id,
      })
    } catch (error: unknown) {
      logger.error('Error updating source', { error })
      notify.error(getErrorMessage(error, 'Failed to update source. Please try again.'))
    } finally {
      sourceToUpdate.value = null
      showUpdateConfirmation.value = false
      isUpdatingSource.value = false
    }
  }

  const handleUpdateCancel = () => {
    sourceToUpdate.value = null
    showUpdateConfirmation.value = false
  }

  // --- Add Files ---
  const sourceToAddFiles = ref<Source | null>(null)

  const addFilesToSource = (item: Source) => {
    sourceToAddFiles.value = item
    showAddFilesDialog.value = true
  }

  const handleAddFilesClose = () => {
    sourceToAddFiles.value = null
  }

  // --- Ingestion Task Delete ---
  const taskToDelete = ref<IngestionTask | null>(null)
  const showIngestionTaskDeleteConfirmation = ref(false)

  const deleteIngestionTask = (item: IngestionTask) => {
    taskToDelete.value = item
    showIngestionTaskDeleteConfirmation.value = true
  }

  const handleIngestionTaskDeleteConfirm = async () => {
    if (!taskToDelete.value || !selectedOrgId.value) return
    try {
      await deleteIngestionTaskMutation.mutateAsync({
        orgId: selectedOrgId.value,
        taskId: taskToDelete.value.id,
      })
    } catch (error: unknown) {
      logger.error('Error deleting ingestion task', { error })
      notify.error(getErrorMessage(error, 'Failed to delete ingestion task. Please try again.'))
    } finally {
      taskToDelete.value = null
      showIngestionTaskDeleteConfirmation.value = false
    }
  }

  const handleIngestionTaskDeleteCancel = () => {
    taskToDelete.value = null
    showIngestionTaskDeleteConfirmation.value = false
  }

  // --- Ingestion Task Error ---
  const taskWithError = ref<IngestionTask | null>(null)
  const showIngestionTaskErrorDialog = ref(false)

  const showTaskErrorDetails = (task: IngestionTask) => {
    if (hasTaskErrorOrWarning(task)) {
      taskWithError.value = task
      showIngestionTaskErrorDialog.value = true
    }
  }

  // --- Cross-tab Navigation ---
  const viewSourceFromIngestion = async (task: IngestionTask) => {
    if (!task.source_id) return
    highlightedSourceId.value = task.source_id
    activeTab.value = 'sources'
    await nextTick()

    const sourceIndex = filteredSources.value.findIndex(s => s.id === task.source_id)
    if (sourceIndex !== -1) {
      sourcePage.value = Math.floor(sourceIndex / sourceItemsPerPage.value) + 1

      const source = filteredSources.value[sourceIndex]
      if (source) openKnowledgeExplorer(source)
    }
    setTimeout(() => {
      highlightedSourceId.value = null
    }, 3000)
  }

  const handleDialogCreated = () => {
    activeTab.value = 'ingestion'
  }

  // --- Watchers ---
  watch(orgChangeCounter, () => {
    if (selectedOrgId.value) {
      router.push(`/org/${selectedOrgId.value}/data-sources`)
    }
  })

  return {
    selectedOrgId,
    queryClient,
    activeTab,
    selectedKnowledgeSource,
    knowledgeExplorerKey,
    highlightedSourceId,
    openKnowledgeExplorer,
    closeKnowledgeExplorer,
    showFileUploadDialog,
    showAddFilesDialog,
    showDatabaseDialog,
    showWebsiteDialog,
    showGoogleDriveDialog,
    sourceSearch,
    sourceItemsPerPage,
    sourcePage,
    sourceHeaders,
    sourcesData,
    paginatedSources,
    totalSources,
    updateSourceOptions,
    ingestionTasksData,
    viewDataSource: openKnowledgeExplorer,
    updateDataSource,
    deleteDataSource,
    addFilesToSource,
    handleAddFilesClose,
    sourceToDelete,
    showDeleteConfirmation,
    sourceUsage,
    isCheckingUsage,
    handleDeleteConfirm,
    handleDeleteCancel,
    getDeleteTitle,
    getDeleteMessage,
    sourceToUpdate,
    showUpdateConfirmation,
    isUpdatingSource,
    handleUpdateConfirm,
    handleUpdateCancel,
    sourceToAddFiles,
    viewSourceFromIngestion,
    deleteIngestionTask,
    showTaskErrorDetails,
    taskToDelete,
    showIngestionTaskDeleteConfirmation,
    handleIngestionTaskDeleteConfirm,
    handleIngestionTaskDeleteCancel,
    taskWithError,
    showIngestionTaskErrorDialog,
    handleDialogCreated,
  }
}
