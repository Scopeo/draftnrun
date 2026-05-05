<script setup lang="ts">
import { computed, toRef } from 'vue'
import { usePromptVersionDetailQuery } from '@/composables/queries/usePromptsQuery'
import { computeWordDiff, type DiffSegment } from '@/utils/textDiff'

const visible = defineModel<boolean>({ required: true })

const props = defineProps<{
  orgId: string
  promptId: string
  baseVersionId: string | null
  compareVersionId: string | null
}>()

const orgId = toRef(props, 'orgId')
const promptId = toRef(props, 'promptId')
const sameVersion = computed(() => !!props.baseVersionId && props.baseVersionId === props.compareVersionId)
const baseVersionRef = computed(() => (visible.value && props.baseVersionId && !sameVersion.value) ? props.baseVersionId : undefined)
const compareVersionRef = computed(() => (visible.value && props.compareVersionId && !sameVersion.value) ? props.compareVersionId : undefined)

const baseQuery = usePromptVersionDetailQuery(orgId, promptId, baseVersionRef)
const compareQuery = usePromptVersionDetailQuery(orgId, promptId, compareVersionRef)

const loading = computed(() => baseQuery.isLoading.value || compareQuery.isLoading.value)
const hasError = computed(() => baseQuery.isError.value || compareQuery.isError.value)
const baseVersion = computed(() => baseQuery.data.value ?? null)
const compareVersion = computed(() => compareQuery.data.value ?? null)

const diffSegments = computed<DiffSegment[]>(() => {
  const base = baseVersion.value
  const compare = compareVersion.value
  if (!base || !compare) return []
  const older = base.version_number < compare.version_number ? base : compare
  const newer = base.version_number < compare.version_number ? compare : base
  return computeWordDiff(older.content, newer.content)
})

const olderNumber = computed(() => {
  if (!baseVersion.value || !compareVersion.value) return 0
  return Math.min(baseVersion.value.version_number, compareVersion.value.version_number)
})

const newerNumber = computed(() => {
  if (!baseVersion.value || !compareVersion.value) return 0
  return Math.max(baseVersion.value.version_number, compareVersion.value.version_number)
})
</script>

<template>
  <VDialog v-model="visible" max-width="900" scrollable>
    <VCard>
      <VCardTitle class="d-flex align-center gap-2 pa-4">
        <VIcon icon="tabler-git-compare" size="20" />
        Compare versions
        <template v-if="!loading && baseVersion && compareVersion">
          <VChip size="small" variant="tonal" label>#{{ olderNumber }}</VChip>
          <VIcon icon="tabler-arrow-right" size="16" />
          <VChip size="small" variant="tonal" label>#{{ newerNumber }}</VChip>
        </template>
        <VSpacer />
        <div class="d-flex align-center gap-4 me-2">
          <div class="d-flex align-center gap-2">
            <span class="diff-legend__dot diff-legend__dot--removed" />
            <span class="text-caption text-medium-emphasis">Removed</span>
          </div>
          <div class="d-flex align-center gap-2">
            <span class="diff-legend__dot diff-legend__dot--added" />
            <span class="text-caption text-medium-emphasis">Added</span>
          </div>
        </div>
        <VBtn icon variant="text" size="small" aria-label="Close dialog" @click="visible = false">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="diff-container pa-0">
        <div v-if="sameVersion" class="d-flex justify-center align-center pa-8">
          <EmptyState icon="tabler-equal" title="Same version" description="Select two different versions to compare." size="sm" />
        </div>

        <div v-else-if="loading" class="diff-loading d-flex justify-center align-center">
          <VProgressCircular indeterminate color="primary" />
        </div>

        <div v-else-if="hasError" class="d-flex justify-center align-center pa-8">
          <EmptyState icon="tabler-alert-triangle" title="Error loading versions" description="Something went wrong while fetching the version data. Please try again." size="sm" />
        </div>

        <div v-else-if="diffSegments.length" class="diff-view">
          <pre class="diff-content pa-4"><template
              v-for="(seg, idx) in diffSegments"
              :key="idx"
            ><span :class="'diff-' + seg.type">{{ seg.value }}</span></template></pre>
        </div>

        <div v-else class="d-flex justify-center align-center pa-8">
          <EmptyState icon="tabler-equal" title="Identical" description="Both versions have the same content." size="sm" />
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.diff-container {
  max-block-size: 70vh;
}

.diff-loading {
  min-block-size: 200px;
}

.diff-view {
  font-family: 'DM Mono', 'Fira Code', monospace;
  font-size: 0.8125rem;
  line-height: 1.7;
}

.diff-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.diff-equal {
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.diff-removed {
  background: rgba(var(--v-theme-error), 0.12);
  color: rgb(var(--v-theme-error));
  text-decoration: line-through;
  border-radius: 2px;
  padding-inline: 2px;
}

.diff-added {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
  border-radius: 2px;
  padding-inline: 2px;
}

.diff-legend {
  &__dot {
    display: inline-block;
    inline-size: 10px;
    block-size: 10px;
    border-radius: 2px;

    &--removed {
      background: rgba(var(--v-theme-error), 0.25);
      border: 1px solid rgb(var(--v-theme-error));
    }

    &--added {
      background: rgba(var(--v-theme-success), 0.25);
      border: 1px solid rgb(var(--v-theme-success));
    }
  }
}
</style>
