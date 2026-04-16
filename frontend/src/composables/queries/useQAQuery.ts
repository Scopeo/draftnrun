import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { qaEvaluationApi, scopeoApi } from '@/api'
import type {
  QAColumnCreate,
  QAColumnListResponse,
  QAColumnRename,
  QADataset,
  QATestCaseUI,
  QAVersion,
} from '@/types/qa'
import type { QAAsyncRunResponse, QASession } from '@/types/qaStream'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

// Re-export types for convenience
export type { QADataset, QATestCaseUI, QAVersion }

/**
 * Fetches QA datasets for a project
 */
export function useQADatasetsQuery(projectId: Ref<string | undefined>) {
  const queryKey = computed(() => ['qa-datasets', projectId.value] as const)

  return useQuery<QADataset[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['qa-datasets', projectId.value], 'useQADatasetsQuery')

      if (!projectId.value) {
        return []
      }

      const data = await scopeoApi.qa.getDatasets(projectId.value)
      return data || []
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Fetches QA versions (graph runners) for a project
 */
export function useQAVersionsQuery(projectId: Ref<string | undefined>) {
  const queryKey = computed(() => ['qa-versions', projectId.value] as const)

  return useQuery<QAVersion[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['qa-versions', projectId.value], 'useQAVersionsQuery')

      if (!projectId.value) {
        return []
      }

      return []
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Fetches input-groundtruth pairs for a dataset and version
 * Includes full transformation logic with pagination, sorting, outputs, and version_output_ids
 */
export function useQAInputGroundtruthsQuery(
  projectId: Ref<string | undefined>,
  datasetId: Ref<string | undefined>,
  graphRunnerId: Ref<string | undefined>
) {
  const queryKey = computed(
    () => ['qa-input-groundtruths', projectId.value, datasetId.value, graphRunnerId.value] as const
  )

  const query = useQuery<{ testCases: QATestCaseUI[]; lastLoadedAt: string }>({
    queryKey,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      logQueryStart(
        ['qa-input-groundtruths', projectId.value, datasetId.value, graphRunnerId.value],
        'useQAInputGroundtruthsQuery'
      )

      if (!projectId.value || !datasetId.value) {
        return { testCases: [], lastLoadedAt: new Date().toISOString() }
      }

      // 1) Fetch ALL the base inputs/groundtruth list using pagination
      const pageSize = 200
      let allBaseData: any[] = []
      let page = 1
      let hasMore = true

      while (hasMore) {
        const baseResp = await scopeoApi.qa.getInputGroundtruths(projectId.value, datasetId.value, {
          page,
          page_size: pageSize,
        })

        const pageData: any[] =
          baseResp && baseResp.inputs_groundtruths
            ? baseResp.inputs_groundtruths
            : Array.isArray(baseResp)
              ? baseResp
              : []

        allBaseData = [...allBaseData, ...pageData]

        // If we got fewer results than pageSize, we've reached the end
        hasMore = pageData.length === pageSize
        page++
      }

      const baseData = allBaseData
      const total = baseData.length

      // Sort by created_at
      const baseList = baseData
        .map((e: any, idx: number) => ({
          ...e,
          __order: e.created_at ? new Date(e.created_at).getTime() : total - idx,
        }))
        .sort((a: any, b: any) => (a.__order as number) - (b.__order as number))

      // Build initial test cases
      const initialCases: QATestCaseUI[] = baseList.map((entry: any) => ({
        id: entry.id,
        input: entry.input,
        groundtruth: entry.groundtruth,
        custom_columns: entry.custom_columns || {},
        output: null,
        version: null,
        version_output_id: null,
        status: 'Pending' as const,
        position: entry.position,
        evaluations: undefined,
      }))

      // If graphRunnerId is provided, fetch outputs and version_output_ids
      if (graphRunnerId.value) {
        // Get outputs (Dict[input_id, output])
        const outputsResp = await scopeoApi.qa.getOutputs(projectId.value, datasetId.value, graphRunnerId.value)
        const outputsDict: Record<string, string> = outputsResp || {}

        // Get all input IDs from the test cases
        const allInputIds = initialCases.map(tc => tc.id)

        // Get version_output_ids (Dict[input_id, version_output_id])
        let versionOutputIdsResp: Record<string, string | null> = {}
        if (allInputIds.length > 0) {
          versionOutputIdsResp = await qaEvaluationApi.getVersionOutputIds(
            projectId.value,
            graphRunnerId.value,
            allInputIds
          )
        }

        const versionOutputIdsDict: Record<string, string | null> = versionOutputIdsResp || {}

        const outputByInputId = new Map<string, { output: string; version_output_id: string | null }>()

        Object.keys(outputsDict).forEach(inputId => {
          outputByInputId.set(String(inputId), {
            output: outputsDict[inputId] || '',
            version_output_id: versionOutputIdsDict[inputId] || null,
          })
        })

        const casesWithOutputs: QATestCaseUI[] = initialCases.map(tc => {
          const outputData = outputByInputId.get(String(tc.id))
          if (!outputData) {
            return {
              ...tc,
              output: null,
              version: null,
              version_output_id: null,
              status: 'Pending' as const,
              evaluations: undefined,
            }
          }

          return {
            ...tc,
            output: outputData.output || null,
            version: graphRunnerId.value!,
            version_output_id: outputData.version_output_id,
            status: outputData.output ? ('Run' as const) : ('Pending' as const),
            evaluations: undefined,
          }
        })

        return { testCases: casesWithOutputs, lastLoadedAt: new Date().toISOString() }
      }

      return { testCases: initialCases, lastLoadedAt: new Date().toISOString() }
    },
    enabled: computed(() => !!projectId.value && !!datasetId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })

  // Convenience computed for just the test cases array
  const testCases = computed(() => query.data.value?.testCases || [])
  const queryLastLoadedAt = computed(() => query.data.value?.lastLoadedAt || null)

  return {
    ...query,
    testCases,
    lastLoadedAt: queryLastLoadedAt,
  }
}

/**
 * Mutation to create a QA dataset
 */
export function useCreateQADatasetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ projectId, data }: { projectId: string; data: any }) => {
      return await scopeoApi.qa.createDatasets(projectId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['qa-datasets', variables.projectId] })
    },
  })
}

