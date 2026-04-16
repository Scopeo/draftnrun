<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    uploadedFiles: File[]
    isTyping: boolean
    isStreaming: boolean
    hasMessages: boolean
    displayTitle: string
    showSendButton?: boolean
    showClearChat?: boolean
    showWelcome?: boolean
    showSetIdsSelector: boolean
    availableSetIds: string[]
    selectedSetIds: string[]
    isSetIdsLoading: boolean
    isSetIdsError: boolean
  }>(),
  { showSendButton: true, showClearChat: true, showWelcome: true }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:selectedSetIds': [value: string[]]
  send: []
  clear: []
  keydown: [event: KeyboardEvent]
  'file-select': [event: Event]
  'remove-file': [index: number]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const triggerFileInput = () => fileInput.value?.click()
</script>

<template>
  <div v-if="hasMessages && showClearChat" class="d-flex justify-end mb-2">
    <VBtn variant="text" color="primary" size="small" prepend-icon="tabler-reload" @click="emit('clear')">
      Clear Chat
    </VBtn>
  </div>

  <div v-if="!hasMessages && showWelcome" class="welcome-message">
    <VIcon icon="tabler-message-circle" size="24" color="primary" class="mb-2" />
    <p class="text-body-1 text-center">Start a conversation with {{ displayTitle }}</p>
  </div>

  <!-- Compact File Display -->
  <div v-if="uploadedFiles.length > 0" class="uploaded-files-compact mb-2">
    <div v-for="(file, index) in uploadedFiles" :key="index" class="file-chip">
      <VIcon
        :icon="
          file.type.startsWith('image/')
            ? 'tabler-photo'
            : file.type === 'application/pdf'
              ? 'tabler-file-type-pdf'
              : 'tabler-file-text'
        "
        size="12"
        class="me-1"
      />
      <span class="file-name-small">{{ file.name }}</span>
      <VBtn icon size="x-small" variant="text" color="error" class="remove-btn" @click="emit('remove-file', index)">
        <VIcon icon="tabler-x" size="10" />
      </VBtn>
    </div>
  </div>

  <input
    ref="fileInput"
    type="file"
    accept=".txt,.pdf,.doc,.docx,.md,.png,.jpg,.jpeg,.gif,.webp"
    style="display: none"
    @change="emit('file-select', $event)"
  />

  <!-- Variable Set IDs selector -->
  <div v-if="showSetIdsSelector" class="d-flex align-center gap-2 mb-2">
    <VMenu open-on-hover location="top" :close-on-content-click="false">
      <template #activator="{ props: menuProps }">
        <VIcon
          v-bind="menuProps"
          icon="tabler-help-circle"
          size="18"
          class="text-medium-emphasis cursor-pointer flex-shrink-0"
        />
      </template>
      <VCard max-width="280" variant="elevated">
        <VCardText class="text-body-2 pa-4">
          Named groups of variable values injected at runtime — e.g. select "production" or "staging" to test with
          different environment values.
        </VCardText>
      </VCard>
    </VMenu>
    <VSelect
      :model-value="selectedSetIds"
      :items="availableSetIds"
      label="Variable sets"
      multiple
      chips
      closable-chips
      density="compact"
      variant="outlined"
      hide-details
      :loading="isSetIdsLoading"
      :no-data-text="isSetIdsError ? 'Failed to load variable sets' : 'No variable sets for this project'"
      style="flex: 1"
      @update:model-value="emit('update:selectedSetIds', $event as string[])"
    />
  </div>

  <VTextarea
    :model-value="modelValue"
    placeholder="Ask something..."
    variant="outlined"
    density="compact"
    hide-details
    rows="2"
    auto-grow
    max-rows="4"
    class="chat-textarea"
    @update:model-value="emit('update:modelValue', $event as string)"
    @keydown="emit('keydown', $event)"
  >
    <template #prepend-inner>
      <VBtn icon size="small" variant="text" color="primary" class="attach-button" @click="triggerFileInput">
        <VIcon icon="tabler-paperclip" size="18" />
      </VBtn>
    </template>
    <template v-if="showSendButton" #append-inner>
      <VBtn
        color="primary"
        icon
        size="x-small"
        class="send-button"
        :disabled="!modelValue.trim() || isTyping || isStreaming"
        @click="emit('send')"
      >
        <VIcon icon="tabler-send" size="14" />
      </VBtn>
    </template>
  </VTextarea>
</template>

<style lang="scss" scoped>
.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 1rem;

  p {
    color: rgba(var(--v-theme-on-surface), 0.7);
    margin: 0;
  }
}

.uploaded-files-compact {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: rgba(var(--v-theme-primary), 0.1);
  border: 1px solid rgba(var(--v-theme-primary), 0.3);
  border-radius: 12px;
  font-size: 0.75rem;
  max-width: 200px;

  .file-name-small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: rgb(var(--v-theme-primary));
    font-weight: 500;
  }

  .remove-btn {
    margin-left: 0.25rem;
    width: 16px;
    height: 16px;
  }
}

.chat-textarea {
  :deep(.v-field) {
    border-radius: 20px;
  }

  :deep(.v-field__input) {
    min-height: 44px;
    padding: 8px 12px;
  }

  :deep(.v-field__prepend-inner) {
    align-items: flex-end;
    padding-bottom: 6px;
  }

  :deep(.v-field__append-inner) {
    align-items: flex-end;
    padding-bottom: 6px;
  }
}

.send-button {
  margin-inline-end: 0.25rem;
}

.attach-button {
  margin-inline-start: 0.25rem;
}
</style>
