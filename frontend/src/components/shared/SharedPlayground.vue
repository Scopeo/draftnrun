<script setup lang="ts">
import { readonly } from 'vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import SaveToQADialog from '@/components/qa/SaveToQADialog.vue'
import ChatMessages from '@/components/shared/ChatMessages.vue'
import { usePlaygroundSession } from '@/composables/usePlaygroundSession'

interface Props {
  agentId?: string
  projectId?: string
  mode: 'agent' | 'workflow'
  title?: string
}

const props = defineProps<Props>()

const {
  chatMessages,
  isTyping,
  isStreaming,
  newMessage,
  hasAdditionalFields,
  displayTitle,
  messagesContainer,
  uploadedFiles,
  downloadingFiles,
  downloadingResponseFiles,
  showSetIdsSelector,
  availableSetIds,
  selectedSetIds,
  isSetIdsLoading,
  isSetIdsError,
  customFieldsData,
  expandedFields,
  playgroundConfig,
  sendMessage,
  clearChatHandler,
  handleKeyDown,
  handleMessageEdit,
  handleMessageReplay,
  handleFileSelect,
  removeFile,
  handleSourceClick,
  onFileClick,
  openSaveModeDialog,
  showSaveToQADialog,
  selectedQADataset,
  qaDatasets,
  loadingQADatasets,
  savingToQA,
  saveToQAError,
  saveToQASuccess,
  showCreateDataset,
  newDatasetName,
  creatingDataset,
  saveToQA,
  createDataset,
  showClearChatConfirm,
  onConfirmLoadTrace,
  onCancelLoadTrace,
  loadTraceInPlayground,
  isLoadingTrace,
} = usePlaygroundSession(props)

defineExpose({
  loadTraceInPlayground,
  isLoadingTrace: readonly(isLoadingTrace),
})
</script>

<template>
  <div class="agent-playground">
    <VCard class="chat-container" style="max-inline-size: 100%; overflow-x: hidden">
      <VCardText
        class="chat-layout"
        :class="{ 'has-additional-fields': hasAdditionalFields }"
        style="box-sizing: border-box; max-inline-size: 100%; overflow-x: hidden"
      >
        <!-- Simple mode: messages at top -->
        <ChatMessages
          v-if="!hasAdditionalFields"
          ref="messagesContainer"
          :messages="chatMessages"
          :downloading-files="downloadingFiles"
          :downloading-response-files="downloadingResponseFiles"
          @save-to-qa="openSaveModeDialog"
          @source-click="handleSourceClick"
          @file-click="onFileClick"
          @edit-message="handleMessageEdit"
          @replay-message="handleMessageReplay"
        />

        <div v-if="chatMessages.length === 0" class="welcome-state" />

        <div class="chat-input-container bottom" :class="{ 'has-additional-fields': hasAdditionalFields }">
          <div class="input-wrapper">
            <!-- Simple mode -->
            <template v-if="!hasAdditionalFields">
              <PlaygroundInputBar
                v-model="newMessage"
                v-model:selected-set-ids="selectedSetIds"
                :uploaded-files="uploadedFiles"
                :is-typing="isTyping"
                :is-streaming="isStreaming"
                :has-messages="chatMessages.length > 0"
                :display-title="displayTitle"
                :show-set-ids-selector="showSetIdsSelector"
                :available-set-ids="availableSetIds"
                :is-set-ids-loading="isSetIdsLoading"
                :is-set-ids-error="isSetIdsError"
                @send="sendMessage"
                @clear="clearChatHandler"
                @keydown="handleKeyDown"
                @file-select="handleFileSelect"
                @remove-file="removeFile"
              />
            </template>

            <!-- Additional fields mode -->
            <template v-else>
              <div class="playground-with-fields-wrapper">
                <div class="playground-scrollable-content">
                  <!-- Messages + input card -->
                  <VCard variant="outlined" class="messages-card mb-3">
                    <VCardText class="pa-4">
                      <div class="d-flex justify-space-between align-center mb-3">
                        <label class="text-subtitle-1 font-weight-medium text-primary"> messages </label>
                        <VChip size="small" variant="tonal" color="primary">messages</VChip>
                      </div>

                      <ChatMessages
                        :messages="chatMessages"
                        :downloading-files="downloadingFiles"
                        :downloading-response-files="downloadingResponseFiles"
                        container-class="messages-in-card"
                        @save-to-qa="openSaveModeDialog"
                        @source-click="handleSourceClick"
                        @file-click="onFileClick"
                        @edit-message="handleMessageEdit"
                        @replay-message="handleMessageReplay"
                      />

                      <PlaygroundInputBar
                        v-model="newMessage"
                        v-model:selected-set-ids="selectedSetIds"
                        :uploaded-files="uploadedFiles"
                        :is-typing="isTyping"
                        :is-streaming="isStreaming"
                        :has-messages="chatMessages.length > 0"
                        :display-title="displayTitle"
                        :show-send-button="false"
                        :show-clear-chat="false"
                        :show-welcome="false"
                        :show-set-ids-selector="showSetIdsSelector"
                        :available-set-ids="availableSetIds"
                        :is-set-ids-loading="isSetIdsLoading"
                        :is-set-ids-error="isSetIdsError"
                        @keydown="handleKeyDown"
                        @file-select="handleFileSelect"
                        @remove-file="removeFile"
                      />
                    </VCardText>
                  </VCard>

                  <PlaygroundAdditionalFields
                    v-model:custom-fields-data="customFieldsData"
                    v-model:expanded-fields="expandedFields"
                    :playground-field-types="playgroundConfig?.playground_field_types ?? {}"
                  />
                </div>

                <div class="playground-send-button-container">
                  <div v-if="chatMessages.length > 0" class="d-flex justify-end mb-1">
                    <VBtn
                      variant="text"
                      color="primary"
                      size="x-small"
                      prepend-icon="tabler-reload"
                      @click="clearChatHandler"
                    >
                      Clear Chat
                    </VBtn>
                  </div>
                  <VBtn
                    color="primary"
                    block
                    size="default"
                    :disabled="!newMessage.trim() || isTyping || isStreaming"
                    @click="sendMessage"
                  >
                    <VIcon icon="tabler-send" class="me-2" />
                    Send Message
                  </VBtn>
                </div>
              </div>
            </template>
          </div>
        </div>
      </VCardText>
    </VCard>
  </div>

  <SaveToQADialog
    v-model:show-save-to-q-a-dialog="showSaveToQADialog"
    v-model:selected-q-a-dataset="selectedQADataset"
    v-model:show-create-dataset="showCreateDataset"
    v-model:new-dataset-name="newDatasetName"
    :qa-datasets="qaDatasets"
    :loading-q-a-datasets="loadingQADatasets"
    :saving-to-q-a="savingToQA"
    :save-to-q-a-error="saveToQAError"
    :save-to-q-a-success="saveToQASuccess"
    :creating-dataset="creatingDataset"
    @save="saveToQA"
    @create-dataset="createDataset"
  />

  <GenericConfirmDialog
    v-model:is-dialog-visible="showClearChatConfirm"
    title="Load trace in playground"
    message="This will clear your current chat. Do you want to continue?"
    confirm-text="Continue"
    confirm-color="warning"
    @confirm="onConfirmLoadTrace"
    @cancel="onCancelLoadTrace"
  />
