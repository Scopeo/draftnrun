import { reactive } from 'vue'
import { type ChatMessage, useChatHistory } from './useChatHistory'
import { logger } from '@/utils/logger'

interface ChatState {
  messages: ChatMessage[]
  isTyping: boolean
  error: string | null
  chatId: string | null
  persistenceEnabled: boolean
}

// Global state for agent chat
const chatStates = reactive<Record<string, ChatState>>({})

/** Remove all cached chat states (called on project/agent switch) */
export function clearAllChatStates() {
  for (const key of Object.keys(chatStates)) {
    delete chatStates[key]
  }
}

export function usePlaygroundChat(entityId: string, persistenceEnabled: boolean = true) {
  // Initialize chat state for this entity if it doesn't exist
  if (!chatStates[entityId]) {
    chatStates[entityId] = {
      messages: [],
      isTyping: false,
      error: null,
      chatId: null,
      persistenceEnabled,
    }
  }

  const state = chatStates[entityId]
  const chatHistory = useChatHistory()

  const addMessage = (message: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const newMessage: ChatMessage = {
      id: chatHistory.generateMessageId(),
      timestamp: new Date().toISOString(),
      ...message,
    }

    state.messages.push(newMessage)

    // Auto-save to database if persistence is enabled and we have a chat ID
    if (state.persistenceEnabled && state.chatId) {
      // Use setTimeout to avoid blocking the UI and ensure message is fully added
      setTimeout(() => saveChatToHistory(), 100)
    }

    return newMessage
  }

  const updateMessage = (messageId: string, updates: Partial<ChatMessage>) => {
    const messageIndex = state.messages.findIndex(msg => msg.id === messageId)
    if (messageIndex !== -1) {
      state.messages[messageIndex] = { ...state.messages[messageIndex], ...updates }

      // Auto-save to database if persistence is enabled and we have a chat ID
      if (state.persistenceEnabled && state.chatId) {
        // Use setTimeout to avoid blocking the UI and ensure message is fully updated
        setTimeout(() => saveChatToHistory(), 100)
      }
    }
  }

  const setTyping = (isTyping: boolean) => {
    state.isTyping = isTyping
  }

  const setError = (error: string | null) => {
    state.error = error
  }

  const clearChat = () => {
    // Clear the chat array and reset chat ID so next message creates new chat
    state.messages.splice(0, state.messages.length)
    state.chatId = null
  }

  const removeMessagesAfterIndex = (messageIndex: number) => {
    // Remove all messages after the specified index
    if (messageIndex >= 0 && messageIndex < state.messages.length) {
      state.messages.splice(messageIndex + 1)

      // Auto-save to database if persistence is enabled
      if (state.persistenceEnabled && state.chatId) {
        setTimeout(() => saveChatToHistory(), 100)
      }
    }
  }

  // Generate a new chat ID immediately (for API calls)
  const initializeNewChat = () => {
    if (!state.chatId) {
      state.chatId = chatHistory.generateChatId()
    }
    return state.chatId
  }

  // Create a new chat and enable persistence
  const createNewChat = async () => {
    if (!state.persistenceEnabled) return

    // Ensure we have a chat ID
    if (!state.chatId) {
      state.chatId = chatHistory.generateChatId()
    }

    try {
      // Persist using the same chatId so updates don't 404 (PGRST116)
      await chatHistory.createChatHistory(entityId, state.messages, state.chatId)
      return state.chatId
    } catch (error) {
      throw error
    }
  }

  // Load an existing chat from history
  const loadChatFromHistory = async (chatId: string) => {
    try {
      const chat = await chatHistory.loadChat(chatId)
      if (chat) {
        // Clear current messages and replace with loaded chat messages
        state.messages.splice(0, state.messages.length)
        if (chat.messages && chat.messages.length > 0) {
          state.messages.push(...chat.messages)
        }

        state.chatId = chatId
        state.error = null

        return chat
      }
      return null
    } catch (error) {
      state.error = 'Failed to load chat history'
      throw error
    }
  }

  // Save current chat state to history
  const saveChatToHistory = async () => {
    if (!state.persistenceEnabled || !state.chatId) return

    try {
      await chatHistory.updateChatHistory(state.chatId, state.messages)
    } catch (error: unknown) {
      logger.warn('Failed to save chat history', { error })
    }
  }

  // Start a new persistent chat session
  const startNewChatSession = async () => {
    if (!state.persistenceEnabled) return

    clearChat()
    await createNewChat()
  }

  // Enable/disable persistence for this chat
  const setPersistence = (enabled: boolean) => {
    state.persistenceEnabled = enabled
  }

  // Get current chat ID
  const getCurrentChatId = () => state.chatId

  const getMessages = () => state.messages
  const getTyping = () => state.isTyping
  const getError = () => state.error

  return {
    // State
    messages: state.messages,
    isTyping: state.isTyping,
    error: state.error,
    chatId: state.chatId,
    persistenceEnabled: state.persistenceEnabled,

    // Actions
    addMessage,
    updateMessage,
    setTyping,
    setError,
    clearChat,
    removeMessagesAfterIndex,
    initializeNewChat,
    createNewChat,
    loadChatFromHistory,
    saveChatToHistory,
    startNewChatSession,
    setPersistence,

    // Getters
    getCurrentChatId,
    getMessages,
    getTyping,
    getError,

    // Chat history instance
    chatHistory,
  }
}
