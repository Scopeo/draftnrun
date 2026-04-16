<script setup lang="ts">
interface HistoryItem {
  id: string
  timestamp: string
  type: 'conversation' | 'test'
  title: string
  summary: string
  duration: string
  messages: number
}

interface Props {
  title?: string
  description?: string
  items: HistoryItem[]
  loading?: boolean
  emptyStateTitle?: string
  emptyStateMessage?: string
  emptyStateActionText?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'History',
  description: 'View conversation history and usage patterns.',
  loading: false,
  emptyStateTitle: 'No history yet',
  emptyStateMessage: 'Start using to see conversation history here.',
  emptyStateActionText: 'Get Started',
})

const emit = defineEmits<{
  export: []
  filter: []
  view: [item: HistoryItem]
  download: [item: HistoryItem]
  emptyStateAction: []
}>()

const handleExport = () => {
  emit('export')
}

const handleFilter = () => {
  emit('filter')
}

const handleView = (item: HistoryItem) => {
  emit('view', item)
}

const handleDownload = (item: HistoryItem) => {
  emit('download', item)
}

const handleEmptyStateAction = () => {
  emit('emptyStateAction')
}
</script>

<template>
  <div class="history-panel">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h2 class="text-h5 mb-2">{{ props.title }}</h2>
        <p class="text-body-1 text-medium-emphasis">
          {{ props.description }}
        </p>
      </div>
      <div class="d-flex gap-2">
        <VBtn variant="outlined" size="small" @click="handleExport">
          <VIcon icon="tabler-download" class="me-2" />
          Export
        </VBtn>
        <VBtn variant="outlined" size="small" @click="handleFilter">
          <VIcon icon="tabler-filter" class="me-2" />
          Filter
        </VBtn>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState v-if="props.loading" />

    <!-- History List -->
    <div v-else-if="props.items.length > 0" class="history-list">
      <VCard v-for="item in props.items" :key="item.id" variant="outlined" class="history-item mb-3">
        <VCardText class="pa-4">
          <div class="d-flex align-center justify-space-between">
            <div class="d-flex align-center gap-4">
              <VAvatar :color="item.type === 'conversation' ? 'success' : 'info'" variant="tonal" size="40">
                <VIcon :icon="item.type === 'conversation' ? 'tabler-message-circle' : 'tabler-test-pipe'" />
              </VAvatar>
              <div>
                <h4 class="text-h6 mb-1">{{ item.title }}</h4>
                <p class="text-body-2 text-medium-emphasis mb-2">
                  {{ item.summary }}
                </p>
                <div class="d-flex align-center gap-4 text-caption">
                  <span class="d-flex align-center gap-1">
                    <VIcon icon="tabler-clock" size="14" />
                    {{ new Date(item.timestamp).toLocaleString() }}
                  </span>
                  <span class="d-flex align-center gap-1">
                    <VIcon icon="tabler-timer" size="14" />
                    {{ item.duration }}
                  </span>
                  <span class="d-flex align-center gap-1">
                    <VIcon icon="tabler-message" size="14" />
                    {{ item.messages }} messages
                  </span>
                </div>
              </div>
            </div>
            <div class="d-flex gap-2">
              <VBtn variant="text" size="small" @click="handleView(item)">
                <VIcon icon="tabler-eye" />
              </VBtn>
              <VBtn variant="text" size="small" @click="handleDownload(item)">
                <VIcon icon="tabler-download" />
              </VBtn>
            </div>
          </div>
        </VCardText>
      </VCard>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      icon="tabler-history"
      :title="props.emptyStateTitle"
      :description="props.emptyStateMessage"
      :action-text="props.emptyStateActionText"
      @action="handleEmptyStateAction"
    />
  </div>
</template>

<style lang="scss" scoped>
.history-item {
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
}
</style>
