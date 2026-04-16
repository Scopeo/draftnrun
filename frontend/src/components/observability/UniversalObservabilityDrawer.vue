<script setup lang="ts">
import SaveToQADialog from '@/components/qa/SaveToQADialog.vue'
import { type TraceListParams, useTraceDetailsQuery, useTracesQuery } from '@/composables/queries/useObservabilityQuery'
import { DATE_RANGES, formatDuration, useDateRangeFilter } from '@/composables/useDateRangeFilter'
import { useSaveToQA } from '@/composables/useSaveToQA'
import { useSpanIconMap } from '@/composables/useSpanIconMap'
import type { CallType, Span } from '@/types/observability'
import { formatDateCalendar, formatNumberWithSpaces } from '@/utils/formatters'
import { useQueryClient } from '@tanstack/vue-query'
import { useDebounceFn } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import SpanDetails from './SpanDetails.vue'
import TreeItem from './TreeItem.vue'

interface Props {
  projectId: string
  callTypeFilter?: CallType
  isLoadingPlayground?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'view-mode', expanded: boolean): void
  (e: 'load-in-playground', traceData: { span: Span }): void
}>()

const queryClient = useQueryClient()

const selectedTrace = ref<any>(null)
const selectedSpan = ref<any>(null)
const rootSpan = ref<any>(null)
const sortDirection = ref<'asc' | 'desc'>('desc')

// Pagination state
const currentPage = ref(1)
const itemsPerPage = ref(20)
const showTreeView = ref(false)

const resetPage = () => {
  currentPage.value = 1
}

// Search state
const searchInput = ref('')
const searchValue = ref('')

const debouncedSearch = useDebounceFn(() => {
  searchValue.value = searchInput.value
  resetPage()
}, 400)

// Date range filter state
const { selectedRange, customStartDate, customEndDate, isCustomRange, dateRangeParams } = useDateRangeFilter()
const dateRanges = DATE_RANGES

// Save to QA state (local to component)
const traceToSave = ref<{ trace: any; index: number } | null>(null)

// Helper functions for extracting conversation data from traces
const extractConversationId = (span: any): string | null => {
  const id = span.conversation_id || span.trace_id
  if (!id) return null
  return id
}

const getMessageCount = (span: any): number => {
  if (Array.isArray(span.input)) {
    for (const item of span.input) {
      if (typeof item === 'object' && item?.messages) {
        return item.messages.length - 1
      }
    }
  }
  return 0
}

// Save to QA composable
const projectIdRef = computed(() => props.projectId)
const spanIconMap = useSpanIconMap(projectIdRef)

const {
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
  openSaveDialog,
  saveToQA,
  createDataset,
} = useSaveToQA({
  projectId: projectIdRef,
  getConversationData: () => {
    if (!traceToSave.value) return null

    const trace = traceToSave.value.trace

    if (trace.trace_id) {
      return {
        traceId: trace.trace_id,
      }
    }

    return null
  },
})

// TanStack Query for traces list
const traceParams = computed<TraceListParams>(() => ({
  call_type: props.callTypeFilter && props.callTypeFilter !== 'all' ? props.callTypeFilter : undefined,
  page: currentPage.value,
  size: itemsPerPage.value,
  search: searchValue.value || undefined,
  ...dateRangeParams.value,
}))

const tracesQuery = useTracesQuery(projectIdRef, traceParams)

// TanStack Query for trace details
const selectedTraceId = ref<string | undefined>(undefined)

const traceDetailsQuery = useTraceDetailsQuery(
  selectedTraceId,
  computed(() => !!selectedTraceId.value)
)

// Derived state from queries
const spans = computed(() => tracesQuery.data.value?.traces || [])
const totalPages = computed(() => tracesQuery.data.value?.pagination.total_pages ?? 1)
const initialLoading = computed(() => tracesQuery.isLoading.value && !tracesQuery.data.value)
const isFetching = computed(() => tracesQuery.isFetching.value)
const loadingDetails = computed(() => traceDetailsQuery.isLoading.value)
const error = computed(() => tracesQuery.error.value?.message || traceDetailsQuery.error.value?.message || null)

// Watch for trace details data
watch(
  () => traceDetailsQuery.data.value,
  data => {
    if (data) {
      rootSpan.value = data
      selectedSpan.value = data
      showTreeView.value = true
      emit('view-mode', true)
    }
  }
)

