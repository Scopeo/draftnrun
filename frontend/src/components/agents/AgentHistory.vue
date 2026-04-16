<script setup lang="ts">
import HistoryPanel from '@/components/shared/HistoryPanel.vue'
import type { Agent } from '@/composables/queries/useAgentsQuery'

interface Props {
  agent: Agent
}

defineProps<Props>()

// Mock history data
const historyItems = [
  {
    id: '1',
    timestamp: '2024-01-22T14:30:00Z',
    type: 'conversation' as const,
    title: 'Customer Support Session',
    summary: 'Helped user resolve billing issue',
    duration: '5m 23s',
    messages: 12,
  },
  {
    id: '2',
    timestamp: '2024-01-22T10:15:00Z',
    type: 'test' as const,
    title: 'Q&A Testing Session',
    summary: 'Tested agent responses to common questions',
    duration: '3m 45s',
    messages: 8,
  },
  {
    id: '3',
    timestamp: '2024-01-21T16:45:00Z',
    type: 'conversation' as const,
    title: 'Product Inquiry',
    summary: 'Provided information about product features',
    duration: '7m 12s',
    messages: 15,
  },
]

// Event handlers
const handleExport = () => {
  // Export functionality to be implemented
}

const handleFilter = () => {
  // Filter functionality to be implemented
}

const handleView = (item: any) => {
  // View functionality to be implemented
}

const handleDownload = (item: any) => {
  // Download functionality to be implemented
}

const handleEmptyStateAction = () => {
  // Empty state action to be implemented
}
</script>

<template>
  <HistoryPanel
    title="Agent History"
    description="View conversation history and usage patterns."
    :items="historyItems"
    empty-state-title="No history yet"
    empty-state-message="Start using your agent to see conversation history here."
    empty-state-action-text="Test Agent"
    @export="handleExport"
    @filter="handleFilter"
    @view="handleView"
    @download="handleDownload"
    @empty-state-action="handleEmptyStateAction"
  />
</template>
