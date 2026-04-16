<script setup lang="ts">
defineProps<{
  loading?: boolean
  loadingText?: string
}>()
</script>

<template>
  <div class="studio-shell">
    <div class="studio-shell__toolbar">
      <div class="studio-shell__toolbar-left">
        <slot name="toolbar-left" />
      </div>
      <div class="studio-shell__toolbar-right">
        <slot name="toolbar-right" />
      </div>
    </div>

    <div class="studio-shell__canvas">
      <div v-if="loading" class="studio-shell__loading">
        <div class="d-flex flex-column align-center text-center">
          <VProgressCircular indeterminate color="primary" size="48" />
          <p v-if="loadingText" class="text-body-2 text-medium-emphasis mt-3">{{ loadingText }}</p>
        </div>
      </div>
      <slot v-else />
    </div>

    <div v-if="$slots['bottom-bar']" class="studio-shell__bottom-bar">
      <slot name="bottom-bar" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.studio-shell {
  display: flex;
  flex-direction: column;
  block-size: 100%;
  min-height: 0;
  position: relative;

  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--dnr-space-3);
    padding: var(--dnr-space-2) var(--dnr-space-4);
    min-height: var(--dnr-toolbar-height);
    border-block-end: var(--dnr-border-subtle);
    background: rgb(var(--v-theme-surface));
    flex-shrink: 0;
    z-index: 4;
  }

  &__toolbar-left,
  &__toolbar-right {
    display: flex;
    align-items: center;
    gap: var(--dnr-space-2);
  }

  &__canvas {
    flex: 1;
    min-height: 0;
    position: relative;
  }

  &__bottom-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--dnr-space-3);
    padding: var(--dnr-space-2) var(--dnr-space-4);
    border-block-start: var(--dnr-border-subtle);
    background: rgb(var(--v-theme-surface));
    flex-shrink: 0;
    z-index: 4;
  }

  &__loading {
    position: absolute;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(4px);
    background-color: rgba(var(--v-theme-surface), 0.9);
    inset: 0;
  }
}
</style>
