<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'

import KnowledgeFileSidebar from './KnowledgeFileSidebar.vue'
import KnowledgeChunkCard from './KnowledgeChunkCard.vue'
import { logger } from '@/utils/logger'
import type { Source } from '@/composables/queries/useDataSourcesQuery'
import {
  type KnowledgeFileSummary,
  type UpdateDocumentChunksPayload,
  useDeleteKnowledgeChunkMutation,
  useDeleteKnowledgeFileMutation,
  useKnowledgeFileDetailQuery,
  useKnowledgeFilesQuery,
  useUpdateDocumentChunksMutation,
} from '@/composables/queries/useKnowledgeQueries'
import { type EditableChunk, createEmptyChunk, toEditableChunks, totalTokenCount } from '@/utils/knowledge'
import { countTokens } from '@/utils/tokenizer'

const props = defineProps<{
  organizationId?: string
  source: Source
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const organizationIdRef = computed(() => props.organizationId)
const sourceIdRef = computed(() => props.source?.id ?? undefined)

const selectedFileId = ref<string | undefined>()
const chunks = ref<EditableChunk[]>([])
const initialChunks = ref<EditableChunk[]>([])
const deletedChunkIds = ref<string[]>([])
const isSaving = ref(false)
const isDirty = ref(false)
const chunkCardRefs = ref<Map<string, InstanceType<typeof KnowledgeChunkCard>>>(new Map())

const SNACKBAR_TIMEOUT_MS = 3000

const snackbarMessage = ref('')
const snackbarColor = ref<'success' | 'error'>('success')
const snackbarVisible = ref(false)

const filesQuery = useKnowledgeFilesQuery(organizationIdRef, sourceIdRef)
const fileDetailQuery = useKnowledgeFileDetailQuery(organizationIdRef, sourceIdRef, selectedFileId)
const deleteChunkMutation = useDeleteKnowledgeChunkMutation()
const deleteFileMutation = useDeleteKnowledgeFileMutation()
const updateChunksMutation = useUpdateDocumentChunksMutation()

// File deletion confirmation
const deleteFileDialogVisible = ref(false)
const fileToDelete = ref<string | null>(null)
const isFileDeleting = ref(false)

const refetchFileDetail = fileDetailQuery.refetch
const refetchFiles = filesQuery.refetch

const files = computed<KnowledgeFileSummary[]>(() => filesQuery.data.value?.items ?? [])

const hasFilesError = computed(() => filesQuery.isError.value)
const hasFileDetailError = computed(() => fileDetailQuery.isError.value)

const activeFile = computed(() => files.value.find(file => file.file_id === selectedFileId.value) ?? null)

const activeFileDetail = computed(() => fileDetailQuery.data.value?.file ?? null)

const totalTokens = computed(() => totalTokenCount(chunks.value))

// Simple dirty flag - set on any edit, reset on save/load
const hasChanges = computed(() => isDirty.value || deletedChunkIds.value.length > 0)

watch(files, newFiles => {
  if (!newFiles.length) {
    selectedFileId.value = undefined
    chunks.value = []

    return
  }

  if (!selectedFileId.value || !newFiles.some(file => file.file_id === selectedFileId.value))
    selectFile(newFiles[0].file_id)
})

watch(
  () => fileDetailQuery.data.value,
  detail => {
    if (detail) {
      const editableChunks = toEditableChunks(detail.chunks)

      chunks.value = editableChunks
      // Use structuredClone for deep copy to avoid shared references
      initialChunks.value = structuredClone(editableChunks)
      deletedChunkIds.value = []
      isDirty.value = false
    } else {
      chunks.value = []
      initialChunks.value = []
      deletedChunkIds.value = []
      isDirty.value = false
    }
  },
  { immediate: true }
)

watch(
  () => sourceIdRef.value,
  () => {
    if (props.organizationId && sourceIdRef.value) refetchFiles()
  }
)

// Debounced token count update for all chunks
const updateTokenCounts = useDebounceFn(() => {
  chunks.value.forEach(chunk => {
    chunk.tokenCount = countTokens(chunk.markdown)
  })
}, 300)

// Watch for changes in chunk markdown content - mark as dirty
watch(
  () => chunks.value.map(c => c.markdown),
  (_newValues, oldValues) => {
    updateTokenCounts()
    // Only mark dirty if there were previous values (not initial load)
    if (oldValues && oldValues.length > 0) {
      isDirty.value = true
    }
  },
  { deep: true }
)

function selectFile(fileId: string) {
  if (!fileId || selectedFileId.value === fileId) return

  selectedFileId.value = fileId
  chunks.value = []

  if (props.organizationId && sourceIdRef.value) refetchFileDetail()
}

function showSnackbar(message: string, color: 'success' | 'error' = 'success') {
  snackbarMessage.value = message
  snackbarColor.value = color
  snackbarVisible.value = true
}

function handleDeleteChunk(chunk: EditableChunk) {
  // Track deleted chunk if it existed on backend
  if (chunk.originalChunkId) deletedChunkIds.value.push(chunk.originalChunkId)

  // Remove from local list
  const index = chunks.value.findIndex(c => c.chunkId === chunk.chunkId)

  if (index !== -1) {
    chunks.value.splice(index, 1)
    isDirty.value = true

    // If all chunks deleted, add a new empty chunk
    if (chunks.value.length === 0) {
      const newChunk = createEmptyChunk()

      chunks.value.push(newChunk)
      nextTick(() => {
        chunkCardRefs.value.get(newChunk.chunkId)?.focusAtStart()
      })
      return
    }

    // Focus on preceding chunk (or next if deleting first)
    nextTick(() => {
      const focusIndex = index > 0 ? index - 1 : 0
      const chunkToFocus = chunks.value[focusIndex]
      if (chunkToFocus) {
        chunkCardRefs.value.get(chunkToFocus.chunkId)?.focusAtEnd()
      }
    })
  }
}

function handleAddChunkBelow(index: number) {
  // Insert new empty chunk after the given index
  const newChunk = createEmptyChunk()

  chunks.value.splice(index + 1, 0, newChunk)
  isDirty.value = true

  // Auto-focus the new chunk after Vue renders it
  nextTick(() => {
    chunkCardRefs.value.get(newChunk.chunkId)?.focusAtStart()
  })
}

function handleMergeChunk(index: number) {
  if (index <= 0) return // Can't merge first chunk

  const prevChunk = chunks.value[index - 1]
  const currentChunk = chunks.value[index]

  // Track if we're deleting an existing chunk from backend
  if (currentChunk.originalChunkId) deletedChunkIds.value.push(currentChunk.originalChunkId)

  // Combine markdown with newline separator
  prevChunk.markdown = `${prevChunk.markdown}\n\n${currentChunk.markdown}`.trim()
  prevChunk.tokenCount = countTokens(prevChunk.markdown)

  // Remove current chunk
  chunks.value.splice(index, 1)
  isDirty.value = true
}

function handleSplitAtCursor(index: number, payload: { before: string; after: string }) {
  const currentChunk = chunks.value[index]

  // Update current chunk with "before" content
  currentChunk.markdown = payload.before
  currentChunk.tokenCount = countTokens(payload.before)

  // Create new chunk with "after" content
  const newChunk: EditableChunk = {
    chunkId: crypto.randomUUID(),
    originalChunkId: '',
    markdown: payload.after,
    initialMarkdown: '',
    tokenCount: countTokens(payload.after),
    order: index + 1,
    lastEditedTs: null,
  }

  // Insert new chunk after current
  chunks.value.splice(index + 1, 0, newChunk)
  isDirty.value = true

  // Auto-focus the new chunk after Vue renders it
  nextTick(() => {
    chunkCardRefs.value.get(newChunk.chunkId)?.focusAtStart()
  })
}

function handleArrowUpAtStart(index: number) {
  const prevChunk = chunks.value[index - 1]

  if (prevChunk) {
    nextTick(() => {
      chunkCardRefs.value.get(prevChunk.chunkId)?.focusAtEnd()
    })
  }
}

function handleArrowDownAtEnd(index: number) {
  const nextChunk = chunks.value[index + 1]

  if (nextChunk) {
    // Wait for Vue to render before accessing ref (handles newly created chunks)
    nextTick(() => {
      chunkCardRefs.value.get(nextChunk.chunkId)?.focusAtStart()
    })
  }
}

async function handleSave() {
  const orgId = props.organizationId
  const sourceId = sourceIdRef.value
  const fileId = selectedFileId.value

  if (!orgId || !sourceId || !fileId) return

  isSaving.value = true

  try {
    // Find existing chunks that are now empty and should be deleted
    const emptyExistingChunks = chunks.value.filter(
      chunk => chunk.originalChunkId && chunk.markdown.trim().length === 0
    )

    // Combine explicitly deleted chunks with empty existing chunks
    const allChunksToDelete = [...deletedChunkIds.value, ...emptyExistingChunks.map(c => c.originalChunkId)]

    // Delete chunks in parallel using Promise.allSettled for partial success handling
    let failedDeletes: string[] = []
    if (allChunksToDelete.length > 0) {
      const deleteResults = await Promise.allSettled(
        allChunksToDelete.map(chunkId =>
          deleteChunkMutation.mutateAsync({
            organizationId: orgId,
            sourceId,
            chunkId,
          })
        )
      )

      // Track which deletes failed
      failedDeletes = allChunksToDelete.filter((_, index) => deleteResults[index].status === 'rejected')

      // Log failed deletions for debugging
      deleteResults.forEach((result, index) => {
        if (result.status === 'rejected') {
          logger.error(`Failed to delete chunk ${allChunksToDelete[index]}`, { error: result.reason })
        }
      })
    }

    // Filter out empty chunks (OpenAI embeddings API rejects empty/whitespace-only content)
    const nonEmptyChunks = chunks.value.filter(chunk => chunk.markdown.trim().length > 0)

    // Then, batch update remaining chunks
    const chunksPayload: UpdateDocumentChunksPayload[] = nonEmptyChunks.map((chunk, index) => ({
      chunk_id: chunk.originalChunkId || chunk.chunkId,
      order: index,
      content: chunk.markdown,
      last_edited_ts: chunk.lastEditedTs || new Date().toISOString(),
      document_id: fileId,
      document_title: activeFileDetail.value?.title || null,
      url: activeFileDetail.value?.url || null,
      metadata: {
        title: activeFileDetail.value?.title || null,
        url: activeFileDetail.value?.url || null,
      },
    }))

    await updateChunksMutation.mutateAsync({
      organizationId: orgId,
      sourceId,
      documentId: fileId,
      chunks: chunksPayload,
    })

    // Keep failed chunk IDs for retry on next save
    deletedChunkIds.value = failedDeletes

    // Reset dirty flag on successful save (or partial success)
    isDirty.value = false

    // Show appropriate message based on partial success
    if (failedDeletes.length > 0) {
      const successCount = allChunksToDelete.length - failedDeletes.length

      showSnackbar(
        `Saved changes. ${successCount}/${allChunksToDelete.length} deletions succeeded. ${failedDeletes.length} failed.`,
        'error'
      )
    } else {
      showSnackbar('Changes saved successfully')
    }
  } catch (error: unknown) {
    logger.error('Failed to save changes', { error })

    const message = error instanceof Error ? error.message : 'Failed to save changes'

    showSnackbar(message, 'error')
  } finally {
    isSaving.value = false
  }
}

function handleDeleteFileRequest(fileId: string) {
  fileToDelete.value = fileId
  deleteFileDialogVisible.value = true
}

async function confirmDeleteFile() {
  const orgId = props.organizationId
  const sourceId = sourceIdRef.value
  const fileId = fileToDelete.value

  if (!orgId || !sourceId || !fileId) return

  isFileDeleting.value = true

  try {
    await deleteFileMutation.mutateAsync({
      organizationId: orgId,
      sourceId,
      fileId,
    })

    // Clear selection if deleted file was selected
    if (selectedFileId.value === fileId) {
      selectedFileId.value = undefined
      chunks.value = []
    }

    showSnackbar('File deleted successfully')
  } catch (error: unknown) {
    logger.error('Failed to delete file', { error })

    const message = error instanceof Error ? error.message : 'Failed to delete file'

    showSnackbar(message, 'error')
  } finally {
    isFileDeleting.value = false
    deleteFileDialogVisible.value = false
    fileToDelete.value = null
  }
}

function cancelDeleteFile() {
  deleteFileDialogVisible.value = false
  fileToDelete.value = null
}

function requestClose() {
  emit('close')
}

defineExpose({ requestClose })
</script>

<template>
  <div class="knowledge-explorer">
    <KnowledgeFileSidebar
      :files="files"
      :selected-file-id="selectedFileId"
      :is-loading="filesQuery.isLoading.value"
      :editable="editable"
      @select-file="selectFile"
      @delete-file="handleDeleteFileRequest"
    />

    <main class="knowledge-explorer__main">
      <div v-if="hasFilesError" class="knowledge-explorer__error">
        <VIcon icon="tabler-alert-triangle" size="40" color="error" class="mb-2" />
        <span class="text-body-1 text-error mb-2">Failed to load files</span>
        <VBtn variant="outlined" color="error" size="small" @click="refetchFiles"> Try Again </VBtn>
      </div>

      <div v-else-if="hasFileDetailError && selectedFileId" class="knowledge-explorer__error">
        <VIcon icon="tabler-alert-triangle" size="40" color="error" class="mb-2" />
        <span class="text-body-1 text-error mb-2">Failed to load file details</span>
        <VBtn variant="outlined" color="error" size="small" @click="refetchFileDetail"> Try Again </VBtn>
      </div>

      <div v-else-if="fileDetailQuery.isLoading.value && selectedFileId" class="knowledge-explorer__loading">
        <VProgressCircular indeterminate size="48" />
        <span class="text-body-1 text-medium-emphasis mt-3">Loading chunks...</span>
      </div>

      <template v-else-if="selectedFileId">
        <VCard class="mb-4 knowledge-explorer__sticky-header">
          <VCardText>
            <div class="d-flex align-center gap-4">
              <div class="flex-grow-1 overflow-hidden">
                <div class="d-flex align-center gap-2 flex-wrap">
                  <span class="text-h6 text-truncate">
                    {{ activeFileDetail?.title || activeFile?.file_id }}
                  </span>
                  <VChip v-if="hasChanges" size="x-small" color="warning" variant="flat" class="flex-shrink-0">
                    Unsaved
                  </VChip>
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ totalTokens }} tokens across {{ chunks.length }} chunks
                </div>
              </div>
              <VBtn
                class="flex-shrink-0"
                color="primary"
                :disabled="!hasChanges"
                :loading="isSaving"
                @click="handleSave"
              >
                <VIcon icon="tabler-device-floppy" start />
                Save
              </VBtn>
            </div>
          </VCardText>
        </VCard>

        <VCard class="mb-4">
          <VCardText>
            <VRow>
              <VCol cols="12" md="6">
                <VTextField
                  :model-value="activeFileDetail?.title?.trim() || ''"
                  label="Document title"
                  variant="outlined"
                  density="comfortable"
                  readonly
                />
              </VCol>
              <VCol cols="12" md="6">
                <VTextField
                  :model-value="activeFileDetail?.url?.trim() || ''"
                  label="Document URL"
                  variant="outlined"
                  density="comfortable"
                  readonly
                />
              </VCol>
            </VRow>
          </VCardText>
        </VCard>

        <VCard class="knowledge-explorer__document">
          <VCardText class="knowledge-explorer__chunks">
            <KnowledgeChunkCard
              v-for="(chunk, index) in chunks"
              :ref="
                el => {
                  if (el) chunkCardRefs.set(chunk.chunkId, el as InstanceType<typeof KnowledgeChunkCard>)
                  else chunkCardRefs.delete(chunk.chunkId)
                }
              "
              :key="chunk.chunkId"
              :chunk="chunk"
              :index="index"
              @delete="handleDeleteChunk(chunk)"
              @backspace-at-start="handleMergeChunk(index)"
              @arrow-up-at-start="handleArrowUpAtStart(index)"
              @arrow-down-at-end="handleArrowDownAtEnd(index)"
              @split-at-cursor="payload => handleSplitAtCursor(index, payload)"
              @add-chunk-below="handleAddChunkBelow(index)"
            />
          </VCardText>
        </VCard>
      </template>

      <div v-else class="knowledge-explorer__empty-main">
        <VIcon icon="tabler-arrows-join" size="40" class="mb-2" />
        <span class="text-body-2 text-medium-emphasis">Select a file from the explorer to view its chunks.</span>
      </div>
    </main>

    <VSnackbar v-model="snackbarVisible" :color="snackbarColor" :timeout="SNACKBAR_TIMEOUT_MS">
      {{ snackbarMessage }}
    </VSnackbar>

    <!-- Delete file confirmation dialog -->
    <VDialog v-model="deleteFileDialogVisible" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6">Delete File</VCardTitle>
        <VCardText> Are you sure you want to delete this file? This action cannot be undone. </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="isFileDeleting" @click="cancelDeleteFile"> Cancel </VBtn>
          <VBtn color="error" :loading="isFileDeleting" @click="confirmDeleteFile"> Delete </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped lang="scss">
