import type { LLMJudgeCreate, LLMJudgeUpdate } from '@/types/qa'
import type { QAAsyncRunResponse, QASession } from '@/types/qaStream'
import { $api, getApiBaseUrl, getAuthHeaders } from '@/utils/api'
import { logger } from '@/utils/logger'

interface QAProcessRunPayload {
  graph_runner_id: string
  input_ids?: string[]
  run_all?: boolean
}

export const qaApi = {
  // Organization-scoped dataset CRUD
  getDatasets: (orgId: string) => $api(`/organizations/${orgId}/qa/datasets`),

  createDatasets: (orgId: string, data: { datasets_name: string[] }) =>
    $api(`/organizations/${orgId}/qa/datasets`, { method: 'POST', body: data }),

  updateDataset: (orgId: string, datasetId: string, datasetName: string) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}`, {
      method: 'PATCH',
      query: { dataset_name: datasetName },
    }),

  deleteDatasets: (orgId: string, data: { dataset_ids: string[] }) =>
    $api(`/organizations/${orgId}/qa/datasets`, { method: 'DELETE', body: data }),

  setDatasetProjects: (orgId: string, datasetId: string, projectIds: string[]) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/projects`, {
      method: 'PUT',
      body: { project_ids: projectIds },
    }),

  // Organization-scoped entries
  getInputGroundtruths: (orgId: string, datasetId: string, params?: { page?: number; page_size?: number }) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/entries`, { query: params }),

  getOutputs: (orgId: string, datasetId: string, graphRunnerId: string) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/outputs`, { query: { graph_runner_id: graphRunnerId } }),

  saveTraceToQA: (orgId: string, traceId: string, datasetId: string) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/entries/from-history`, {
      method: 'POST',
      query: { trace_id: traceId },
    }),

  createInputGroundtruths: (
    orgId: string,
    datasetId: string,
    data: { inputs_groundtruths: Array<{ input: any; groundtruth: string }> }
  ) => $api(`/organizations/${orgId}/qa/datasets/${datasetId}/entries`, { method: 'POST', body: data }),

  updateInputGroundtruths: (
    orgId: string,
    datasetId: string,
    data: { inputs_groundtruths: Array<{ id: string; input?: any; groundtruth?: string }> }
  ) => $api(`/organizations/${orgId}/qa/datasets/${datasetId}/entries`, { method: 'PATCH', body: data }),

  deleteInputGroundtruths: (orgId: string, datasetId: string, data: { input_groundtruth_ids: string[] }) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/entries`, { method: 'DELETE', body: data }),

  // Organization-scoped custom columns
  getCustomColumns: (orgId: string, datasetId: string) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/custom-columns`),

  createCustomColumn: (orgId: string, datasetId: string, data: { column_name: string }) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/custom-columns`, { method: 'POST', body: data }),

  renameCustomColumn: (orgId: string, datasetId: string, columnId: string, data: { column_name: string }) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/custom-columns/${columnId}`, {
      method: 'PATCH',
      body: data,
    }),

  deleteCustomColumn: (orgId: string, datasetId: string, columnId: string) =>
    $api(`/organizations/${orgId}/qa/datasets/${datasetId}/custom-columns/${columnId}`, { method: 'DELETE' }),

  // Project-scoped QA runs (unchanged)
  runQAProcess: (projectId: string, datasetId: string, data: QAProcessRunPayload) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/run`, { method: 'POST', body: data }),

  runQAProcessAsync: (projectId: string, datasetId: string, data: QAProcessRunPayload): Promise<QAAsyncRunResponse> =>
    $api<QAAsyncRunResponse>(`/projects/${projectId}/qa/datasets/${datasetId}/run/async`, {
      method: 'POST',
      body: data,
    }),

  getQASession: (projectId: string, sessionId: string): Promise<QASession> =>
    $api<QASession>(`/projects/${projectId}/qa/sessions/${sessionId}`),

  getQASessions: (projectId: string, datasetId: string): Promise<QASession[]> =>
    $api<QASession[]>(`/projects/${projectId}/qa/sessions`, { query: { dataset_id: datasetId } }),

  // Organization-scoped CSV export/import
  exportToCSV: async (orgId: string, datasetId: string, graphRunnerId: string) => {
    const authHeaders = await getAuthHeaders()
    const path = `/organizations/${orgId}/qa/datasets/${datasetId}/export`
    const url = `${getApiBaseUrl()}${path}?graph_runner_id=${encodeURIComponent(graphRunnerId)}`

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: authHeaders,
      })

      if (!response.ok) {
        let errorMessage = `Failed to export CSV: ${response.status} ${response.statusText}`
        try {
          const clonedResponse = response.clone()
          const contentType = response.headers.get('content-type') || ''

          if (contentType.includes('application/json')) {
            const errorData = await clonedResponse.json()
            if (errorData?.detail) errorMessage = errorData.detail
            else if (typeof errorData === 'string') errorMessage = errorData
          } else {
            const errorText = await clonedResponse.text()
            if (errorText) {
              try {
                const parsed = JSON.parse(errorText)
                if (parsed?.detail) errorMessage = parsed.detail
                else errorMessage = errorText
              } catch (error: unknown) {
                errorMessage = errorText
              }
            }
          }
        } catch (parseError) {
          logger.error('Failed to parse error response', { error: parseError })
        }
        logger.error('CSV Export HTTP Error', {
          status: response.status,
          statusText: response.statusText,
          url,
          errorMessage,
        })
        throw new Error(errorMessage)
      }

      const contentDisposition = response.headers.get('Content-Disposition')
      let filename = `qa_export_${datasetId}_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5).replace('T', '_')}.csv`

      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
        if (filenameMatch && filenameMatch[1]) filename = filenameMatch[1].replace(/['"]/g, '')
      }

      const blob = await response.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')

      link.href = downloadUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(downloadUrl)
    } catch (error: unknown) {
      logger.error('CSV Export Error', {
        url,
        orgId,
        datasetId,
        graphRunnerId,
        error,
      })
      throw error
    }
  },

  importFromCSV: async (orgId: string, datasetId: string, file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('File must be a CSV file')

    const formData = new FormData()
    formData.append('file', file)

    return $api(`/organizations/${orgId}/qa/datasets/${datasetId}/import`, {
      method: 'POST',
      body: formData,
    })
  },
}

