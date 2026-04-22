<script setup lang="ts">
import type { QADataset, QAVersion } from '@/types/qa'

interface Props {
  currentDataset: QADataset | null
  currentVersion: QAVersion | null
  datasets: Array<{ title: string; value: string }>
  versions: Array<{ title: string; value: string; env?: string }>
  canManageDatasets: boolean
  unlinkedDatasets: Array<{ title: string; value: string }>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'dataset-change': [datasetId: string]
  'version-change': [versionId: string]
  'create-dataset': []
  'add-existing-dataset': [datasetId: string]
  'remove-dataset': []
  'import-csv': []
  'export-csv': []
}>()

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

        <!-- Add Dataset (split button) -->
        <div v-if="canManageDatasets" class="d-flex split-btn-wrapper">
          <VMenu location="bottom end" :close-on-content-click="true">
            <template #activator="{ props: menuProps }">
              <VBtn color="primary" variant="outlined" v-bind="menuProps" class="split-btn-main">
                <VIcon icon="tabler-plus" class="me-2" />
                Add Dataset
              </VBtn>
            </template>

            <VList density="compact" min-width="220">
              <VListSubheader v-if="unlinkedDatasets.length > 0">Existing datasets</VListSubheader>
              <VListItem
                v-for="ds in unlinkedDatasets"
                :key="ds.value"
                @click="emit('add-existing-dataset', ds.value)"
              >
                <template #prepend>
                  <VIcon icon="tabler-database" size="18" />
                </template>
                <VListItemTitle>{{ ds.title }}</VListItemTitle>
              </VListItem>

              <VListItem
                v-if="unlinkedDatasets.length === 0"
                disabled
              >
                <VListItemTitle class="text-medium-emphasis text-body-2">
                  No other datasets in this organization
                </VListItemTitle>
              </VListItem>

              <VDivider class="my-1" />

              <VListItem @click="emit('create-dataset')">
                <template #prepend>
                  <VIcon icon="tabler-file-plus" size="18" />
                </template>
                <VListItemTitle>Create New Dataset</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
        </div>

        <!-- Remove Dataset from Project -->
        <VBtn
          v-if="canManageDatasets"
          color="warning"
          variant="outlined"
          :disabled="!currentDataset"
          @click="emit('remove-dataset')"
        >
          <VIcon icon="tabler-unlink" class="me-2" />
          Remove from Project
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

<style lang="scss" scoped>
.split-btn-wrapper {
  border-radius: 6px;
  overflow: hidden;
}

.split-btn-main {
  border-start-end-radius: 0;
  border-end-end-radius: 0;
}
</style>
