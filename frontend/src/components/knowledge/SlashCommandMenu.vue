<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import type { SlashCommandItem } from './extensions/SlashCommands'

const props = defineProps<{
  items: SlashCommandItem[]
  command: (item: SlashCommandItem) => void
}>()

const selectedIndex = ref(0)
const listRef = ref<{ $el: HTMLElement } | null>(null)

watch(
  () => props.items,
  () => {
    selectedIndex.value = 0
  }
)

function scrollToSelected() {
  nextTick(() => {
    const list = listRef.value?.$el as HTMLElement | undefined
    if (!list) return

    const selectedItem = list.querySelector('.v-list-item--active') as HTMLElement
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: 'nearest' })
    }
  })
}

function selectItem(index: number) {
  const item = props.items[index]
  if (item) props.command(item)
}

function onKeyDown(event: KeyboardEvent): boolean {
  if (event.key === 'ArrowUp') {
    selectedIndex.value = (selectedIndex.value + props.items.length - 1) % props.items.length
    scrollToSelected()

    return true
  }

  if (event.key === 'ArrowDown') {
    selectedIndex.value = (selectedIndex.value + 1) % props.items.length
    scrollToSelected()

    return true
  }

  if (event.key === 'Enter') {
    selectItem(selectedIndex.value)

    return true
  }

  return false
}

defineExpose({ onKeyDown })
</script>

<template>
  <VCard class="slash-command-menu" elevation="8">
    <VList v-if="items.length" ref="listRef" density="compact" class="py-1">
      <VListItem
        v-for="(item, index) in items"
        :key="item.title"
        :class="{ 'v-list-item--active': index === selectedIndex }"
        @click="selectItem(index)"
        @mouseenter="selectedIndex = index"
      >
        <template #prepend>
          <VIcon :icon="item.icon" size="18" class="me-2" />
        </template>
        <VListItemTitle>{{ item.title }}</VListItemTitle>
      </VListItem>
    </VList>
    <div v-else class="slash-command-menu__empty pa-3 text-medium-emphasis text-body-2">No commands found</div>
  </VCard>
</template>

<style scoped lang="scss">
.slash-command-menu {
  min-inline-size: 200px;
  max-inline-size: 280px;
  max-block-size: 300px;
  overflow-y: auto;
}

.slash-command-menu__empty {
  text-align: center;
}
</style>
