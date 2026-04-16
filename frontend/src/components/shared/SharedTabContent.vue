<script setup lang="ts">
import QADatasetTable from '@/components/qa/QADatasetTable.vue'

interface Props {
  tabValue: string
  projectId: string
  graphRunners?: any[]
}

const props = withDefaults(defineProps<Props>(), {
  graphRunners: () => [],
})
</script>

<template>
  <!-- QA Tab Content -->
  <VCard v-if="tabValue === 'qa'" class="tab-card">
    <VCardTitle class="d-flex align-center tab-card-header">
      <VIcon icon="tabler-test-pipe" size="24" class="me-2" />
      Quality Assurance
    </VCardTitle>
    <VDivider />
    <VCardText class="tab-card-content">
      <QADatasetTable :project-id="projectId" :graph-runners="graphRunners" />
    </VCardText>
  </VCard>
</template>

<style scoped>
.tab-card {
  display: flex;
  overflow: hidden;
  flex-direction: column;
  block-size: 100%;
}

.tab-card-header {
  flex-shrink: 0;
}

.tab-card-content {
  flex: 1;
  overflow-y: auto;
}
</style>