// Reset to first page when call type filter prop changes
watch(
  () => props.callTypeFilter,
  () => {
    resetPage()
  }
)

const rootSpans = computed(() => {
  return [...spans.value].sort((a, b) => {
    const timeA = new Date(a.start_time).getTime()
    const timeB = new Date(b.start_time).getTime()

    return sortDirection.value === 'asc' ? timeA - timeB : timeB - timeA
  })
})

const getTotalCredits = (span: any) => {
  return span.total_credits ?? null
}

const handleSpanSelect = (span: any) => {
  selectedTrace.value = span

  if (span.trace_id) {
    selectedTraceId.value = span.trace_id
  }
}

const handleTreeSpanSelect = (span: any) => {
  selectedSpan.value = span
}

const handleBack = () => {
  selectedTrace.value = null
  selectedSpan.value = null
  rootSpan.value = null
  selectedTraceId.value = undefined
  showTreeView.value = false
  emit('view-mode', false)
}

const clearTraceSelection = () => {
  selectedTrace.value = null
  selectedSpan.value = null
  rootSpan.value = null
  selectedTraceId.value = undefined
  showTreeView.value = false
  emit('view-mode', false)
}

// Open save to QA dialog
const openSaveToQADialog = (trace: any) => {
  const conversationId = extractConversationId(trace)
  if (!conversationId) {
    saveToQAError.value = 'This trace does not have a conversation ID'
    setTimeout(() => {
      saveToQAError.value = null
    }, 3000)

    return
  }

  traceToSave.value = {
    trace,
    index: getMessageCount(trace),
  }
  openSaveDialog()
}

const refreshTraces = () => {
  queryClient.invalidateQueries({ queryKey: ['traces', props.projectId] })
}

const handleLoadInPlayground = (span: Span) => {
  emit('load-in-playground', { span })
}

const isLoading = computed(() => isFetching.value || loadingDetails.value)

defineExpose({
  refreshTraces,
  selectedTrace,
  showTreeView,
  clearTraceSelection,
  isLoading,
})
</script>

