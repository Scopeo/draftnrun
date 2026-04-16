<script setup lang="ts">
import { computed, ref } from 'vue'

import KnowledgeEditor from './KnowledgeEditor.vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import type { EditableChunk } from '@/utils/knowledge'
import { MAX_CHUNK_TOKENS } from '@/utils/tokenizer'

const props = defineProps<{
  chunk: EditableChunk
  index: number
  isDeleting?: boolean
}>()

const emit = defineEmits<{
  (e: 'delete'): void
  (e: 'backspace-at-start'): void
  (e: 'arrow-up-at-start'): void
  (e: 'arrow-down-at-end'): void
  (e: 'split-at-cursor', payload: { before: string; after: string }): void
  (e: 'add-chunk-below'): void
}>()

const editorRef = ref<InstanceType<typeof KnowledgeEditor> | null>(null)
const showDeleteConfirm = ref(false)

const isOversized = computed(() => props.chunk.tokenCount > MAX_CHUNK_TOKENS)

function handleDelete() {
  emit('delete')
  showDeleteConfirm.value = false
}

function focusAtStart() {
  editorRef.value?.focusAtStart()
}

function focusAtEnd() {
  editorRef.value?.focusAtEnd()
}

defineExpose({ focusAtStart, focusAtEnd })
</script>

<template>
  <div class="chunk-section">
    <!-- Separator (skip for first chunk) -->
    <VDivider v-if="index > 0" class="chunk-section__separator" />

    <div class="chunk-section__header">
      <span class="chunk-section__title" :class="{ 'chunk-section__title--error': isOversized }">
        Chunk {{ index + 1 }} · {{ chunk.tokenCount }} tokens
        <VIcon v-if="isOversized" icon="tabler-alert-triangle" size="16" color="error" class="ms-1" />
      </span>
      <VChip v-if="isOversized" size="x-small" color="error" variant="flat">
        Exceeds {{ MAX_CHUNK_TOKENS }} limit
      </VChip>
      <VSpacer />
      <IconBtn
        variant="text"
        color="error"
        title="Delete chunk"
        :loading="isDeleting"
        @click="showDeleteConfirm = true"
      >
        <VIcon icon="tabler-trash" />
      </IconBtn>
    </div>

    <GenericConfirmDialog
      v-model:is-dialog-visible="showDeleteConfirm"
      title="Delete Chunk"
      :message="`Are you sure you want to delete <strong>Chunk ${index + 1}</strong>? This action cannot be undone.`"
      confirm-text="Delete"
      confirm-color="error"
      @confirm="handleDelete"
    />

    <div class="chunk-section__content">
      <KnowledgeEditor
        ref="editorRef"
        v-model="chunk.markdown"
        :editable="true"
        @backspace-at-start="emit('backspace-at-start')"
        @arrow-up-at-start="emit('arrow-up-at-start')"
        @arrow-down-at-end="emit('arrow-down-at-end')"
        @split-at-cursor="payload => emit('split-at-cursor', payload)"
        @add-chunk-below="emit('add-chunk-below')"
        @delete-chunk="emit('delete')"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.chunk-section {
  display: flex;
  flex-direction: column;
}

.chunk-section__separator {
  margin-block: 1.5rem 0.75rem;
}

.chunk-section__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-block: 0.5rem;
}

.chunk-section__title {
  display: flex;
  align-items: center;
  font-size: 0.875rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.chunk-section__title--error {
  color: rgb(var(--v-theme-error));
}

.chunk-section__content {
  overflow: hidden;
  min-block-size: 100px;
}
</style>
