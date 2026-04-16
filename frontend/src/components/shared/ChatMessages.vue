<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ClickOutside as vClickOutside } from 'vuetify/directives'
import MDContent from '@/components/MDContent.vue'
import { formatFileSize, getFileIcon } from '@/utils/fileUtils'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string | Date
  isError?: boolean
  isLoading?: boolean
  artifacts?: {
    sources?: any[]
  }
  files?: any[]
}

interface Props {
  messages: ChatMessage[]
  downloadingFiles?: Record<string, boolean>
  downloadingResponseFiles?: Record<string, boolean>
  showSaveToQa?: boolean
  containerClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  downloadingFiles: () => ({}),
  downloadingResponseFiles: () => ({}),
  showSaveToQa: true,
  containerClass: '',
})

const emit = defineEmits<{
  'save-to-qa': [message: ChatMessage, index: number]
  'source-click': [source: any]
  'file-click': [file: any]
  'edit-message': [newContent: string, messageIndex: number]
  'replay-message': [messageIndex: number]
}>()

// Ref to the container element
const containerRef = ref<HTMLDivElement>()

// Edit mode state
const editingMessageIndex = ref<number | null>(null)
const editedContent = ref('')
const editTextarea = ref<InstanceType<(typeof import('vuetify/components'))['VTextarea']> | null>(null)

const formatTimestamp = (timestamp: string | Date) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)

  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const isHttpUrl = (url: string) => {
  return url && (url.startsWith('http://') || url.startsWith('https://'))
}

const handleSourceClick = (source: any) => {
  emit('source-click', source)
}

const handleFileClick = (file: any) => {
  emit('file-click', file)
}

const handleSaveToQa = (message: ChatMessage, index: number) => {
  emit('save-to-qa', message, index)
}

const canShowSaveButton = (index: number) => {
  const message = props.messages[index]
  const nextMessage = props.messages[index + 1]

  return props.showSaveToQa && message.role === 'user' && nextMessage?.role === 'assistant' && !nextMessage?.isLoading
}

const handleReplayMessage = (index: number) => {
  emit('replay-message', index)
}

// Edit message functions
const startEditingMessage = (index: number) => {
  const message = props.messages[index]
  if (message.role === 'user' && !message.isLoading && !message.isError) {
    editingMessageIndex.value = index
    editedContent.value = message.content
    // Focus textarea after DOM update
    nextTick(() => {
      editTextarea.value?.focus()
    })
  }
}

const cancelEditing = () => {
  editingMessageIndex.value = null
  editedContent.value = ''
}

const saveEdit = () => {
  if (editingMessageIndex.value !== null && editedContent.value.trim()) {
    emit('edit-message', editedContent.value.trim(), editingMessageIndex.value)
    cancelEditing()
  }
}

const handleEditKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelEditing()
  } else if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    saveEdit()
  }
}

// Expose the container element properties and cancel editing function
defineExpose({
  scrollTo: (options: ScrollToOptions) => {
    containerRef.value?.scrollTo(options)
  },
  get scrollHeight() {
    return containerRef.value?.scrollHeight
  },
  cancelEditing,
})
</script>