/**
 * Mutation to delete a QA dataset
 */
export function useDeleteQADatasetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ projectId, datasetIds }: { projectId: string; datasetIds: string[] }) => {
      return await scopeoApi.qa.deleteDatasets(projectId, { dataset_ids: datasetIds })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['qa-datasets', variables.projectId] })
      variables.datasetIds.forEach(datasetId => {
        queryClient.invalidateQueries({ queryKey: ['qa-input-groundtruths', variables.projectId, datasetId] })
      })
    },
  })
}

/**
 * Mutation to add input-groundtruth pairs
 */
export function useAddInputGroundtruthMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      data,
    }: {
      projectId: string
      datasetId: string
      data: {
        inputs_groundtruths: Array<{
          input: unknown
          groundtruth: string
          custom_columns?: Record<string, string | null> | null
        }>
      }
    }) => {
      return await scopeoApi.qa.createInputGroundtruths(projectId, datasetId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['qa-input-groundtruths', variables.projectId, variables.datasetId],
      })
    },
  })
}

/**
 * Mutation to update input-groundtruth pairs
 */
export function useUpdateInputGroundtruthMutation() {
  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      data,
    }: {
      projectId: string
      datasetId: string
      data: {
        inputs_groundtruths: Array<{
          id: string
          input?: unknown
          groundtruth?: string
          custom_columns?: Record<string, string | null> | null
        }>
      }
    }) => {
      return await scopeoApi.qa.updateInputGroundtruths(projectId, datasetId, data)
    },
    // No onSuccess/cache patch — the local ref in QADatasetTable is the source of truth
    // while editing. Patching the cache here would trigger the queryTestCases watcher
    // and overwrite in-progress edits.
  })
}

/**
 * Mutation to delete input-groundtruth pairs
 */
export function useDeleteInputGroundtruthMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      entryIds,
    }: {
      projectId: string
      datasetId: string
      entryIds: string[]
    }) => {
      return await scopeoApi.qa.deleteInputGroundtruths(projectId, datasetId, { input_groundtruth_ids: entryIds })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['qa-input-groundtruths', variables.projectId, variables.datasetId],
      })
    },
  })
}

/**
 * Mutation to run QA process
 */
export function useRunQAProcessMutation() {
  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      data,
    }: {
      projectId: string
      datasetId: string
      data: {
        graph_runner_id: string
        input_ids?: string[]
        run_all?: boolean
      }
    }) => {
      return await scopeoApi.qa.runQAProcess(projectId, datasetId, data)
    },
  })
}

