<script setup lang="ts">
// 1. Vue/core imports

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types
import type { QADataset, QAVersion } from '@/types/qa'

// Props & Emits
interface Props {
  currentDataset: QADataset | null
  currentVersion: QAVersion | null
  datasets: Array<{ title: string; value: string }>
  versions: Array<{ title: string; value: string; env?: string }>
  canManageDatasets: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'dataset-change': [datasetId: string]
  'version-change': [versionId: string]
  'create-dataset': []
  'delete-dataset': []
  'import-csv': []
  'export-csv': []
}>()

// Methods
const handleDatasetChange = (datasetId: string) => {
  emit('dataset-change', datasetId)
}

const handleVersionChange = (versionId: string) => {
  emit('version-change', versionId)
}
</script>

<template>
  <VCard class="mb-4">
    <VCardTitle class="d-flex align-center justify-space-between">
      <div class="d-flex align-center">
        <VIcon icon="tabler-database" size="24" class="me-2" />
        Evaluation Datasets
      </div>

      <div class="d-flex align-center gap-2">
        <!-- Dataset Selector -->
        <VSelect
          :model-value="currentDataset?.id"
          :items="datasets"
          item-title="title"
          item-value="value"
          label="Dataset"
          variant="outlined"
          density="compact"
          style="inline-size: 150px"
          @update:model-value="handleDatasetChange"
        />

        <!-- Version Selector -->
        <VSelect
          :model-value="currentVersion?.id"
          :items="versions"
          item-title="title"
          item-value="value"
          label="Project Version"
          variant="outlined"
          density="compact"
          style="inline-size: 200px"
          @update:model-value="handleVersionChange"
        >
          <template #selection="{ item }">
            <div class="d-flex align-center gap-2">
              <span class="font-weight-medium">{{ item.raw.title }}</span>
              <VChip
                v-if="item.raw.env"
                :color="item.raw.env === 'production' ? 'success' : 'warning'"
                size="x-small"
                class="text-capitalize"
              >
                {{ item.raw.env }}
              </VChip>
            </div>
          </template>

          <template #item="{ props: itemProps, item }">
            <VListItem v-bind="itemProps" :title="item.raw.title">
              <template #append>
                <VChip
                  v-if="item.raw.env"
                  :color="item.raw.env === 'production' ? 'success' : 'warning'"
                  size="x-small"
                  class="text-capitalize"
                >
                  {{ item.raw.env }}
                </VChip>
              </template>
            </VListItem>
          </template>
        </VSelect>

        <!-- Create Dataset Button -->
        <VBtn color="primary" variant="outlined" @click="emit('create-dataset')">
          <VIcon icon="tabler-plus" class="me-2" />
          Create Dataset
        </VBtn>

        <!-- Delete Dataset Button (Admin only) -->
        <VBtn
          v-if="canManageDatasets"
          color="error"
          variant="outlined"
          :disabled="!currentDataset"
          @click="emit('delete-dataset')"
        >
          <VIcon icon="tabler-trash" class="me-2" />
          Delete Dataset
        </VBtn>

        <!-- CSV Import/Export Menu -->
        <VMenu>
          <template #activator="{ props: menuProps }">
            <VTooltip location="bottom">
              <template #activator="{ props: tooltipProps }">
                <span v-bind="tooltipProps">
                  <VBtn v-bind="menuProps" variant="text" icon>
                    <VIcon icon="tabler-dots-vertical" />
                  </VBtn>
                </span>
              </template>
              <span>Import/Export CSV</span>
            </VTooltip>
          </template>

          <VList density="compact">
            <VTooltip location="right">
              <template #activator="{ props: tooltipProps }">
                <span v-bind="tooltipProps" style="display: block; inline-size: 100%">
                  <VListItem :disabled="!currentDataset" @click="emit('import-csv')">
                    <template #prepend>
                      <VIcon icon="tabler-download" size="18" class="me-2" />
                    </template>
                    <VListItemTitle>Import CSV</VListItemTitle>
                  </VListItem>
                </span>
              </template>
              <span>Import test cases from a CSV file</span>
            </VTooltip>

            <VTooltip location="right">
              <template #activator="{ props: tooltipProps }">
                <span v-bind="tooltipProps" style="display: block; inline-size: 100%">
                  <VListItem :disabled="!currentDataset || !currentVersion" @click="emit('export-csv')">
                    <template #prepend>
                      <VIcon icon="tabler-upload" size="18" class="me-2" />
                    </template>
                    <VListItemTitle>Export CSV</VListItemTitle>
                  </VListItem>
                </span>
              </template>
              <span>Export test cases to a CSV file</span>
            </VTooltip>
          </VList>
        </VMenu>
      </div>
    </VCardTitle>
  </VCard>
</template>
