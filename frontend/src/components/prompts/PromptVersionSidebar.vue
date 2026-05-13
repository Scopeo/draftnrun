<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { computed, ref } from 'vue'
import { format } from 'date-fns'
import type { PromptVersionSummary } from '@/api/prompts'

const props = defineProps<{
  versions: PromptVersionSummary[]
  selectedVersionId: string | null
  newVersionRoute: RouteLocationRaw
}>()

const emit = defineEmits<{
  select: [versionId: string]
  compare: [versionId: string]
}>()

const search = ref('')

const latestVersionNumber = computed(() => {
  if (!props.versions.length) return 0
  return Math.max(...props.versions.map((v) => v.version_number))
})

const filteredVersions = computed(() => {
  let list = [...props.versions].sort((a, b) => b.version_number - a.version_number)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(
      (v) =>
        v.name.toLowerCase().includes(q) ||
        `#${v.version_number}`.includes(q) ||
        v.change_description?.toLowerCase().includes(q)
    )
  }
  return list
})

function formatVersionDate(dateStr: string): string {
  return format(new Date(dateStr), 'dd/MM/yyyy HH:mm:ss')
}

function isLatest(v: PromptVersionSummary): boolean {
  return v.version_number === latestVersionNumber.value
}

function prodChipLabel(v: PromptVersionSummary): string {
  const count = v.production_usages?.length ?? 0
  return count > 1 ? `Prod (${count})` : 'Prod'
}

function prodTooltipText(v: PromptVersionSummary): string {
  return (v.production_usages ?? []).map((u) => u.project_name).join(', ')
}
</script>

<template>
  <div class="version-sidebar">
    <div class="version-sidebar__header">
      <VTextField
        v-model="search"
        prepend-inner-icon="tabler-search"
        placeholder="Search..."
        variant="outlined"
        density="compact"
        hide-details
        class="version-sidebar__search"
      />
      <VBtn color="primary" block class="mt-3" prepend-icon="tabler-plus" :to="newVersionRoute">
        New version
      </VBtn>
    </div>

    <VList class="version-sidebar__list" density="compact">
      <VListItem
        v-for="version in filteredVersions"
        :key="version.id"
        :value="version.id"
        :active="version.id === selectedVersionId"
        class="version-card"
        @click="emit('select', version.id)"
      >
        <div class="d-flex align-center gap-2 mb-1">
          <span class="text-subtitle-2 font-weight-bold"># {{ version.version_number }}</span>
          <VChip v-if="isLatest(version)" size="x-small" variant="flat" color="default" label> Latest </VChip>
          <VChip
            v-if="version.production_usages?.length"
            size="x-small"
            variant="flat"
            color="success"
            label
          >
            {{ prodChipLabel(version) }}
            <VTooltip activator="parent" location="top">{{ prodTooltipText(version) }}</VTooltip>
          </VChip>
          <VSpacer />
          <VBtn
            v-if="version.id !== selectedVersionId"
            icon
            variant="text"
            size="x-small"
            aria-label="Compare with selected version"
            class="version-card__compare"
            @click.stop="emit('compare', version.id)"
          >
            <VIcon icon="tabler-git-compare" size="16" />
            <VTooltip activator="parent" location="top">Compare with selected version</VTooltip>
          </VBtn>
        </div>
        <div v-if="version.change_description" class="text-caption text-medium-emphasis mt-1 version-card__commit">
          {{ version.change_description }}
        </div>
        <div class="text-caption text-medium-emphasis mt-1">
          {{ formatVersionDate(version.created_at) }}
        </div>
      </VListItem>

      <EmptyState
        v-if="!filteredVersions.length && search"
        icon="tabler-search"
        title="No matching versions"
        size="sm"
      />
    </VList>
  </div>
</template>

<style lang="scss" scoped>
.version-sidebar {
  display: flex;
  flex-direction: column;
  block-size: 100%;
  border-inline-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));

  &__header {
    padding: 16px;
    border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }

  &__list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
}

.version-card {
  padding: 12px;
  border-radius: 8px;
  transition: background-color 0.15s;
  border-inline-start: 3px solid transparent;

  &:hover {
    background: rgba(var(--v-theme-on-surface), 0.04);
  }

  &:global(.v-list-item--active) {
    background: rgba(var(--v-theme-primary), 0.08);
    border-inline-start-color: rgb(var(--v-theme-primary));
  }

  & + & {
    margin-block-start: 4px;
  }

  &__commit {
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  &__compare {
    opacity: 0;
    transition: opacity 0.15s;
  }

  &:hover &__compare,
  &__compare:focus-visible {
    opacity: 1;
  }
}
</style>
