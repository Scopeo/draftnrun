<script setup lang="ts">
import { type TraceListParams, useTraceDetailsQuery, useTracesQuery } from '@/composables/queries/useObservabilityQuery'
import { DATE_RANGES, formatDuration, useDateRangeFilter } from '@/composables/useDateRangeFilter'
import { useSpanIconMap } from '@/composables/useSpanIconMap'
import { CALL_TYPE_OPTIONS, type CallType, type Span } from '@/types/observability'
import { formatDateCalendar } from '@/utils/formatters'
import { useQueryClient } from '@tanstack/vue-query'
import { useDebounceFn } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SpanDetails from './SpanDetails.vue'
import TreeItem from './TreeItem.vue'

const route = useRoute()
const queryClient = useQueryClient()
const projectId = ref(route.params.id as string)
const spanIconMap = useSpanIconMap(projectId)

const selectedSpan = ref<Span | null>(null)
const rootSpan = ref<Span | null>(null)
const traceDetails = ref<any>(null) // Store full trace tree details
const showList = ref(true)
const sortDirection = ref<'asc' | 'desc'>('desc')
const newTraceIds = ref<Set<string>>(new Set()) // Track new traces for animation
const callTypeFilter = ref<CallType>('all')
const callTypeOptions = CALL_TYPE_OPTIONS

// Pagination state
const currentPage = ref(1)
const itemsPerPage = ref(20)

