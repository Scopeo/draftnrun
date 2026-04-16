/**
 * QA run stream WebSocket event payloads (server → client only).
 * Each message is one JSON line (UTF-8). Parse with JSON.parse(payload) and switch on type.
 */

export interface QAEntryStartedPayload {
  type: 'qa.entry.started'
  input_id: string
  index: number
  total: number
}

export interface QAEntryCompletedPayload {
  type: 'qa.entry.completed'
  input_id: string
  output: string
  success: boolean
  error: string | null
}

export interface QACompletedPayload {
  type: 'qa.completed'
  summary: {
    total: number
    passed: number
    failed: number
    success_rate: number
  }
}

export interface QAFailedPayload {
  type: 'qa.failed'
  error: {
    message: string
    type?: string
  }
}

export interface QAPingPayload {
  type: 'ping'
}

export type QAStreamEvent =
  | QAEntryStartedPayload
  | QAEntryCompletedPayload
  | QACompletedPayload
  | QAFailedPayload
  | QAPingPayload

export type QASessionStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface QASession {
  id: string
  project_id: string
  dataset_id: string
  graph_runner_id: string
  status: QASessionStatus
  total: number | null
  passed: number | null
  failed: number | null
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface QAAsyncRunResponse {
  session_id: string
  status: QASessionStatus
}
