<script setup lang="ts">
import { computed } from 'vue'
import MDContent from '@/components/MDContent.vue'
import { useImageUtils } from '@/composables/useImageUtils'

const props = withDefaults(
  defineProps<{
    content: any
    showTimestamps?: boolean
  }>(),
  {
    showTimestamps: true,
  }
)

// Use image utilities
const { openImageModal, downloadImage } = useImageUtils()

const contentType = computed(() => {
  if (typeof props.content === 'string') {
    // Try to parse if it looks like JSON with artifacts text
    try {
      const artifactsMatch = props.content.match(/^(.*)\s*\[.*?image.*?artifacts.*?\]\s*$/s)
      if (artifactsMatch) {
        const parsed = JSON.parse(artifactsMatch[1])
        if (parsed.results && Array.isArray(parsed.results) && parsed.results.some((result: any) => result.png)) {
          return 'results_with_images'
        }
      }
    } catch (e) {
      // Ignore parsing errors
    }
    return 'text'
  }

  // Check for array containing mixed content
  if (Array.isArray(props.content) && props.content.length > 0) {
    // Handle both old format (JSON strings) and new format (direct objects)
    const parsedContent = props.content.map(item => {
      if (typeof item === 'string') {
        try {
          // Try to parse JSON strings (old format)
          return JSON.parse(item)
        } catch (error: unknown) {
          return item
        }
      }
      // Item is already an object (new format)
      return item
    })

    // Check for results with images (after parsing)
    for (const item of parsedContent) {
      if (typeof item === 'object' && item !== null) {
        if (item.results && Array.isArray(item.results) && item.results.some((result: any) => result.png)) {
          return 'results_with_images'
        }
      }
    }

    // Check for chat data - direct message objects
    const hasDirectMessages = parsedContent.some(
      item => item && typeof item === 'object' && item.role && (item.content || item.tool_calls || item.tool_call_id)
    )

    // Check for chat data - objects with messages arrays
    const hasMessagesArray = parsedContent.some(
      item =>
        item &&
        typeof item === 'object' &&
        item.messages &&
        Array.isArray(item.messages) &&
        item.messages.every((msg: any) => msg.role && msg.content)
    )

    // Check for complex chat objects (like the new format)
    const hasComplexChat = parsedContent.some(
      item => item && typeof item === 'object' && (item.conversation_id || item.messages)
    )

    // Check for objects with message property containing chat data
    const hasMessageProperty = parsedContent.some(
      item =>
        item &&
        typeof item === 'object' &&
        item.message &&
        item.message.role &&
        (item.message.content || item.message.tool_calls || item.message.tool_call_id)
    )

    if (hasDirectMessages || hasMessagesArray || hasComplexChat || hasMessageProperty) {
      return 'chat'
    }

    // Check for documents
    if (parsedContent.every(item => item && typeof item === 'object' && item.document)) {
      return 'documents'
    }

    // If all items are strings, treat as text
    if (props.content.every(item => typeof item === 'string')) {
      return 'text'
    }
  }

  // Check for single object with messages array
  if (props.content && typeof props.content === 'object' && !Array.isArray(props.content)) {
    if (
      props.content.messages &&
      Array.isArray(props.content.messages) &&
      props.content.messages.every((msg: any) => msg.role && msg.content)
    ) {
      return 'chat'
    }
  }

  return 'json'
})

const formatText = computed(() => {
  if (Array.isArray(props.content)) {
    // Parse JSON strings and extract text content
    const textContent = props.content.map(item => {
      if (typeof item === 'string') {
        try {
          const parsed = JSON.parse(item)
          // If it's a parsed object, convert back to readable text
          return JSON.stringify(parsed, null, 2)
        } catch (error: unknown) {
          return item
        }
      }
      // If it's already an object, stringify it
      return JSON.stringify(item, null, 2)
    })

    return textContent.join('\n\n')
  }
  return props.content
})

