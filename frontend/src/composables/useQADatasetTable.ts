import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  type QADataset,
  type QATestCaseUI,
  type QAVersion,
  useAddInputGroundtruthMutation,
  useCreateQACustomColumnMutation,
  useCreateQADatasetMutation,
  useDeleteInputGroundtruthMutation,
  useDeleteQACustomColumnMutation,
  useDeleteQADatasetMutation,
  useQACustomColumnsQuery,
  useQADatasetsQuery,
  useQAInputGroundtruthsQuery,
  useRenameQACustomColumnMutation,
  useRunQAProcessAsyncMutation,
  useRunQAProcessMutation,
  useUpdateInputGroundtruthMutation,
} from '@/composables/queries/useQAQuery'
import { useQAColumnVisibility } from '@/composables/useQAColumnVisibility'
import { useQAEvaluation } from '@/composables/useQAEvaluation'
import { useQAEventsListener } from '@/composables/useQAEvents'
import { useQANotifications } from '@/composables/useQANotifications'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { useQATestCaseEditing } from '@/composables/useQATestCaseEditing'
import { useQARunOrchestration } from '@/composables/useQARunOrchestration'
import { useQAEvaluationActions } from '@/composables/useQAEvaluationActions'
import { useQATestCaseCrud } from '@/composables/useQATestCaseCrud'

interface Props {
  projectId?: string
  graphRunners?: Array<{ graph_runner_id: string; tag_name?: string; env?: string | null }>
}

