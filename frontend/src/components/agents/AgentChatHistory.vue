<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { type ChatHistory, useChatHistory } from '@/composables/useChatHistory'

interface Props {
  agentId: string
  isVisible: boolean
  currentChatId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'load-chat': [chatId: string]
  'new-chat': []
  'delete-chat': [chatId: string]
}>()

const chatHistory = useChatHistory()
const searchQuery = ref('')
const selectedChatId = ref<string | null>(null)
const showDeleteConfirm = ref<string | null>(null)

// Computed filtered histories
const filteredHistories = computed(() => {
  if (!searchQuery.value.trim()) {
    return chatHistory.chatHistories.value
  }

  const query = searchQuery.value.toLowerCase()
  return chatHistory.chatHistories.value.filter(
    chat =>
      chat.title?.toLowerCase().includes(query) || chat.messages.some(msg => msg.content.toLowerCase().includes(query))
  )
})

// Format date for display
const formatDate = (dateString: string): string => {
  const date = new Date(dateString)
  const now = new Date()
  const diffTime = Math.abs(now.getTime() - date.getTime())
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

  if (diffDays === 1) {
    return 'Today'
  } else if (diffDays === 2) {
    return 'Yesterday'
  } else if (diffDays <= 7) {
    return `${diffDays - 1} days ago`
  } else {
    return date.toLocaleDateString()
  }
}

// Get preview of last message
const getLastMessagePreview = (chat: ChatHistory): string => {
  if (!chat.messages || chat.messages.length === 0) {
    return 'No messages yet'
  }

  const lastMessage = chat.messages[chat.messages.length - 1]
  const maxLength = 60
  const content = lastMessage.content.trim()

  return content.length > maxLength ? `${content.substring(0, maxLength)}...` : content
}

// Load chat history
const loadChatHistory = async () => {
  await chatHistory.fetchChatHistories(props.agentId)
}

// Handle chat selection
const selectChat = (chat: ChatHistory) => {
  selectedChatId.value = chat.chat_id
  emit('load-chat', chat.chat_id)
}

// Handle new chat
const handleNewChat = () => {
  selectedChatId.value = null
  emit('new-chat')
}

// Handle delete chat
const handleDeleteChat = async (chatId: string) => {
  try {
    await chatHistory.deleteChatHistory(chatId)

    // If this was the selected chat, clear selection
    if (selectedChatId.value === chatId) {
      selectedChatId.value = null
    }

    emit('delete-chat', chatId)
    showDeleteConfirm.value = null
  } catch (error) {
    logger.error('Failed to delete chat', { error })
  }
}

// Show delete confirmation
const confirmDelete = (chatId: string, event: Event) => {
  event.stopPropagation()
  showDeleteConfirm.value = chatId
}

// Cancel delete
const cancelDelete = () => {
  showDeleteConfirm.value = null
}

// Watch for current chat changes
watch(
  () => props.currentChatId,
  newChatId => {
    selectedChatId.value = newChatId || null
  }
)

// Watch for visibility changes to load data
watch(
  () => props.isVisible,
  visible => {
    if (visible) {
      loadChatHistory()
    }
  }
)

// Load initial data
onMounted(() => {
  if (props.isVisible) {
    loadChatHistory()
  }
  selectedChatId.value = props.currentChatId || null
})
</script>

<template>
  <div class="chat-history-sidebar" :class="{ visible: isVisible }">
    <div class="sidebar-header">
      <div class="d-flex align-center justify-space-between mb-3">
        <h6 class="text-h6">Chat History</h6>
        <VBtn icon size="small" variant="text" color="primary" title="Start new chat" @click="handleNewChat">
          <VIcon icon="tabler-plus" />
        </VBtn>
      </div>

      <!-- Search -->
      <VTextField
        v-model="searchQuery"
        placeholder="Search chats..."
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="mb-3"
      >
        <template #prepend-inner>
          <VIcon icon="tabler-search" size="18" />
        </template>
      </VTextField>
    </div>

    <div class="sidebar-content">
      <!-- Loading state -->
      <LoadingState v-if="chatHistory.loading.value" size="sm" />

      <!-- Empty state -->
      <EmptyState
        v-else-if="!chatHistory.hasChatHistories.value"
        icon="tabler-message-circle-off"
        title="No chat history found"
        action-text="Start First Chat"
        size="sm"
        @action="handleNewChat"
      />

      <!-- Chat history list -->
      <div v-else class="chat-list">
        <VCard
          v-for="chat in filteredHistories"
          :key="chat.id"
          variant="outlined"
          class="chat-item mb-2"
          :class="{ selected: selectedChatId === chat.chat_id }"
          @click="selectChat(chat)"
        >
          <VCardText class="pa-3">
            <div class="d-flex justify-space-between align-start mb-1">
              <h6 class="text-subtitle-2 text-truncate flex-grow-1">
                {{ chat.title || 'New Chat' }}
              </h6>
              <div class="chat-actions">
                <VBtn icon size="x-small" variant="text" color="error" @click="confirmDelete(chat.chat_id, $event)">
                  <VIcon icon="tabler-trash" size="14" />
                </VBtn>
              </div>
            </div>

            <p class="text-caption text-disabled text-truncate mb-2">
              {{ getLastMessagePreview(chat) }}
            </p>

            <div class="d-flex justify-space-between align-center">
              <span class="text-caption text-medium-emphasis"> {{ chat.message_count || 0 }} messages </span>
              <span class="text-caption text-disabled">
                {{ formatDate(chat.updated_at) }}
              </span>
            </div>
          </VCardText>
        </VCard>

        <!-- No search results -->
        <EmptyState
          v-if="searchQuery && filteredHistories.length === 0"
          icon="tabler-search-off"
          :title="`No chats found for &quot;${searchQuery}&quot;`"
          size="sm"
        />
      </div>
    </div>

    <!-- Delete confirmation dialog -->
    <VDialog :model-value="!!showDeleteConfirm" max-width="var(--dnr-dialog-sm)" @update:model-value="cancelDelete">
      <VCard>
        <VCardTitle>Delete Chat</VCardTitle>
        <VCardText> Are you sure you want to delete this chat? This action cannot be undone. </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="cancelDelete">Cancel</VBtn>
          <VBtn color="error" variant="text" @click="handleDeleteChat(showDeleteConfirm!)"> Delete </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.chat-history-sidebar {
  position: fixed;
  top: 0;
  right: -350px;
  width: 350px;
  height: 100vh;
  background: rgb(var(--v-theme-surface));
  border-left: 1px solid rgba(var(--v-border-color), 0.12);
  transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1000;
  display: flex;
  flex-direction: column;

  &.visible {
    right: 0;
  }
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  flex-shrink: 0;
}

.sidebar-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.2);
  }

  &::-webkit-scrollbar-thumb:hover {
    background: rgba(var(--v-theme-on-surface), 0.3);
  }
}

.chat-item {
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;

  &:hover {
    border-color: rgba(var(--v-theme-primary), 0.3);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  &.selected {
    border-color: rgb(var(--v-theme-primary));
    background-color: rgba(var(--v-theme-primary), 0.05);
  }
}

.chat-actions {
  opacity: 0;
  transition: opacity 0.2s ease;
}

.chat-item:hover .chat-actions {
  opacity: 1;
}
</style>
