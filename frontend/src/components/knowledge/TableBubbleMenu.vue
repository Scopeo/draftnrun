<script setup lang="ts">
import type { Editor } from '@tiptap/core'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import { computed } from 'vue'

const props = defineProps<{
  editor: Editor
}>()

const isInTable = computed(() => {
  if (!props.editor?.state?.selection) return false
  const { $from } = props.editor.state.selection
  for (let d = $from.depth; d > 0; d--) {
    if ($from.node(d).type.name === 'table') return true
  }
  return false
})

function addRowAbove() {
  props.editor.chain().focus().addRowBefore().run()
}

function addRowBelow() {
  props.editor.chain().focus().addRowAfter().run()
}

function deleteRow() {
  props.editor.chain().focus().deleteRow().run()
}

function addColumnLeft() {
  props.editor.chain().focus().addColumnBefore().run()
}

function addColumnRight() {
  props.editor.chain().focus().addColumnAfter().run()
}

function deleteColumn() {
  props.editor.chain().focus().deleteColumn().run()
}

function deleteTable() {
  props.editor.chain().focus().deleteTable().run()
}
</script>

<template>
  <BubbleMenu
    :editor="editor"
    :options="{ placement: 'top', offset: 8 }"
    :should-show="() => isInTable"
    class="table-bubble-menu"
  >
    <VBtnGroup density="compact" variant="flat" color="surface">
      <!-- Row controls -->
      <VBtn size="x-small" @click="addRowAbove">
        <VIcon icon="tabler-row-insert-top" size="16" />
        <VTooltip activator="parent" location="top">Add row above</VTooltip>
      </VBtn>
      <VBtn size="x-small" @click="addRowBelow">
        <VIcon icon="tabler-row-insert-bottom" size="16" />
        <VTooltip activator="parent" location="top">Add row below</VTooltip>
      </VBtn>
      <VBtn size="x-small" color="error" @click="deleteRow">
        <VIcon icon="tabler-row-remove" size="16" />
        <VTooltip activator="parent" location="top">Delete row</VTooltip>
      </VBtn>

      <VDivider vertical class="mx-1" />

      <!-- Column controls -->
      <VBtn size="x-small" @click="addColumnLeft">
        <VIcon icon="tabler-column-insert-left" size="16" />
        <VTooltip activator="parent" location="top">Add column left</VTooltip>
      </VBtn>
      <VBtn size="x-small" @click="addColumnRight">
        <VIcon icon="tabler-column-insert-right" size="16" />
        <VTooltip activator="parent" location="top">Add column right</VTooltip>
      </VBtn>
      <VBtn size="x-small" color="error" @click="deleteColumn">
        <VIcon icon="tabler-column-remove" size="16" />
        <VTooltip activator="parent" location="top">Delete column</VTooltip>
      </VBtn>

      <VDivider vertical class="mx-1" />

      <!-- Table control -->
      <VBtn size="x-small" color="error" @click="deleteTable">
        <VIcon icon="tabler-table-off" size="16" />
        <VTooltip activator="parent" location="top">Delete table</VTooltip>
      </VBtn>
    </VBtnGroup>
  </BubbleMenu>
</template>

<style scoped lang="scss">
.table-bubble-menu {
  background: rgb(var(--v-theme-surface));
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 4px;
}
</style>