<template>
  <div class="agent-observability-drawer" :class="{ expanded: showTreeView }">
    <!-- Header with close detail button (refresh is in drawer header) -->
    <div v-if="selectedTrace" class="observability-header">
      <div class="d-flex align-center justify-end mb-2">
        <VBtn icon variant="text" size="small" title="Close Details" @click="clearTraceSelection">
          <VIcon icon="tabler-x" size="16" />
        </VBtn>
      </div>
    </div>

    <!-- Date range filter (outside the card, between call type toggle and results) -->
    <div v-if="!showTreeView && !selectedTrace" class="trace-list-filters">
      <div class="d-flex align-center gap-2">
        <VIcon icon="tabler-calendar" size="18" class="flex-shrink-0" />
        <VSelect
          v-model="selectedRange"
          :items="dateRanges"
          item-title="title"
          item-value="value"
          density="compact"
          hide-details
          variant="outlined"
          class="date-range-select"
          @update:model-value="resetPage"
        />
      </div>
      <div v-if="isCustomRange" class="d-flex flex-wrap gap-3">
        <VTextField
          v-model="customStartDate"
          type="datetime-local"
          density="compact"
          hide-details
          variant="outlined"
          label="Start"
          @update:model-value="resetPage"
        />
        <VTextField
          v-model="customEndDate"
          type="datetime-local"
          density="compact"
          hide-details
          variant="outlined"
          label="End"
          @update:model-value="resetPage"
        />
      </div>
    </div>

    <!-- Main Content - Side by side layout when trace selected -->
    <div class="observability-content" :class="{ 'split-layout': showTreeView }">
      <!-- Left Panel: Traces List OR Tree View -->
      <VCard :class="showTreeView ? 'tree-card' : 'traces-list-card'" variant="outlined">
        <VCardTitle v-if="showTreeView" class="px-4 py-2">
          <VBtn icon variant="text" size="small" class="me-2" @click="handleBack">
            <VIcon icon="tabler-arrow-left" />
          </VBtn>
          <span class="text-h6">Trace Tree</span>
          <VSpacer />
        </VCardTitle>

        <VCardText class="pa-0">
          <VProgressCircular v-if="initialLoading || loadingDetails" indeterminate color="primary" class="ma-4" />
          <VAlert v-else-if="error" type="error" variant="tonal" class="ma-4">
            {{ error }}
          </VAlert>

          <!-- Tree View for detailed traces -->
          <div v-else-if="showTreeView && rootSpan?.span_id" class="trace-tree">
            <TreeItem
              :item="rootSpan"
              :level="0"
              :selected-span-id="selectedSpan?.span_id"
              :icon-map="spanIconMap"
              @click="handleTreeSpanSelect"
            />
          </div>

          <!-- Trace List View -->
          <div v-else class="trace-list-simple">
            <div class="px-2 pt-2 pb-2">
              <VTextField
                v-model="searchInput"
                prepend-inner-icon="tabler-search"
                placeholder="Search traces..."
                variant="outlined"
                density="compact"
                hide-details
                clearable
                :loading="isFetching && !!searchValue"
                @update:model-value="debouncedSearch"
              />
            </div>

            <div
              v-if="rootSpans.length === 0 && searchValue"
              class="d-flex flex-column align-center justify-center pa-8 text-center"
            >
              <VIcon size="40" icon="tabler-search-off" color="medium-emphasis" class="mb-3" />
              <p class="text-body-1 text-medium-emphasis mb-1">No traces matching your query</p>
              <p class="text-body-2 text-disabled mb-3">No results for "{{ searchValue }}"</p>
              <VBtn variant="text" color="primary" size="small" @click="searchInput = ''"> Clear Search </VBtn>
            </div>

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
                  <span class="text-caption">{{ formatDateCalendar(span.start_time) }}</span>
                </div>
                <div class="d-flex align-center gap-1">
                  <VChip size="x-small" color="primary" variant="tonal">
                    {{
                      getTotalCredits(span) != null ? `${formatNumberWithSpaces(getTotalCredits(span))} credits` : '-'
                    }}
                  </VChip>
                  <VTooltip location="top">
                    <template #activator="{ props: tooltipProps }">
                      <VBtn
                        v-bind="tooltipProps"
                        icon
                        variant="text"
                        size="x-small"
                        color="success"
                        @click.stop="openSaveToQADialog(span)"
                      >
                        <VIcon icon="tabler-device-floppy" size="14" />
                      </VBtn>
                    </template>
                    <span>Save to QA Dataset</span>
                  </VTooltip>
                </div>
              </div>
              <div class="trace-content">
                <div class="trace-input mb-2">
                  <div class="d-flex align-center gap-1">
                    <VIcon icon="tabler-arrow-right" size="14" color="info" />
                    <div class="trace-text flex-grow-1">
                      {{ span.input_preview || 'No input' }}
                    </div>
                  </div>
                </div>
                <div class="trace-output">
                  <div class="d-flex align-center gap-1">
                    <VIcon icon="tabler-arrow-left" size="14" color="success" />
                    <div class="trace-text flex-grow-1">
                      {{ span.output_preview || 'No output' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Pagination Controls -->
            <div v-if="rootSpans.length > 0" class="d-flex justify-center pa-4">
              <VPagination
                v-model="currentPage"
                :length="totalPages"
                :total-visible="5"
                density="compact"
                variant="text"
                show-first-last-page
                first-icon="tabler-chevrons-left"
                last-icon="tabler-chevrons-right"
                prev-icon="tabler-chevron-left"
                next-icon="tabler-chevron-right"
                class="pagination-minimal"
              />
            </div>
          </div>
        </VCardText>
      </VCard>

      <!-- Right Panel: Span Details (always shown in tree view) -->
      <VCard v-if="showTreeView" class="flex-grow-1 details-card-scrollable" variant="outlined">
        <VCardTitle v-if="selectedTrace" class="px-4 py-2 d-flex align-center justify-space-between">
          <span class="text-h6">Trace Details</span>
          <div class="d-flex align-center gap-1">
            <VTooltip location="top">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon
                  variant="text"
                  size="small"
                  color="primary"
                  :loading="props.isLoadingPlayground"
                  :disabled="props.isLoadingPlayground"
                  @click.stop="handleLoadInPlayground(selectedSpan)"
                >
                  <VIcon icon="tabler-player-play" size="18" />
                </VBtn>
              </template>
              <span>Run in playground</span>
            </VTooltip>
            <VTooltip location="top">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon
                  variant="text"
                  size="small"
                  color="success"
                  @click.stop="openSaveToQADialog(selectedTrace)"
                >
                  <VIcon icon="tabler-device-floppy" size="18" />
                </VBtn>
              </template>
              <span>Save to QA Dataset</span>
            </VTooltip>
          </div>
        </VCardTitle>
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

      <!-- Right Panel: Basic trace details (only for chat messages when not in tree view) -->
      <VCard v-else-if="selectedTrace && !showTreeView" class="details-card" variant="outlined">
        <VCardTitle class="px-4 py-2">
          <div class="d-flex align-center justify-space-between w-100">
            <div class="d-flex align-center gap-2">
              <span class="text-h6">Trace Details</span>
              <VChip v-if="selectedTrace.source === 'chat'" size="small" color="info" variant="tonal">
                Chat Message
              </VChip>
            </div>
            <VTooltip location="top">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon
                  variant="text"
                  size="small"
                  color="success"
                  @click.stop="openSaveToQADialog(selectedTrace)"
                >
                  <VIcon icon="tabler-device-floppy" size="18" />
                </VBtn>
              </template>
              <span>Save to QA Dataset</span>
            </VTooltip>
          </div>
        </VCardTitle>
        <VCardText class="pa-4">
          <div class="d-flex flex-column gap-3">
            <div>
              <h4 class="text-subtitle-1 mb-1">Input</h4>
              <p class="text-body-2">
                {{ selectedTrace.input_preview || '-' }}
              </p>
            </div>
            <div>
              <h4 class="text-subtitle-1 mb-1">Output</h4>
              <p class="text-body-2">
                {{ selectedTrace.output_preview || '-' }}
              </p>
            </div>
            <div class="d-flex gap-4">
              <div>
                <h4 class="text-subtitle-1 mb-1">Duration</h4>
                <p class="text-body-2">{{ formatDuration(selectedTrace.start_time, selectedTrace.end_time) }}s</p>
              </div>
              <div>
                <h4 class="text-subtitle-1 mb-1">Credits</h4>
                <p class="text-body-2">
                  {{
                    getTotalCredits(selectedTrace) != null
                      ? `${formatNumberWithSpaces(getTotalCredits(selectedTrace))} credits`
                      : '-'
                  }}
                </p>
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

  <!-- Save to QA Dataset Dialog -->
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
</template>

<style lang="scss" scoped>
.pagination-minimal {
  :deep(.v-pagination__item--is-active .v-btn) {
    background: rgb(var(--v-theme-primary)) !important;
    color: rgb(var(--v-theme-on-primary)) !important;
    border-radius: 8px;
  }
}

.agent-observability-drawer {
  padding: 1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));

  /* Custom scrollbar */
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
  min-height: 0; /* allow children to size and scroll correctly */

  &.split-layout {
    flex-direction: row;
    gap: 8px;
  }
}

