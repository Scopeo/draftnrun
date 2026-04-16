import { qaEvaluationApi, scopeoApi } from '@/api'
import type { QATestCaseUI } from '@/composables/queries/useQAQuery'
import { useQARunStream } from '@/composables/useQARunStream'
import { logger } from '@/utils/logger'
import type { ComputedRef, Ref } from 'vue'
import { computed, reactive, ref } from 'vue'

interface RunDeps {
  projectId: ComputedRef<string>
  currentDataset: Ref<{ id: string } | null>
  currentVersion: Ref<{ id: string; graph_runner_id?: string | null } | null>
  testCases: Ref<QATestCaseUI[]>
  versions: ComputedRef<Array<{ id: string; graph_runner_id?: string | null }>>
  selected: Ref<string[]>
  patchTestCase: (id: string, patch: Partial<QATestCaseUI>) => void
  patchTestCases: (updates: Record<string, Partial<QATestCaseUI>>) => void
  runQAProcessMutation: (args: {
    projectId: string
    datasetId: string
    data: { graph_runner_id: string; input_ids?: string[]; run_all?: true }
  }) => Promise<{ results?: Array<{ input_id: string; output?: string; version?: string; success?: boolean }> }>
  runQAProcessAsyncMutation: (args: {
    projectId: string
    datasetId: string
    data: { graph_runner_id: string; input_ids?: string[]; run_all?: true }
  }) => Promise<{ session_id: string }>
  deleteEvaluationsForVersionOutput: (projectId: string, versionOutputId: string) => Promise<unknown>
  refetchTestCases: () => Promise<unknown>
  showSuccess: (msg: string) => void
  showError: (msg: string) => void
  showWarning: (msg: string) => void
}

