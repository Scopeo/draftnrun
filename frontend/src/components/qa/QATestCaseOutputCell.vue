<script setup lang="ts">
import { computed } from 'vue'
import type { QATestCaseUI } from '@/types/qa'

// Props & Emits
interface Props {
  testCase: QATestCaseUI
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
}>()

const formattedOutput = computed(() => {
  if (!props.testCase.output) return 'No output yet'
  try {
    const parsed = JSON.parse(props.testCase.output)
    return JSON.stringify(parsed, null, 2)
  } catch (error: unknown) {
    return props.testCase.output
  }
})
</script>

<template>
  <div class="cell-preview" :class="{ 'text-disabled': !testCase.output }" @click="testCase.output && emit('click')">
    <div class="cell-content pa-2">
      <pre class="cell-preview-text">{{ formattedOutput }}</pre>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;

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
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  background: rgba(var(--v-theme-surface), 0.5);
  block-size: 120px;
  transition: all 0.2s ease;

  &::after {
    position: absolute;
    inset-block-end: 0;
    inset-inline: 0;
    block-size: 28px;
    background: linear-gradient(transparent, rgba(var(--v-theme-surface), 1));
    content: '';
    pointer-events: none;
  }
}

.cell-preview-text {
  overflow: hidden;
  margin: 0;
  font-family: $font-mono;
  font-size: 0.75rem;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
