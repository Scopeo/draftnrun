<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useTraceDetailsQuery } from '@/composables/queries/useObservabilityQuery'
import type { Span } from '@/types/observability'
import SpanDetails from './SpanDetails.vue'
import TreeItem from './TreeItem.vue'

const props = defineProps<{
  traceId: string | undefined
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const drawerOpen = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})

const selectedSpan = ref<Span | null>(null)

const traceIdRef = computed(() => props.traceId)
const enabledRef = computed(() => !!props.traceId && props.open)

const traceDetailsQuery = useTraceDetailsQuery(traceIdRef, enabledRef)
const traceTree = computed(() => traceDetailsQuery.data.value ?? null)

watch(
  () => traceDetailsQuery.data.value,
  data => {
    if (data) selectedSpan.value = data
  }
)

watch(
  () => props.traceId,
  () => {
    selectedSpan.value = null
  }
)

const close = () => {
  emit('update:open', false)
}

const onSpanClick = (span: Span) => {
  selectedSpan.value = span
}
</script>

<template>
  <VNavigationDrawer
    v-if="drawerOpen"
    v-model="drawerOpen"
    location="end"
    temporary
    class="trace-preview-nav-drawer"
  >
    <div class="trace-drawer">
      <div class="trace-drawer__header">
        <div class="d-flex align-center gap-2">
          <VIcon icon="tabler-list-tree" color="primary" size="20" />
          <span class="text-h6">Trace Details</span>
        </div>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="tabler-x" />
        </VBtn>
      </div>

      <VProgressCircular v-if="traceDetailsQuery.isLoading.value" indeterminate color="primary" class="d-block mx-auto my-8" />

      <div v-else-if="traceTree" class="trace-drawer__content">
        <VCard class="trace-drawer__tree-card" variant="outlined">
          <VCardText class="pa-1">
            <TreeItem
              :item="traceTree"
              :level="0"
              :selected-span-id="selectedSpan?.span_id"
              @click="onSpanClick"
            />
          </VCardText>
        </VCard>
        <VCard class="trace-drawer__details-card" variant="outlined">
          <VCardText class="pa-2">
            <SpanDetails v-if="selectedSpan" :span="selectedSpan" />
            <div v-else class="d-flex align-center justify-center pa-8">
              <div class="text-center">
                <VIcon size="48" icon="tabler-click" color="primary" class="mb-4" />
                <p class="text-body-1 text-medium-emphasis">Select a span from the tree to view details</p>
              </div>
            </div>
          </VCardText>
        </VCard>
      </div>

      <VAlert v-else type="info" variant="tonal" class="ma-4">No trace data available.</VAlert>
    </div>
  </VNavigationDrawer>
</template>

<style lang="scss" scoped>
:deep(.trace-preview-nav-drawer) {
  inline-size: min(90vw, 1200px) !important;
}

.trace-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: rgb(var(--v-theme-surface));
}

.trace-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  flex-shrink: 0;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.trace-drawer__content {
  display: flex;
  flex-direction: row;
  gap: 12px;
  flex: 1;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.trace-drawer__tree-card {
  flex: 0 0 auto;
  inline-size: min(480px, 40%);
  min-inline-size: 280px;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  :deep(.v-card-text) {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    max-height: 100%;
  }
}

.trace-drawer__details-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-width: 0;

  :deep(.v-card-text) {
    flex: 1;
    overflow-y: auto;
    overflow-x: auto;
    max-height: 100%;
  }
}
</style>