export function useQARunOrchestration(deps: RunDeps) {
  const {
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
    refetchTestCases,
    showSuccess,
    showError,
    showWarning,
  } = deps

  const isAsyncEnabled = import.meta.env.VITE_RUN_ASYNC_CREDENTIALS === 'true'
  const rowRunning = ref<Record<string, boolean>>({})
  const batchRunningAll = ref(false)
  const currentSessionId = ref<string | null>(null)
  const qaProgress = reactive({ index: 0, total: 0 })
  const cleanupWs = ref<(() => void) | null>(null)
  const wsDisconnected = ref(false)
  const refreshing = ref(false)
  const { connect: connectQAStream } = useQARunStream()

  const isRunning = computed(
    () => batchRunningAll.value || !!currentSessionId.value || Object.values(rowRunning.value).some(Boolean)
  )

  const getSessionStorageKey = () => `qa-session:${projectId.value}:${currentDataset.value?.id}`

  // --- Shared helpers ---

  const resetRunState = () => {
    Object.keys(rowRunning.value).forEach(id => {
      rowRunning.value[id] = false
    })
    batchRunningAll.value = false
    currentSessionId.value = null
    qaProgress.index = 0
    qaProgress.total = 0
    cleanupWs.value = null
    wsDisconnected.value = false
    try {
      sessionStorage.removeItem(getSessionStorageKey())
    } catch (e: unknown) {
      logger.warn('Failed to remove QA session from storage', { error: e })
    }
  }

  const prepareRowsForRun = (ids: string[]) => {
    const updates: Record<string, Partial<QATestCaseUI>> = {}

    ids.forEach(id => {
      const row = testCases.value.find(tc => tc.id === id)
      if (!row) return
      const oldVoId = row.version_output_id

      updates[id] = { output: null, status: 'Running', version_output_id: null, evaluations: [] }
      if (oldVoId) {
        deleteEvaluationsForVersionOutput(projectId.value, oldVoId).catch(err => {
          logger.error(`Error deleting evaluations for version_output_id ${oldVoId}`, { error: err })
        })
      }
      rowRunning.value[id] = true
    })
    patchTestCases(updates)
  }

  // --- Async run ---

  const connectToQASession = (projId: string, sessionId: string, _targetIds: string[], graphRunnerId: string) => {
    cleanupWs.value?.()
    wsDisconnected.value = false

    cleanupWs.value = connectQAStream(projId, sessionId, {
      onEntryStarted(_inputId, index, total) {
        qaProgress.index = index + 1
        qaProgress.total = total
      },
      async onEntryCompleted(inputId, output, success, error) {
        patchTestCase(inputId, {
          output: success ? output : `Error: ${error || output}`,
          version: graphRunnerId,
          status: success ? 'Run' : 'Failed',
        })
        rowRunning.value[inputId] = false

        if (graphRunnerId) {
          try {
            const voIds = await qaEvaluationApi.getVersionOutputIds(projId, graphRunnerId, [inputId])
            if (voIds?.[inputId]) patchTestCase(inputId, { version_output_id: voIds[inputId] })
          } catch (err) {
            logger.error(`Error fetching version_output_id for ${inputId}`, { error: err })
          }
        }
      },
      onCompleted(summary) {
        resetRunState()
        showSuccess(`QA run complete: ${summary.passed}/${summary.total} passed (${summary.success_rate.toFixed(0)}%)`)
      },
      onFailed(error) {
        testCases.value.forEach(tc => {
          if (tc.status === 'Running') patchTestCase(tc.id, { status: 'Failed' })
        })
        resetRunState()
        showError(`QA run failed: ${error.message}`)
      },
      onError(message) {
        logger.error('QA WebSocket error', { error: message })
      },
      onReconnectFailed() {
        wsDisconnected.value = true
        showWarning('Live refresh is not working. Use the Refresh button to update results.')
      },
    })
  }

  const startAsyncRun = async (ids: string[], runAll: boolean) => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    if (currentSessionId.value) {
      showWarning('A QA run is already in progress. Please wait for it to finish.')
      return
    }
    const projId = projectId.value
    const datasetId = currentDataset.value.id
    const graphRunnerId = currentVersion.value.graph_runner_id!

    prepareRowsForRun(ids)

    try {
      const body = runAll
        ? { graph_runner_id: graphRunnerId, run_all: true as const }
        : { graph_runner_id: graphRunnerId, input_ids: ids }

      const { session_id } = await runQAProcessAsyncMutation({ projectId: projId, datasetId, data: body })

      currentSessionId.value = session_id
      qaProgress.index = 0
      qaProgress.total = 0
      try {
        sessionStorage.setItem(getSessionStorageKey(), session_id)
      } catch (e: unknown) {
        logger.warn('Failed to save QA session to storage', { error: e })
      }
      connectToQASession(projId, session_id, ids, graphRunnerId)
    } catch (err) {
      ids.forEach(id => {
        rowRunning.value[id] = false
        patchTestCase(id, { status: 'Failed' })
      })
      batchRunningAll.value = false
      showError(`Failed to start QA run: ${err instanceof Error ? err.message : 'Unknown error'}`)
    }
  }

  // --- Sync run ---

  const runSingleTestSync = async (testCase: QATestCaseUI) => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    rowRunning.value[testCase.id] = true

    const originalStatus = testCase.status
    const oldVoId = testCase.version_output_id

    patchTestCase(testCase.id, { output: null, status: 'Running', version_output_id: null, evaluations: [] })
    if (oldVoId && projectId.value) await deleteEvaluationsForVersionOutput(projectId.value, oldVoId)

    try {
      const result = await runQAProcessMutation({
        projectId: projectId.value,
        datasetId: currentDataset.value.id,
        data: { graph_runner_id: currentVersion.value.graph_runner_id!, input_ids: [testCase.id] },
      })

      const runResult = result?.results?.find(r => r.input_id === testCase.id)
      if (runResult) {
        patchTestCase(testCase.id, {
          output: runResult.output,
          version: runResult.version,
          status: runResult.success ? 'Run' : 'Failed',
        })
      }

      const current = testCases.value.find(tc => tc.id === testCase.id)
      if (current?.output && currentVersion.value?.graph_runner_id) {
        const voIds = await qaEvaluationApi.getVersionOutputIds(projectId.value, currentVersion.value.graph_runner_id, [
          testCase.id,
        ])

        if (voIds?.[testCase.id]) patchTestCase(testCase.id, { version_output_id: voIds[testCase.id] })
      }
    } finally {
      rowRunning.value[testCase.id] = false

      const current = testCases.value.find(tc => tc.id === testCase.id)
      if (current && !current.output) patchTestCase(testCase.id, { status: originalStatus || 'Pending' })
    }
  }

  const runSelectedTestsSync = async (idsOverride?: string[] | Event) => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    const projId = projectId.value
    const datasetId = currentDataset.value.id
    const graphRunnerId = currentVersion.value.graph_runner_id!
    const ids = Array.isArray(idsOverride) ? [...idsOverride] : [...selected.value]
    if (!ids.length) return
    if (!Array.isArray(idsOverride)) selected.value = []

    prepareRowsForRun(ids)

    for (const id of ids) {
      try {
        const result = await runQAProcessMutation({
          projectId: projId,
          datasetId,
          data: { graph_runner_id: graphRunnerId, input_ids: [id] },
        })

        const runResult = result?.results?.find(r => r.input_id === id)
        if (runResult) {
          patchTestCase(id, {
            output: runResult.output,
            version: runResult.version,
            status: runResult.success ? 'Run' : 'Failed',
          })
        }
        const row = testCases.value.find(tc => tc.id === id)
        if (row?.output && currentVersion.value?.graph_runner_id) {
          const voIds = await qaEvaluationApi.getVersionOutputIds(projId, currentVersion.value.graph_runner_id, [id])
          if (voIds?.[id]) patchTestCase(id, { version_output_id: voIds[id] })
        }
      } catch (err) {
        logger.error(`Error running test case ${id}`, { error: err })
      } finally {
        rowRunning.value[id] = false

        const row = testCases.value.find(tc => tc.id === id)
        if (row && !row.output && row.status === 'Running') patchTestCase(id, { status: 'Failed' })
      }
    }
  }

  // --- Public dispatchers ---

  const runSingleTest = async (testCase: QATestCaseUI) => {
    if (isRunning.value) {
      showWarning('A QA run is already in progress. Please wait for it to finish.')
      return
    }
    if (isAsyncEnabled) {
      batchRunningAll.value = false
      await startAsyncRun([testCase.id], false)
    } else {
      await runSingleTestSync(testCase)
    }
  }

  const runSelectedTests = async (idsOverride?: string[] | Event) => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    if (isRunning.value) {
      showWarning('A QA run is already in progress. Please wait for it to finish.')
      return
    }
    const ids = Array.isArray(idsOverride) ? [...idsOverride] : [...selected.value]
    if (!ids.length) return
    if (!Array.isArray(idsOverride)) selected.value = []
    if (isAsyncEnabled) {
      await startAsyncRun(ids, false)
    } else {
      await runSelectedTestsSync(idsOverride)
    }
  }

  const runAllTests = async () => {
    if (!projectId.value || !currentDataset.value || !currentVersion.value) return
    if (isRunning.value) {
      showWarning('A QA run is already in progress. Please wait for it to finish.')
      return
    }
    const allInputIds = testCases.value.map(tc => tc.id)
    if (!allInputIds.length) return
    batchRunningAll.value = true
    if (isAsyncEnabled) {
      await startAsyncRun(allInputIds, true)
    } else {
      try {
        await runSelectedTestsSync(allInputIds)
      } finally {
        batchRunningAll.value = false
      }
    }
  }

  // --- Reconnect after page refresh ---

  const tryReconnectAsyncSession = async () => {
    if (!isAsyncEnabled || !projectId.value || !currentDataset.value || !currentVersion.value) return

    let savedSessionId: string | null = null
    try {
      savedSessionId = sessionStorage.getItem(getSessionStorageKey())
    } catch (e: unknown) {
      logger.warn('Failed to read QA session from storage', { error: e })
    }
    if (!savedSessionId) return

    try {
      const session = await scopeoApi.qa.getQASession(projectId.value, savedSessionId)

      if (session.status === 'pending' || session.status === 'running') {
        currentSessionId.value = savedSessionId
        batchRunningAll.value = true

        const graphRunnerId = session.graph_runner_id
        const allIds = testCases.value.map(tc => tc.id)

        testCases.value.forEach(tc => {
          if (!tc.output) {
            patchTestCase(tc.id, { status: 'Running' })
            rowRunning.value[tc.id] = true
          }
        })
        connectToQASession(projectId.value, savedSessionId, allIds, graphRunnerId)
      } else if (session.status === 'completed') {
        try {
          sessionStorage.removeItem(getSessionStorageKey())
        } catch (e: unknown) {
          logger.warn('Failed to remove QA session from storage', { error: e })
        }
        if (session.total !== null) showSuccess(`QA run complete: ${session.passed ?? 0}/${session.total} passed`)
      } else if (session.status === 'failed') {
        try {
          sessionStorage.removeItem(getSessionStorageKey())
        } catch (e: unknown) {
          logger.warn('Failed to remove QA session from storage', { error: e })
        }
        showError(`QA run failed: ${session.error || 'Unknown error'}`)
      }
    } catch (err: unknown) {
      const errObj = err && typeof err === 'object' ? (err as Record<string, any>) : null
      const status = errObj?.status ?? errObj?.response?.status
      if (status === 404 || status === 410) {
        try {
          sessionStorage.removeItem(getSessionStorageKey())
        } catch (se: unknown) {
          logger.warn('Failed to remove QA session from storage', { error: se })
        }
      }
      logger.error('Failed to reconnect to QA session', { error: err })
    }
  }

  const refreshSessionStatus = async () => {
    if (!projectId.value) return
    refreshing.value = true
    try {
      if (currentSessionId.value) {
        const session = await scopeoApi.qa.getQASession(projectId.value, currentSessionId.value)

        if (session.status === 'completed') {
          await refetchTestCases()
          resetRunState()
          if (session.total !== null) {
            showSuccess(`QA run complete: ${session.passed ?? 0}/${session.total} passed`)
          }
          return
        } else if (session.status === 'failed') {
          await refetchTestCases()
          testCases.value.forEach(tc => {
            if (!tc.output) patchTestCase(tc.id, { status: 'Failed' })
          })
          resetRunState()
          showError(`QA run failed: ${session.error || 'Unknown error'}`)
          return
        } else {
          await refetchTestCases()
          testCases.value.forEach(tc => {
            if (!tc.output) {
              patchTestCase(tc.id, { status: 'Running' })
              rowRunning.value[tc.id] = true
            }
          })
          return
        }
      }

      await refetchTestCases()
    } catch (err) {
      logger.error('Failed to refresh QA session status', { error: err })
      showError('Failed to refresh results. Please try again.')
    } finally {
      refreshing.value = false
    }
  }

  const cleanupWebSocket = () => {
    cleanupWs.value?.()
  }

  return {
    isAsyncEnabled,
    isRunning,
    rowRunning,
    batchRunningAll,
    currentSessionId,
    qaProgress,
    wsDisconnected,
    refreshing,
    runSingleTest,
    runSelectedTests,
    runAllTests,
    refreshSessionStatus,
    tryReconnectAsyncSession,
    cleanupWebSocket,
  }
}
