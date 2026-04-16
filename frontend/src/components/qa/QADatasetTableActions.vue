<script setup lang="ts">
// 1. Vue/core imports (none needed - template only)

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  selectedCount: number
  selectedWithOutputCount: number
  testCasesCount: number
  testCasesWithOutputCount: number
  hasDatasets: boolean
  judgesCount: number
  canEvaluateSelected: boolean
  evaluatingSelected: boolean
  batchRunningAll: boolean
  evaluatingAll: boolean
  isRunning: boolean
  refreshing: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'run-selected': []
  'evaluate-selected': []
  'run-all': []
  'evaluate-all': []
  'delete-selected': []
  'add-test-case': []
  refresh: []
}>()
</script>

<template>
  <VCardActions class="justify-space-between">
    <div class="d-flex align-center flex-wrap gap-4">
      <div class="d-flex flex-column gap-2">
        <VBtn variant="outlined" :disabled="selectedCount === 0 || isRunning" @click="emit('run-selected')">
          <VIcon icon="tabler-play" class="me-2" />
          Run Selected ({{ selectedCount }})
        </VBtn>

        <VBtn
          variant="outlined"
          color="secondary"
          :disabled="!canEvaluateSelected"
          :loading="evaluatingSelected"
          @click="emit('evaluate-selected')"
        >
          <VIcon icon="tabler-gavel" class="me-2" />
          Evaluate Selected ({{ selectedWithOutputCount }})
        </VBtn>
      </div>

      <div class="d-flex flex-column gap-2">
        <VBtn
          variant="outlined"
          color="primary"
          :disabled="testCasesCount === 0 || isRunning"
          :loading="batchRunningAll"
          @click="emit('run-all')"
        >
          <VIcon icon="tabler-player-play" class="me-2" />
          Run All Rows
        </VBtn>

        <VBtn
          variant="outlined"
          color="secondary"
          :disabled="testCasesWithOutputCount === 0 || judgesCount === 0"
          :loading="evaluatingAll"
          @click="emit('evaluate-all')"
        >
          <VIcon icon="tabler-gavel" class="me-2" />
          Evaluate All Rows
        </VBtn>
      </div>

      <div class="d-flex flex-column gap-2">
        <VBtn variant="outlined" :loading="refreshing" :disabled="testCasesCount === 0" @click="emit('refresh')">
          <VIcon icon="tabler-refresh" class="me-2" />
          Refresh
        </VBtn>
      </div>

      <div class="d-flex flex-column gap-2">
        <VBtn variant="outlined" color="error" :disabled="selectedCount === 0" @click="emit('delete-selected')">
          <VIcon icon="tabler-trash" class="me-2" />
          Delete Selected ({{ selectedCount }})
        </VBtn>
      </div>
    </div>

    <VBtn v-if="hasDatasets" color="primary" variant="flat" @click="emit('add-test-case')">
      <VIcon icon="tabler-plus" class="me-2" />
      Add Test Case
    </VBtn>
  </VCardActions>
</template>
