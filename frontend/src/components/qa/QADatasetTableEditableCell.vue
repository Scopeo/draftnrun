<script setup lang="ts">
defineProps<{
  modelValue: string | null | undefined
  saving: boolean
  placeholder?: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
  cellClick: [event: MouseEvent]
}>()
</script>

<template>
  <div class="editable-cell">
    <VTextarea
      :model-value="modelValue || ''"
      variant="plain"
      density="compact"
      rows="5"
      no-resize
      hide-details
      :placeholder="placeholder || 'Click to add value...'"
      @update:model-value="$emit('update:modelValue', $event as string)"
      @click.stop="$emit('cellClick', $event)"
    />
    <VProgressCircular
      v-if="saving"
      indeterminate
      size="16"
      class="position-absolute"
      style="inset-block-start: 8px; inset-inline-end: 8px"
    />
  </div>
</template>

<style lang="scss" scoped>
.editable-cell {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  background: rgba(var(--v-theme-surface), 0.5);
  block-size: 120px;
  transition: all 0.2s ease;

  &:hover,
  &:focus-within {
    border-color: rgba(var(--v-theme-primary), 0.3);
    background-color: rgba(var(--v-theme-primary), 0.05);
  }

  :deep(.v-textarea) {
    block-size: 100%;

    .v-field {
      block-size: 100%;
    }

    .v-field__field {
      block-size: 100%;
    }

    .v-field__input {
      overflow: auto;
      padding: 8px;
      font-size: 0.8125rem;
      line-height: 1.4;
      mask-image: none;
    }
  }
}
</style>