</template>

<style lang="scss" scoped>
.agent-playground {
  block-size: 100%;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  position: relative;
  z-index: 1001;
  font-size: 0.85rem;

  :deep(.v-field__input),
  :deep(.v-label),
  :deep(.v-select__selection-text),
  :deep(.v-chip__content),
  :deep(.v-btn),
  :deep(.v-expansion-panel-title),
  :deep(.text-subtitle-1),
  :deep(.text-body-1),
  :deep(.text-body-2) {
    font-size: 0.85rem !important;
  }

  :deep(.chat-messages) .message-text,
  :deep(.chat-messages) .message-user-info,
  :deep(.chat-messages) .markdown-message {
    font-size: 0.85rem !important;
  }
}

.chat-container {
  display: flex;
  flex-direction: column;
  block-size: 100%;
  max-inline-size: 100%;
  overflow: hidden;
  border-radius: 0;
  box-shadow: none;
  border: none;
}

.chat-layout {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
  flex: 1;
  padding: 1rem;
  block-size: 100%;
  max-inline-size: 100%;
}

.welcome-state {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fade-in 0.5s ease-out 0.2s forwards;
  inset: 0;
  opacity: 0;
}

.chat-input-container {
  display: flex;
  flex-shrink: 0;
  justify-content: center;
  padding: 0.5rem 0 0;

  &.bottom {
    background-color: rgb(var(--v-theme-surface));
    border-top: 1px solid rgba(var(--v-border-color), 0.12);
    margin: 0 -1rem -0.5rem;
    padding: 1rem;

    &.has-additional-fields {
      flex: 1;
      min-height: 0;
    }
  }
}

.input-wrapper {
  inline-size: 100%;
  max-inline-size: 100%;

  &:has(.playground-with-fields-wrapper) {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
}

.playground-with-fields-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.playground-scrollable-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  min-height: 0;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(var(--v-theme-on-surface), 0.2);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: rgba(var(--v-theme-on-surface), 0.3);
  }
}

.playground-send-button-container {
  flex-shrink: 0;
  padding-top: 12px;
  border-top: 1px solid rgba(var(--v-border-color), 0.12);
  background: rgb(var(--v-theme-surface));
}

.messages-card {
  transition: all 0.2s ease;

  &:hover {
    box-shadow: 0 2px 8px rgba(var(--v-theme-on-surface), 0.08);
  }
}

:deep(.messages-in-card) {
  max-height: 300px;
  margin-bottom: 1rem;
  overflow-y: auto;
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(1rem);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
