<script setup lang="ts">
import { format } from 'date-fns'
import type { Span } from '../../types/observability'
import ContentDisplay from './ContentDisplay.vue'

const props = defineProps<{
  span: Span
}>()

const formatDateTime = (value: string) => format(new Date(value), 'dd/MM/yyyy HH:mm:ss')

// Set input and output panels to be open by default
const openPanels = ref([0, 1])

// Track RAW mode for each section
const showInputRaw = ref(false)
const showOutputRaw = ref(false)
const showDocumentsRaw = ref(false)

const duration = computed(() => {
  const start = new Date(props.span.start_time).getTime()
  const end = new Date(props.span.end_time).getTime()
  return ((end - start) / 1000).toFixed(2)
})

// Calculate rank change info for each document
const rankItems = computed(() => {
  if (!props.span.original_retrieval_rank?.length) {
    return []
  }

  const hasReranker = (props.span.original_reranker_rank?.length ?? 0) > 0

  return props.span.original_retrieval_rank.map((retrievalRank, index) => {
    const citation = index + 1

    if (!hasReranker) {
      // No reranker data - just show retrieval rank
      return {
        citation,
        retrievalRank,
        rerankerRank: null,
        change: null,
        changeIcon: '',
        changeText: 'No reranking applied',
      }
    }

    const rerankerRank = props.span.original_reranker_rank![index]
    const change = retrievalRank - rerankerRank

    let changeIcon = ''
    let changeText = ''
    if (change > 0) {
      changeIcon = '↑'
      changeText = `+${change} position${change > 1 ? 's' : ''}`
    } else if (change < 0) {
      changeIcon = '↓'
      changeText = `${change} position${Math.abs(change) > 1 ? 's' : ''}`
    } else {
      changeIcon = '━'
      changeText = 'Position unchanged'
    }

    return {
      citation,
      retrievalRank,
      rerankerRank,
      change,
      changeIcon,
      changeText,
    }
  })
})

// Calculate rank changes for retrieval/reranking table
const rankChanges = computed(() => {
  if (!props.span.original_retrieval_rank?.length || !props.span.original_reranker_rank?.length) {
    return []
  }

  return props.span.original_retrieval_rank.map((retrievalRank, index) => {
    const rerankerRank = props.span.original_reranker_rank?.[index] ?? retrievalRank
    const change = retrievalRank - rerankerRank

    return {
      citation: index + 1,
      retrievalRank,
      rerankerRank,
      change,
      changeIcon: change > 0 ? '↑' : change < 0 ? '↓' : '━',
      changeColor: change > 0 ? 'success' : change < 0 ? 'error' : 'default',
    }
  })
})
</script>

