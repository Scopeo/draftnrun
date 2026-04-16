import { ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import type { ChatMessage } from '@/composables/useChatHistory'
import { usePlaygroundChat } from '@/composables/usePlaygroundChat'
import { type StreamMetadata, resolvePlaygroundRunIds, usePlaygroundChatRun } from '@/composables/usePlaygroundChatRun'
import { formatContentWithFile, readFileContent, type usePlaygroundFiles } from '@/composables/usePlaygroundFiles'
import type { Agent } from '@/composables/queries/useAgentsQuery'

interface ChatMessagesExpose {
  scrollTo: (options: ScrollToOptions) => void
  scrollHeight: number
  cancelEditing: () => void
}

export interface ChatOps {
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => ChatMessage
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void
  setTyping: (v: boolean) => void
  setError: (msg: string | null) => void
  initializeNewChat: () => string
  createNewChat: () => Promise<string | undefined>
  getCurrentChatId: () => string | null
  clearChat: () => void
  removeMessagesAfterIndex: (idx: number) => void
}

export interface MessagingDeps {
  props: { mode: 'agent' | 'workflow'; projectId?: string }
  chatMessages: Ref<ChatMessage[]>
  isTyping: Ref<boolean>
  newMessage: Ref<string>
  messagesContainer: Ref<ChatMessagesExpose | null>
  response: Ref<any>
  runStreamCleanup: Ref<(() => void) | null>
  isAsyncRunStream: Ref<boolean>
  agent: Ref<Agent | null>
  currentGraphRunner: ComputedRef<any>
  hasCustomFields: ComputedRef<boolean>
  customFieldsData: Ref<Record<string, any>>
  playgroundConfig: Ref<any>
  selectedSetIds: Ref<string[]>
  files: ReturnType<typeof usePlaygroundFiles>
  chatOps: ChatOps
  loadAgent: () => Promise<void>
  ensureScrollToBottom: () => void
  scrollToBottom: () => void
}

const inputHistoryMap = new Map<string, string[]>()
const MAX_HISTORY = 50

export function usePlaygroundMessaging(deps: MessagingDeps) {
  const { notify } = useNotifications()
  const { executeChatRun } = usePlaygroundChatRun()
  const isStreaming = ref(false)

  const {
    props,
    chatMessages,
    isTyping,
    newMessage,
    messagesContainer,
    response,
    runStreamCleanup,
    isAsyncRunStream,
    agent,
    currentGraphRunner,
    hasCustomFields,
    customFieldsData,
    playgroundConfig,
    selectedSetIds,
    files,
    chatOps,
    loadAgent,
    ensureScrollToBottom,
    scrollToBottom,
  } = deps

  // --- Streaming ---
  const streamResponse = async (messageId: string, fullText: string, metadata: StreamMetadata) => {
    isStreaming.value = true
    try {
      if (!fullText.length) {
        chatOps.updateMessage(messageId, {
          content: fullText,
          isLoading: false,
          ...metadata,
        })
        return
      }
      const MAX_MS = 3000
      const PER_CHAR = 2
      const delay = Math.min(PER_CHAR, MAX_MS / fullText.length)
      const chunkSize = Math.max(1, Math.floor(30 / delay))
      const chunkDelay = delay * chunkSize
      let idx = 0
      let text = ''

      while (idx < fullText.length) {
        const next = Math.min(idx + chunkSize, fullText.length)

        text += fullText.slice(idx, next)
        chatOps.updateMessage(messageId, { content: text, isLoading: false })
        idx = next
        if (idx % (chunkSize * 5) === 0) scrollToBottom()
        await new Promise(resolve => setTimeout(resolve, chunkDelay))
      }

      chatOps.updateMessage(messageId, {
        content: fullText,
        isLoading: false,
        ...metadata,
      })
      ensureScrollToBottom()
    } finally {
      isStreaming.value = false
    }
  }

  // --- Payload helpers ---
  function buildConversationMessages(
    messages: ChatMessage[],
    endIndex?: number,
    currentUserText?: string,
    currentContent?: any
  ) {
    const slice = endIndex !== undefined ? messages.slice(0, endIndex + 1) : messages
    return slice
      .filter((m: any) => !m.isLoading && !m.isError)
      .map((m: any) => {
        let content = m.content
        if (m.files?.length) {
          const f = m.files[0]

          content = formatContentWithFile(m.content, f.data, f.filename)
        }
        if (currentUserText && m.role === 'user' && m.content === currentUserText && currentContent) {
          content = currentContent
        }
        return { role: m.role, content }
      })
  }

  function buildApiPayload(conversationMessages: any[], chatId: string | null) {
    const payload: any = {
      messages: conversationMessages,
      conversation_id: chatId,
    }

    const fieldTypes = playgroundConfig.value?.playground_field_types
    if (hasCustomFields.value && fieldTypes) {
      for (const [name, type] of Object.entries(fieldTypes)) {
        if (name === 'messages' || name === 'conversation_id') continue
        let val = customFieldsData.value[name]
        if (type === 'json' && typeof val === 'string') {
          try {
            val = JSON.parse(val)
          } catch {
            /* keep string */
          }
        }
        payload[name] = val
      }
    }
    if (selectedSetIds.value.length) payload.set_ids = selectedSetIds.value
    return payload
  }

  async function executeRun(
    conversationMessages: any[],
    loadingMessageId: string,
    opts?: { onSyncSuccess?: () => Promise<void> }
  ) {
    const startTime = Date.now()
    const { projectId, graphRunnerId } = resolvePlaygroundRunIds(props.mode, props, agent, currentGraphRunner)
    const payload = buildApiPayload(conversationMessages, chatOps.getCurrentChatId())

    await executeChatRun(
      projectId,
      graphRunnerId,
      payload,
      {
        loadingMessageId,
        startTime,
        updateMessage: chatOps.updateMessage,
        streamResponse,
        setTyping: chatOps.setTyping,
        setError: chatOps.setError,
        ensureScrollToBottom,
        setResponse: r => {
          response.value = r
        },
      },
      {
        onSyncSuccess: opts?.onSyncSuccess,
        isAsyncRunStream,
        runStreamCleanup,
      }
    )
  }

  // --- Send message ---
  const sendMessage = async () => {
    if (!newMessage.value.trim()) return
    messagesContainer.value?.cancelEditing?.()

    const text = newMessage.value
    const pid = props.projectId
    if (pid) {
      const h = inputHistoryMap.get(pid) || []
      if (h[h.length - 1] !== text) {
        h.push(text)
        if (h.length > MAX_HISTORY) h.shift()
      }
      inputHistoryMap.set(pid, h)
    }
    historyIndex.value = -1
    newMessage.value = ''

    if (props.mode === 'agent' && !agent.value) await loadAgent()
    if (!chatOps.getCurrentChatId()) chatOps.initializeNewChat()

    let filesMetadata: any[] | undefined
    if (files.uploadedFiles.value.length > 0) {
      try {
        filesMetadata = await Promise.all(
          files.uploadedFiles.value.map(async f => {
            const info = await readFileContent(f)
            return {
              filename: f.name,
              content_type: f.type,
              size: f.size,
              data: info.fileData,
            }
          })
        )
      } catch (error: unknown) {
        notify.warning(`Failed to process file for replay: ${error instanceof Error ? error.message : 'Unknown error'}`)
      }
    }

    chatOps.addMessage({ role: 'user', content: text, files: filesMetadata })
    ensureScrollToBottom()

    let messageContent: any = text
    if (files.uploadedFiles.value.length > 0) {
      try {
        const info = await readFileContent(files.uploadedFiles.value[0])

        messageContent = formatContentWithFile(text, info.fileData, info.filename)
      } catch (error) {
        logger.error('Error reading file for message', { error })
      }
    }

    const msgs = buildConversationMessages(chatMessages.value, undefined, text, messageContent)

    const loading = chatOps.addMessage({
      role: 'assistant',
      content: '',
      isLoading: true,
    })

    ensureScrollToBottom()

    try {
      chatOps.setTyping(true)
      chatOps.setError(null)
      await executeRun(msgs, loading.id, {
        onSyncSuccess: async () => {
          if (chatMessages.value.length === 2) await chatOps.createNewChat()
        },
      })
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : `Failed to get response from ${props.mode}`

      logger.error(`${props.mode} API call failed`, { error })
      chatOps.updateMessage(loading.id, {
        content: `Error: ${msg}`,
        isLoading: false,
        isError: true,
        metadata: { status: 'error', error: msg },
      })
      chatOps.setError(msg)
      ensureScrollToBottom()
    } finally {
      if (!isAsyncRunStream.value) chatOps.setTyping(false)
      files.uploadedFiles.value = []

      if (chatOps.getCurrentChatId() && props.projectId) {
        setTimeout(async () => {
          if (chatOps.getCurrentChatId?.() && props.projectId) {
            const { saveChatToHistory } = usePlaygroundChat(props.projectId, true)

            await saveChatToHistory()
          }
        }, 1000)
      }
    }
  }

  // --- Replay ---
  const replayFromMessage = async (startIndex: number) => {
    const userMsg = chatMessages.value[startIndex]
    if (!userMsg || userMsg.role !== 'user') return

    const loading = chatOps.addMessage({
      role: 'assistant',
      content: '',
      isLoading: true,
    })

    ensureScrollToBottom()

    const msgs = buildConversationMessages(chatMessages.value, startIndex)

    try {
      chatOps.setTyping(true)
      chatOps.setError(null)
      await executeRun(msgs, loading.id)
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : `Failed to replay message from ${props.mode}`

      logger.error(`${props.mode} API call failed during replay`, { error })
      chatOps.updateMessage(loading.id, {
        content: `Error: ${msg}`,
        isLoading: false,
        isError: true,
        metadata: { status: 'error', error: msg },
      })
      chatOps.setError(msg)
      ensureScrollToBottom()
    } finally {
      if (!isAsyncRunStream.value) chatOps.setTyping(false)
      ensureScrollToBottom()
    }
  }

  const handleMessageEdit = async (newContent: string, idx: number) => {
    if (isTyping.value || isStreaming.value) return
    const msg = chatMessages.value[idx]
    if (!msg || msg.role !== 'user') return
    chatOps.updateMessage(msg.id, {
      content: newContent,
      timestamp: new Date().toISOString(),
    })
    chatOps.removeMessagesAfterIndex(idx)
    await replayFromMessage(idx)
  }

  const handleMessageReplay = async (idx: number) => {
    if (isTyping.value || isStreaming.value) return
    const msg = chatMessages.value[idx]
    if (!msg || msg.role !== 'user') return
    chatOps.updateMessage(msg.id, { timestamp: new Date().toISOString() })
    chatOps.removeMessagesAfterIndex(idx)
    await replayFromMessage(idx)
  }

  // --- Keyboard ---
  const historyIndex = ref(-1)

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!isTyping.value && !isStreaming.value) sendMessage()
      return
    }
    const pid = props.projectId
    if (!pid) return
    const history = inputHistoryMap.get(pid) || []
    if (event.key === 'ArrowUp' && !newMessage.value.trim()) {
      event.preventDefault()
      if (history.length) {
        historyIndex.value = Math.min(historyIndex.value + 1, history.length - 1)
        newMessage.value = history[history.length - 1 - historyIndex.value] || ''
      }
    }
    if (event.key === 'ArrowDown' && historyIndex.value >= 0) {
      event.preventDefault()
      historyIndex.value--
      newMessage.value = historyIndex.value < 0 ? '' : history[history.length - 1 - historyIndex.value] || ''
    }
  }

  // --- Clear ---
  const clearChatHandler = () => {
    messagesContainer.value?.cancelEditing?.()
    chatOps.clearChat()
    newMessage.value = ''
    files.uploadedFiles.value = []
    response.value = undefined
    chatOps.initializeNewChat()
  }

  return {
    isStreaming,
    sendMessage,
    replayFromMessage,
    handleMessageEdit,
    handleMessageReplay,
    handleKeyDown,
    clearChatHandler,
  }
}
