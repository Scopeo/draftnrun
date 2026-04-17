/**
 * Graph execution stream WebSocket event payloads (server -> client).
 * Project-level channel: all run + node events for a project.
 * Each message is one JSON line (UTF-8). Parse with JSON.parse(payload) and switch on type.
 */

export interface RunActivePayload {
  type: 'run.active'
  run_id: string
  graph_runner_id: string | null
}

export interface GraphNodeStartedPayload {
  type: 'node.started'
  run_id: string
  node_id: string
}

export interface GraphNodeCompletedPayload {
  type: 'node.completed'
  run_id: string
  node_id: string
}

export interface GraphRunCompletedPayload {
  type: 'run.completed'
  run_id: string
  trace_id: string
  result_id: string | null
}

export interface GraphRunFailedPayload {
  type: 'run.failed'
  run_id: string
  error: {
    message: string
    type?: string
  }
}

export interface GraphExecutionPingPayload {
  type: 'ping'
}

export interface GraphExecutionErrorPayload {
  type: 'error'
  message: string
}

export type GraphExecutionEvent =
  | RunActivePayload
  | GraphNodeStartedPayload
  | GraphNodeCompletedPayload
  | GraphRunCompletedPayload
  | GraphRunFailedPayload
  | GraphExecutionPingPayload
  | GraphExecutionErrorPayload

export type NodeExecutionState = 'idle' | 'running' | 'completed' | 'failed'

export const GRAPH_EXECUTION_CLOSE_CODES = {
  UNAUTHORIZED: 4401,
  FORBIDDEN: 4403,
  PROJECT_NOT_FOUND: 4404,
  REDIS_UNAVAILABLE: 4510,
} as const

export function getGraphExecutionCloseMessage(code: number, reason?: string): string {
  switch (code) {
    case 4401:
      return 'Authentication failed or token missing.'
    case 4403:
      return "You don't have access to this project."
    case 4404:
      return 'Project not found.'
    case 4510:
      return 'Server temporarily unavailable (Redis).'
    default:
      return reason || `Connection closed (code ${code}).`
  }
}