<template>
  <div class="span-details-container">
    <div class="d-flex justify-space-between align-center mb-1">
      <div>
        <div class="d-flex gap-2 text-medium-emphasis text-sm">
          <template v-if="span.name !== 'Workflow'">
            <span v-if="span.cumulative_llm_token_count_prompt">
              {{ span.cumulative_llm_token_count_prompt }} input tokens
            </span>
            <span v-if="span.cumulative_llm_token_count_completion">
              {{ span.cumulative_llm_token_count_completion }} output tokens
            </span>
          </template>
          <span v-if="span.total_credits != null"> {{ formatNumberWithSpaces(span.total_credits) }} credits </span>
          <span>{{ duration }}s</span>
        </div>
      </div>
      <VChip :color="span.status_code === 'OK' ? 'success' : 'warning'" size="small">
        {{ span.status_code }}
      </VChip>
    </div>

    <VDivider class="my-1" />

    <VExpansionPanels v-model="openPanels" variant="accordion" multiple class="compact-panels">
      <VExpansionPanel>
        <VExpansionPanelTitle>
          <span>Input</span>
          <VSpacer />
          <VBtn
            size="x-small"
            :variant="showInputRaw ? 'flat' : 'outlined'"
            :color="showInputRaw ? 'primary' : undefined"
            class="raw-btn"
            @click.stop="showInputRaw = !showInputRaw"
          >
            {{ showInputRaw ? 'PRETTY' : 'RAW' }}
          </VBtn>
        </VExpansionPanelTitle>
        <VExpansionPanelText class="pa-0">
          <VCard variant="flat" class="bg-surface">
            <VCardText class="pa-1">
              <div v-if="showInputRaw" class="json-content">
                <pre>{{ JSON.stringify(span.input, null, 2) }}</pre>
              </div>
              <ContentDisplay v-else :content="span.input" :show-timestamps="false" />
            </VCardText>
          </VCard>
        </VExpansionPanelText>
      </VExpansionPanel>

      <VExpansionPanel v-if="!(Array.isArray(span.output) && span.output.length === 0)">
        <VExpansionPanelTitle>
          <span>Output</span>
          <VSpacer />
          <VBtn
            size="x-small"
            :variant="showOutputRaw ? 'flat' : 'outlined'"
            :color="showOutputRaw ? 'primary' : undefined"
            class="raw-btn"
            @click.stop="showOutputRaw = !showOutputRaw"
          >
            {{ showOutputRaw ? 'PRETTY' : 'RAW' }}
          </VBtn>
        </VExpansionPanelTitle>
        <VExpansionPanelText class="pa-0">
          <VCard variant="flat" class="bg-surface">
            <VCardText class="pa-1">
              <div v-if="showOutputRaw" class="json-content">
                <pre>{{ JSON.stringify(span.output, null, 2) }}</pre>
              </div>
              <ContentDisplay v-else :content="span.output" :show-timestamps="false" />
            </VCardText>
          </VCard>
        </VExpansionPanelText>
      </VExpansionPanel>

      <!-- Retrieval & Ranking Panel -->
      <VExpansionPanel v-if="rankItems.length > 0">
        <VExpansionPanelTitle>
          <span>Search Results</span>
          <VTooltip location="top" max-width="400">
            <template #activator="{ props: helpProps }">
              <VIcon v-bind="helpProps" icon="tabler-help-circle" size="14" class="ms-2 icon-muted" @click.stop />
            </template>
            <div class="tooltip-content">
              <strong>How Search Results Works:</strong>
              <br /><br />
              <strong>Retrieval:</strong> The system searches your knowledge base and retrieves a set of documents
              relevant to your query. <br /><br />
              <strong>Reranking:</strong> The retrieved documents are reordered using a more advanced model, and the
              most relevant ones are selected. <br /><br />
              <strong>LLM Processing:</strong> The selected documents are sent to the language model as context to
              generate an accurate and relevant response. <br /><br />
              The arrows (↑/↓) indicate how each document's position changed from retrieval to reranking.
            </div>
          </VTooltip>
        </VExpansionPanelTitle>
        <VExpansionPanelText class="pa-0">
          <VCard variant="flat" class="bg-surface">
            <VCardText class="pa-2">
              <div class="rank-flow-items">
                <div v-for="item in rankItems" :key="item.citation" class="rank-flow-item">
                  <span class="source-label">Source [{{ item.citation }}]</span>
                  <span v-if="item.rerankerRank !== null" class="rank-flow"
                    >{{ item.retrievalRank }}→{{ item.rerankerRank }}</span
                  >
                  <span v-else class="rank-flow">#{{ item.retrievalRank }}</span>
                  <VTooltip location="top">
                    <template #activator="{ props: tooltipProps }">
                      <VIcon v-bind="tooltipProps" icon="tabler-info-circle" size="12" class="info-icon" />
                    </template>
                    <div class="rank-tooltip">
                      <div class="rank-tooltip-header">Rank History</div>
                      <VDivider class="my-1" />
                      <div class="rank-tooltip-content">
                        <div class="rank-row">
                          <span>Ranking after retrieval:</span>
                          <span class="rank-value">#{{ item.retrievalRank }}</span>
                        </div>
                        <div v-if="item.rerankerRank !== null" class="rank-row">
                          <span>Ranking after reranking:</span>
                          <span class="rank-value">#{{ item.rerankerRank }}</span>
                        </div>
                        <VDivider class="my-1" />
                        <div class="rank-status">
                          <VIcon
                            v-if="item.change !== null"
                            :icon="
                              item.change > 0
                                ? 'tabler-arrow-up'
                                : item.change < 0
                                  ? 'tabler-arrow-down'
                                  : 'tabler-minus'
                            "
                            size="14"
                            :color="item.change > 0 ? 'success' : item.change < 0 ? 'warning' : 'default'"
                          />
                          <VIcon v-else icon="tabler-search" size="14" />
                          {{ item.changeText }}
                        </div>
                      </div>
                    </div>
                  </VTooltip>
                </div>
              </div>
            </VCardText>
          </VCard>
        </VExpansionPanelText>
      </VExpansionPanel>

      <VExpansionPanel v-if="span.documents.length">
        <VExpansionPanelTitle>
          <span>Documents</span>
          <VSpacer />
          <VBtn
            size="x-small"
            :variant="showDocumentsRaw ? 'flat' : 'outlined'"
            :color="showDocumentsRaw ? 'primary' : undefined"
            class="raw-btn"
            @click.stop="showDocumentsRaw = !showDocumentsRaw"
          >
            {{ showDocumentsRaw ? 'PRETTY' : 'RAW' }}
          </VBtn>
        </VExpansionPanelTitle>
        <VExpansionPanelText class="pa-0">
          <VCard variant="flat" class="bg-surface">
            <VCardText class="pa-1">
              <div v-if="showDocumentsRaw" class="json-content">
                <pre>{{ JSON.stringify(span.documents, null, 2) }}</pre>
              </div>
              <ContentDisplay v-else :content="span.documents" :show-timestamps="false" />
            </VCardText>
          </VCard>
        </VExpansionPanelText>
      </VExpansionPanel>
    </VExpansionPanels>

    <VDivider class="my-1" />

    <div class="d-flex flex-column gap-1 text-medium-emphasis text-xs">
      <div class="d-flex align-center gap-1">
        <VIcon size="14" icon="tabler-clock" />
        <span>Started at {{ formatDateTime(span.start_time) }}</span>
      </div>
      <div class="d-flex align-center gap-1">
        <VIcon size="14" icon="tabler-clock-check" />
        <span>Ended at {{ formatDateTime(span.end_time) }}</span>
      </div>
      <div v-if="span.model_name" class="d-flex align-center gap-1">
        <VIcon size="14" icon="tabler-brain" />
        <span>Model: {{ span.model_name }}</span>
      </div>
      <div class="d-flex align-center gap-1">
        <VIcon size="14" icon="tabler-id" />
        <span>Span ID: {{ span.span_id }}</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.span-details-container {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  height: 100%;
  overflow-y: auto;
  max-height: 100%;
  padding: 4px 6px 4px 4px; // Reduced padding, space for scrollbar on right
  font-size: 0.8rem; // Smaller base font
}

