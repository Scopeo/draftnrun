import type { ComputedRef, Ref } from 'vue'
import { ref } from 'vue'
import type { QACustomColumn, QADataset } from '@/types/qa'
import type { QATestCaseUI } from '@/composables/queries/useQAQuery'
import { parseQAInput } from '@/utils/qaUtils'
import { scopeoApi } from '@/api'

// --- Utility functions ---

interface QAError {
  data?: { detail?: string }
}

const getQAErrorCode = (error: unknown): string | null => {
  const qaError = error as QAError
  if (qaError?.data?.detail && typeof qaError.data.detail === 'string') {
    const match = qaError.data.detail.match(/QA_\w+/)
    return match ? match[0] : null
  }
  return null
}

export const extractErrorMessage = (error: unknown, defaultMessage: string): string => {
  if (error && typeof error === 'object') {
    if ('data' in error && error.data && typeof error.data === 'object' && 'detail' in error.data) {
      const detail = error.data.detail
      if (typeof detail === 'string') return detail
    }
    if ('response' in error && error.response && typeof error.response === 'object') {
      const response = error.response as { data?: { detail?: unknown } }
      if (response.data?.detail && typeof response.data.detail === 'string') return response.data.detail
    }
    if (
      'message' in error &&
      typeof error.message === 'string' &&
      error.message !== 'An unexpected API error occurred.'
    ) {
      return error.message
    }
  }
  if (error instanceof Error && error.message) return error.message
  return defaultMessage
}

// --- Deps interface ---

interface CrudDeps {
  projectId: ComputedRef<string>
  currentDataset: Ref<QADataset | null>
  currentVersion: Ref<{ id: string; graph_runner_id?: string | null } | null>
  testCases: Ref<QATestCaseUI[]>
  datasets: ComputedRef<QADataset[]>
  customColumns: ComputedRef<QACustomColumn[]>
  allCustomColumns: ComputedRef<QACustomColumn[]>
  columnVisibility: {
    isColumnVisible: (columnId: string) => boolean
    setColumnVisibility: (id: string, columnId: string, visible: boolean, onError?: (msg: string) => void) => void
  }
  datasetIdRef: ComputedRef<string | undefined>

  selected: Ref<string[]>
  patchTestCase: (id: string, patch: Partial<QATestCaseUI>) => void
  pushTestCases: (newCases: QATestCaseUI[]) => void
  removeTestCases: (ids: string[]) => void

  createDatasetMutation: (args: { projectId: string; data: { datasets_name: string[] } }) => Promise<unknown>
  deleteDatasetMutation: (args: { projectId: string; datasetIds: string[] }) => Promise<unknown>
  addInputGroundtruthMutation: (args: {
    projectId: string
    datasetId: string
    data: { inputs_groundtruths: any[] }
  }) => Promise<any>
  updateInputGroundtruthMutation: (args: {
    projectId: string
    datasetId: string
    data: { inputs_groundtruths: any[] }
  }) => Promise<unknown>
  deleteInputGroundtruthMutation: (args: {
    projectId: string
    datasetId: string
    entryIds: string[]
  }) => Promise<unknown>
  createCustomColumnMutation: (args: {
    projectId: string
    datasetId: string
    data: { column_name: string }
  }) => Promise<{ column_id?: string } | null>
  deleteCustomColumnMutation: (args: { projectId: string; datasetId: string; columnId: string }) => Promise<unknown>
  renameCustomColumnMutation: (args: {
    projectId: string
    datasetId: string
    columnId: string
    data: { column_name: string }
  }) => Promise<unknown>

  refetchDatasets: () => Promise<unknown>
  refetchTestCases: () => Promise<unknown>
  refetchCustomColumns: () => Promise<unknown>

  showSuccess: (msg: string) => void
  showError: (msg: string) => void
  showWarning: (msg: string) => void
}