/**
 * Fetches custom columns for a dataset
 */
export function useQACustomColumnsQuery(projectId: Ref<string | undefined>, datasetId: Ref<string | undefined>) {
  const queryKey = computed(() => ['qa-custom-columns', projectId.value, datasetId.value] as const)

  return useQuery<QAColumnListResponse>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['qa-custom-columns', projectId.value, datasetId.value], 'useQACustomColumnsQuery')

      if (!projectId.value || !datasetId.value) {
        return []
      }

      const data = await scopeoApi.qa.getCustomColumns(projectId.value, datasetId.value)
      return data || []
    },
    enabled: computed(() => !!projectId.value && !!datasetId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Mutation to create a custom column
 */
export function useCreateQACustomColumnMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      data,
    }: {
      projectId: string
      datasetId: string
      data: QAColumnCreate
    }) => {
      return await scopeoApi.qa.createCustomColumn(projectId, datasetId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['qa-custom-columns', variables.projectId, variables.datasetId],
      })
    },
  })
}

/**
 * Mutation to rename a custom column
 */
export function useRenameQACustomColumnMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      columnId,
      data,
    }: {
      projectId: string
      datasetId: string
      columnId: string
      data: QAColumnRename
    }) => {
      return await scopeoApi.qa.renameCustomColumn(projectId, datasetId, columnId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['qa-custom-columns', variables.projectId, variables.datasetId],
      })
    },
  })
}

/**
 * Mutation to delete a custom column
 */
export function useDeleteQACustomColumnMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      datasetId,
      columnId,
    }: {
      projectId: string
      datasetId: string
      columnId: string
    }) => {
      return await scopeoApi.qa.deleteCustomColumn(projectId, datasetId, columnId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['qa-custom-columns', variables.projectId, variables.datasetId],
      })
      // Also invalidate entries since deleting a column affects the data
      queryClient.invalidateQueries({
        queryKey: ['qa-input-groundtruths', variables.projectId, variables.datasetId],
      })
    },
  })
}

/**
 * Mutation to start an async QA run (returns session_id for WebSocket streaming)
 */
export function useRunQAProcessAsyncMutation() {
  return useMutation<
    QAAsyncRunResponse,
    Error,
    {
      projectId: string
      datasetId: string
      data: {
        graph_runner_id: string
        input_ids?: string[]
        run_all?: boolean
      }
    }
  >({
    mutationFn: async ({ projectId, datasetId, data }) => {
      logNetworkCall(
        ['qa-async-run', projectId, datasetId],
        `/projects/${projectId}/qa/datasets/${datasetId}/run/async`
      )
      return await scopeoApi.qa.runQAProcessAsync(projectId, datasetId, data)
    },
  })
}

/**
 * Query to fetch a single QA session (for polling / reconnect after page refresh)
 */
export function useQASessionQuery(projectId: Ref<string | undefined>, sessionId: Ref<string | undefined>) {
  const queryKey = computed(() => ['qa-session', projectId.value, sessionId.value] as const)

  return useQuery<QASession>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['qa-session', projectId.value, sessionId.value], 'useQASessionQuery')
      logNetworkCall(
        ['qa-session', projectId.value, sessionId.value],
        `/projects/${projectId.value}/qa/sessions/${sessionId.value}`
      )
      return await scopeoApi.qa.getQASession(projectId.value!, sessionId.value!)
    },
    enabled: computed(() => !!projectId.value && !!sessionId.value),
    staleTime: 0,
    gcTime: 1000 * 60 * 5,
    refetchOnMount: true,
  })
}

/**
 * Query to list QA sessions for a dataset (history)
 */
export function useQASessionsQuery(projectId: Ref<string | undefined>, datasetId: Ref<string | undefined>) {
  const queryKey = computed(() => ['qa-sessions', projectId.value, datasetId.value] as const)

  return useQuery<QASession[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['qa-sessions', projectId.value, datasetId.value], 'useQASessionsQuery')

      if (!projectId.value || !datasetId.value) {
        return []
      }

      logNetworkCall(
        ['qa-sessions', projectId.value, datasetId.value],
        `/projects/${projectId.value}/qa/sessions?dataset_id=${datasetId.value}`
      )
      return await scopeoApi.qa.getQASessions(projectId.value, datasetId.value)
    },
    enabled: computed(() => !!projectId.value && !!datasetId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}