const resetPage = () => {
  currentPage.value = 1
  newTraceIds.value.clear()
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

// Query params for traces list
const traceParams = computed<TraceListParams>(() => ({
  call_type: callTypeFilter.value !== 'all' ? callTypeFilter.value : undefined,
  page: currentPage.value,
  size: itemsPerPage.value,
  search: searchValue.value || undefined,
  ...dateRangeParams.value,
}))

// Queries
const tracesQuery = useTracesQuery(projectId, traceParams)
const selectedTraceId = ref<string | undefined>(undefined)

const traceDetailsQuery = useTraceDetailsQuery(
  selectedTraceId,
  computed(() => !!selectedTraceId.value)
)

// Extract query state
const spans = computed(() => tracesQuery.data.value?.traces || [])
const totalPages = computed(() => tracesQuery.data.value?.pagination.total_pages ?? 1)
const initialLoading = computed(() => tracesQuery.isLoading.value && !tracesQuery.data.value)
const isFetching = computed(() => tracesQuery.isFetching.value)
const loadingDetails = computed(() => traceDetailsQuery.isLoading.value)
const error = computed(() => tracesQuery.error.value?.message || traceDetailsQuery.error.value?.message || null)

// Watch for trace details query data changes
watch(
  () => traceDetailsQuery.data.value,
  data => {
    if (data) {
      traceDetails.value = data
      rootSpan.value = data
      selectedSpan.value = data
    }
  }
)

// Headers for VDataTable
const headers = computed(() => [
  {
    title: 'Date',
    key: 'date',
    sortable: true,
    width: '15%',
  },
  {
    title: 'Input',
    key: 'input',
    sortable: false,
    width: '30%',
  },
  {
    title: 'Output',
    key: 'output',
    sortable: false,
    width: '30%',
  },
  {
    title: 'Tokens',
    key: 'tokens',
    sortable: false,
    width: '10%',
    align: 'center' as const,
  },
  {
    title: 'Duration',
    key: 'duration',
    sortable: false,
    width: '15%',
    align: 'center' as const,
  },
])

// Update the rootSpans computed property to include sorting
const rootSpans = computed(() => {
  const filteredSpans = spans.value.filter((span: Span) => !span.parent_id)
  return filteredSpans.sort((a, b) => {
    const timeA = new Date(a.start_time).getTime()
    const timeB = new Date(b.start_time).getTime()
    return sortDirection.value === 'asc' ? timeA - timeB : timeB - timeA
  })
})

const getTotalTokens = (span: Span) => {
  return (span.cumulative_llm_token_count_prompt || 0) + (span.cumulative_llm_token_count_completion || 0)
}

const handleSpanSelect = (span: Span) => {
  showList.value = false

  if ((span as any).trace_id) {
    // Set the trace ID to trigger the query
    selectedTraceId.value = (span as any).trace_id
  } else {
    rootSpan.value = span
    selectedSpan.value = span
  }
}

const handleTreeSpanSelect = (span: Span) => {
  selectedSpan.value = span
}

const handleBack = () => {
  rootSpan.value = null
  selectedSpan.value = null
  traceDetails.value = null
  selectedTraceId.value = undefined
  showList.value = true
}

const toggleSort = () => {
  sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
}

const isNewTrace = (spanId: string) => {
  return newTraceIds.value.has(spanId)
}

// Manual refresh function
const handleRefresh = () => {
  newTraceIds.value.clear()
  queryClient.invalidateQueries({ queryKey: ['traces', projectId.value] })
}

watch(
  () => route.params.id,
  newId => {
    if (newId && typeof newId === 'string' && newId !== projectId.value) {
      projectId.value = newId
      selectedSpan.value = null
      rootSpan.value = null
      traceDetails.value = null
      selectedTraceId.value = undefined
      showList.value = true
      newTraceIds.value.clear()
    }
  }
)
</script>

<template>
  <div class="observability-container d-flex gap-4">
    <VCard :class="showList ? 'flex-grow-1' : 'tree-card'">
      <VCardTitle class="d-flex align-center px-4 py-2">
        <VBtn v-if="!showList" icon variant="text" size="small" class="me-2" @click="handleBack">
          <VIcon icon="tabler-arrow-left" />
        </VBtn>
        <span class="text-h6">{{ showList ? 'Trace List' : 'Trace Tree' }}</span>
        <VSpacer />
        <div v-if="showList" class="d-flex align-center gap-2">
          <div class="d-flex align-center gap-2">
            <VIcon icon="tabler-calendar" size="20" />
            <VSelect
              v-model="selectedRange"
              :items="dateRanges"
              item-title="title"
              item-value="value"
              density="compact"
              hide-details
              variant="plain"
              class="date-range-select"
              style="max-inline-size: 180px"
              @update:model-value="resetPage"
            />
          </div>
          <template v-if="isCustomRange">
            <VTextField
              v-model="customStartDate"
              type="datetime-local"
              density="compact"
              hide-details
              variant="outlined"
              label="Start"
              style="max-inline-size: 210px"
              @update:model-value="resetPage"
            />
            <VTextField
              v-model="customEndDate"
              type="datetime-local"
              density="compact"
              hide-details
              variant="outlined"
              label="End"
              style="max-inline-size: 210px"
              @update:model-value="resetPage"
            />
          </template>
          <VSelect
            v-model="callTypeFilter"
            :items="callTypeOptions"
            item-title="label"
            item-value="value"
            density="compact"
            hide-details
            variant="outlined"
            style="min-width: 160px"
            @update:model-value="resetPage"
          >
            <template #selection="{ item }">
              <div class="d-flex align-center gap-1">
                <VIcon v-if="item.raw.icon" :icon="item.raw.icon" size="16" />
                <span>{{ item.raw.label }}</span>
              </div>
            </template>
            <template #item="{ item, props: itemProps }">
              <VListItem v-bind="itemProps" :prepend-icon="item.raw.icon" :title="item.raw.label" />
            </template>
          </VSelect>
          <VBtn icon variant="text" size="small" :loading="isFetching" title="Refresh" @click="handleRefresh">
            <VIcon icon="tabler-refresh" />
          </VBtn>
        </div>
      </VCardTitle>

      <VCardText class="pa-4">
        <LoadingState v-if="initialLoading || loadingDetails" size="sm" />
        <ErrorState v-else-if="error" :message="error" />

        <!-- List View with detailed columns -->
        <div v-else-if="showList">
          <div class="mb-4">
            <VTextField
              v-model="searchInput"
              prepend-inner-icon="tabler-search"
              placeholder="Search traces by keyword..."
              variant="outlined"
              density="compact"
              hide-details
              clearable
              :loading="isFetching && !!searchValue"
              @update:model-value="debouncedSearch"
            />
          </div>
          <EmptyState
            v-if="rootSpans.length === 0 && searchValue"
            icon="tabler-search-off"
            title="No traces matching your query"
            :description="`No traces found for &quot;${searchValue}&quot;. Try a different keyword.`"
            action-text="Clear Search"
            @action="searchInput = ''"
          />
          <EmptyState
            v-else-if="rootSpans.length === 0"
            icon="tabler-route"
            title="No traces loaded"
            description="Click the refresh button to load observability data"
            action-text="Load Traces"
            @action="handleRefresh"
          />
          <VDataTableServer
            v-else
            v-model:page="currentPage"
            v-model:items-per-page="itemsPerPage"
            :headers="headers"
            :items="rootSpans"
            :items-length="-1"
            :loading="isFetching"
            density="compact"
            hover
            class="trace-list"
            hide-default-footer
          >
            <thead>
              <tr>
                <th style="inline-size: 15%" class="cursor-pointer" @click="toggleSort">
                  <div class="d-flex align-center">
                    Date
                    <VIcon
                      size="16"
                      :icon="sortDirection === 'asc' ? 'tabler-chevron-up' : 'tabler-chevron-down'"
                      class="ms-1"
                    />
                  </div>
                </th>
                <th style="inline-size: 30%">Input</th>
                <th style="inline-size: 30%">Output</th>
                <th style="inline-size: 10%" class="text-center">Tokens</th>
                <th style="inline-size: 15%" class="text-center">Duration</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="span in rootSpans"
                :key="span.span_id"
                class="cursor-pointer"
                :class="{ 'new-trace': isNewTrace(span.span_id) }"
                @click="handleSpanSelect(span)"
              >
                <td>
                  <div class="d-flex align-center">
                    <VIcon size="16" icon="tabler-activity" color="primary" class="me-2" />
                    <div class="date-time-container">
                      <div class="date-line">
                        {{ formatDateCalendar(span.start_time) }}
                      </div>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="text-wrap input-wrap">
                    {{ span.input_preview || '-' }}
                  </div>
                </td>
                <td>
                  <div class="text-wrap">
                    {{ span.output_preview || '-' }}
                  </div>
                </td>
                <td class="text-center">
                  <div class="d-flex align-center justify-center">{{ getTotalTokens(span) || '-' }}</div>
                </td>
                <td class="text-center">
                  <VChip size="small" color="primary" variant="tonal">
                    {{ formatDuration(span.start_time, span.end_time) }}s
                  </VChip>
                </td>
              </tr>
            </tbody>

            <!-- Date Column -->
            <template #item.date="{ item }">
              <div class="d-flex align-center">
                <VIcon size="16" icon="tabler-activity" color="primary" class="me-2" />
                <div class="date-time-container">
                  <div class="date-line">
                    {{ formatDateCalendar(item.start_time) }}
                  </div>
                </div>
              </div>
            </template>

            <!-- Input Column -->
            <template #item.input="{ item }">
              <div class="text-wrap input-wrap">
                {{ item.input_preview || '-' }}
              </div>
            </template>

            <!-- Output Column -->
            <template #item.output="{ item }">
              <div class="text-wrap">
                {{ item.output_preview || '-' }}
              </div>
            </template>

            <!-- Tokens Column -->
            <template #item.tokens="{ item }">
              <div class="d-flex align-center justify-center">{{ getTotalTokens(item) || '-' }}</div>
            </template>

            <!-- Duration Column -->
            <template #item.duration="{ item }">
              <VChip size="small" color="primary" variant="tonal">
                {{ formatDuration(item.start_time, item.end_time) }}s
              </VChip>
            </template>

            <!-- Row click handler -->
            <template #item="{ item, props }">
              <tr
                v-bind="props"
                class="cursor-pointer"
                :class="{ 'new-trace': isNewTrace(item.span_id) }"
                @click="handleSpanSelect(item)"
              >
                <td>
                  <div class="d-flex align-center">
                    <VIcon size="16" icon="tabler-activity" color="primary" class="me-2" />
                    <div class="date-time-container">
                      <div class="date-line">{{ new Date(item.start_time).toLocaleDateString() }}</div>
                      <div class="time-line">{{ new Date(item.start_time).toLocaleTimeString() }}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="text-wrap input-wrap">
                    {{ item.input_preview || '-' }}
                  </div>
                </td>
                <td>
                  <div class="text-wrap">
                    {{ item.output_preview || '-' }}
                  </div>
                </td>
                <td class="text-center">
                  <div class="d-flex align-center justify-center">{{ getTotalTokens(item) || '-' }}</div>
                </td>
                <td class="text-center">
                  <VChip size="small" color="primary" variant="tonal">
                    {{ formatDuration(item.start_time, item.end_time) }}s
                  </VChip>
                </td>
              </tr>
            </template>

            <!-- Pagination at bottom -->
            <template #bottom>
              <div class="d-flex justify-center py-2">
                <VPagination
                  v-model="currentPage"
                  :length="totalPages"
                  :total-visible="5"
                  size="small"
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
            </template>
          </VDataTableServer>
        </div>

        <!-- Tree View -->
        <div v-else-if="rootSpan" class="trace-tree">
          <TreeItem
            :item="rootSpan"
            :level="0"
            :selected-span-id="selectedSpan?.span_id"
            :icon-map="spanIconMap"
            @click="handleTreeSpanSelect"
          />
        </div>
      </VCardText>
    </VCard>

    <!-- Details Panel -->
    <VCard v-if="selectedSpan" class="flex-grow-1 details-card">
      <VCardText class="details-card-content">
        <SpanDetails :span="selectedSpan" />
      </VCardText>
    </VCard>
  </div>
</template>

<style lang="scss" scoped>
.pagination-minimal {
  :deep(.v-pagination__item--is-active .v-btn) {
    background: rgb(var(--v-theme-primary)) !important;
    color: rgb(var(--v-theme-on-primary)) !important;
    border-radius: var(--dnr-radius-md);
  }
}

.observability-container {
  block-size: calc(100dvh - var(--dnr-toolbar-height) - var(--dnr-page-padding) * 2);
  overflow: hidden;
  position: relative;
  overscroll-behavior: contain;
}

.trace-list {
  border: var(--dnr-border-default);
  border-radius: var(--dnr-radius-sm);

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(td) {
    padding: var(--dnr-space-3);
    vertical-align: middle;
    white-space: normal;
  }

  .text-wrap {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    line-height: 24px;
    text-overflow: ellipsis;
    word-break: break-word;
  }

  .input-wrap {
    -webkit-line-clamp: 2;
    max-block-size: 48px;
  }

  .text-wrap:not(.input-wrap) {
    -webkit-line-clamp: 3;
    max-block-size: 72px;
  }
}

.tree-card {
  flex: 0 0 auto;
  inline-size: min(480px, 40%);
  min-inline-size: 280px;
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  overflow: hidden;

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-card-text) {
    flex: 1;
    min-block-size: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
}

.trace-tree {
  overflow-y: auto;
  overflow-x: hidden;
  border-radius: var(--dnr-radius-md);
  flex: 1;
  min-block-size: 0;
  overscroll-behavior: contain;
}

.details-card {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  overflow: hidden;
}

.details-card-content {
  flex: 1;
  min-block-size: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--dnr-space-4);
  overscroll-behavior: contain;
}

.date-time-container {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.date-line,
.time-line {
  font-size: 0.875rem;
}

.new-trace {
  animation: newTraceGlow 2s ease-out;
  position: relative;
}

.date-range-select {
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-field__input) {
    min-block-size: 30px;
    padding-block: 0;
  }
}

@keyframes newTraceGlow {
  0% {
    background-color: rgba(var(--v-theme-primary), 0.2);
    transform: scale(1.01);
  }
  50% {
    background-color: rgba(var(--v-theme-primary), 0.1);
  }
  100% {
    background-color: transparent;
    transform: scale(1);
  }
}
</style>