const chatMessages = computed(() => {
  if (contentType.value !== 'chat') return []

  const messages: any[] = []

  // Handle single object with messages array
  if (!Array.isArray(props.content) && props.content.messages) {
    for (const msg of props.content.messages) {
      messages.push({
        content: msg.content,
        role: msg.role,
        timestamp: msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      })
    }
    return messages
  }

  // Handle array content
  if (Array.isArray(props.content) && props.content.length > 0) {
    // Handle both old format (JSON strings) and new format (direct objects)
    const parsedContent = props.content.map(item => {
      if (typeof item === 'string') {
        try {
          // Try to parse JSON strings (old format)
          return JSON.parse(item)
        } catch (error: unknown) {
          return item
        }
      }
      // Item is already an object (new format)
      return item
    })

    // Process each item in the parsed content
    for (const item of parsedContent) {
      // Handle objects with conversation_id and messages (new format)
      if (item && typeof item === 'object' && item.conversation_id && item.messages) {
        for (const msg of item.messages) {
          // Handle complex content for conversation messages
          let processedContent = ''
          if (Array.isArray(msg.content)) {
            processedContent = msg.content
              .map((contentItem: any) => {
                if (contentItem.type === 'image_url' && contentItem.image_url?.url) {
                  // Create markdown image syntax for proper display
                  return `![Image](${contentItem.image_url.url})`
                } else if (contentItem.text) {
                  return contentItem.text
                } else if (typeof contentItem === 'string') {
                  return contentItem
                } else {
                  return JSON.stringify(contentItem, null, 2)
                }
              })
              .join('\n')
          } else if (typeof msg.content === 'object' && msg.content !== null) {
            processedContent = JSON.stringify(msg.content, null, 2)
          } else {
            processedContent = msg.content || ''
          }

          messages.push({
            content: processedContent,
            role: msg.role,
            timestamp: msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          })
        }
      }
      // Handle objects with messages arrays
      else if (item && typeof item === 'object' && item.messages && Array.isArray(item.messages)) {
        for (const msg of item.messages) {
          // Handle complex content for regular messages
          let processedContent = ''
          if (Array.isArray(msg.content)) {
            processedContent = msg.content
              .map((contentItem: any) => {
                if (contentItem.type === 'image_url' && contentItem.image_url?.url) {
                  // Create markdown image syntax for proper display
                  return `![Image](${contentItem.image_url.url})`
                } else if (contentItem.text) {
                  return contentItem.text
                } else if (typeof contentItem === 'string') {
                  return contentItem
                } else {
                  return JSON.stringify(contentItem, null, 2)
                }
              })
              .join('\n')
          } else if (typeof msg.content === 'object' && msg.content !== null) {
            processedContent = JSON.stringify(msg.content, null, 2)
          } else {
            processedContent = msg.content || ''
          }

          messages.push({
            content: processedContent,
            role: msg.role,
            timestamp: msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          })
        }
      }
      // Handle objects with message property (nested message structure)
      else if (item && typeof item === 'object' && item.message && item.message.role) {
        messages.push({
          content: item.message.content || '',
          role: item.message.role,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          tool_calls: item.message.tool_calls || undefined,
          tool_call_id: item.message.tool_call_id || undefined,
        })
      }
      // Handle direct message objects
      else if (
        item &&
        typeof item === 'object' &&
        item.role &&
        (item.content || item.tool_calls || item.tool_call_id)
      ) {
        // Handle complex content (arrays, objects) by converting to readable format
        let processedContent = ''
        if (Array.isArray(item.content)) {
          // Handle array content (like image_url structures)
          processedContent = item.content
            .map((contentItem: any) => {
              if (contentItem.type === 'image_url' && contentItem.image_url?.url) {
                // Create markdown image syntax for proper display
                return `![Image](${contentItem.image_url.url})`
              } else if (contentItem.text) {
                return contentItem.text
              } else if (typeof contentItem === 'string') {
                return contentItem
              } else {
                return JSON.stringify(contentItem, null, 2)
              }
            })
            .join('\n')
        } else if (typeof item.content === 'object' && item.content !== null) {
          processedContent = JSON.stringify(item.content, null, 2)
        } else {
          processedContent = item.content || ''
        }

        messages.push({
          content: processedContent,
          role: item.role,
          timestamp: item.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          tool_calls: item.tool_calls || undefined,
          tool_call_id: item.tool_call_id || undefined,
        })
      }
      // Handle strings as simple text messages
      else if (typeof item === 'string') {
        messages.push({
          content: item,
          role: 'assistant',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        })
      }
    }
  }

  return messages
})

const documents = computed(() => {
  if (contentType.value !== 'documents') return []

  return props.content.map((item: any) => ({
    id: item.document.id,
    content: item.document.content,
    name: item.document.content.split('\n')[0] || 'Untitled Document',
  }))
})

