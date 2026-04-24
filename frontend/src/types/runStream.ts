/**
 * Run stream WebSocket event payloads (server → client only).
 * Each message is one JSON line (UTF-8). Parse with JSON.parse(payload) and switch on type.
 */

export interface NodeStartedPayload {
  type: 'node.started'
  node_id: string
}

export interface NodeCompletedPayload {
  type: 'node.completed'
  node_id: string
}

export interface RunCompletedPayload {
  type: 'run.completed'
  trace_id: string
  result_id: string | null
  /** Optional: message/response in the event so UI can show it without fetching by result_id */
  message?: string
  response?: string
}

export interface RunFailedPayload {
  type: 'run.failed'
  trace_id?: string
  error: {
    message: string
    type?: string
  }
}

export interface PingPayload {
  type: 'ping'
}

export interface ErrorPayload {
  type: 'error'
  message: string
}

export type RunStreamEvent =
  | NodeStartedPayload
  | NodeCompletedPayload
  | RunCompletedPayload
  | RunFailedPayload
  | PingPayload
  | ErrorPayload

/** Close codes from the server for error handling */
export const RUN_STREAM_CLOSE_CODES = {
  BOTH_AUTH_PROVIDED: 4400,
  UNAUTHORIZED: 4401,
  FORBIDDEN: 4403,
  RUN_NOT_FOUND: 4404,
  REDIS_UNAVAILABLE: 4510,
} as const

export function getRunStreamCloseMessage(code: number, reason?: string): string {
  switch (code) {
    case 4400:
      return 'Invalid request (token and API key both provided).'
    case 4401:
      return 'Authentication failed or token missing.'
    case 4403:
      return "You don't have access to this run's project."
    case 4404:
      return 'Run not found.'
    case 4510:
      return 'Server temporarily unavailable (Redis).'
    default:
      return reason || `Connection closed (code ${code}).`
  }
}
