import { useWebSocket } from '@vueuse/core'
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import type { QAStreamEvent } from '@/types/qaStream'

function getWsBaseUrl(): string {
  const base = import.meta.env.VITE_SCOPEO_API_URL
  if (!base) return ''
  const cleaned = base.replace(/\/$/, '')
  if (cleaned.startsWith('https://')) return `wss://${cleaned.slice('https://'.length)}`
  if (cleaned.startsWith('http://')) return `ws://${cleaned.slice('http://'.length)}`
  return cleaned
}

export interface QARunStreamCallbacks {
  onEntryStarted?: (inputId: string, index: number, total: number) => void
  onEntryCompleted?: (inputId: string, output: string, success: boolean, error: string | null) => void
  onCompleted?: (summary: { total: number; passed: number; failed: number; success_rate: number }) => void
  onFailed?: (error: { message: string; type?: string }) => void
  onError?: (message: string) => void
  onClose?: (code: number, reason: string) => void
  onReconnectFailed?: () => void
}

/**
 * Composable for the QA run stream WebSocket.
 * Call connect(projectId, sessionId, callbacks) after your async POST returns 202 with session_id.
 * Returns a cleanup function to close the WebSocket.
 */
export function useQARunStream() {
  const connect = (projectId: string, sessionId: string, callbacks: QARunStreamCallbacks): (() => void) => {
    let closed = false
    let stop: (() => void) | null = null

    const close = () => {
      closed = true
      if (stop) {
        try {
          stop()
        } catch (error: unknown) {
          logger.warn('Failed to stop QA run stream', { error })
        }
        stop = null
      }
    }

    const openConnection = async () => {
      if (closed) return

      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (closed) return

      const token = session?.access_token
      if (!token) {
        callbacks.onError?.('No authentication token found')
        return
      }

      const wsBaseUrl = getWsBaseUrl()
      if (!wsBaseUrl) {
        callbacks.onError?.('WebSocket API URL not configured')
        return
      }

      if (closed) return

      const url = `${wsBaseUrl}/ws/qa/${projectId}/${sessionId}?token=${encodeURIComponent(token)}`

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
            const payload = JSON.parse(event.data as string) as QAStreamEvent
            switch (payload.type) {
              case 'qa.entry.started':
                callbacks.onEntryStarted?.(payload.input_id, payload.index, payload.total)
                break
              case 'qa.entry.completed':
                callbacks.onEntryCompleted?.(payload.input_id, payload.output, payload.success, payload.error)
                break
              case 'qa.completed':
                callbacks.onCompleted?.(payload.summary)
                close()
                break
              case 'qa.failed':
                callbacks.onFailed?.(payload.error)
                close()
                break
              case 'ping':
                break
              default:
                break
            }
          } catch (e) {
            callbacks.onError?.(e instanceof Error ? e.message : 'Failed to parse QA stream message')
          }
        },
        onDisconnected(_ws: WebSocket, event: CloseEvent) {
          if (closed) return
          callbacks.onClose?.(event.code, event.reason || `Connection closed (code ${event.code}).`)
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

    openConnection()
    return close
  }

  return { connect }
}
