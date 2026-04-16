<script setup lang="ts">
withDefaults(
  defineProps<{
    width?: 'full' | 'editor'
  }>(),
  { width: 'full' }
)
</script>

<template>
  <div class="app-page" :class="`app-page--${width}`">
    <slot />
  </div>
</template>

<style lang="scss" scoped>
.app-page {
  width: 100%;

  &--editor {
    display: flex;
    flex-direction: column;
    min-height: 0;
    flex: 1;
  }
}
</style>
