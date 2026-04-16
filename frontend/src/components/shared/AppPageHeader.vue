<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

defineProps<{
  title: string
  description?: string
  backTo?: RouteLocationRaw
}>()
</script>

<template>
  <div class="app-page-header">
    <RouterLink
      v-if="backTo"
      :to="backTo as string"
      class="app-page-header__back text-body-2 text-medium-emphasis mb-1"
    >
      <VIcon icon="tabler-arrow-left" size="16" />
      Back
    </RouterLink>

    <div class="d-flex align-center flex-wrap gap-3 mb-1">
      <h3 class="text-h4">
        <slot name="title">{{ title }}</slot>
      </h3>
      <slot name="badge" />
      <VSpacer />
      <slot name="actions" />
    </div>

    <div v-if="$slots['secondary-actions']" class="d-flex align-center flex-wrap gap-2 mb-2">
      <slot name="secondary-actions" />
    </div>

    <p
      v-if="description || $slots.description"
      class="text-body-2 text-medium-emphasis mt-1"
      style="max-inline-size: 600px"
    >
      <slot name="description">{{ description }}</slot>
    </p>

    <div v-if="$slots.filters" class="mt-4">
      <slot name="filters" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.app-page-header {
  margin-block-end: var(--dnr-space-6);

  &__back {
    display: inline-flex;
    align-items: center;
    gap: var(--dnr-space-1);
    text-decoration: none;
    color: inherit;

    &:hover {
      text-decoration: underline;
    }
  }
}
</style>
