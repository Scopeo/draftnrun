export interface GraphChangedPayload {
  type: 'graph.changed'
  graph_runner_id: string
  action: string
}

export interface GraphDisplayPingPayload {
  type: 'ping'
}

export interface GraphDisplayPongPayload {
  type: 'pong'
}

export interface GraphDisplayErrorPayload {
  type: 'error'
  message: string
}

export type GraphDisplayEvent =
  | GraphChangedPayload
  | GraphDisplayPingPayload
  | GraphDisplayPongPayload
  | GraphDisplayErrorPayload

export const GRAPH_DISPLAY_CLOSE_CODES = {
  UNAUTHORIZED: 4401,
  FORBIDDEN: 4403,
  PROJECT_NOT_FOUND: 4404,
  REDIS_UNAVAILABLE: 4510,
} as const

export function getGraphDisplayCloseMessage(code: number, reason?: string): string {
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