export function useQADatasetTable(props: Props) {
  const route = useRoute()
  const { isOrgAdmin } = useSelectedOrg()
  const notifications = useQANotifications()
  const { showSuccess, showError, showWarning, showInfo } = notifications

  // --- Core computed ---
  const projectId = computed(() => props.projectId || (route.params.id as string))
  const projectIdRef = computed(() => projectId.value)

  // --- Selection state ---
  const currentDataset = ref<QADataset | null>(null)
  const currentVersion = ref<QAVersion | null>(null)
  const selected = ref<string[]>([])
  const currentPage = ref(1)
  const itemsPerPage = ref(20)

  const datasetIdRef = computed(() => currentDataset.value?.id)
  const graphRunnerIdRef = computed(() => currentVersion.value?.graph_runner_id)

  // --- Queries ---
  const { data: datasetsData, isLoading: datasetsLoading, refetch: refetchDatasets } = useQADatasetsQuery(projectIdRef)
  const datasets = computed(() => datasetsData.value || [])

  const { data: customColumnsData, refetch: refetchCustomColumns } = useQACustomColumnsQuery(projectIdRef, datasetIdRef)
  const columnVisibility = useQAColumnVisibility(datasetIdRef)

  const customColumns = computed(() => {
    const cols = customColumnsData.value || []
    const sorted = [...cols].sort((a, b) => a.column_display_position - b.column_display_position)
    if (!datasetIdRef.value) return sorted
    return sorted.filter(col => columnVisibility.isColumnVisible(col.column_id))
  })

  const allCustomColumns = computed(() => {
    const cols = customColumnsData.value || []
    return [...cols].sort((a, b) => a.column_display_position - b.column_display_position)
  })

  const {
    testCases: queryTestCases,
    lastLoadedAt,
    isLoading: entriesLoading,
    refetch: refetchTestCases,
  } = useQAInputGroundtruthsQuery(projectIdRef, datasetIdRef, graphRunnerIdRef)

  // --- Local mutable test cases ---
  const testCases = ref<QATestCaseUI[]>([])

  const patchTestCases = (updates: Record<string, Partial<QATestCaseUI>>) => {
    testCases.value = testCases.value.map(tc => {
      const patch = updates[tc.id]
      return patch ? { ...tc, ...patch } : tc
    })
  }

  const patchTestCase = (id: string, patch: Partial<QATestCaseUI>) => patchTestCases({ [id]: patch })

  const removeTestCases = (ids: string[]) => {
    const idSet = new Set(ids)

    testCases.value = testCases.value.filter(tc => !idSet.has(tc.id))
  }

  const pushTestCases = (newCases: QATestCaseUI[]) => {
    testCases.value.push(...newCases)
  }

  // --- Versions ---
  const versions = computed<QAVersion[]>(() =>
    (props.graphRunners || []).map(runner => ({
      id: runner.graph_runner_id,
      project_id: projectId.value,
      version: runner.tag_name || runner.env || runner.graph_runner_id,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      graph_runner_id: runner.graph_runner_id,
      env: runner.env,
      tag_name: runner.tag_name,
    }))
  )

  // --- Mutations ---
  const { mutateAsync: createDatasetMutation, isPending: creating } = useCreateQADatasetMutation()
  const { mutateAsync: deleteDatasetMutation } = useDeleteQADatasetMutation()
  const { mutateAsync: addInputGroundtruthMutation } = useAddInputGroundtruthMutation()
  const { mutateAsync: updateInputGroundtruthMutation, isPending: updating } = useUpdateInputGroundtruthMutation()
  const { mutateAsync: deleteInputGroundtruthMutation } = useDeleteInputGroundtruthMutation()
  const { mutateAsync: runQAProcessMutation } = useRunQAProcessMutation()
  const { mutateAsync: runQAProcessAsyncMutation } = useRunQAProcessAsyncMutation()
  const { mutateAsync: createCustomColumnMutation } = useCreateQACustomColumnMutation()
  const { mutateAsync: deleteCustomColumnMutation } = useDeleteQACustomColumnMutation()
  const { mutateAsync: renameCustomColumnMutation } = useRenameQACustomColumnMutation()

  const loading = computed(() => datasetsLoading.value || entriesLoading.value)

  // --- QA Evaluation ---
  const {
    judges,
    fetchLLMJudges,
    runEvaluations,
    fetchEvaluationsForVersionOutput,
    deleteEvaluationsForVersionOutput,
    deleteEvaluationsForInputGroundtruth,
  } = useQAEvaluation()

  // --- Sub-composables ---
  const editing = useQATestCaseEditing({
    projectId,
    currentDataset,
    testCases,
    versions,
    patchTestCase,
    updateInputGroundtruthMutation,
    deleteEvaluationsForInputGroundtruth,
    showError,
  })

  const refetchAndSyncTestCases = async () => {
    const result = await refetchTestCases()
    const freshTestCases = (result as any)?.data?.testCases
    if (Array.isArray(freshTestCases)) {
      testCases.value = freshTestCases.map((tc: QATestCaseUI) => ({
        ...tc,
        custom_columns: tc.custom_columns || {},
      }))
    }
    return result
  }

  const runs = useQARunOrchestration({
    projectId,
    currentDataset,
    currentVersion,
    testCases,
    versions,
    selected,
    patchTestCase,
    patchTestCases,
    runQAProcessMutation,
    runQAProcessAsyncMutation,
    deleteEvaluationsForVersionOutput,
    refetchTestCases: refetchAndSyncTestCases,
    showSuccess,
    showError,
    showWarning,
  })

  const evaluations = useQAEvaluationActions({
    projectId,
    testCases,
    selected,
    judges,
    patchTestCase,
    patchTestCases,
    runEvaluations,
    fetchEvaluationsForVersionOutput,
  })

  const crud = useQATestCaseCrud({
    projectId,
    currentDataset,
    currentVersion,
    testCases,
    datasets,
    customColumns,
    allCustomColumns,
    columnVisibility,
    datasetIdRef,
    selected,
    patchTestCase,
    pushTestCases,
    removeTestCases,
    createDatasetMutation,
    deleteDatasetMutation,
    addInputGroundtruthMutation,
    updateInputGroundtruthMutation,
    deleteInputGroundtruthMutation,
    createCustomColumnMutation,
    deleteCustomColumnMutation,
    renameCustomColumnMutation,
    refetchDatasets,
    refetchTestCases,
    refetchCustomColumns,
    showSuccess,
    showError,
    showWarning,
  })

  // --- Sync query → local test cases ---
  watch(
    queryTestCases,
    async newTestCases => {
      if (!newTestCases) return
      testCases.value = newTestCases.map(tc => ({ ...tc, custom_columns: tc.custom_columns || {} }))
      newTestCases.forEach(tc => {
        if (!editing.lastSavedCustomColumns.value[tc.id])
          editing.lastSavedCustomColumns.value[tc.id] = tc.custom_columns ? { ...tc.custom_columns } : {}
        const k1 = `${tc.id}-input`
        const k2 = `${tc.id}-groundtruth`
        if (editing.lastSavedValue.value[k1] === undefined)
          editing.lastSavedValue.value[k1] = typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input || '')
        if (editing.lastSavedValue.value[k2] === undefined) editing.lastSavedValue.value[k2] = tc.groundtruth || ''
      })
      await evaluations.loadEvaluationsForTestCases()
    },
    { immediate: true }
  )

  // --- Permissions ---
  const canManageDatasets = computed(() => {
    const authStore = useAuthStore()
    return isOrgAdmin.value || authStore.userData?.super_admin === true
  })

  // --- Options ---
  const datasetOptions = computed(() => datasets.value.map(d => ({ title: d.dataset_name, value: d.id })))

  const versionOptions = computed(() =>
    versions.value.map((v, i) => ({
      title: v.tag_name || (v.env === 'draft' ? '-' : `Version ${i + 1}`),
      value: v.id,
      env: v.env ?? undefined,
    }))
  )

  const hasDatasets = computed(() => datasets.value.length > 0)

  // --- Status banner ---
  const isBusy = computed(() => loading.value || entriesLoading.value || updating.value)

  const statusText = computed(() => {
    if (loading.value || entriesLoading.value) return 'Loading Dataset'
    if (updating.value) return 'Saving Changes'
    if (lastLoadedAt.value) {
      const d = new Date(lastLoadedAt.value)
      return `Dataset Loaded at ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} for the last time`
    }
    return 'Dataset Loaded'
  })

  const shouldShowStatusBanner = computed(() => isBusy.value || (hasDatasets.value && !!lastLoadedAt.value))

  // --- Headers ---
  const headers = computed(() => {
    const base = [
      { title: '#', key: 'position', sortable: false, align: 'center' as const },
      { title: 'Input', key: 'input', sortable: false, width: '250px' },
      { title: 'Expected Output', key: 'groundtruth', sortable: false, width: '250px' },
      { title: 'Actual Output', key: 'output', sortable: false, width: '250px' },
      { title: 'Status', key: 'status', sortable: false, align: 'center' as const, width: '80px' },
      { title: 'Actions', key: 'actions', sortable: false, align: 'center' as const, width: '70px' },
    ]

    const customHeaders = customColumns.value.map(col => ({
      title: col.column_name,
      key: `custom-${col.column_id}`,
      sortable: false,
      width: '200px',
      column_id: col.column_id,
    }))

    const insertCol = { title: '', key: 'insert-column', sortable: false, align: 'center' as const, width: '60px' }

    if (judges.value.length === 0) return [...base, ...customHeaders, insertCol]

    const evalGroup = {
      title: 'Evaluations',
      key: 'evaluations-group',
      sortable: false,
      align: 'center' as const,
      children: judges.value.map(j => ({
        title: j.name,
        key: `evaluation-${j.id}`,
        sortable: false,
        align: 'center' as const,
        width: '120px',
      })),
    }

    return [...base, evalGroup, ...customHeaders, insertCol]
  })

  // --- Dataset / version change ---
  const onDatasetChange = (datasetId: string) => {
    const dataset = datasets.value.find(d => d.id === datasetId)
    if (!dataset) return
    editing.resetSavedBaselines()
    evaluations.rowEvaluating.value = {}
    evaluations.evaluatingSelected.value = false
    evaluations.evaluatingAll.value = false
    currentDataset.value = dataset
  }

  const onVersionChange = (versionId: string) => {
    const version = versions.value.find(v => v.id === versionId)
    if (!version) return
    editing.resetSavedBaselines()
    evaluations.rowEvaluating.value = {}
    evaluations.evaluatingSelected.value = false
    evaluations.evaluatingAll.value = false
    currentVersion.value = version
  }

  // --- Auto-selection ---
  const autoSelectVersion = () => {
    if (versions.value.length > 0 && !currentVersion.value) {
      currentVersion.value = versions.value.find(v => v.env === 'draft') || versions.value[0]
    }
  }

  const autoSelectDataset = () => {
    if (datasets.value.length > 0) {
      const hasCurrentInList = currentDataset.value
        ? datasets.value.some(d => d.id === currentDataset.value?.id)
        : false

      if (!hasCurrentInList) currentDataset.value = datasets.value[0]
    } else {
      currentDataset.value = null
    }
  }

  // --- Event listeners ---
  const { setupListeners } = useQAEventsListener()

  const handleQAConversationSaved = async (event: { projectId: string; datasetId: string; traceId: string }) => {
    if (!projectId.value || event.projectId !== projectId.value) return
    if (!datasets.value.some(d => d.id === event.datasetId)) await refetchDatasets()
    if (currentDataset.value && currentVersion.value && event.datasetId === currentDataset.value.id)
      await refetchTestCases()
  }

  const handleQADatasetCreated = async (event: { projectId: string; datasetId: string }) => {
    if (!projectId.value || event.projectId !== projectId.value) return
    await refetchDatasets()
    if (!currentDataset.value && event.datasetId) {
      const newDs = datasets.value.find(d => d.id === event.datasetId)
      if (newDs) currentDataset.value = newDs
      else autoSelectDataset()
    }
  }

  const handleQAJudgesUpdated = async (event: { projectId: string }) => {
    if (projectId.value && event.projectId === projectId.value) await fetchLLMJudges(projectId.value)
  }

  // --- Lifecycle ---
  onMounted(async () => {
    if (projectId.value) await fetchLLMJudges(projectId.value)
    setupListeners(handleQAJudgesUpdated, handleQAConversationSaved, handleQADatasetCreated)
    autoSelectVersion()
    autoSelectDataset()
    runs.tryReconnectAsyncSession()
  })

  if (runs.isAsyncEnabled) {
    const stopReconnectWatch = watch(
      [() => projectId.value, currentDataset, currentVersion] as const,
      ([pid, dataset, version]) => {
        if (pid && dataset && version) {
          stopReconnectWatch()
          runs.tryReconnectAsyncSession()
        }
      }
    )
  }

  watch(
    () => projectId.value,
    newProjectId => {
      if (!newProjectId) return
      currentDataset.value = null
      currentVersion.value = null
      columnVisibility.clearCache()
      fetchLLMJudges(newProjectId)
    }
  )

  onUnmounted(() => {
    editing.clearSaveTimers()
    runs.cleanupWebSocket()
  })

  // --- Return ---
  return {
    projectId,
    currentDataset,
    currentVersion,
    selected,
    currentPage,
    itemsPerPage,
    testCases,
    loading,
    creating,
    updating,
    datasets,
    versions,
    customColumns,
    allCustomColumns,
    columnVisibility,
    judges,
    canManageDatasets,
    hasDatasets,
    datasetOptions,
    versionOptions,
    headers,
    isBusy,
    statusText,
    shouldShowStatusBanner,
    onDatasetChange,
    onVersionChange,

    // Notifications
    ...notifications,

    // Editing
    ...editing,

    // Runs
    ...runs,

    // Evaluations
    ...evaluations,

    // CRUD
    ...crud,
  }
}