<template>
  <div ref="containerRef" class="chat-messages" :class="[containerClass, { 'has-messages': messages.length > 0 }]">
    <div
      v-for="(message, index) in messages"
      :key="index"
      class="message-wrapper"
      :class="[message.role, { editing: editingMessageIndex === index }]"
    >
      <div class="message-container">
        <div class="message-header-with-avatar">
          <VAvatar
            size="28"
            :color="message.isError ? 'error' : message.role === 'assistant' ? 'primary' : 'secondary'"
            class="message-avatar"
          >
            <VIcon
              :icon="
                message.isError
                  ? 'tabler-alert-triangle'
                  : message.role === 'assistant'
                    ? 'tabler-robot'
                    : 'tabler-user'
              "
              color="white"
              size="16"
            />
          </VAvatar>
          <div class="message-user-info">
            <span class="text-high-emphasis font-weight-medium">{{
              message.isError ? 'Error' : message.role === 'assistant' ? 'Agent' : 'You'
            }}</span>
          </div>
        </div>
        <div class="message-content">
          <!-- Subtitle for error messages -->
          <p v-if="message.isError" class="text-caption text-disabled error-subtitle">There's been an error:</p>

          <!-- Loading dots for pending messages -->
          <p v-if="message.isLoading" class="message-text loading-dots" />

          <!-- Markdown content for non-loading messages -->
          <div v-else class="message-text">
            <!-- User messages - editable on click -->
            <template v-if="message.role === 'user'">
              <!-- Edit mode -->
              <div v-if="editingMessageIndex === index" v-click-outside="cancelEditing" class="edit-mode">
                <VTextarea
                  ref="editTextarea"
                  v-model="editedContent"
                  variant="outlined"
                  density="compact"
                  hide-details
                  rows="3"
                  auto-grow
                  max-rows="10"
                  class="edit-textarea"
                  @keydown="handleEditKeydown"
                />
                <div class="edit-controls">
                  <VBtn
                    icon
                    variant="flat"
                    size="x-small"
                    color="primary"
                    :disabled="!editedContent.trim()"
                    class="edit-send-btn"
                    @click="saveEdit"
                  >
                    <VIcon icon="tabler-send" size="14" />
                  </VBtn>
                </div>
              </div>
              <!-- Display mode - clickable -->
              <div
                v-else
                class="user-message-content"
                :class="{ editable: !message.isLoading && !message.isError }"
                @click="startEditingMessage(index)"
              >
                {{ message.content }}
              </div>
            </template>

            <!-- Assistant messages are rendered as markdown -->
            <MDContent
              v-else
              :content="message.content"
              class="markdown-message"
              :class="{ 'error-message-text': message.isError }"
            />

            <!-- Sources section for assistant messages -->
            <div v-if="message.role === 'assistant' && message.artifacts?.sources?.length" class="sources-section">
              <h4 class="sources-title">Sources:</h4>
              <div class="sources-list">
                <div v-for="(source, idx) in message.artifacts.sources" :key="idx" class="source-item">
                  <!-- Source number indicator -->
                  <span class="source-number">[{{ idx + 1 }}]</span>

                  <!-- For HTTP URLs -->
                  <a
                    v-if="isHttpUrl(source.url)"
                    :href="source.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="source-link"
                  >
                    {{ (source.document_name || source.name || source.url || `Source ${idx + 1}`).replace(/^\//, '') }}
                  </a>

                  <!-- For Supabase files -->
                  <div v-else class="supabase-file">
                    <a href="#" class="source-link" @click.prevent="handleSourceClick(source)">
                      {{
                        (source.document_name || source.name || source.url || `Source ${idx + 1}`).replace(/^\//, '')
                      }}
                      <VProgressCircular
                        v-if="downloadingFiles[source.url]"
                        indeterminate
                        size="16"
                        width="2"
                        color="primary"
                        class="ms-2"
                      />
                    </a>
                  </div>
                </div>
              </div>
            </div>

            <!-- Files section for assistant messages -->
            <div v-if="message.role === 'assistant' && message.files?.length" class="files-section">
              <h4 class="files-title">Files:</h4>
              <div class="files-list">
                <div v-for="(file, idx) in message.files" :key="idx" class="file-item">
                  <VIcon :icon="getFileIcon(file.content_type, file.filename)" size="16" class="file-icon me-2" />
                  <a href="#" class="file-link" @click.prevent="handleFileClick(file)" @click.stop>
                    {{ file.filename }}
                    <span class="file-size">({{ formatFileSize(file.size) }})</span>
                    <VProgressCircular
                      v-if="downloadingResponseFiles[file.s3_key || file.url || file.filename]"
                      indeterminate
                      size="16"
                      width="2"
                      color="primary"
                      class="ms-2"
                    />
                  </a>
                </div>
              </div>
            </div>
          </div>
          <!-- Message footer - hidden when editing -->
          <div v-if="editingMessageIndex !== index" class="message-footer">
            <!-- Replay button (only for user messages with assistant response) -->
            <VTooltip v-if="message.role === 'user' && canShowSaveButton(index)" location="top">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon
                  variant="text"
                  size="x-small"
                  color="primary"
                  class="replay-btn"
                  @click.stop="handleReplayMessage(index)"
                >
                  <VIcon icon="tabler-reload" size="14" />
                </VBtn>
              </template>
              <span>Replay from this message</span>
            </VTooltip>
            <!-- Save to QA button (only for user messages with assistant response) -->
            <VTooltip v-if="canShowSaveButton(index)" location="top">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon
                  variant="text"
                  size="x-small"
                  color="success"
                  class="save-to-qa-btn"
                  @click.stop="handleSaveToQa(message, index)"
                >
                  <VIcon icon="tabler-device-floppy" size="14" />
                </VBtn>
              </template>
              <span>Save to QA Dataset</span>
            </VTooltip>
            <span class="message-timestamp">{{ formatTimestamp(message.timestamp) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
// Only minimal container styles - inherit most from parent
.chat-messages {
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1;
  max-block-size: 100%;
  min-block-size: 0;
  padding-block-start: 0.75rem;
  padding-block-end: 1rem;
  padding-inline: 0.25rem;

  &.has-messages {
    min-height: 0;
  }

  &.messages-in-card {
    max-block-size: 400px;
    min-block-size: 200px;
    background-color: rgb(var(--v-theme-surface));
    border-radius: 4px;
  }

  /* Custom scrollbar styling */
  &::-webkit-scrollbar {
    inline-size: 6px;
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

.message-wrapper {
  margin-block-end: 1rem;

  &.assistant {
    .message-container {
      background-color: rgba(var(--v-theme-primary), 0.05);
      align-items: stretch;
      text-align: left;
    }

    .message-header-with-avatar {
      flex-direction: row;
    }

    .message-content {
      text-align: left;
    }
  }

  &.user {
    .message-container {
      margin-inline-start: auto;
      background-color: rgba(var(--v-theme-on-surface), 0.06);
    }

    .message-header-with-avatar {
      flex-direction: row-reverse;
    }

    // Make user messages look clickable only when editable
    .user-message-content {
      padding: 0.25rem;
      margin: -0.25rem;
      border-radius: 4px;

      &.editable {
        cursor: pointer;
        transition: background-color 0.2s ease;

        &:hover {
          background-color: rgba(var(--v-theme-primary), 0.08);
        }
      }
    }
  }

  // Highlight when editing
  &.editing {
    .message-container {
      border: 2px solid rgb(var(--v-theme-primary));
      background-color: rgba(var(--v-theme-primary), 0.02);
    }
  }
}

.message-container {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 0.5rem 0.625rem;
  border-radius: 14px;
  gap: 0.1rem;
  max-inline-size: 100%;
  max-width: 80%;
  box-shadow: 0px 0px 10px 2px rgba(0, 0, 0, 0.03);
  overflow: hidden;
}

.message-header-with-avatar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.message-user-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.message-content {
  flex-grow: 1;
  max-inline-size: 100%;
  overflow-wrap: break-word;
  word-wrap: break-word;
  word-break: break-word;
  min-width: 0;
  overflow-x: auto;
}

.error-subtitle {
  margin-block-end: 0.25rem;
}

.message-text {
  margin: 0;
  line-height: 1.5;
  white-space: pre-wrap;

  &.loading-dots {
    &::after {
      display: inline-block;
      animation: dotty steps(1, end) 1s infinite;
      content: '';
    }
  }

  &.error-message {
    color: rgb(var(--v-theme-error));
  }
}

@keyframes dotty {
  0%,
  20% {
    content: '.';
  }
  40% {
    content: '..';
  }
  60%,
  100% {
    content: '...';
  }
}

.markdown-message {
  :deep(p) {
    margin-block: 0;
  }

  :deep(a) {
    color: rgb(var(--v-theme-primary));
    font-weight: 500;
    text-decoration: underline;

    &:hover {
      color: rgb(var(--v-theme-primary-darken-1));
      text-decoration: underline;
    }
  }

  :deep(code) {
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.08);
    font-size: 0.875em;
    padding-block: 0.2rem;
    padding-inline: 0.4rem;
  }

  :deep(pre code) {
    padding: 0;
    background: none;
  }

  :deep(ul, ol) {
    margin-block: 0.25rem;
    padding-inline-start: 1.5rem;
  }

  :deep(p:last-child),
  :deep(ul:last-child),
  :deep(ol:last-child) {
    margin-bottom: 0;
  }

  :deep(h1, h2, h3, h4, h5, h6) {
    margin-block: 1rem 0.5rem;
  }

  :deep(.source-reference) {
    color: rgb(var(--v-theme-primary));
    font-weight: 500;
  }

  :deep(.source-link) {
    color: rgb(var(--v-theme-primary));
    font-weight: 500;
    text-decoration: underline;

    &:hover {
      color: rgb(var(--v-theme-primary-darken-1));
    }
  }
}

.sources-section {
  margin-block-start: 1rem;
}

.sources-title {
  font-weight: 600;
  margin-block-end: 0.5rem;
}

.sources-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  .source-number {
    color: rgb(var(--v-theme-primary));
    font-weight: 500;
  }

  .source-link {
    color: rgb(var(--v-theme-primary));
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}

.supabase-file {
  display: flex;
  align-items: center;
}

.files-section {
  margin-block-start: 1rem;
}

.files-title {
  font-weight: 600;
  margin-block-end: 0.5rem;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  .file-icon {
    color: rgb(var(--v-theme-primary));
  }

  .file-link {
    color: rgb(var(--v-theme-primary));
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;

    &:hover {
      text-decoration: underline;
    }
  }

  .file-size {
    color: rgba(var(--v-theme-on-surface), 0.6);
    font-size: 0.75rem;
  }
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0;
  margin-top: 0;
  padding-top: 0;

  :deep(.v-btn--icon.v-btn--size-x-small) {
    width: 20px;
    height: 20px;
    font-size: 14px;
  }

  .message-timestamp {
    margin-inline-start: 4px;
  }
}

.message-timestamp {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

// Edit mode styles
.edit-mode {
  width: 100%;
}

.edit-textarea {
  margin-bottom: 0.5rem;

  :deep(.v-field) {
    background-color: rgb(var(--v-theme-surface));
  }
}

.edit-controls {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
  align-items: center;
}
</style>
