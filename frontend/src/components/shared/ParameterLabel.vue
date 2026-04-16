<script setup lang="ts">
import InfoPopover from './InfoPopover.vue'

interface Props {
  label: string
  description?: string
  required?: boolean
}

defineProps<Props>()
</script>

<template>
  <div class="parameter-label-wrapper d-flex align-center mb-1">
    <span class="parameter-label-text"> {{ label }}<span v-if="required" class="required-indicator">*</span> </span>
    <InfoPopover v-if="description" :text="description" class="parameter-label-info" />
  </div>
</template>

<style lang="scss" scoped>
.parameter-label-wrapper {
  width: 100%;

  .parameter-label-text {
    font-size: 0.875rem;
    line-height: 1.5;
    color: rgba(var(--v-theme-on-background), var(--v-high-emphasis-opacity));

    .required-indicator {
      color: rgb(var(--v-theme-error));
      margin-left: 2px;
    }
  }

  .parameter-label-info {
    flex-shrink: 0;
    margin-left: 10px;
  }
}
</style>