export const qaEvaluationApi = {
  // Organization-scoped judge CRUD
  getLLMJudges: (orgId: string) => $api(`/organizations/${orgId}/qa/llm-judges`),

  getLLMJudgeDefaults: (evaluationType?: 'boolean' | 'score' | 'free_text' | 'json_equality') =>
    $api('/qa/llm-judges/defaults', { query: evaluationType ? { evaluation_type: evaluationType } : {} }),

  createLLMJudge: (orgId: string, data: LLMJudgeCreate) =>
    $api(`/organizations/${orgId}/qa/llm-judges`, { method: 'POST', body: data }),

  updateLLMJudge: (orgId: string, judgeId: string, data: LLMJudgeUpdate) =>
    $api(`/organizations/${orgId}/qa/llm-judges/${judgeId}`, { method: 'PATCH', body: data }),

  deleteLLMJudges: (orgId: string, judgeIds: string[]) =>
    $api(`/organizations/${orgId}/qa/llm-judges`, { method: 'DELETE', body: judgeIds }),

  setJudgeProjects: (orgId: string, judgeId: string, projectIds: string[]) =>
    $api(`/organizations/${orgId}/qa/llm-judges/${judgeId}/projects`, {
      method: 'PUT',
      body: { project_ids: projectIds },
    }),

  // Project-scoped evaluations (unchanged)
  runJudgeEvaluation: (projectId: string, judgeId: string, versionOutputId: string) =>
    $api(`/projects/${projectId}/qa/llm-judges/${judgeId}/evaluations/run`, {
      method: 'POST',
      body: { version_output_id: versionOutputId },
    }),

  getEvaluationsByVersionOutput: (projectId: string, versionOutputId: string) =>
    $api(`/projects/${projectId}/qa/version-outputs/${versionOutputId}/evaluations`),

  deleteEvaluations: (projectId: string, evaluationIds: string[]) =>
    $api(`/projects/${projectId}/qa/evaluations`, {
      method: 'DELETE',
      body: evaluationIds,
    }),

  getVersionOutputIds: (projectId: string, graphRunnerId: string, inputIds: string[]) =>
    $api(`/projects/${projectId}/qa/version-outputs`, {
      query: {
        graph_runner_id: graphRunnerId,
        input_ids: inputIds,
      },
    }),
}
