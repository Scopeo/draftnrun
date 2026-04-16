<script setup lang="ts">
import { computed } from 'vue'
import type { LLMJudge, QATestCaseUI } from '@/types/qa'
import { getEvaluationForJudge } from '@/utils/qaUtils'

interface Props {
  testCase: QATestCaseUI
  judge: LLMJudge
  loading?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: [testCase: QATestCaseUI, judge: LLMJudge]
}>()

const display = computed(() => {
  const evaluation = getEvaluationForJudge(props.testCase, props.judge.id)
  if (!evaluation) return null

  const result = evaluation.evaluation_result || {}

  if (result.type === 'error') {
    return {
      type: 'error',
      value: result.justification || 'Evaluation error',
      evaluation,
    }
  }

  if (
    (props.judge.evaluation_type === 'boolean' || props.judge.evaluation_type === 'json_equality') &&
    'result' in result &&
    result.result !== undefined
  ) {
    return { type: 'boolean', value: result.result, evaluation }
  }

  if (props.judge.evaluation_type === 'score' && 'score' in result) {
    const maxScore = result.max_score || 4

    return { type: 'score', value: result.score, maxScore, evaluation }
  }

  if (props.judge.evaluation_type === 'free_text' && 'result' in result && result.result !== undefined) {
    // Backend returns "result" and "justification" (consistent with other types)
    return { type: 'free_text', value: result.result, evaluation }
  }

  return null
})

const handleClick = () => {
  if (display.value) emit('click', props.testCase, props.judge)
}
</script>

<template>
  <div v-if="loading" class="d-flex justify-center py-2">
    <VProgressCircular indeterminate size="16" />
  </div>
  <div v-else class="evaluation-cell" :class="{ 'has-result': display }" @click.stop="handleClick">
    <template v-if="display">
      <VIcon
        v-if="display.type === 'boolean'"
        :icon="display.value ? 'tabler-check' : 'tabler-x'"
        :color="display.value ? 'success' : 'error'"
        size="20"
      />
      <span v-else-if="display.type === 'score'" class="text-body-2"> {{ display.value }}/{{ display.maxScore }} </span>
      <div v-else-if="display.type === 'free_text'" class="free-text-display">
        <template v-for="(word, index) in String(display.value || '').split(' ')" :key="`${index}-${word}`">
          <span class="free-text-word">{{ word }}</span>
        </template>
      </div>
      <VTooltip v-else-if="display.type === 'error'" location="bottom">
        <template #activator="{ props: tooltipProps }">
          <VChip v-bind="tooltipProps" color="warning" size="small">
            <VIcon icon="tabler-alert-triangle" color="warning" size="16" class="me-1" />
            Failed
          </VChip>
        </template>
        <span>{{ display.value }}</span>
      </VTooltip>
    </template>
    <span v-else class="text-disabled">-</span>
  </div>
</template>

<style scoped>
.evaluation-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  min-height: 40px;
  transition: background-color 0.2s;
  width: 100%;
  max-width: 120px;
}

.evaluation-cell:has(.free-text-display) {
  align-items: flex-start;
  padding-top: 0.5rem;
  padding-bottom: 0.5rem;
}

.evaluation-cell.has-result {
  cursor: pointer;
}

.evaluation-cell.has-result:hover {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

.evaluation-cell:not(.has-result) {
  cursor: default;
}

.free-text-display {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  max-width: 120px;
  justify-content: center;
  align-items: flex-start;
  gap: 0.25rem;
  line-height: 1.3;
  font-size: 0.7rem;
}

.free-text-word {
  display: inline-block;
  white-space: nowrap;
}
</style>
