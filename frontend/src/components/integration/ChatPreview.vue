<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { scopeoApi } from '@/api'
import type { WidgetConfig } from '@/api'

interface Props {
  projectId?: string
  graphRunnerId?: string
  config: WidgetConfig
}

const props = defineProps<Props>()

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<ChatMessage[]>([])
const inputValue = ref('')
const isLoading = ref(false)
const messagesEndRef = ref<HTMLElement | null>(null)

// Initialize with welcome messages from config
onMounted(() => {
  if (props.config.first_messages?.length) {
    messages.value = props.config.first_messages.map((content, i) => ({
      id: `first-${i}`,
      role: 'assistant' as const,
      content,
    }))
  }
})

// Watch for config changes to update welcome messages
watch(
  () => props.config.first_messages,
  newMessages => {
    if (messages.value.length === 0 || messages.value.every(m => m.id.startsWith('first-'))) {
      messages.value = (newMessages || []).map((content, i) => ({
        id: `first-${i}`,
        role: 'assistant' as const,
        content,
      }))
    }
  },
  { deep: true }
)

// Apply theme via CSS custom properties
const chatStyle = computed(() => ({
  '--primary-color': props.config.theme?.primary_color || '#6366F1',
  '--secondary-color': props.config.theme?.secondary_color || '#4F46E5',
  '--background-color': props.config.theme?.background_color || '#FFFFFF',
  '--text-color': props.config.theme?.text_color || '#1F2937',
  '--border-radius': `${props.config.theme?.border_radius || 12}px`,
  '--font-family': props.config.theme?.font_family || 'Inter, system-ui, sans-serif',
  '--message-user-bg': props.config.theme?.primary_color || '#6366F1',
  '--message-assistant-bg': '#F3F4F6',
}))

