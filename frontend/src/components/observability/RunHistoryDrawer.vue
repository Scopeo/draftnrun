<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { format } from 'date-fns'
import SpanDetails from './SpanDetails.vue'
import TreeItem from './TreeItem.vue'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'
import type { CallType } from '@/types/observability'
import { useSpanIconMap } from '@/composables/useSpanIconMap'

interface Props {
  projectId: string
  callTypeFilter?: CallType
  durationDays?: number // Duration in days for the traces API
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'view-mode', expanded: boolean): void
}>()

const projectIdRef = computed(() => props.projectId)
const spanIconMap = useSpanIconMap(projectIdRef)

const traces = ref<any[]>([])
const selectedTrace = ref<any>(null)
const selectedSpan = ref<any>(null)
const rootSpan = ref<any>(null)
const traceDetails = ref<any>(null)
const loading = ref(false)
const loadingDetails = ref(false)
const error = ref<string | null>(null)
const sortDirection = ref<'asc' | 'desc'>('desc')
const showTreeView = ref(false)

const normalizeTraceList = (payload: unknown): any[] => {
  if (Array.isArray(payload)) return payload
  if (payload && typeof payload === 'object') {
    const candidate =
      (payload as Record<string, any>).items ??
      (payload as Record<string, any>).spans ??
      (payload as Record<string, any>).results ??
      (payload as Record<string, any>).data

    if (Array.isArray(candidate)) return candidate
  }
  return []
}