const resultsWithImages = computed(() => {
  if (contentType.value !== 'results_with_images') return []

  // Helper function to extract results from JSON string
  const extractResults = (str: string) => {
    try {
      const artifactsMatch = str.match(/^(.*)\s*\[.*?image.*?artifacts.*?\]\s*$/s)
      if (artifactsMatch) {
        const parsed = JSON.parse(artifactsMatch[1])
        if (parsed.results && Array.isArray(parsed.results)) {
          return parsed.results.filter((result: any) => result.png || result.text)
        }
      }
    } catch (e) {
      // Ignore parsing errors
    }
    return []
  }

  // Handle single string
  if (typeof props.content === 'string') {
    return extractResults(props.content)
  }

  // Handle array of strings
  if (Array.isArray(props.content)) {
    for (const item of props.content) {
      if (typeof item === 'string') {
        const results = extractResults(item)
        if (results.length > 0) {
          return results
        }
      }
    }
  }

  return []
})

// Function to download image from base64
const downloadImageFromBase64 = (base64: string, index: number) => {
  downloadImage(base64, index, `generated-chart-${index + 1}.png`)
}
</script>

<template>
  <div class="content-display">
    <!-- Text Display -->
    <div v-if="contentType === 'text'" class="text-content">
      <MDContent :content="formatText" />
    </div>

    <!-- Chat Display -->
    <div v-else-if="contentType === 'chat'" class="chat-content">
      <div class="chat-messages">
        <div v-for="(message, index) in chatMessages" :key="index" class="message-wrapper" :class="message.role">
          <div class="message-container">
            <VAvatar
              size="36"
              :color="message.role === 'assistant' || message.role === 'system' ? 'primary' : 'secondary'"
              class="message-avatar"
            >
              <VIcon
                :icon="message.role === 'assistant' || message.role === 'system' ? 'tabler-robot' : 'tabler-user'"
                color="white"
                size="20"
              />
            </VAvatar>
            <div class="message-content">
              <div class="message-header">
                <span class="text-high-emphasis font-weight-medium">
                  {{ message.role === 'assistant' ? 'Agent' : message.role === 'system' ? 'System' : 'You' }}
                </span>
                <span v-if="showTimestamps" class="text-disabled text-sm">{{ message.timestamp }}</span>
              </div>
              <div class="message-text">
                <MDContent :content="message.content" />
              </div>

              <!-- Tool Calls -->
              <div v-if="message.tool_calls && message.tool_calls.length > 0" class="tool-calls-section">
                <div class="tool-calls-header">
                  <VIcon icon="tabler-tools" size="16" class="me-2" />
                  <span class="text-caption font-weight-medium">Tool Calls ({{ message.tool_calls.length }})</span>
                </div>

                <div class="tool-calls-list">
                  <VCard
                    v-for="(toolCall, idx) in message.tool_calls"
                    :key="toolCall.id || idx"
                    variant="outlined"
                    class="tool-call-card mb-2"
                  >
                    <VCardText class="pa-3">
                      <div class="d-flex align-center mb-2">
                        <VChip size="small" color="primary" variant="tonal" class="me-2">
                          {{ toolCall.type || 'function' }}
                        </VChip>
                        <span class="font-weight-medium text-high-emphasis">{{ toolCall.function?.name }}</span>
                      </div>

                      <div class="tool-arguments">
                        <span class="text-caption text-medium-emphasis">Arguments:</span>
                        <div class="mt-1">
                          <VCard variant="flat" color="surface">
                            <VCardText class="pa-2">
                              <pre class="text-caption" style="color: black">{{ toolCall.function?.arguments }}</pre>
                            </VCardText>
                          </VCard>
                        </div>
                      </div>
                    </VCardText>
                  </VCard>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Results with Images -->
    <div v-else-if="contentType === 'results_with_images'" class="results-content">
      <div class="results-list">
        <div v-for="(result, idx) in resultsWithImages" :key="idx" class="result-item mb-4">
          <!-- Text content -->
          <div v-if="result.text" class="result-text mb-3">
            <MDContent :content="result.text" />
          </div>

          <!-- Image content -->
          <div v-if="result.png" class="result-image">
            <VCard variant="outlined" class="image-card">
              <div class="image-container" @click="openImageModal(result.png, idx)">
                <VImg
                  :src="`data:image/png;base64,${result.png}`"
                  :alt="`Generated chart ${idx + 1}`"
                  class="generated-image"
                  contain
                />
                <VBtn
                  icon="tabler-download"
                  variant="elevated"
                  color="secondary"
                  size="small"
                  class="download-btn"
                  @click.stop="downloadImageFromBase64(result.png, idx)"
                />
              </div>

              <!-- Chart metadata if available -->
              <VCardText v-if="result.chart" class="pa-3">
                <div class="text-caption text-medium-emphasis">
                  <strong>Chart Type:</strong> {{ result.chart.type }}<br />
                  <strong>Title:</strong> {{ result.chart.title }}
                </div>
              </VCardText>
            </VCard>
          </div>
        </div>
      </div>
    </div>

    <!-- Documents Display -->
    <div v-else-if="contentType === 'documents'" class="documents-content">
      <VExpansionPanels variant="accordion">
        <VExpansionPanel v-for="doc in documents" :key="doc.id" class="document-panel">
          <VExpansionPanelTitle class="py-2">
            {{ doc.name.replace(/^\*\*|\*\*$/g, '') }}
          </VExpansionPanelTitle>
          <VExpansionPanelText>
            <div class="document-content bg-surface rounded pa-4">
              <MDContent :content="doc.content" />
            </div>
          </VExpansionPanelText>
        </VExpansionPanel>
      </VExpansionPanels>
    </div>

    <!-- JSON Display -->
    <div v-else class="json-content">
      <pre>{{ JSON.stringify(content, null, 2) }}</pre>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.content-display {
  block-size: 100%;
  inline-size: 100%;
}