.traces-panel {
  flex: 1;
  display: flex;
  flex-direction: column;

  &.compact {
    flex: 0 0 40%; /* Take 40% width when in split layout */
    min-width: 300px;
  }
}

.traces-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .v-card-text {
    flex: 1;
    overflow-y: auto;
    min-height: 0; /* ensures scroll instead of overflow cutoff */
  }
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
    overflow-y: auto;
    max-height: 100%;
  }
}

.details-panel {
  flex: 0 0 60%; /* Take 60% width in split layout */
  display: flex;
  flex-direction: column;
  max-height: 100%;
  overflow: hidden;
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
    min-height: 0; /* ensures scrolling to the bottom works */
    max-height: 100%;
  }
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}

.trace-list-filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  margin-block-start: -8px;
  margin-block-end: 8px;
  flex-shrink: 0;
  font-size: 0.75rem;

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-field__input),
  :deep(.v-label) {
    font-size: 0.75rem;
  }
}

.date-range-select {
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-field__input) {
    min-block-size: 30px;
    padding-block: 0;
    font-size: 0.75rem;
  }
}

.trace-list-simple {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-height: 100%;
  overflow-y: auto;
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

.trace-input,
.trace-output {
  .text-body-2 {
    font-size: 0.75rem;
    line-height: 1.2;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    word-break: break-word;
  }
}

.trace-tree {
  overflow: hidden auto;
  border-radius: 8px;
  height: 100%;
}

.details-card-scrollable {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
  min-width: 0; // Allow card to shrink if needed
  flex: 1; // Take remaining space

  .v-card-text {
    flex: 1;
    overflow-y: auto;
    overflow-x: auto; // Allow horizontal scrolling if content is wider
    max-height: 100%;
    font-size: 0.8rem; // Smaller font for details
    padding: 2px; // Reduced padding
  }
}
</style>