.compact-panels {
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-expansion-panel) {
    margin-bottom: 2px;
  }

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-expansion-panel-title) {
    min-height: 0px;
    padding: 4px 12px;
    font-size: 0.95rem;
  }

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-expansion-panel-text__wrapper) {
    padding: 0;
  }

  /* Fix expansion panel icon direction - rotate so > shows when collapsed and v shows when expanded */
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-expansion-panel-title__icon) {
    .v-icon {
      transform: rotate(-90deg) !important;
      transition: transform 0.3s ease;
    }
  }

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-expansion-panel-title--active) {
    .v-expansion-panel-title__icon .v-icon {
      transform: rotate(90deg) !important;
    }
  }

  .raw-btn {
    margin-right: 8px;
  }

  .json-content {
    pre {
      padding: 0.5rem;
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
      font-size: 0.75rem;
    }
  }
}

.content-display {
  block-size: 100%;
  inline-size: 100%;
  font-size: 0.8rem;
}

.text-content {
  pre {
    padding: 0.5rem;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.chat-content {
  block-size: 100%;
  min-block-size: 200px;

  .chat-scroll {
    block-size: 100%;
  }

  .message-bubble {
    max-inline-size: 70%;

    p {
      margin-block-end: 0.25rem;
      white-space: pre-wrap;
    }
  }

  .message-time {
    font-size: 0.75rem;
    opacity: 0.7;
  }
}

.json-content {
  pre {
    padding: 0.5rem;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.rank-flow-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rank-flow-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  font-size: 0.75rem;
}

.source-label {
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  min-width: 60px;
}

.rank-flow {
  font-family: monospace;
  font-size: 0.7rem;
  color: rgb(var(--v-theme-on-surface));
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  padding: 2px 6px;
  border-radius: 3px;
}

.change-indicator {
  font-size: 0.9rem;
  margin-left: 2px;
}

.info-icon {
  margin-left: 4px;
  opacity: 0.5;
}

.rank-tooltip {
  padding: 8px;
  min-width: 200px;
}

.rank-tooltip-header {
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 4px;
}

.rank-tooltip-content {
  font-size: 0.75rem;
}

.rank-row {
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
}

.rank-value {
  font-weight: 600;
  font-family: monospace;
}

.rank-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.text-sm {
  font-size: 0.8rem;
}

.text-xs {
  font-size: 0.75rem;
}

.icon-muted {
  opacity: 0.6;
}

.tooltip-content {
  padding: 8px;
  line-height: 1.5;
}
</style>
