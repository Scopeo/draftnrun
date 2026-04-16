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
  getDatasets: (projectId: string) => $api(`/projects/${projectId}/qa/datasets`),

  createDatasets: (projectId: string, data: { datasets_name: string[] }) =>
    $api(`/projects/${projectId}/qa/datasets`, { method: 'POST', body: data }),

  updateDataset: (projectId: string, datasetId: string, datasetName: string) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}`, {
      method: 'PATCH',
      query: { dataset_name: datasetName },
    }),

  deleteDatasets: (projectId: string, data: { dataset_ids: string[] }) =>
    $api(`/projects/${projectId}/qa/datasets`, { method: 'DELETE', body: data }),

  getInputGroundtruths: (projectId: string, datasetId: string, params?: { page?: number; page_size?: number }) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/entries`, { query: params }),

  getOutputs: (projectId: string, datasetId: string, graphRunnerId: string) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/outputs`, { query: { graph_runner_id: graphRunnerId } }),

  saveTraceToQA: (projectId: string, traceId: string, datasetId: string) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/entries/from-history`, {
      method: 'POST',
      query: {
        trace_id: traceId,
      },
    }),

  createInputGroundtruths: (
    projectId: string,
    datasetId: string,
    data: { inputs_groundtruths: Array<{ input: any; groundtruth: string }> }
  ) => $api(`/projects/${projectId}/qa/datasets/${datasetId}/entries`, { method: 'POST', body: data }),

  updateInputGroundtruths: (
    projectId: string,
    datasetId: string,
    data: { inputs_groundtruths: Array<{ id: string; input?: any; groundtruth?: string }> }
  ) => $api(`/projects/${projectId}/qa/datasets/${datasetId}/entries`, { method: 'PATCH', body: data }),

  deleteInputGroundtruths: (projectId: string, datasetId: string, data: { input_groundtruth_ids: string[] }) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/entries`, { method: 'DELETE', body: data }),

  getCustomColumns: (projectId: string, datasetId: string) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/custom-columns`),

  createCustomColumn: (projectId: string, datasetId: string, data: { column_name: string }) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/custom-columns`, { method: 'POST', body: data }),

  renameCustomColumn: (projectId: string, datasetId: string, columnId: string, data: { column_name: string }) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/custom-columns/${columnId}`, { method: 'PATCH', body: data }),

  deleteCustomColumn: (projectId: string, datasetId: string, columnId: string) =>
    $api(`/projects/${projectId}/qa/datasets/${datasetId}/custom-columns/${columnId}`, { method: 'DELETE' }),

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

  // Uses raw fetch because $api doesn't support blob responses for file downloads
  exportToCSV: async (projectId: string, datasetId: string, graphRunnerId: string) => {
    const authHeaders = await getAuthHeaders()
    const path = `/projects/${projectId}/qa/datasets/${datasetId}/export`
    const url = `${getApiBaseUrl()}${path}?graph_runner_id=${encodeURIComponent(graphRunnerId)}`

    try {
      const response = await fetch(url, {
        method: 'GET',
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
        projectId,
        datasetId,
        graphRunnerId,
        error,
      })
      throw error
    }
  },

  importFromCSV: async (projectId: string, datasetId: string, file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('File must be a CSV file')

    const formData = new FormData()

    formData.append('file', file)

    return $api(`/projects/${projectId}/qa/datasets/${datasetId}/import`, {
      method: 'POST',
      body: formData,
    })
  },
}

export const qaEvaluationApi = {
  getLLMJudges: (projectId: string) => $api(`/projects/${projectId}/qa/llm-judges`),

  getLLMJudgeDefaults: (evaluationType?: 'boolean' | 'score' | 'free_text' | 'json_equality') =>
    $api('/qa/llm-judges/defaults', { query: evaluationType ? { evaluation_type: evaluationType } : {} }),

  createLLMJudge: (projectId: string, data: LLMJudgeCreate) =>
    $api(`/projects/${projectId}/qa/llm-judges`, { method: 'POST', body: data }),

  updateLLMJudge: (projectId: string, judgeId: string, data: LLMJudgeUpdate) =>
    $api(`/projects/${projectId}/qa/llm-judges/${judgeId}`, { method: 'PATCH', body: data }),

  deleteLLMJudges: (projectId: string, judgeIds: string[]) =>
    $api(`/projects/${projectId}/qa/llm-judges`, { method: 'DELETE', body: judgeIds }),

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