export function useQATestCaseCrud(deps: CrudDeps) {
  const {
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
  } = deps

  // --- Dataset delete ---
  const showDeleteDatasetDialog = ref(false)
  const deleteDatasetLoading = ref(false)

  const openDeleteDatasetDialog = () => {
    showDeleteDatasetDialog.value = true
  }

  const confirmDeleteDataset = async () => {
    if (!projectId.value || !currentDataset.value) return
    try {
      deleteDatasetLoading.value = true

      const deletedId = currentDataset.value.id

      await deleteDatasetMutation({ projectId: projectId.value, datasetIds: [deletedId] })
      await refetchDatasets()
      if (currentDataset.value?.id === deletedId) currentDataset.value = datasets.value[0] || null
      showDeleteDatasetDialog.value = false
    } finally {
      deleteDatasetLoading.value = false
    }
  }

  // --- Test case delete ---
  const showDeleteDialog = ref(false)
  const testCaseToDelete = ref<QATestCaseUI | null>(null)

  const deleteSelectedTestCase = async () => {
    if (!projectId.value || !currentDataset.value || !testCaseToDelete.value) return
    await deleteInputGroundtruthMutation({
      projectId: projectId.value,
      datasetId: currentDataset.value.id,
      entryIds: [testCaseToDelete.value.id],
    })
    removeTestCases([testCaseToDelete.value.id])
    showDeleteDialog.value = false
    testCaseToDelete.value = null
  }

  // --- Bulk delete ---
  const showBulkDeleteDialog = ref(false)
  const bulkDeleteLoading = ref(false)

  const confirmDeleteSelected = () => {
    if (!selected.value.length) return
    showBulkDeleteDialog.value = true
  }

  const deleteSelectedTestCases = async () => {
    if (!projectId.value || !currentDataset.value || !selected.value.length) return
    try {
      bulkDeleteLoading.value = true

      const ids = [...selected.value]

      await deleteInputGroundtruthMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        entryIds: ids,
      })
      removeTestCases(ids)
      showBulkDeleteDialog.value = false
      selected.value = []
    } finally {
      bulkDeleteLoading.value = false
    }
  }

  // --- Add test case ---
  const showAddTestCaseDialog = ref(false)

  const addTestCaseMessages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([
    { role: 'user', content: '' },
  ])

  const addTestCaseAdditionalFields = ref<Array<{ key: string; value: string }>>([])
  const addTestCaseGroundtruth = ref('')
  const addTestCaseCustomColumns = ref<Record<string, string>>({})
  const addingTestCase = ref(false)

  const addNewTestCase = () => {
    addTestCaseMessages.value = [{ role: 'user', content: '' }]
    addTestCaseAdditionalFields.value = []
    addTestCaseGroundtruth.value = ''
    addTestCaseCustomColumns.value = {}
    if (currentDataset.value) {
      allCustomColumns.value.forEach(col => {
        if (columnVisibility.isColumnVisible(col.column_id)) addTestCaseCustomColumns.value[col.column_id] = ''
      })
    }
    showAddTestCaseDialog.value = true
  }

  const saveNewTestCase = async () => {
    if (!projectId.value || !currentDataset.value) return
    const validMessages = addTestCaseMessages.value.filter(m => m.content.trim())
    if (!validMessages.length) return

    addingTestCase.value = true
    try {
      const inputObj: Record<string, unknown> = {
        messages: validMessages.map(m => ({ role: m.role, content: m.content })),
      }

      addTestCaseAdditionalFields.value.forEach(f => {
        if (f.key.trim() && f.value.trim()) inputObj[f.key.trim()] = f.value.trim()
      })

      const customColumnsData: Record<string, string | null> = {}

      Object.keys(addTestCaseCustomColumns.value).forEach(cid => {
        const v = addTestCaseCustomColumns.value[cid]?.trim()

        customColumnsData[cid] = v || null
      })

      const newEntry = {
        input: inputObj,
        groundtruth: addTestCaseGroundtruth.value,
        custom_columns: Object.keys(customColumnsData).length > 0 ? customColumnsData : undefined,
      }

      const datasetId = currentDataset.value.id

      const result = await addInputGroundtruthMutation({
        projectId: projectId.value,
        datasetId,
        data: { inputs_groundtruths: [newEntry] },
      })

      if (result?.inputs_groundtruths && currentDataset.value?.id === datasetId) {
        const newTCs = result.inputs_groundtruths.map(
          (e: { id: string; input: unknown; groundtruth: string; position: number }) => ({
            id: e.id,
            input: e.input,
            groundtruth: e.groundtruth,
            output: null,
            version: null,
            status: 'Pending' as const,
            position: e.position,
          })
        )

        pushTestCases(newTCs)
      }
      showAddTestCaseDialog.value = false
    } finally {
      addingTestCase.value = false
    }
  }

  // --- Edit test case ---
  const showEditTestCaseDialog = ref(false)
  const editingTestCase = ref<QATestCaseUI | null>(null)
  const editTestCaseMessages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const editTestCaseAdditionalFields = ref<Array<{ key: string; value: string }>>([])
  const editingTestCaseLoading = ref(false)

  const openEditTestCaseDialog = (testCase: QATestCaseUI) => {
    editingTestCase.value = testCase

    const { messages, additionalFields } = parseQAInput(testCase.input)

    editTestCaseMessages.value =
      messages.length > 0
        ? messages.map((m: { role?: string; content?: string }) => ({
            role: m.role === 'assistant' ? ('assistant' as const) : ('user' as const),
            content: m.content || '',
          }))
        : [{ role: 'user' as const, content: '' }]
    editTestCaseAdditionalFields.value = additionalFields
    showEditTestCaseDialog.value = true
  }

  const saveEditedTestCase = async () => {
    if (!projectId.value || !currentDataset.value || !editingTestCase.value) return
    const tcId = editingTestCase.value.id

    editingTestCaseLoading.value = true
    try {
      const inputObj: any = {
        messages: editTestCaseMessages.value
          .filter(m => m.content.trim())
          .map(m => ({ role: m.role, content: m.content })),
      }

      editTestCaseAdditionalFields.value.forEach(f => {
        if (f.key.trim() && f.value.trim()) inputObj[f.key.trim()] = f.value.trim()
      })

      patchTestCase(tcId, { evaluations: [], output: null, version_output_id: null, status: 'Pending' })
      await updateInputGroundtruthMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        data: { inputs_groundtruths: [{ id: tcId, input: inputObj }] },
      })
      await refetchTestCases()
      showEditTestCaseDialog.value = false
      editingTestCase.value = null
    } finally {
      editingTestCaseLoading.value = false
    }
  }

  // --- Custom columns ---
  const showCreateColumnDialog = ref(false)
  const creatingColumn = ref(false)
  const showDeleteColumnDialog = ref(false)
  const columnToDelete = ref<{ column_id: string; column_name: string } | null>(null)
  const deletingColumn = ref(false)
  const editingColumnId = ref<string | null>(null)
  const editingColumnName = ref('')

  const createCustomColumn = async (name: string) => {
    if (!projectId.value || !currentDataset.value || !name.trim()) return
    creatingColumn.value = true
    try {
      const newCol = await createCustomColumnMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        data: { column_name: name.trim() },
      })

      if (currentDataset.value && newCol?.column_id && datasetIdRef.value)
        columnVisibility.setColumnVisibility(datasetIdRef.value, newCol.column_id, true, showError)
      showCreateColumnDialog.value = false
    } catch (error: unknown) {
      const code = getQAErrorCode(error)

      showError(
        code === 'QA_DATASET_NOT_IN_PROJECT'
          ? 'This dataset is not associated with the current project. Please refresh and try again.'
          : 'Failed to create custom column. Please try again.'
      )
    } finally {
      creatingColumn.value = false
    }
  }

  const startEditingColumnName = (col: { column_id: string; column_name: string }) => {
    editingColumnId.value = col.column_id
    editingColumnName.value = col.column_name
  }

  const cancelEditingColumnName = () => {
    editingColumnId.value = null
    editingColumnName.value = ''
  }

  const saveEditingColumnName = async () => {
    if (!editingColumnId.value || !editingColumnName.value.trim() || !projectId.value || !currentDataset.value) {
      cancelEditingColumnName()
      return
    }
    const col = customColumns.value.find(c => c.column_id === editingColumnId.value)
    if (!col || col.column_name === editingColumnName.value.trim()) {
      cancelEditingColumnName()
      return
    }
    const columnId = editingColumnId.value
    const newName = editingColumnName.value.trim()
    try {
      await renameCustomColumnMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        columnId,
        data: { column_name: newName },
      })
      await refetchCustomColumns()
      cancelEditingColumnName()
    } catch (error: unknown) {
      const code = getQAErrorCode(error)
      if (code === 'QA_COLUMN_NOT_FOUND') {
        showError('This column no longer exists. Please refresh the page.')
        await refetchCustomColumns()
      } else if (code === 'QA_DATASET_NOT_IN_PROJECT') {
        showError('This dataset is not associated with the current project. Please refresh and try again.')
      } else {
        showError('Failed to rename custom column. Please try again.')
      }
      cancelEditingColumnName()
    }
  }

  const openDeleteColumnDialog = (col: { column_id: string; column_name: string }) => {
    columnToDelete.value = col
    showDeleteColumnDialog.value = true
  }

  const deleteCustomColumn = async () => {
    if (!projectId.value || !currentDataset.value || !columnToDelete.value) return
    deletingColumn.value = true
    try {
      await deleteCustomColumnMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        columnId: columnToDelete.value.column_id,
      })
      await refetchCustomColumns()
      showDeleteColumnDialog.value = false
      columnToDelete.value = null
    } catch (error: unknown) {
      const code = getQAErrorCode(error)
      if (code === 'QA_COLUMN_NOT_FOUND') {
        showError('This column no longer exists. Please refresh the page.')
        await refetchCustomColumns()
      } else if (code === 'QA_DATASET_NOT_IN_PROJECT') {
        showError('This dataset is not associated with the current project. Please refresh and try again.')
      } else {
        showError('Failed to delete custom column. Please try again.')
      }
    } finally {
      deletingColumn.value = false
    }
  }

  // --- Dataset create ---
  const showCreateDatasetDialog = ref(false)

  const createNewDataset = async (name: string) => {
    if (!projectId.value || !name.trim()) return
    const createdName = name.trim()

    await createDatasetMutation({ projectId: projectId.value, data: { datasets_name: [createdName] } })
    await refetchDatasets()
    showCreateDatasetDialog.value = false

    const justCreated = datasets.value.find(d => d.dataset_name === createdName)
    if (justCreated) currentDataset.value = justCreated
  }

  // --- CSV ---
  const exportingCSV = ref(false)
  const importingCSV = ref(false)
  const fileInputRef = ref<HTMLInputElement | null>(null)

  const triggerFileInput = () => {
    fileInputRef.value?.click()
  }

  const exportDatasetToCSV = async () => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    exportingCSV.value = true
    try {
      await scopeoApi.qa.exportToCSV(
        projectId.value,
        currentDataset.value.id,
        currentVersion.value?.graph_runner_id || ''
      )
      showSuccess('CSV exported successfully')
    } catch (error: unknown) {
      showWarning(extractErrorMessage(error, 'Failed to export CSV. Please try again.'))
    } finally {
      exportingCSV.value = false
    }
  }

  const handleFileSelect = async (event: Event) => {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    if (!file) return
    if (!projectId.value || !currentDataset.value) {
      showError('Please select a dataset first')
      return
    }

    const maxFileSize = 10 * 1024 * 1024
    if (file.size > maxFileSize) {
      showError(
        `File size exceeds the maximum limit of 10MB. Current file size: ${(file.size / (1024 * 1024)).toFixed(2)}MB`
      )
      if (fileInputRef.value) fileInputRef.value.value = ''
      return
    }

    importingCSV.value = true
    try {
      const result = await scopeoApi.qa.importFromCSV(projectId.value, currentDataset.value.id, file)

      await refetchCustomColumns()
      if (currentVersion.value) await refetchTestCases()
      const cnt = result?.inputs_groundtruths?.length || 0

      showSuccess(`Successfully imported ${cnt} test case${cnt !== 1 ? 's' : ''} from CSV`)
    } catch (error: unknown) {
      showWarning(extractErrorMessage(error, 'Failed to import CSV. Please try again.'))
    } finally {
      importingCSV.value = false
      if (fileInputRef.value) fileInputRef.value.value = ''
    }
  }

  return {
    // Dataset
    showCreateDatasetDialog,
    showDeleteDatasetDialog,
    deleteDatasetLoading,
    openDeleteDatasetDialog,
    confirmDeleteDataset,
    createNewDataset,
    // Test case delete
    showDeleteDialog,
    testCaseToDelete,
    deleteSelectedTestCase,
    // Bulk delete
    showBulkDeleteDialog,
    bulkDeleteLoading,
    confirmDeleteSelected,
    deleteSelectedTestCases,
    // Add test case
    showAddTestCaseDialog,
    addTestCaseMessages,
    addTestCaseAdditionalFields,
    addTestCaseGroundtruth,
    addTestCaseCustomColumns,
    addingTestCase,
    addNewTestCase,
    saveNewTestCase,
    // Edit test case
    showEditTestCaseDialog,
    editingTestCase,
    editTestCaseMessages,
    editTestCaseAdditionalFields,
    editingTestCaseLoading,
    openEditTestCaseDialog,
    saveEditedTestCase,
    // Custom columns
    showCreateColumnDialog,
    creatingColumn,
    showDeleteColumnDialog,
    columnToDelete,
    deletingColumn,
    editingColumnId,
    editingColumnName,
    createCustomColumn,
    startEditingColumnName,
    cancelEditingColumnName,
    saveEditingColumnName,
    openDeleteColumnDialog,
    deleteCustomColumn,
    // CSV
    exportingCSV,
    importingCSV,
    fileInputRef,
    triggerFileInput,
    exportDatasetToCSV,
    handleFileSelect,
  }
}
