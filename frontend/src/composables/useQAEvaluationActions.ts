import type { ComputedRef, Ref } from 'vue'
import { computed, ref } from 'vue'
import type { QATestCaseUI } from '@/composables/queries/useQAQuery'
import type { LLMJudge } from '@/types/qa'
import { getEvaluationForJudge } from '@/utils/qaUtils'
import { logger } from '@/utils/logger'

interface Evaluation {
  judge_id: string
  evaluation_result?: {
    type?: string
    justification?: string
  }
}

interface EvaluationDeps {
  projectId: ComputedRef<string>
  testCases: Ref<QATestCaseUI[]>
  selected: Ref<string[]>
  judges: Ref<LLMJudge[]>
  patchTestCase: (id: string, patch: Partial<QATestCaseUI>) => void
  patchTestCases: (updates: Record<string, Partial<QATestCaseUI>>) => void
  runEvaluations: (projectId: string, judgeIds: string[], versionOutputIds: string[]) => Promise<unknown>
  fetchEvaluationsForVersionOutput: (projectId: string, versionOutputId: string) => Promise<any[]>
}

export function useQAEvaluationActions(deps: EvaluationDeps) {
  const {
    projectId,
    testCases,
    selected,
    judges,
    patchTestCase,
    patchTestCases,
    runEvaluations,
    fetchEvaluationsForVersionOutput,
  } = deps

  const loadingEvaluations = ref<Record<string, boolean>>({})
  const rowEvaluating = ref<Record<string, boolean>>({})
  const evaluatingSelected = ref(false)
  const evaluatingAll = ref(false)

  const showEvaluationDialog = ref(false)
  const evaluationDialogText = ref('')
  const evaluationDialogTitle = ref('')
  const evaluationDialogData = ref<Record<string, unknown> | null>(null)
  const evaluationDialogIsError = ref(false)

  const selectedWithOutput = computed(() =>
    testCases.value.filter(tc => selected.value.includes(tc.id) && tc.output && tc.version_output_id)
  )

  const testCasesWithOutput = computed(() => testCases.value.filter(tc => tc.output && tc.version_output_id))

  const canEvaluateSelected = computed(() => selectedWithOutput.value.length > 0 && judges.value.length > 0)

  const evaluateSelectedTests = async (testCaseIdsOverride?: string[]) => {
    const toEvaluate = testCaseIdsOverride
      ? testCases.value.filter(tc => testCaseIdsOverride.includes(tc.id) && tc.output && tc.version_output_id)
      : selectedWithOutput.value

    if (!projectId.value || !judges.value.length || !toEvaluate.length) return

    const voIds = toEvaluate.map(tc => tc.version_output_id).filter((id): id is string => !!id)
    if (!voIds.length) return
    if (!testCaseIdsOverride) evaluatingSelected.value = true

    try {
      const judgeIds = judges.value.map(j => j.id)
      const clearUpdates: Record<string, Partial<QATestCaseUI>> = {}

      voIds.forEach(voId => {
        const tc = testCases.value.find(t => t.version_output_id === voId)
        if (tc?.output) {
          clearUpdates[tc.id] = { evaluations: [] }
          rowEvaluating.value[tc.id] = true
        }
      })
      patchTestCases(clearUpdates)

      await runEvaluations(projectId.value, judgeIds, voIds)

      for (const voId of voIds) {
        const evals = await fetchEvaluationsForVersionOutput(projectId.value, voId)
        const tc = testCases.value.find(t => t.version_output_id === voId)
        if (tc) patchTestCase(tc.id, { evaluations: evals || [] })
      }
    } catch (err: unknown) {
      logger.error('Error evaluating selected tests', { error: err })
    } finally {
      if (!testCaseIdsOverride) evaluatingSelected.value = false
      toEvaluate.forEach(tc => {
        if (tc.version_output_id) rowEvaluating.value[tc.id] = false
      })
    }
  }

  const evaluateAllTests = async () => {
    if (!projectId.value || !judges.value.length) return
    const allIds = testCasesWithOutput.value.map(tc => tc.id)
    if (!allIds.length) return
    evaluatingAll.value = true
    try {
      await evaluateSelectedTests(allIds)
    } finally {
      evaluatingAll.value = false
    }
  }

  const getEvaluateTooltip = (testCase: QATestCaseUI) => {
    if (!judges.value.length) return 'Create judge before evaluating'
    if (!testCase.output || !testCase.version_output_id) return 'Run test case before evaluating'
    return 'Evaluate test case'
  }

  const evaluateSingleTest = async (testCase: QATestCaseUI) => {
    if (!projectId.value || !testCase.output || !testCase.version_output_id || !judges.value.length) return
    rowEvaluating.value[testCase.id] = true
    patchTestCase(testCase.id, { evaluations: [] })
    try {
      await runEvaluations(
        projectId.value,
        judges.value.map(j => j.id),
        [testCase.version_output_id]
      )

      const evals = await fetchEvaluationsForVersionOutput(projectId.value, testCase.version_output_id)

      patchTestCase(testCase.id, { evaluations: evals || [] })
    } catch (err: unknown) {
      logger.error('Error evaluating test case', { error: err })
    } finally {
      rowEvaluating.value[testCase.id] = false
    }
  }

  const getJudgeName = (judgeId: string) => judges.value.find(j => j.id === judgeId)?.name || 'Unknown Judge'

  const openEvaluationDialog = (evaluation: Evaluation) => {
    evaluationDialogTitle.value = getJudgeName(evaluation.judge_id)

    const result = evaluation.evaluation_result
    const isError = result?.type === 'error'

    evaluationDialogIsError.value = isError

    const raw = result?.justification

    if (raw) {
      if (isError) {
        evaluationDialogData.value = null
        evaluationDialogText.value = raw
      } else {
        try {
          evaluationDialogData.value = JSON.parse(raw)
          evaluationDialogText.value = ''
        } catch {
          evaluationDialogData.value = null
          evaluationDialogText.value = raw
        }
      }
    } else {
      evaluationDialogData.value = null
      evaluationDialogText.value = isError ? 'No error details available' : 'No justification available'
    }
    showEvaluationDialog.value = true
  }

  const handleJudgeEvaluationClick = (testCase: QATestCaseUI, judge: { id: string; name: string }) => {
    const evaluation = getEvaluationForJudge(testCase, judge.id)
    if (evaluation) openEvaluationDialog(evaluation)
  }

  const loadEvaluationsForTestCases = async () => {
    if (!projectId.value || !testCases.value.length) return
    const withVo = testCases.value.filter(tc => tc.version_output_id)
    if (!withVo.length) return
    for (const tc of withVo) {
      if (!tc.version_output_id) continue
      try {
        tc.evaluations = (await fetchEvaluationsForVersionOutput(projectId.value, tc.version_output_id)) || []
      } catch (err) {
        logger.error(
          `Error loading evaluations for test case ${tc.id} (version_output_id: ${tc.version_output_id})`,
          err
        )
        tc.evaluations = []
      }
    }
  }

  return {
    loadingEvaluations,
    rowEvaluating,
    evaluatingSelected,
    evaluatingAll,
    showEvaluationDialog,
    evaluationDialogText,
    evaluationDialogTitle,
    evaluationDialogData,
    evaluationDialogIsError,
    selectedWithOutput,
    testCasesWithOutput,
    canEvaluateSelected,
    evaluateSelectedTests,
    evaluateAllTests,
    evaluateSingleTest,
    getEvaluateTooltip,
    getJudgeName,
    openEvaluationDialog,
    handleJudgeEvaluationClick,
    loadEvaluationsForTestCases,
  }
}
