import { computed, ref } from 'vue'

// Chat history persistence is currently disabled (Supabase chat_history table not configured).
// All functions are safe no-op stubs so consumers don't need conditional logic.
const CHAT_HISTORY_ENABLED = import.meta.env.VITE_ENABLE_CHAT_HISTORY === 'true'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isLoading?: boolean
  isError?: boolean
  artifacts?: {
    sources?: Array<{
      name: string
      document_name: string
      content: string
      url: string
      metadata: any
    }>
    images?: string[]
  }
  files?: Array<{
    filename: string
    content_type: string
    size: number
    s3_key?: string
    url?: string
    data?: string
  }>
  metadata?: {
    tokens?: number
    duration?: number
    status?: string
    trace_id?: string
    project_id?: string
    error?: string
  }
}

export interface ChatHistory {
  id: string
  user_id: string
  agent_id: string
  chat_id: string
  title?: string
  messages: ChatMessage[]
  created_at: string
  updated_at: string
  message_count?: number
  last_message_at?: string
}

export function useChatHistory() {
  const chatHistories = ref<ChatHistory[]>([])
  const currentChat = ref<ChatHistory | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const generateMessageId = (): string => `msg_${crypto.randomUUID()}`
  const generateChatId = (): string => crypto.randomUUID()

  const fetchChatHistories = async (_agentId?: string, _limit: number = 50) => {
    loading.value = false
    error.value = null
    chatHistories.value = []
  }

  const loadChat = async (_chatId: string): Promise<ChatHistory | null> => {
    loading.value = false
    error.value = null
    return null
  }

  const createChatHistory = async (
    _agentId: string,
    _initialMessages: ChatMessage[] = [],
    chatIdOverride?: string
  ): Promise<string> => {
    const chatId = chatIdOverride || generateChatId()

    loading.value = false
    error.value = null
    return chatId
  }

  const updateChatHistory = async (_chatId: string, _messages: ChatMessage[], _title?: string) => {
    loading.value = false
    error.value = null
  }

  const deleteChatHistory = async (_chatId: string) => {
    loading.value = false
    error.value = null
  }

  const clearAllChatHistories = async (_agentId?: string) => {
    loading.value = false
    error.value = null
    chatHistories.value = []
    currentChat.value = null
  }

  const chatHistoriesCount = computed(() => chatHistories.value.length)
  const hasChatHistories = computed(() => chatHistories.value.length > 0)

  return {
    chatHistories,
    currentChat,
    loading,
    error,
    isEnabled: computed(() => CHAT_HISTORY_ENABLED),
    generateMessageId,
    generateChatId,
    fetchChatHistories,
    loadChat,
    createChatHistory,
    updateChatHistory,
    deleteChatHistory,
    clearAllChatHistories,
    chatHistoriesCount,
    hasChatHistories,
  }
}
