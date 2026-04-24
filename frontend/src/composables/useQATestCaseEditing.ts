import type { ComponentPublicInstance, ComputedRef, Ref } from 'vue'
import { reactive, ref } from 'vue'
import type { QATestCaseUI, QAVersion } from '@/composables/queries/useQAQuery'

export type EditableField = 'input' | 'groundtruth' | `custom-${string}`

interface EditingDeps {
  orgId: ComputedRef<string>
  projectId: ComputedRef<string>
  currentDataset: Ref<{ id: string } | null>
  testCases: Ref<QATestCaseUI[]>
  versions: ComputedRef<QAVersion[]>
  patchTestCase: (id: string, patch: Partial<QATestCaseUI>) => void
  updateInputGroundtruthMutation: (args: {
    orgId: string
    datasetId: string
    data: { inputs_groundtruths: any[] }
  }) => Promise<unknown>
  deleteEvaluationsForInputGroundtruth: (
    projectId: string,
    datasetId: string,
    inputGroundtruthId: string,
    graphRunners: Array<{ id: string }>
  ) => Promise<unknown>
  showError: (msg: string) => void
}

export function useQATestCaseEditing(deps: EditingDeps) {
  const {
    orgId,
    projectId,
    currentDataset,
    testCases,
    versions,
    patchTestCase,
    updateInputGroundtruthMutation,
    deleteEvaluationsForInputGroundtruth,
    showError,
  } = deps

  // --- Floating editor ---
  const floatingEditor = reactive({
    open: false,
    value: '',
    rowId: '' as string,
    field: '' as EditableField | '',
    activatorEl: undefined as Element | ComponentPublicInstance | string | undefined,
  })

  const closeFloatingEditor = () => {
    floatingEditor.open = false
    floatingEditor.activatorEl = undefined
  }

  // --- Debounced save state ---
  const savingState = ref<Record<string, boolean>>({})
  const saveTimers = ref<Record<string, ReturnType<typeof setTimeout>>>({})
  const activeSavingKey = ref<string | null>(null)
  const lastSavedValue = ref<Record<string, string>>({})
  const lastSavedCustomColumns = ref<Record<string, Record<string, string | null>>>({})

  // --- Output dialog ---
  const showOutputDialog = ref(false)
  const outputDialogText = ref('')
  const outputDialogExpectedText = ref('')
  const outputDialogTestCaseId = ref<string | null>(null)

  const doesOverflow = (el: HTMLElement | null) => {
    if (!el) return false
    const inputEl = el.querySelector('.v-field__input') as HTMLElement | null
    const target = inputEl || el
    return target.scrollHeight > target.clientHeight || target.scrollWidth > target.clientWidth
  }

  const onCellClick = (testCase: QATestCaseUI, field: EditableField, event: MouseEvent) => {
    const target = event.currentTarget as HTMLElement | null
    if (!target) return
    if (floatingEditor.open && floatingEditor.rowId === testCase.id && floatingEditor.field === field) {
      closeFloatingEditor()
      return
    }
    if (!doesOverflow(target)) return
    floatingEditor.rowId = testCase.id
    floatingEditor.field = field
    floatingEditor.value = field === 'input' ? testCase.input || '' : testCase.groundtruth || ''
    floatingEditor.activatorEl = target
    floatingEditor.open = true
  }

  const openOutputDialog = (testCase: QATestCaseUI) => {
    if (!testCase.output) return
    if (floatingEditor.open) closeFloatingEditor()
    outputDialogText.value = testCase.output
    outputDialogExpectedText.value = testCase.groundtruth || ''
    outputDialogTestCaseId.value = testCase.id
    showOutputDialog.value = true
  }

  const onOutputDialogExpectedUpdate = (newValue: string) => {
    if (!outputDialogTestCaseId.value) return
    const testCase = testCases.value.find(tc => tc.id === outputDialogTestCaseId.value)
    if (!testCase) return
    testCase.groundtruth = newValue
    outputDialogExpectedText.value = newValue
    onUpdateTestCase(testCase, 'groundtruth')
  }

  const setupDebouncedSave = (key: string, saveFn: () => Promise<void>, onComplete?: () => void) => {
    if (saveTimers.value[key]) clearTimeout(saveTimers.value[key])
    saveTimers.value[key] = setTimeout(async () => {
      savingState.value[key] = true
      activeSavingKey.value = key
      try {
        await saveFn()
        onComplete?.()
      } finally {
        savingState.value[key] = false
        if (activeSavingKey.value === key) activeSavingKey.value = null
      }
    }, 500)
  }

  const onUpdateTestCase = (testCase: QATestCaseUI, field: EditableField) => {
    if (!orgId.value || !currentDataset.value) return
    const datasetId = currentDataset.value.id
    const currentOrgId = orgId.value
    const projId = projectId.value

    if (field === 'input') return

    if (field.startsWith('custom-')) {
      const columnId = field.replace('custom-', '')
      const key = `${testCase.id}-custom-${columnId}`
      const tcRef = testCases.value.find(tc => tc.id === testCase.id)
      if (!tcRef) return
      const currentValue = tcRef.custom_columns?.[columnId] ?? null
      const baseline = lastSavedCustomColumns.value[testCase.id]?.[columnId]
      if (typeof baseline !== 'undefined' && currentValue === baseline) {
        savingState.value[key] = false
        if (activeSavingKey.value === key) activeSavingKey.value = null
        return
      }

      setupDebouncedSave(
        key,
        async () => {
          const latest = testCases.value.find(tc => tc.id === testCase.id)
          if (!latest) return
          const latestValue = latest.custom_columns?.[columnId] ?? null
          try {
            await updateInputGroundtruthMutation({
              orgId: currentOrgId,
              datasetId,
              data: { inputs_groundtruths: [{ id: testCase.id, custom_columns: { [columnId]: latestValue } }] },
            })
          } catch (error) {
            showError('Failed to save custom column value. Please try again.')
            throw error
          }
        },
        () => {
          const latest = testCases.value.find(tc => tc.id === testCase.id)
          if (!latest) return
          if (!lastSavedCustomColumns.value[testCase.id]) lastSavedCustomColumns.value[testCase.id] = {}
          lastSavedCustomColumns.value[testCase.id][columnId] = latest.custom_columns?.[columnId] ?? null
        }
      )
      return
    }

    const key = `${testCase.id}-${field}`
    const tcRef = testCases.value.find(tc => tc.id === testCase.id)
    if (!tcRef) return
    const currentValue = tcRef.groundtruth || ''
    const baseline = lastSavedValue.value[key]
    if (typeof baseline !== 'undefined' && currentValue === baseline) {
      savingState.value[key] = false
      if (activeSavingKey.value === key) activeSavingKey.value = null
      return
    }

    setupDebouncedSave(
      key,
      async () => {
        const latest = testCases.value.find(tc => tc.id === testCase.id)
        if (!latest) return
        patchTestCase(testCase.id, { evaluations: [] })
        try {
          await updateInputGroundtruthMutation({
            orgId: currentOrgId,
            datasetId,
            data: { inputs_groundtruths: [{ id: testCase.id, groundtruth: latest.groundtruth || '' }] },
          })

          const graphRunners = versions.value.filter(v => v.graph_runner_id).map(v => ({ id: v.graph_runner_id! }))

          await deleteEvaluationsForInputGroundtruth(projId, datasetId, testCase.id, graphRunners)
        } catch (error) {
          showError('Failed to save expected output. Please try again.')
          throw error
        }
      },
      () => {
        const latest = testCases.value.find(tc => tc.id === testCase.id)
        if (latest) lastSavedValue.value[key] = latest.groundtruth || ''
      }
    )
  }

  const onFloatingEditorBlur = () => {
    if (!floatingEditor.open) return
    const row = testCases.value.find(r => r.id === floatingEditor.rowId)
    if (!row || !floatingEditor.field) return closeFloatingEditor()
    if (floatingEditor.field === 'input') row.input = floatingEditor.value
    if (floatingEditor.field === 'groundtruth') row.groundtruth = floatingEditor.value
    onUpdateTestCase(row, floatingEditor.field as EditableField)
    closeFloatingEditor()
  }

  const clearSaveTimers = () => {
    Object.values(saveTimers.value).forEach(timer => clearTimeout(timer))
  }

  const resetSavedBaselines = () => {
    lastSavedValue.value = {}
    lastSavedCustomColumns.value = {}
  }

  return {
    floatingEditor,
    closeFloatingEditor,
    savingState,
    activeSavingKey,
    lastSavedValue,
    lastSavedCustomColumns,
    showOutputDialog,
    outputDialogText,
    outputDialogExpectedText,
    outputDialogTestCaseId,
    onCellClick,
    openOutputDialog,
    onOutputDialogExpectedUpdate,
    onUpdateTestCase,
    onFloatingEditorBlur,
    clearSaveTimers,
    resetSavedBaselines,
  }
}
