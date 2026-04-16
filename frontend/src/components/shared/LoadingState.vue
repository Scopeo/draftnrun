<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string
    size?: 'sm' | 'md' | 'lg'
  }>(),
  { size: 'md' }
)

const sizeMap = {
  sm: { spinner: 24, py: 'py-6' },
  md: { spinner: 40, py: 'py-12' },
  lg: { spinner: 56, py: 'py-16' },
}
</script>

<template>
  <div class="loading-state d-flex flex-column align-center justify-center text-center" :class="sizeMap[size].py">
    <VProgressCircular indeterminate color="primary" :size="sizeMap[size].spinner" />
    <p v-if="message" class="text-body-2 text-medium-emphasis mt-4">{{ message }}</p>
  </div>
</template>
