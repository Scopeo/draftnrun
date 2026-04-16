<script setup lang="ts">
withDefaults(
  defineProps<{
    icon?: string
    title?: string
    message?: string
  }>(),
  { icon: 'tabler-alert-circle', title: 'Something went wrong' }
)
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="error-state d-flex flex-column align-center justify-center py-12 text-center">
    <div class="error-state__icon mb-5">
      <VIcon :icon="icon" size="48" color="error" />
    </div>
    <h3 class="text-h6 mb-2">{{ title }}</h3>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-inline-size: 420px">
      {{ message || 'An unexpected error occurred. Please try again.' }}
    </p>
    <slot name="actions">
      <VBtn color="primary" variant="tonal" @click="$emit('retry')">Retry</VBtn>
    </slot>
  </div>
</template>

<style lang="scss" scoped>
.error-state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: 80px;
  block-size: 80px;
  border-radius: 20px;
  background: rgba(var(--v-theme-error), 0.08);
}
</style>
