<script setup lang="ts">
// 1. Vue/core imports (none here)

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  hasDatasets: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'create-dataset': []
  'add-test-case': []
}>()
</script>

<template>
  <div class="text-center pa-8">
    <VIcon icon="tabler-database-off" size="64" class="mb-4 text-disabled" />
    <h3 class="text-h6 mb-2">
      {{ hasDatasets ? 'No Test Cases' : 'No Dataset' }}
    </h3>
    <p class="text-body-2 mb-4">
      {{ hasDatasets ? 'Get started by creating your first test case' : 'Create a dataset to start adding test cases' }}
    </p>
    <VBtn color="primary" @click="hasDatasets ? emit('add-test-case') : emit('create-dataset')">
      <VIcon icon="tabler-plus" class="me-2" />
      {{ hasDatasets ? 'Add Test Case' : 'Create Dataset' }}
    </VBtn>
  </div>
</template>