.knowledge-explorer {
  display: grid;
  gap: 1.5rem;
  grid-template-columns: minmax(220px, 280px) 1fr;
  flex: 1;
  min-block-size: 0;
  overflow: hidden;
  align-items: stretch;
  position: relative;
}

.knowledge-explorer__main {
  padding-inline-end: 0.5rem;
  display: flex;
  flex-direction: column;
  block-size: 100%;
  max-block-size: 100%;
  min-block-size: 0;
  overflow-y: auto;
  position: relative;
}

:deep(.knowledge-explorer__main > .v-card) {
  block-size: auto;
  min-block-size: unset;
  flex: 0 0 auto;
}

.knowledge-explorer__sticky-header {
  position: sticky;
  inset-block-start: 0;
  z-index: 10;
}

.knowledge-explorer__chunks {
  display: flex;
  flex-direction: column;
}

.knowledge-explorer__empty-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.5rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.knowledge-explorer__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  block-size: 100%;
  min-block-size: 300px;
}

.knowledge-explorer__error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  block-size: 100%;
  min-block-size: 300px;
}

@media (max-width: 1180px) {
  .knowledge-explorer {
    grid-template-columns: 1fr;
    block-size: auto;
  }

  .knowledge-explorer__main {
    block-size: auto;
    max-block-size: none;
    overflow: visible;
  }
}
</style>
