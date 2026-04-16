<script setup lang="ts">
// 1. Vue/core imports
import { computed } from 'vue'

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers
import { getLastMessage } from '@/utils/qaUtils'

// 6. Types
import type { QATestCaseUI } from '@/types/qa'

// Props & Emits
interface Props {
  testCase: QATestCaseUI
  isSaving: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
}>()

const displayText = computed(() => {
  const item = props.testCase
  return (
    getLastMessage(item.input)?.content ||
    (item.input ? (typeof item.input === 'string' ? item.input : JSON.stringify(item.input)) : 'Click to add input...')
  )
})
</script>

<template>
  <div class="cell-preview" @click="emit('click')">
    <div class="cell-content pa-2">
      <span class="cell-preview-text">{{ displayText }}</span>
    </div>
    <VProgressCircular
      v-if="isSaving"
      indeterminate
      size="16"
      class="position-absolute"
      style="inset-block-start: 8px; inset-inline-end: 8px"
    />
  </div>
</template>

<style lang="scss" scoped>
.cell-preview {
  position: relative;
  display: block;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    .cell-content {
      border-color: rgba(var(--v-theme-primary), 0.3);
      background-color: rgba(var(--v-theme-primary), 0.05);
    }
  }
}

.cell-content {
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  background: rgba(var(--v-theme-surface), 0.5);
  block-size: 120px;
  transition: all 0.2s ease;
}

.cell-preview-text {
  display: -webkit-box;
  overflow: hidden;
  flex: 1 1 auto;
  -webkit-box-orient: vertical;
  font-size: 0.8125rem;
  -webkit-line-clamp: 10;
  line-clamp: 10;
  line-height: 1.4;
  min-inline-size: 0;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
  word-break: break-word;
}
</style>