const fetchTraceData = async () => {
  if (!props.projectId) {
    return
  }

  clearTraceSelection()
  loading.value = true
  error.value = null

  try {
    const params: { duration: number; call_type?: string } = {
      duration: props.durationDays ?? 90, // 90 days
    }

    if (props.callTypeFilter && props.callTypeFilter !== 'all') {
      params.call_type = props.callTypeFilter
    }

    const tracesData = await scopeoApi.observability.getTracesList(props.projectId, params)

    traces.value = normalizeTraceList(tracesData)
  } catch (err) {
    logger.error('[Observability] Failed to fetch trace data', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to fetch trace data'
    traces.value = []
  } finally {
    loading.value = false
  }
}

const fetchTraceDetails = async (traceId: string) => {
  loadingDetails.value = true
  error.value = null

  try {
    const data = await scopeoApi.observability.getTraceDetails(traceId)

    traceDetails.value = data
    rootSpan.value = data
    selectedSpan.value = data
    showTreeView.value = true
    emit('view-mode', true)
  } catch (err) {
    logger.error('[Observability] Failed to fetch trace details', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to fetch trace details'
  } finally {
    loadingDetails.value = false
  }
}

const rootSpans = computed(() => {
  return traces.value
    .filter(span => !span.parent_id)
    .sort((a, b) => {
      const timeA = new Date(a.start_time).getTime()
      const timeB = new Date(b.start_time).getTime()
      return sortDirection.value === 'asc' ? timeA - timeB : timeB - timeA
    })
})

const getTotalTokens = (span: any) => {
  return (span.cumulative_llm_token_count_prompt || 0) + (span.cumulative_llm_token_count_completion || 0)
}

const formatDuration = (start: string, end: string) => {
  const startTime = new Date(start).getTime()
  const endTime = new Date(end).getTime()
  return ((endTime - startTime) / 1000).toFixed(2)
}

const handleSpanSelect = async (span: any) => {
  selectedTrace.value = span
  error.value = null

  if (span.trace_id) {
    await fetchTraceDetails(span.trace_id)
  }
}

const handleTreeSpanSelect = (span: any) => {
  selectedSpan.value = span
}

const handleBack = () => {
  selectedTrace.value = null
  selectedSpan.value = null
  rootSpan.value = null
  traceDetails.value = null
  showTreeView.value = false
  emit('view-mode', false)
}

const clearTraceSelection = () => {
  selectedTrace.value = null
  selectedSpan.value = null
  rootSpan.value = null
  traceDetails.value = null
  showTreeView.value = false
  emit('view-mode', false)
}

const toggleSort = () => {
  sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
}

const refreshTraces = () => {
  fetchTraceData()
}

watch(
  () => props.projectId,
  (newProjectId, oldProjectId) => {
    if (!newProjectId || newProjectId === oldProjectId) return
    clearTraceSelection()
    traces.value = []
    fetchTraceData()
  },
  { immediate: true }
)

watch(
  () => props.callTypeFilter,
  () => {
    fetchTraceData()
  }
)

defineExpose({
  refreshTraces,
  selectedTrace,
  showTreeView,
  clearTraceSelection,
  isLoading: computed(() => loading.value || loadingDetails.value),
})
</script>

<template>
  <div class="observability-drawer" :class="{ expanded: showTreeView }">
    <div v-if="selectedTrace" class="observability-header">
      <div class="d-flex align-center justify-end mb-2">
        <VBtn icon variant="text" size="small" title="Close Details" @click="clearTraceSelection">
          <VIcon icon="tabler-x" size="16" />
        </VBtn>
      </div>
    </div>

    <div class="observability-content" :class="{ 'split-layout': showTreeView }">
      <VCard :class="showTreeView ? 'tree-card' : 'traces-list-card'" variant="outlined">
        <VCardTitle v-if="showTreeView" class="px-4 py-2">
          <VBtn icon variant="text" size="small" class="me-2" @click="handleBack">
            <VIcon icon="tabler-arrow-left" />
          </VBtn>
          <span class="text-h6">Trace Tree</span>
          <VSpacer />
        </VCardTitle>

        <VCardText class="pa-0">
          <VProgressCircular v-if="loading || loadingDetails" indeterminate color="primary" class="ma-4" />
          <VAlert v-else-if="error" type="error" variant="tonal" class="ma-4">
            {{ error }}
          </VAlert>

          <div v-else-if="showTreeView && rootSpan?.span_id" class="trace-tree">
            <TreeItem
              :item="rootSpan"
              :level="0"
              :selected-span-id="selectedSpan?.span_id"
              :icon-map="spanIconMap"
              @click="handleTreeSpanSelect"
            />
          </div>

          <div v-else class="trace-list-simple">
            <div
              v-for="span in rootSpans"
              :key="span.span_id"
              class="trace-item"
              :class="{ selected: selectedTrace?.span_id === span.span_id }"
              @click.stop="handleSpanSelect(span)"
            >
              <div class="trace-header">
                <div class="d-flex align-center gap-2">
                  <VIcon size="12" icon="tabler-activity" color="primary" />
                  <span class="text-caption">{{ format(new Date(span.start_time), 'HH:mm:ss') }}</span>
                </div>
                <VChip size="x-small" color="primary" variant="tonal">
                  {{ getTotalTokens(span) }}
                </VChip>
              </div>
              <div class="trace-content">
                <div class="trace-input mb-2">
                  <div class="d-flex align-center gap-1">
                    <VIcon icon="tabler-arrow-right" size="14" color="info" />
                    <div class="trace-text flex-grow-1">{{ span.input_preview || 'No input' }}</div>
                  </div>
                </div>
                <div class="trace-output">
                  <div class="d-flex align-center gap-1">
                    <VIcon icon="tabler-arrow-left" size="14" color="success" />
                    <div class="trace-text flex-grow-1">{{ span.output_preview || 'No output' }}</div>
                  </div>
                </div>
                <div class="trace-meta mt-2">
                  <VIcon icon="tabler-clock" size="14" class="me-1" />
                  <span class="text-caption"> {{ formatDuration(span.start_time, span.end_time) }}s </span>
                </div>
              </div>
            </div>
          </div>
        </VCardText>
      </VCard>

      <VCard v-if="showTreeView" class="flex-grow-1 details-card-scrollable" variant="outlined">
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

      <VCard v-else-if="selectedTrace && !showTreeView" class="details-card" variant="outlined">
        <VCardTitle class="px-4 py-2">
          <div class="d-flex align-center justify-space-between w-100">
            <div class="d-flex align-center gap-2">
              <span class="text-h6">Trace Details</span>
              <VChip v-if="selectedTrace.source === 'chat'" size="small" color="info" variant="tonal">
                Chat Message
              </VChip>
            </div>
          </div>
        </VCardTitle>
        <VCardText class="pa-4">
          <div class="d-flex flex-column gap-3">
            <div>
              <h4 class="text-subtitle-1 mb-1">Input</h4>
              <p class="text-body-2">{{ selectedTrace.input_preview || '-' }}</p>
            </div>
            <div>
              <h4 class="text-subtitle-1 mb-1">Output</h4>
              <p class="text-body-2">{{ selectedTrace.output_preview || '-' }}</p>
            </div>
            <div class="d-flex gap-4">
              <div>
                <h4 class="text-subtitle-1 mb-1">Duration</h4>
                <p class="text-body-2">{{ formatDuration(selectedTrace.start_time, selectedTrace.end_time) }}s</p>
              </div>
              <div>
                <h4 class="text-subtitle-1 mb-1">Tokens</h4>
                <p class="text-body-2">{{ getTotalTokens(selectedTrace) }}</p>
              </div>
              <div>
                <h4 class="text-subtitle-1 mb-1">Status</h4>
                <VChip size="small" :color="selectedTrace.status === 'success' ? 'success' : 'error'" variant="tonal">
                  {{ selectedTrace.status }}
                </VChip>
              </div>
            </div>
          </div>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.observability-drawer {
  padding: 1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 2px;
    background: rgba(var(--v-theme-on-surface), 0.2);
  }

  &::-webkit-scrollbar-thumb:hover {
    background: rgba(var(--v-theme-on-surface), 0.3);
  }
}

.observability-header {
  flex-shrink: 0;
}

.observability-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;

  &.split-layout {
    flex-direction: row;
    gap: 8px;
  }
}

.trace-list-simple {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.trace-item {
  padding: 8px;
  border: 1px solid rgba(var(--v-border-color), 0.2);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: rgb(var(--v-theme-surface));

  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.04);
    border-color: rgba(var(--v-theme-primary), 0.3);
  }

  &.selected {
    background-color: rgba(var(--v-theme-primary), 0.1);
    border-color: rgb(var(--v-theme-primary));
  }
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.trace-content {
  font-size: 0.75rem;
  line-height: 1.3;
}

.trace-text {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 0.8rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border: 1px solid rgba(var(--v-border-color), 0.08);
}

.trace-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.tree-card {
  flex: 0 0 auto;
  max-inline-size: 320px;
  min-inline-size: 260px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;

  .v-card-text {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    max-height: 100%;
    padding: 4px;
  }

  .v-card-title {
    font-size: 0.9rem;
    padding: 8px 12px;
  }
}

.traces-list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;

  .v-card-text {
    flex: 1;
    overflow: hidden;
    max-height: 100%;
    display: flex;
    flex-direction: column;
  }
}

.details-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-height: 100%;

  .v-card-text {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    max-height: 100%;
  }
}
</style>
