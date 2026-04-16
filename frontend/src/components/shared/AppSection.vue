<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    description?: string
    collapsible?: boolean
    defaultOpen?: boolean
  }>(),
  { collapsible: false, defaultOpen: true }
)

const isOpen = ref(props.defaultOpen)

function toggle() {
  if (props.collapsible) isOpen.value = !isOpen.value
}
</script>

<template>
  <section class="app-section">
    <div
      v-if="title || $slots['header-actions']"
      class="app-section__header"
      :class="{ 'app-section__header--clickable': collapsible }"
      @click="toggle"
    >
      <div class="d-flex align-center gap-2">
        <VIcon
          v-if="collapsible"
          :icon="isOpen ? 'tabler-chevron-down' : 'tabler-chevron-right'"
          size="18"
          class="text-medium-emphasis"
        />
        <h4 v-if="title" class="text-h6">{{ title }}</h4>
      </div>
      <p v-if="description && isOpen" class="text-body-2 text-medium-emphasis mt-1">{{ description }}</p>
      <VSpacer />
      <slot name="header-actions" />
    </div>

    <VExpandTransition>
      <div v-show="isOpen">
        <slot />
      </div>
    </VExpandTransition>
  </section>
</template>

<style lang="scss" scoped>
.app-section {
  margin-block-end: var(--dnr-space-6);

  &__header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--dnr-space-3);
    margin-block-end: var(--dnr-space-3);

    &--clickable {
      cursor: pointer;
      user-select: none;
    }
  }
}
</style>
