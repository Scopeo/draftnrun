<script setup lang="ts">
// 1. Vue/core imports (none here)

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  show: boolean
  isBusy: boolean
  text: string
}

defineProps<Props>()
</script>

<template>
  <VAlert v-if="show" :color="isBusy ? 'warning' : 'success'" variant="tonal" density="compact" class="mb-4">
    <VIcon v-if="isBusy" icon="tabler-loader-2" class="me-2" />
    {{ text }}
  </VAlert>
</template>
