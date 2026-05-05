<script setup lang="ts">
import { computed } from 'vue'
import type { PromptVersionDetail } from '@/api/prompts'

const props = defineProps<{
  version: PromptVersionDetail | null | undefined
  latestVersionNumber: number
  isLoadingVersion: boolean
}>()

const isLatest = computed(() => {
  if (!props.version) return false
  return props.version.version_number === props.latestVersionNumber
})
</script>

<template>
  <div class="version-detail">
    <template v-if="isLoadingVersion">
      <LoadingState message="Loading version..." />
    </template>

    <template v-else-if="!version">
      <EmptyState icon="tabler-click" title="Select a version" description="Pick a version from the list to view its details." />
    </template>

    <template v-else>
      <div class="version-detail__header">
        <div class="d-flex align-center gap-4 flex-wrap">
          <span class="text-body-2 text-medium-emphasis me-2"># {{ version.version_number }}</span>
          <h3 class="text-h5 me-2">{{ version.name }}</h3>
          <VChip v-if="isLatest" size="small" variant="flat" color="default" label> Latest </VChip>
        </div>
      </div>

      <VDivider />

      <div class="version-detail__body">
        <div class="pa-4">
          <h4 class="text-subtitle-1 font-weight-medium mb-3">Text Prompt</h4>
          <div class="version-detail__content">
            {{ version.content }}
          </div>
        </div>

      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.version-detail {
  display: flex;
  flex-direction: column;
  block-size: 100%;

  &__header {
    padding: 20px 24px 12px;
  }

  &__body {
    flex: 1;
    overflow-y: auto;
  }

  &__content {
    background: rgba(var(--v-theme-on-surface), 0.03);
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    border-radius: 8px;
    padding: 16px;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 0.875rem;
    line-height: 1.6;
  }

}
</style>
