import { useWebSocket } from '@vueuse/core'
import { type InjectionKey, type Ref, computed, onUnmounted, provide, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import { getApiBaseUrl } from '@/utils/api'
import type {
  GraphExecutionEvent,
  NodeExecutionState,
} from '@/types/graphExecutionStream'
import { getGraphExecutionCloseMessage } from '@/types/graphExecutionStream'

function getWsBaseUrl(): string {
  const base = getApiBaseUrl()
  if (!base) return ''
  if (base.startsWith('https://')) return `wss://${base.slice('https://'.length)}`
  if (base.startsWith('http://')) return `ws://${base.slice('http://'.length)}`
  return base
}

export interface ActiveRunInfo {
  runId: string
  graphRunnerId: string | null
}

export const GRAPH_EXECUTION_KEY: InjectionKey<{
  nodeStates: Ref<Map<string, NodeExecutionState>>
  activeRun: Ref<ActiveRunInfo | null>
  isConnected: Ref<boolean>
}> = Symbol('graphExecution')

const CLEAR_DELAY_MS = 3000

/**
 * Composable for project-level graph execution streaming.
 * Connects to WS /ws/projects/{projectId}/graph-execution and maintains
 * reactive node execution states for the graph overlay.
 */
export function useGraphExecutionStream(projectId: Ref<string>) {
  const nodeStates = ref<Map<string, NodeExecutionState>>(new Map())
  const activeRun = ref<ActiveRunInfo | null>(null)
  const isConnected = ref(false)

  let wsClose: (() => void) | null = null
  let clearTimer: ReturnType<typeof setTimeout> | null = null

  const hasActiveRun = computed(() => activeRun.value !== null)

  function clear() {
    nodeStates.value = new Map()
    activeRun.value = null
    if (clearTimer) {
      clearTimeout(clearTimer)
      clearTimer = null
    }
  }

  function scheduleClear() {
    if (clearTimer) clearTimeout(clearTimer)
    clearTimer = setTimeout(clear, CLEAR_DELAY_MS)
  }

  function handleEvent(payload: GraphExecutionEvent) {
    switch (payload.type) {
      case 'run.active': {
        if (clearTimer) {
          clearTimeout(clearTimer)
          clearTimer = null
        }
        activeRun.value = {
          runId: payload.run_id,
          graphRunnerId: payload.graph_runner_id,
        }
        nodeStates.value = new Map()
        break
      }
      case 'node.started': {
        if (!activeRun.value || activeRun.value.runId !== payload.run_id) break
        const next = new Map(nodeStates.value)
        next.set(payload.node_id, 'running')
        nodeStates.value = next
        break
      }
      case 'node.completed': {
        if (!activeRun.value || activeRun.value.runId !== payload.run_id) break
        const next = new Map(nodeStates.value)
        next.set(payload.node_id, 'completed')
        nodeStates.value = next
        break
      }
      case 'run.completed': {
        if (!activeRun.value || activeRun.value.runId !== payload.run_id) break
        scheduleClear()
        break
      }
      case 'run.failed': {
        if (!activeRun.value || activeRun.value.runId !== payload.run_id) break
        const next = new Map(nodeStates.value)
        for (const [nodeId, state] of next) {
          if (state === 'running') next.set(nodeId, 'failed')
        }
        nodeStates.value = next
        scheduleClear()
        break
      }
      case 'ping':
      case 'error':
        break
    }
  }

  async function connect() {
    disconnect()

    const {
      data: { session },
    } = await supabase.auth.getSession()

    const token = session?.access_token
    if (!token) {
      logger.warn('Graph execution stream: no auth token')
      return
    }

    const wsBaseUrl = getWsBaseUrl()
    if (!wsBaseUrl) {
      logger.warn('Graph execution stream: no WS base URL')
      return
    }

    const url = `${wsBaseUrl}/ws/projects/${projectId.value}/graph-execution?token=${encodeURIComponent(token)}`

    const { close } = useWebSocket(url, {
      autoReconnect: {
        retries: 5,
        delay: 2000,
        onFailed() {
          isConnected.value = false
          logger.warn('Graph execution stream: reconnect failed after 5 retries')
        },
      },
      heartbeat: {
        message: 'ping',
        interval: 25_000,
        pongTimeout: 10_000,
      },
      onConnected() {
        isConnected.value = true
      },
      onMessage(_ws: WebSocket, event: MessageEvent) {
        try {
          const payload = JSON.parse(event.data as string) as GraphExecutionEvent
          handleEvent(payload)
        } catch (e) {
          logger.warn('Graph execution stream: failed to parse message', { error: e })
        }
      },
      onDisconnected(_ws: WebSocket, event: CloseEvent) {
        isConnected.value = false
        if (event.code >= 4400 && event.code <= 4510) {
          logger.warn('Graph execution stream closed', {
            code: event.code,
            reason: getGraphExecutionCloseMessage(event.code, event.reason),
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
        logger.warn('Graph execution stream: failed to close', { error: e })
      }
      wsClose = null
    }
    isConnected.value = false
  }

  watch(
    projectId,
    (newId: string, oldId: string | undefined) => {
      if (newId && newId !== oldId) {
        clear()
        connect()
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    disconnect()
    if (clearTimer) clearTimeout(clearTimer)
  })

  provide(GRAPH_EXECUTION_KEY, { nodeStates, activeRun, isConnected })

  return {
    nodeStates,
    activeRun,
    hasActiveRun,
    isConnected,
    clear,
  }
}
