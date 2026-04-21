import { useWebSocket } from '@vueuse/core'
import { type Ref, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import { getApiBaseUrl } from '@/utils/api'
import type { GraphDisplayEvent } from '@/types/graphDisplayStream'
import { getGraphDisplayCloseMessage } from '@/types/graphDisplayStream'

function getWsBaseUrl(): string {
  const base = getApiBaseUrl()
  if (!base) return ''
  if (base.startsWith('https://')) return `wss://${base.slice('https://'.length)}`
  if (base.startsWith('http://')) return `ws://${base.slice('http://'.length)}`
  return base
}

const RELOAD_DEBOUNCE_MS = 500

export function useGraphDisplayStream(
  projectId: Ref<string>,
  reloadGraph: () => Promise<void> | void,
  hasUnsavedChanges: Ref<boolean>,
) {
  const isWsEnabled = import.meta.env.VITE_RUN_ASYNC_CREDENTIALS === 'true'
  const isConnected = ref(false)
  const wsDisconnected = ref(!isWsEnabled)
  const refreshing = ref(false)
  let wsClose: (() => void) | null = null
  let reloadTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleReload() {
    if (reloadTimer) clearTimeout(reloadTimer)
    reloadTimer = setTimeout(() => {
      reloadTimer = null
      if (hasUnsavedChanges.value) {
        logger.info('Graph display stream: skipping reload — unsaved local changes')
        return
      }
      reloadGraph()
    }, RELOAD_DEBOUNCE_MS)
  }

  function handleEvent(payload: GraphDisplayEvent) {
    switch (payload.type) {
      case 'graph.changed':
        scheduleReload()
        break
      case 'ping':
      case 'pong':
      case 'error':
        break
    }
  }

  async function connect() {
    disconnect()
    wsDisconnected.value = false

    const {
      data: { session },
    } = await supabase.auth.getSession()

    const token = session?.access_token
    if (!token) {
      logger.warn('Graph display stream: no auth token')
      wsDisconnected.value = true
      return
    }

    const wsBaseUrl = getWsBaseUrl()
    if (!wsBaseUrl) {
      logger.warn('Graph display stream: no WS base URL')
      wsDisconnected.value = true
      return
    }

    const url = `${wsBaseUrl}/ws/projects/${projectId.value}/graph-updates?token=${encodeURIComponent(token)}`

    const { close } = useWebSocket(url, {
      autoReconnect: {
        retries: 5,
        delay: 2000,
        onFailed() {
          isConnected.value = false
          wsDisconnected.value = true
          logger.warn('Graph display stream: reconnect failed after 5 retries')
        },
      },
      heartbeat: {
        message: 'ping',
        interval: 25_000,
        pongTimeout: 30_000,
      },
      onConnected() {
        isConnected.value = true
        wsDisconnected.value = false
      },
      onMessage(_ws: WebSocket, event: MessageEvent) {
        try {
          const payload = JSON.parse(event.data as string) as GraphDisplayEvent
          handleEvent(payload)
        } catch (e) {
          logger.warn('Graph display stream: failed to parse message', { error: e })
        }
      },
      onDisconnected(_ws: WebSocket, event: CloseEvent) {
        isConnected.value = false
        if (event.code >= 4400 && event.code <= 4510) {
          logger.warn('Graph display stream closed', {
            code: event.code,
            reason: getGraphDisplayCloseMessage(event.code, event.reason),
          })
        }
      },
      onError() {
        isConnected.value = false
      },
    })

    wsClose = close
  }

  function disconnect() {
    if (wsClose) {
      try {
        wsClose()
      } catch (e) {
        logger.warn('Graph display stream: failed to close', { error: e })
      }
      wsClose = null
    }
    isConnected.value = false
  }

  async function manualRefresh() {
    refreshing.value = true
    try {
      await reloadGraph()
    } catch (e) {
      logger.error('Graph display stream: manual refresh failed', { error: e })
    } finally {
      refreshing.value = false
    }
  }

  if (isWsEnabled) {
    watch(
      projectId,
      (newId: string, oldId: string | undefined) => {
        if (newId && newId !== oldId) {
          connect()
        }
      },
      { immediate: true },
    )

    onUnmounted(() => {
      disconnect()
      if (reloadTimer) clearTimeout(reloadTimer)
    })
  }

  return { isConnected, wsDisconnected, refreshing, manualRefresh }
}
