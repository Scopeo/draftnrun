import type { Ref } from 'vue'
import type { Agent } from '@/composables/queries/useAgentsQuery'
import { useRunStream } from '@/composables/useRunStream'
import type { ChatAsyncAccepted, ChatAsyncResult } from '@/api'
import { scopeoApi } from '@/api'

/** Extract displayable message from API result (various backend shapes) */
export function getResponseTextFromResult(result: Record<string, any>): string {
  return (
    result?.response ?? result?.message ?? result?.content ?? result?.output ?? result?.text ?? 'No response received'
  )
}

export interface StreamMetadata {
  artifacts?: any
  files?: any[]
  metadata?: {
    tokens?: number
    duration?: number
    status?: string
    project_id?: string
    trace_id?: string
  }
}

export interface PlaygroundChatRunContext {
  loadingMessageId: string
  startTime: number
  updateMessage: (id: string, patch: Record<string, unknown>) => void
  streamResponse: (id: string, text: string, metadata: StreamMetadata) => Promise<void>
  setTyping: (v: boolean) => void
  setError: (msg: string | null) => void
  ensureScrollToBottom: () => void
  setResponse: (result: Record<string, any> | undefined) => void
}

export interface PlaygroundChatRunOptions {
  onSyncSuccess?: () => Promise<void>
  isAsyncRunStream: Ref<boolean>
  runStreamCleanup: Ref<(() => void) | null>
}

/**
 * Resolve projectId and graphRunnerId for playground chat/run based on mode (agent vs workflow).
 */
export function resolvePlaygroundRunIds(
  mode: 'agent' | 'workflow',
  props: { projectId?: string; mode: string },
  agent: Ref<Agent | null>,
  currentGraphRunner: Ref<{ graph_runner_id: string } | null | undefined>
): { projectId: string; graphRunnerId: string } {
  let projectId: string
  if (mode === 'agent') {
    projectId = (props.projectId || agent.value?.project_id || '') as string
    if (!projectId)
      throw new Error(
        `Project ID not found. props.projectId: ${props.projectId}, agent.project_id: ${agent.value?.project_id}`
      )
  } else {
    if (!props.projectId) throw new Error('Project ID is required for workflow mode')
    projectId = props.projectId
  }
  const graphRunnerId = currentGraphRunner.value?.graph_runner_id
  if (!graphRunnerId) throw new Error('No graph runner selected. Please select a version.')
  return { projectId, graphRunnerId }
}

/**
 * Execute chat async API and handle both 202 (stream) and 200 (sync) responses.
 * Shared by sendMessage and replayFromMessage in SharedPlayground.
 */
export function usePlaygroundChatRun() {
  const { connect } = useRunStream()

  const executeChatRun = async (
    projectId: string,
    graphRunnerId: string,
    apiPayload: any,
    context: PlaygroundChatRunContext,
    options: PlaygroundChatRunOptions
  ): Promise<ChatAsyncAccepted | ChatAsyncResult> => {
    const {
      loadingMessageId,
      startTime,
      updateMessage,
      streamResponse,
      setTyping,
      setError,
      ensureScrollToBottom,
      setResponse,
    } = context

    const { onSyncSuccess, isAsyncRunStream, runStreamCleanup } = options

    const failStream = (error?: string) => {
      const errorMessage = error ?? 'Unknown error'

      runStreamCleanup.value?.()
      runStreamCleanup.value = null
      updateMessage(loadingMessageId, {
        content: errorMessage,
        isLoading: false,
        isError: true,
        metadata: { status: 'error' },
      })
      setError(errorMessage)
      ensureScrollToBottom()
      isAsyncRunStream.value = false
      setTyping(false)
    }

    const chatResponse = await scopeoApi.chat.chatAsync(projectId, graphRunnerId, apiPayload)

    if (chatResponse.accepted) {
      isAsyncRunStream.value = true
      runStreamCleanup.value = connect(chatResponse.run_id, {
        onNodeStarted: () => {
          updateMessage(loadingMessageId, { content: `Running step…`, isLoading: true })
        },
        onNodeCompleted: () => {
          updateMessage(loadingMessageId, { content: `Step done, continuing…`, isLoading: true })
        },
        onRunCompleted: async ({ trace_id, message: eventMessage, response: eventResponse }) => {
          runStreamCleanup.value?.()
          runStreamCleanup.value = null

          const runId = chatResponse.run_id
          let result: Record<string, any>
          try {
            result = await scopeoApi.runs.getResult(projectId, runId)
          } catch {
            result = {
              trace_id,
              response: eventResponse ?? eventMessage ?? 'No response received',
              message: eventMessage ?? eventResponse ?? 'No response received',
            }
          }
          setResponse(result)

          const responseText = getResponseTextFromResult(result)
          const duration = (Date.now() - startTime) / 1000

          await streamResponse(loadingMessageId, responseText, {
            artifacts: result.artifacts,
            files: result.files || [],
            metadata: {
              tokens: result.tokens || 0,
              duration,
              status: 'success',
              project_id: projectId,
              trace_id: result.trace_id ?? trace_id,
            },
          })
          if (onSyncSuccess) {
            try {
              await onSyncSuccess()
            } catch (err) {
              console.warn('⚠️ Failed to save chat to database:', err)
            }
          }
          isAsyncRunStream.value = false
          setTyping(false)
        },
        onRunFailed: ({ message, type }) => failStream(type ? `${type}: ${message}` : message),
        onError: message => failStream(message),
        onClose: (code, reason) => {
          if (code >= 4400 && code <= 4510) failStream(reason || `Connection closed (${code})`)
        },
        onReconnectFailed: () => failStream('Connection lost after multiple reconnect attempts'),
      })
      return chatResponse
    }

    const result = chatResponse.result
    const duration = (Date.now() - startTime) / 1000

    setResponse(result)

    const responseText = getResponseTextFromResult(result)

    await streamResponse(loadingMessageId, responseText, {
      artifacts: result.artifacts,
      files: result.files || [],
      metadata: {
        tokens: result.tokens || 0,
        duration,
        status: 'success',
        project_id: projectId,
        trace_id: result.trace_id || result.traceId,
      },
    })
    if (onSyncSuccess) {
      try {
        await onSyncSuccess()
      } catch (error) {
        console.warn('⚠️ Failed to save chat to database:', error)
      }
    }
    return chatResponse
  }

  return { executeChatRun }
}
