import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import { type Agent, useCurrentAgent } from '@/composables/queries/useAgentsQuery'
import { useCurrentProject } from '@/composables/queries/useProjectsQuery'
import { useSetIdsQuery } from '@/composables/queries/useVariableSetsQuery'
import type { ChatMessage } from '@/composables/useChatHistory'
import { usePlaygroundChat } from '@/composables/usePlaygroundChat'
import { useSaveToQA } from '@/composables/useSaveToQA'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { usePlaygroundFiles } from '@/composables/usePlaygroundFiles'
import { type ChatOps, usePlaygroundMessaging } from '@/composables/usePlaygroundMessaging'
import { scopeoApi } from '@/api'
import type { TraceData } from '@/types/observability'
import { findDraftGraphRunner } from '@/utils/agentUtils'
import { supabase } from '@/services/auth'

interface ChatMessagesExpose {
  scrollTo: (options: ScrollToOptions) => void
  scrollHeight: number
  cancelEditing: () => void
}

const CHAT_HISTORY_ENABLED = import.meta.env.VITE_ENABLE_CHAT_HISTORY === 'true'

export function usePlaygroundSession(props: {
  agentId?: string
  projectId?: string
  mode: 'agent' | 'workflow'
  title?: string
}) {
  const { notify } = useNotifications()
  const route = useRoute()
  const { selectedOrgId } = useSelectedOrg()
  const files = usePlaygroundFiles()

  const { currentGraphRunner: agentGraphRunner } = useCurrentAgent()
  const { currentProject, currentGraphRunner: projectGraphRunner, playgroundConfig } = useCurrentProject()

  // --- Variable sets ---
  const projectIdRef = computed(() => props.projectId)

  const {
    data: setIdsData,
    isLoading: isSetIdsLoading,
    isError: isSetIdsError,
  } = useSetIdsQuery(selectedOrgId, projectIdRef)

  const availableSetIds = computed(() => setIdsData.value?.set_ids ?? [])
  const selectedSetIds = ref<string[]>([])
  const showSetIdsSelector = computed(() => availableSetIds.value.length > 0)

  watch([selectedOrgId, projectIdRef], () => {
    selectedSetIds.value = []
  })
  watch(
    availableSetIds,
    next => {
      if (!selectedSetIds.value.length) return
      const allowed = new Set(next)
      const clamped = selectedSetIds.value.filter(id => allowed.has(id))
      if (clamped.length !== selectedSetIds.value.length) selectedSetIds.value = clamped
    },
    { immediate: true }
  )

  // --- Custom fields ---
  const customFieldsData = ref<Record<string, any>>({})
  const expandedFields = ref<number[]>([0])

  const hasCustomFields = computed(
    () =>
      props.mode === 'workflow' &&
      !!playgroundConfig.value?.playground_field_types &&
      Object.keys(playgroundConfig.value.playground_field_types).length > 0
  )

  const hasAdditionalFields = computed(() => {
    if (!hasCustomFields.value || !playgroundConfig.value?.playground_field_types) return false
    const names = Object.keys(playgroundConfig.value.playground_field_types)
    return names.length > 1 || (names.length === 1 && names[0] !== 'messages')
  })

  // --- Agent ---
  const agent = ref<Agent | null>(null)

  const currentGraphRunner = computed(() =>
    props.mode === 'agent' ? agentGraphRunner.value : projectGraphRunner.value
  )

  const getAgentById = async (agentId: string): Promise<Agent | null> => {
    try {
      const orgId = selectedOrgId.value || currentProject.value?.organization_id
      if (!orgId) return null
      const agents = await scopeoApi.agents.getAll(orgId)
      const info = agents?.find((a: any) => a.id === agentId)
      if (!info?.graph_runners?.length) return null
      const draft = findDraftGraphRunner(info.graph_runners)
      if (!draft) return null
      return (await scopeoApi.agents.getById(agentId, draft.graph_runner_id)) as Agent
    } catch (e) {
      logger.error('Error fetching agent', { error: e })
      return null
    }
  }

  const loadAgent = async () => {
    if (props.mode !== 'agent' || !props.agentId) return
    try {
      agent.value = await getAgentById(props.agentId)
    } catch (error) {
      logger.error('Failed to load agent', { error })
    }
  }

  // --- Chat state ---
  type PlaygroundChatState = ReturnType<typeof usePlaygroundChat>

  const chatMessages = ref<ChatMessage[]>([])
  const isTyping = ref(false)
  const newMessage = ref('')
  const messagesContainer = ref<ChatMessagesExpose | null>(null)
  const response = ref<any>()
  const runStreamCleanup = ref<(() => void) | null>(null)
  const isAsyncRunStream = ref(false)

  const chatOps: ChatOps = {
    addMessage: msg => ({
      id: `tmp_${crypto.randomUUID()}`,
      timestamp: new Date().toISOString(),
      ...msg,
    }),
    updateMessage: () => {},
    setTyping: v => {
      isTyping.value = v
    },
    setError: () => {},
    initializeNewChat: () => '',
    createNewChat: async () => undefined,
    getCurrentChatId: () => null,
    clearChat: () => {
      chatMessages.value.splice(0, chatMessages.value.length)
    },
    removeMessagesAfterIndex: () => {},
  }

  const bindChatState = (entityId: string) => {
    const s = usePlaygroundChat(entityId, CHAT_HISTORY_ENABLED)

    chatMessages.value = s.messages
    isTyping.value = s.isTyping
    chatOps.addMessage = s.addMessage
    chatOps.updateMessage = s.updateMessage
    chatOps.setTyping = v => {
      s.setTyping(v)
      isTyping.value = v
    }
    chatOps.setError = s.setError
    chatOps.initializeNewChat = s.initializeNewChat
    chatOps.createNewChat = s.createNewChat
    chatOps.getCurrentChatId = s.getCurrentChatId
    chatOps.clearChat = s.clearChat
    chatOps.removeMessagesAfterIndex = s.removeMessagesAfterIndex
  }

  // --- Scroll ---
  const scrollToBottom = () => {
    messagesContainer.value?.scrollTo({
      top: messagesContainer.value.scrollHeight,
      behavior: 'smooth',
    })
  }

  const ensureScrollToBottom = () => {
    nextTick(() => {
      scrollToBottom()
      setTimeout(scrollToBottom, 100)
    })
  }

  watch(chatMessages, ensureScrollToBottom, { deep: true })

  // --- Messaging (send, replay, keyboard, clear) ---
  const messaging = usePlaygroundMessaging({
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
  })

  // --- Display ---
  const displayTitle = computed(() => {
    if (props.title) return props.title
    return props.mode === 'agent' ? agent.value?.name || 'Agent Chat' : 'Chat'
  })

  // --- File click (resolves project/org context) ---
  const onFileClick = (file: any) => {
    let pid: string
    if (props.mode === 'agent') {
      pid = (props.projectId || agent.value?.project_id || '') as string
      if (!pid) {
        notify.error('Project ID not found')
        return
      }
    } else {
      if (!props.projectId) {
        notify.error('Project ID is required')
        return
      }
      pid = props.projectId
    }
    files.handleResponseFileClick(file, pid, currentProject.value?.organization_id)
  }

  // --- QA ---
  const messageToSave = ref<{ message: any; index: number } | null>(null)

  const qa = useSaveToQA({
    orgId: selectedOrgId,
    projectId: projectIdRef,
    getConversationData: () => {
      if (!messageToSave.value) return null
      const { message, index } = messageToSave.value
      let traceId: string | undefined
      if (message.role === 'user') {
        const next = chatMessages.value[index + 1]
        if (next?.role === 'assistant') traceId = (next as any).metadata?.trace_id || (next as any).trace_id
      } else {
        traceId = (message as any).metadata?.trace_id || (message as any).trace_id
      }
      if (!traceId) return null
      return { traceId }
    },
  })

  const openSaveModeDialog = (message: any, index: number) => {
    messageToSave.value = { message, index }
    qa.openSaveDialog()
  }

  // --- Trace loading ---
  const showClearChatConfirm = ref(false)
  const pendingTraceData = ref<TraceData | null>(null)
  const isLoadingTrace = ref(false)

  const doLoadTrace = async (traceData: TraceData) => {
    try {
      chatOps.clearChat()
      chatOps.initializeNewChat()

      const history: Array<{ role: 'user' | 'assistant'; content: string }> = []
      let lastUserMessage = ''
      const extractedFields: Record<string, any> = {}
      const spanInput = traceData.span.input
      if (!spanInput || !Array.isArray(spanInput)) return

      for (const item of spanInput) {
        if (typeof item === 'string') {
          lastUserMessage = item
        } else if (typeof item === 'object') {
          if (Array.isArray(item.messages)) {
            for (const msg of item.messages) {
              if (msg.role === 'user' || msg.role === 'assistant')
                history.push({ role: msg.role, content: msg.content || '' })
            }
            const userMsgs = item.messages.filter((m: any) => m.role === 'user')
            if (userMsgs.length) lastUserMessage = userMsgs[userMsgs.length - 1].content || ''
          }
          for (const key of Object.keys(item)) {
            if (key !== 'messages' && key !== 'conversation_id') extractedFields[key] = item[key]
          }
        }
      }

      if (hasCustomFields.value) {
        for (const k of Object.keys(customFieldsData.value)) customFieldsData.value[k] = ''
        for (const k of Object.keys(extractedFields)) {
          if (k in customFieldsData.value) {
            customFieldsData.value[k] =
              typeof extractedFields[k] === 'object' ? JSON.stringify(extractedFields[k]) : extractedFields[k]
          }
        }
      }

      if (!lastUserMessage.trim()) return
      if (props.mode === 'agent' && !agent.value) await loadAgent()
      if (history.length > 1) history.slice(0, -1).forEach(msg => chatOps.addMessage(msg))

      newMessage.value = lastUserMessage
      await nextTick()
      if (newMessage.value.trim()) await messaging.sendMessage()
    } catch (error) {
      logger.error('Error loading trace in playground', { error })
      notify.error('Failed to load trace in playground')
    }
  }

  const loadTraceInPlayground = async (traceData: TraceData) => {
    if (isLoadingTrace.value) return
    isLoadingTrace.value = true
    try {
      if ((chatMessages.value?.length ?? 0) > 0) {
        pendingTraceData.value = traceData
        showClearChatConfirm.value = true
        return
      }
      await doLoadTrace(traceData)
    } finally {
      isLoadingTrace.value = false
    }
  }

  const onConfirmLoadTrace = async () => {
    if (!pendingTraceData.value || isLoadingTrace.value) return
    isLoadingTrace.value = true
    try {
      await doLoadTrace(pendingTraceData.value)
      pendingTraceData.value = null
    } finally {
      isLoadingTrace.value = false
    }
  }

  const onCancelLoadTrace = () => {
    pendingTraceData.value = null
  }

  // --- Watchers & lifecycle ---
  watch(() => props.agentId, loadAgent, { immediate: true })

  watch(projectIdRef, async (newPid, oldPid) => {
    if (newPid !== oldPid && oldPid) {
      runStreamCleanup.value?.()
      runStreamCleanup.value = null
      isAsyncRunStream.value = false
      chatMessages.value.splice(0, chatMessages.value.length)
      newMessage.value = ''
      files.uploadedFiles.value = []
      response.value = undefined
      if (newPid) {
        bindChatState(newPid)
        chatOps.initializeNewChat()
      }
    }
  })

  watch(
    playgroundConfig,
    cfg => {
      if (props.mode !== 'workflow' || !cfg) {
        customFieldsData.value = {}
        return
      }
      if (cfg.playground_field_types && Object.keys(cfg.playground_field_types).length > 0) {
        const init: Record<string, any> = {}

        Object.keys(cfg.playground_field_types).forEach(name => {
          if (name !== 'messages') init[name] = cfg.playground_input_schema?.[name] || ''
        })
        customFieldsData.value = init
      } else {
        customFieldsData.value = {}
      }
    },
    { immediate: true }
  )

  watch(
    () => route.fullPath,
    (newPath, oldPath) => {
      if (newPath !== oldPath && oldPath) {
        chatMessages.value.splice(0, chatMessages.value.length)
        newMessage.value = ''
        files.uploadedFiles.value = []
        response.value = undefined
        chatOps.initializeNewChat()
      }
    }
  )

  onMounted(async () => {
    const {
      data: { user },
    } = await supabase.auth.getUser()

    if (user && props.projectId) {
      bindChatState(props.projectId)
      if (!chatMessages.value.length) chatOps.initializeNewChat()
    }
  })

  onBeforeUnmount(() => {
    runStreamCleanup.value?.()
    runStreamCleanup.value = null
  })

  return {
    chatMessages,
    isTyping,
    isStreaming: messaging.isStreaming,
    newMessage,
    hasAdditionalFields,
    displayTitle,
    messagesContainer,
    uploadedFiles: files.uploadedFiles,
    downloadingFiles: files.downloadingFiles,
    downloadingResponseFiles: files.downloadingResponseFiles,
    showSetIdsSelector,
    availableSetIds,
    selectedSetIds,
    isSetIdsLoading,
    isSetIdsError,
    customFieldsData,
    expandedFields,
    playgroundConfig,
    sendMessage: messaging.sendMessage,
    clearChatHandler: messaging.clearChatHandler,
    handleKeyDown: messaging.handleKeyDown,
    handleMessageEdit: messaging.handleMessageEdit,
    handleMessageReplay: messaging.handleMessageReplay,
    handleFileSelect: files.handleFileSelect,
    removeFile: files.removeFile,
    handleSourceClick: files.handleSourceClick,
    onFileClick,
    openSaveModeDialog,
    showSaveToQADialog: qa.showSaveToQADialog,
    selectedQADataset: qa.selectedQADataset,
    qaDatasets: qa.qaDatasets,
    loadingQADatasets: qa.loadingQADatasets,
    savingToQA: qa.savingToQA,
    saveToQAError: qa.saveToQAError,
    saveToQASuccess: qa.saveToQASuccess,
    showCreateDataset: qa.showCreateDataset,
    newDatasetName: qa.newDatasetName,
    creatingDataset: qa.creatingDataset,
    saveToQA: qa.saveToQA,
    createDataset: qa.createDataset,
    showClearChatConfirm,
    onConfirmLoadTrace,
    onCancelLoadTrace,
    loadTraceInPlayground,
    isLoadingTrace,
  }
}
