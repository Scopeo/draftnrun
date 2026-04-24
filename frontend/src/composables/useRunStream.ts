import { useWebSocket } from '@vueuse/core'
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import type { RunStreamEvent } from '@/types/runStream'
import { getRunStreamCloseMessage } from '@/types/runStream'

function getWsBaseUrl(): string {
  const base = import.meta.env.VITE_SCOPEO_API_URL
  if (!base) return ''
  const cleaned = base.replace(/\/$/, '')
  if (cleaned.startsWith('https://')) return `wss://${cleaned.slice('https://'.length)}`
  if (cleaned.startsWith('http://')) return `ws://${cleaned.slice('http://'.length)}`
  return cleaned
}

export interface RunStreamCallbacks {
  onNodeStarted?: (nodeId: string) => void
  onNodeCompleted?: (nodeId: string) => void
  onRunCompleted?: (payload: {
    trace_id: string
    result_id: string | null
    message?: string
    response?: string
  }) => void
  onRunFailed?: (payload: { message: string; type?: string; trace_id?: string }) => void
  onError?: (message: string) => void
  onClose?: (code: number, reason: string) => void
  /** Called when autoReconnect exhausts all retries without a terminal run event. */
  onReconnectFailed?: () => void
}

/**
 * Composable for the run stream WebSocket (JWT-only auth).
 * Use from any feature that has a run_id: chat, workflow runs, cron, etc.
 * Call connect(runId, callbacks) after your async API returns 202 with run_id.
 * Returns a cleanup function to close the WebSocket (e.g. on unmount or when run completes).
 */
export function useRunStream() {
  const connect = (runId: string, callbacks: RunStreamCallbacks): (() => void) => {
    let closed = false
    let stop: (() => void) | null = null

    const close = () => {
      closed = true
      if (stop) {
        try {
          stop()
        } catch (error: unknown) {
          logger.warn('Failed to stop run stream', { error })
        }
        stop = null
      }
    }

    const run = async () => {
      if (closed) return

      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (closed) return

      const token = session?.access_token
      if (!token) {
        callbacks.onError?.('No authentication token found')
        callbacks.onClose?.(4401, getRunStreamCloseMessage(4401))
        return
      }

      const wsBaseUrl = getWsBaseUrl()
      if (!wsBaseUrl) {
        callbacks.onError?.('WebSocket API URL not configured')
        return
      }

      if (closed) return

      const url = `${wsBaseUrl}/ws/runs/${runId}?token=${encodeURIComponent(token)}`

      const { close: wsClose } = useWebSocket(url, {
        autoReconnect: {
          retries: 5,
          delay: 2000,
          onFailed() {
            if (closed) return
            callbacks.onReconnectFailed?.()
          },
        },
        heartbeat: {
          message: 'ping',
          interval: 25_000,
          pongTimeout: 10_000,
        },
        onMessage(_ws: WebSocket, event: MessageEvent) {
          if (closed) return
          try {
            const payload = JSON.parse(event.data as string) as RunStreamEvent
            switch (payload.type) {
              case 'node.started':
                callbacks.onNodeStarted?.(payload.node_id)
                break
              case 'node.completed':
                callbacks.onNodeCompleted?.(payload.node_id)
                break
              case 'run.completed':
                callbacks.onRunCompleted?.({
                  trace_id: payload.trace_id,
                  result_id: payload.result_id ?? null,
                  message: payload.message,
                  response: payload.response,
                })
                close()
                break
              case 'run.failed':
                callbacks.onRunFailed?.({
                  message: payload.error.message,
                  type: payload.error.type,
                  trace_id: payload.trace_id,
                })
                close()
                break
              case 'ping':
                // keep-alive; no action required
                break
              case 'error':
                callbacks.onError?.(payload.message)
                close()
                break
              default:
                // unknown type, ignore
                break
            }
          } catch (e) {
            callbacks.onError?.(e instanceof Error ? e.message : 'Failed to parse run stream message')
          }
        },
        onDisconnected(_ws: WebSocket, event: CloseEvent) {
          if (closed) return
          const message = getRunStreamCloseMessage(event.code, event.reason)

          callbacks.onClose?.(event.code, message)
        },
        onError() {
          if (closed) return
          callbacks.onError?.('WebSocket connection error')
        },
      })

      if (closed) {
        wsClose()
        return
      }

      stop = () => {
        wsClose()
      }
    }

    run()
    return close
  }

  return { connect }
}