.text-content {
  :deep(p) {
    margin-block: 0.5rem;
    white-space: pre-wrap;
  }

  :deep(pre) {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.chat-content {
  .chat-messages {
    padding: 0.5rem 0.25rem 0.5rem 0.25rem;
  }

  .message-wrapper {
    margin-block-end: 0.5rem;

    &.assistant .message-container,
    &.system .message-container {
      background-color: rgba(var(--v-theme-primary), 0.05);
    }
  }

  /* stylelint-disable-next-line no-descending-specificity */
  .message-container {
    display: flex;
    padding: 0.5rem;
    border-radius: 6px;
    gap: 0.5rem;
  }

  .message-content {
    flex-grow: 1;
  }

  .message-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-block-end: 0.25rem;
  }

  .message-text {
    margin: 0;
    line-height: 1.5;

    :deep(p) {
      margin-block: 0.25rem;
      white-space: pre-wrap;
    }
  }
}

.json-content {
  pre {
    padding: 1rem;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.documents-content {
  .document-panel {
    margin-block-end: 0.5rem;
  }

  .document-content {
    :deep(p) {
      line-height: 1.5;
      margin-block: 0.5rem;
    }

    :deep(h1, h2, h3, h4, h5, h6) {
      margin-block: 1rem 0.5rem;
    }

    :deep(ul, ol) {
      margin-block: 0.5rem;
      padding-inline-start: 1.5rem;
    }

    :deep(a) {
      color: rgb(var(--v-theme-primary));
      text-decoration: none;

      &:hover {
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
  }
}

.tool-calls-section {
  margin-block-start: 1rem;
}

.tool-calls-header {
  display: flex;
  align-items: center;
  color: rgb(var(--v-theme-primary));
  margin-block-end: 0.75rem;
}

.tool-call-card {
  border-inline-start: 3px solid rgb(var(--v-theme-primary));
}

.tool-arguments {
  pre {
    margin: 0;
    max-block-size: 200px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.results-content {
  .results-list {
    padding: 1.5rem;
  }

  .result-item {
    margin-block-end: 1.5rem;
  }

  .result-text {
    margin-block-end: 0.75rem;
  }

  .result-image {
    margin-block-start: 0.75rem;
  }

  .image-card {
    overflow: hidden;
    border-radius: 8px;
    max-inline-size: 600px;
  }

  .image-container {
    position: relative;
    cursor: pointer;

    &:hover .download-btn {
      opacity: 1;
    }
  }

  .generated-image {
    inline-size: 100%;
    max-block-size: 400px;
  }

  .download-btn {
    position: absolute;
    z-index: 1;
    backdrop-filter: blur(4px);
    inset-block-start: 8px;
    inset-inline-end: 8px;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
}
</style>
