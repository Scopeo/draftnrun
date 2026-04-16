<script setup lang="ts">
interface Props {
  showSaveToQADialog: boolean
  selectedQADataset: string | null
  qaDatasets: Array<{ id: string; dataset_name: string }>
  loadingQADatasets: boolean
  savingToQA: boolean
  saveToQAError: string | null
  saveToQASuccess: boolean
  showCreateDataset: boolean
  newDatasetName: string
  creatingDataset: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:showSaveToQADialog': [value: boolean]
  'update:selectedQADataset': [value: string | null]
  'update:showCreateDataset': [value: boolean]
  'update:newDatasetName': [value: string]
  save: []
  createDataset: []
}>()

const closeDialog = () => {
  emit('update:showSaveToQADialog', false)
}

const closeCreateDataset = () => {
  emit('update:showCreateDataset', false)
  emit('update:newDatasetName', '')
}
</script>

<template>
  <VDialog
    :model-value="showSaveToQADialog"
    max-width="500"
    @update:model-value="emit('update:showSaveToQADialog', $event)"
  >
    <VCard>
      <VCardTitle>Save Conversation to QA Dataset</VCardTitle>
      <VCardText>
        <!-- Dataset selection dropdown -->
        <VSelect
          :model-value="selectedQADataset"
          :items="qaDatasets"
          item-title="dataset_name"
          item-value="id"
          label="Select QA Dataset"
          variant="outlined"
          :loading="loadingQADatasets"
          :disabled="creatingDataset"
          @update:model-value="emit('update:selectedQADataset', $event)"
        />

        <!-- Create new dataset inline section -->
        <div class="mt-4">
          <div v-if="!showCreateDataset" class="d-flex align-center">
            <VBtn
              variant="text"
              size="small"
              prepend-icon="tabler-plus"
              @click="emit('update:showCreateDataset', true)"
            >
              Create new dataset
            </VBtn>
          </div>

          <div v-else>
            <div class="d-flex align-center gap-2">
              <VTextField
                :model-value="newDatasetName"
                label="New Dataset Name"
                variant="outlined"
                density="compact"
                placeholder="Enter dataset name..."
                :disabled="creatingDataset"
                hide-details
                class="flex-grow-1"
                @update:model-value="emit('update:newDatasetName', $event)"
                @keyup.enter="newDatasetName.trim() && emit('createDataset')"
              />
              <VBtn
                color="primary"
                variant="tonal"
                :disabled="!newDatasetName.trim() || creatingDataset"
                :loading="creatingDataset"
                @click="emit('createDataset')"
              >
                Create
              </VBtn>
              <VBtn icon variant="text" size="small" @click="closeCreateDataset">
                <VIcon icon="tabler-x" />
              </VBtn>
            </div>
          </div>
        </div>

        <VAlert v-if="saveToQAError" type="error" class="mt-4">
          {{ saveToQAError }}
        </VAlert>

        <VAlert v-if="saveToQASuccess" type="success" class="mt-4"> Successfully saved to QA dataset! </VAlert>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn @click="closeDialog">
          {{ !saveToQASuccess ? 'Cancel' : 'Done' }}
        </VBtn>
        <VBtn
          v-if="!saveToQASuccess"
          color="success"
          :disabled="!selectedQADataset || savingToQA"
          :loading="savingToQA"
          @click="emit('save')"
        >
          Save
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
