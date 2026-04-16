<script setup lang="ts">
withDefaults(
  defineProps<{
    icon?: string
    title: string
    description?: string
    actionText?: string
    size?: 'sm' | 'md' | 'lg'
  }>(),
  { size: 'md' }
)
defineEmits<{ action: [] }>()

const sizeMap = {
  sm: { icon: 32, container: 56, radius: 14, py: 'py-6', heading: 'text-subtitle-1', gap: 'mb-3' },
  md: { icon: 48, container: 80, radius: 20, py: 'py-12', heading: 'text-h6', gap: 'mb-5' },
  lg: { icon: 56, container: 96, radius: 24, py: 'py-16', heading: 'text-h5', gap: 'mb-6' },
}
</script>

<template>
  <div class="empty-state d-flex flex-column align-center justify-center text-center" :class="sizeMap[size].py">
    <div
      v-if="icon"
      class="empty-state__icon"
      :class="sizeMap[size].gap"
      :style="{ '--_size': `${sizeMap[size].container}px`, '--_radius': `${sizeMap[size].radius}px` }"
    >
      <VIcon :icon="icon" :size="sizeMap[size].icon" color="grey-400" />
    </div>
    <h3 :class="sizeMap[size].heading" class="mb-2">{{ title }}</h3>
    <p v-if="description" class="text-body-2 text-medium-emphasis mb-4" style="max-inline-size: 420px">
      {{ description }}
    </p>
    <slot name="actions">
      <VBtn v-if="actionText" color="primary" @click="$emit('action')">{{ actionText }}</VBtn>
    </slot>
  </div>
</template>

<style lang="scss" scoped>
.empty-state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: var(--_size);
  block-size: var(--_size);
  border-radius: var(--_radius);
  background: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
