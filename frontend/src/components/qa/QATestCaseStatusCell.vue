<script setup lang="ts">
// 1. Vue/core imports (none here)

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  status?: string | null
}

const props = defineProps<Props>()

const getStatusColor = (status: string) => {
  switch (status) {
    case 'Run':
      return 'success'
    case 'Failed':
      return 'error'
    case 'Running':
      return 'warning'
    default:
      return 'default'
  }
}
</script>

<template>
  <VChip v-if="status" size="small" :color="getStatusColor(status)">
    {{ status }}
  </VChip>
  <span v-else class="text-disabled">-</span>
</template>
