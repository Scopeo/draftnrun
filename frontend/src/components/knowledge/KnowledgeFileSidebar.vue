<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import type { KnowledgeFileSummary } from '@/composables/queries/useKnowledgeQueries'

const props = defineProps<{
  files: KnowledgeFileSummary[]
  selectedFileId?: string
  isLoading?: boolean
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'selectFile', fileId: string): void
  (e: 'deleteFile', fileId: string): void
}>()

const filesSearch = ref('')
const fileListRef = ref<HTMLElement | null>(null)
const sidebarRef = ref<HTMLElement | null>(null)

const filteredFiles = computed(() => {
  if (!filesSearch.value.trim()) return props.files

  const query = filesSearch.value.trim().toLowerCase()

  return props.files.filter(
    file => file.file_id.toLowerCase().includes(query) || file.title?.toLowerCase().includes(query)
  )
})

watch(
  filteredFiles,
  async () => {
    await nextTick()
    resetSidebarScroll()
  },
  { flush: 'post' }
)

function resetSidebarScroll() {
  const scrollTarget = fileListRef.value ?? sidebarRef.value
  if (!scrollTarget) return

  if (typeof scrollTarget.scrollTo === 'function') scrollTarget.scrollTo({ top: 0 })
  else scrollTarget.scrollTop = 0
}

function handleSelectFile(fileId: string) {
  if (fileId && fileId !== props.selectedFileId) emit('selectFile', fileId)
}
</script>

<template>
  <aside ref="sidebarRef" class="knowledge-file-sidebar">
    <VTextField
      v-model="filesSearch"
      placeholder="Search files"
      density="compact"
      clearable
      prepend-inner-icon="tabler-search"
      class="flex-grow-0"
    />

    <div v-if="isLoading" class="knowledge-file-sidebar__loading">
      <VProgressCircular indeterminate size="24" />
      <span class="text-body-2 text-medium-emphasis">Loading files...</span>
    </div>

    <div v-else-if="filteredFiles.length" ref="fileListRef" class="knowledge-file-sidebar__list">
      <VList density="compact">
        <VListItem
          v-for="file in filteredFiles"
          :key="file.file_id"
          :class="{ 'is-active': file.file_id === selectedFileId }"
          @click="handleSelectFile(file.file_id)"
        >
          <VListItemTitle class="text-truncate">
            {{ file.title?.trim() || file.file_id }}
          </VListItemTitle>
          <VListItemSubtitle class="knowledge-file-sidebar__subtitle">
            {{ file.chunk_count }} chunks · {{ file.last_edited_ts || '—' }}
          </VListItemSubtitle>

          <template v-if="editable" #append>
            <IconBtn
              size="x-small"
              variant="text"
              color="error"
              title="Delete file"
              @click.stop="emit('deleteFile', file.file_id)"
            >
              <VIcon icon="tabler-trash" size="16" />
            </IconBtn>
          </template>
        </VListItem>
      </VList>
    </div>

    <div v-else class="knowledge-file-sidebar__empty">
      <VIcon icon="tabler-folder-open" size="32" class="mb-2" />
      <span class="text-body-2 text-medium-emphasis">No files found for this source.</span>
    </div>
  </aside>
</template>

<style scoped lang="scss">
.knowledge-file-sidebar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-inline-end: 0.5rem;
  padding-block-end: 1rem;
  border-inline-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background-color: rgb(var(--v-theme-surface));
  block-size: 100%;
  max-block-size: 100%;
  overflow-y: auto;
}

.knowledge-file-sidebar__list {
  flex: 1;
  overflow: auto;
  margin-block-start: 0.5rem;
}

.knowledge-file-sidebar__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding-block: 2rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

:deep(.knowledge-file-sidebar__subtitle) {
  display: block;
  overflow: visible;
  text-overflow: unset;
  white-space: normal;
  line-clamp: unset;
  -webkit-line-clamp: unset;
}

.knowledge-file-sidebar__list .v-list-item.is-active {
  background-color: rgba(var(--v-theme-primary), 0.12);
}

.knowledge-file-sidebar__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.5rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

@media (max-width: 1180px) {
  .knowledge-file-sidebar {
    border-inline-end: none;
    border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
    padding-block-end: 1rem;
    block-size: auto;
    max-block-size: none;
    overflow: visible;
  }
}
</style>