// Scroll to bottom
function scrollToBottom() {
  nextTick(() => {
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

// Check if we can send real messages
const canSendReal = computed(() => !!props.projectId && !!props.graphRunnerId)

// Show suggestions only if no user messages yet
const showSuggestions = computed(() => {
  return props.config.suggestions?.length && !messages.value.some(m => m.role === 'user')
})

// Handle suggestion click
function handleSuggestionClick(suggestion: string) {
  inputValue.value = suggestion
  handleSubmit()
}

// Handle form submit
function handleSubmit(e?: Event) {
  e?.preventDefault()
  if (!inputValue.value.trim() || isLoading.value) return

  const userMessage = inputValue.value.trim()

  messages.value.push({
    id: `user-${Date.now()}`,
    role: 'user',
    content: userMessage,
  })
  inputValue.value = ''
  scrollToBottom()

  // If no production deployment, show a simulated response
  if (!canSendReal.value) {
    isLoading.value = true
    setTimeout(() => {
      messages.value.push({
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: 'This is a preview. Deploy to production to enable real chat responses.',
      })
      isLoading.value = false
      scrollToBottom()
    }, 500)
    return
  }

  // Send real message
  isLoading.value = true
  scopeoApi.chat
    .chat(props.projectId!, props.graphRunnerId!, {
      messages: messages.value.map(m => ({ role: m.role, content: m.content })),
    })
    .then(response => {
      messages.value.push({
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.message || 'No response',
      })
    })
    .catch((error: unknown) => {
      const err = error as { message?: string; response?: { status?: number } }
      let errorMessage = 'Sorry, something went wrong. Please try again.'
      if (err?.response?.status === 429) {
        errorMessage = 'Rate limit exceeded. Please wait a moment before sending another message.'
      } else if (err?.response?.status === 503) {
        errorMessage = 'Service temporarily unavailable. Please try again in a few moments.'
      }
      messages.value.push({
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
      })
    })
    .finally(() => {
      isLoading.value = false
      scrollToBottom()
    })
}

// Handle keydown for Enter to submit
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

// Get widget name for title
const widgetName = computed(() => props.config.name || 'Chat')
</script>

<template>
  <div class="chat-container" :style="chatStyle">
    <!-- Header -->
    <div class="chat-header">
      <img v-if="config.theme?.logo_url" :src="config.theme.logo_url" :alt="`${widgetName} logo`" class="chat-logo" />
      <span class="chat-title">{{ widgetName }}</span>
    </div>

    <!-- Header Message (fixed notice/terms) -->
    <div v-if="config.header_message" class="header-message">
      {{ config.header_message }}
    </div>

    <!-- Messages -->
    <div class="chat-messages">
      <div v-for="message in messages" :key="message.id" class="message" :class="[message.role]">
        {{ message.content }}
      </div>
      <div v-if="isLoading" class="typing-indicator">
        <span />
        <span />
        <span />
      </div>
      <div ref="messagesEndRef" />
    </div>

    <!-- Suggestions -->
    <div v-if="showSuggestions" class="suggestions">
      <button
        v-for="(suggestion, index) in config.suggestions"
        :key="index"
        type="button"
        class="suggestion-chip"
        :disabled="isLoading"
        @click="handleSuggestionClick(suggestion)"
      >
        {{ suggestion }}
      </button>
    </div>

    <!-- Input -->
    <form class="chat-input-container" @submit.prevent="handleSubmit">
      <textarea
        v-model="inputValue"
        class="chat-input"
        :placeholder="config.placeholder_text || 'Type a message...'"
        :disabled="isLoading"
        rows="1"
        @keydown="handleKeyDown"
      />
      <button type="submit" class="send-button" :disabled="isLoading || !inputValue.trim()">Send</button>
    </form>

    <!-- Powered by -->
    <div v-if="config.powered_by_visible" class="powered-by">
      Powered by <a href="https://draftnrun.com" target="_blank" rel="noopener noreferrer">Draft'n run</a>
    </div>

    <!-- Preview mode warning -->
    <div v-if="!canSendReal" class="preview-warning">Preview mode - deploy to production for real responses</div>
  </div>
</template>

<style scoped>
* {
  box-sizing: border-box;
}

.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: var(--background-color);
  font-family: var(--font-family);
  color: var(--text-color);
  border-radius: var(--border-radius);
  overflow: hidden;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
  background: var(--background-color);
}

.chat-logo {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
}

.chat-title {
  flex: 1;
  font-weight: 600;
  font-size: 16px;
  color: var(--text-color);
}

/* Header Message (fixed notice/terms) */
.header-message {
  padding: 10px 16px;
  background: #fef3c7;
  border-bottom: 1px solid #fcd34d;
  font-size: 12px;
  color: #92400e;
  line-height: 1.4;
  white-space: pre-wrap;
}

/* Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: var(--border-radius);
  font-size: 14px;
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.message.user {
  align-self: flex-end;
  background: var(--message-user-bg);
  color: white;
  border-bottom-right-radius: 4px;
}

.message.assistant {
  align-self: flex-start;
  background: var(--message-assistant-bg);
  color: var(--text-color);
  border-bottom-left-radius: 4px;
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  align-self: flex-start;
  background: var(--message-assistant-bg);
  border-radius: var(--border-radius);
  border-bottom-left-radius: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #9ca3af;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-indicator span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-6px);
  }
}

/* Suggestions */
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 16px;
}

.suggestion-chip {
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.suggestion-chip:hover:not(:disabled) {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.suggestion-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Input */
.chat-input-container {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
  background: var(--background-color);
}

.chat-input {
  flex: 1;
  border: 1px solid #e5e7eb;
  border-radius: var(--border-radius);
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  min-height: 42px;
  max-height: 120px;
}

.chat-input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}

.chat-input::placeholder {
  color: #9ca3af;
}

.chat-input:disabled {
  background: #f9fafb;
  cursor: not-allowed;
}

.send-button {
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--border-radius);
  padding: 10px 16px;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
  font-family: inherit;
}

.send-button:hover:not(:disabled) {
  background: var(--secondary-color);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Powered by */
.powered-by {
  text-align: center;
  padding: 8px;
  font-size: 11px;
  color: #9ca3af;
}

.powered-by a {
  color: var(--primary-color);
  text-decoration: none;
}

.powered-by a:hover {
  text-decoration: underline;
}

/* Preview warning */
.preview-warning {
  text-align: center;
  padding: 4px 8px;
  font-size: 11px;
  color: #f59e0b;
  background: #fef3c7;
  border-top: 1px solid #fcd34d;
}
</style>
