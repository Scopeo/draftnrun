<script setup lang="ts">
import { ref } from 'vue'
import type { Agent } from '@/composables/queries/useAgentsQuery'

interface Props {
  agent: Agent
}

const props = defineProps<Props>()

const question = ref('')
const isTesting = ref(false)
const testResults = ref<any[]>([])

// Mock test questions
const sampleQuestions = [
  'What is your main purpose?',
  'How can you help me today?',
  'What tools do you have available?',
  'Can you search the web for me?',
  'How do I contact support?',
]

const runTest = async () => {
  if (!question.value.trim()) return

  isTesting.value = true
  try {
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 2000))

    // Mock response
    const response = {
      question: question.value,
      answer: `This is a mock response from ${props.agent.name}. The agent would normally process your question and provide a helpful response based on its configuration and available tools.`,
      timestamp: new Date().toISOString(),
      confidence: Math.random() * 0.3 + 0.7, // 70-100% confidence
    }

    testResults.value.unshift(response)
    question.value = ''
  } finally {
    isTesting.value = false
  }
}

const useSampleQuestion = (sampleQ: string) => {
  question.value = sampleQ
}
</script>

<template>
  <div class="agent-qa">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h2 class="text-h5 mb-2">Q&A Testing</h2>
        <p class="text-body-1 text-medium-emphasis">Test your agent with questions and see how it responds.</p>
      </div>
      <VBtn variant="outlined" size="small" @click="() => {}">
        <VIcon icon="tabler-settings" class="me-2" />
        Test Settings
      </VBtn>
    </div>

    <!-- Question Input -->
    <VCard class="mb-6">
      <VCardText class="pa-4">
        <VTextarea
          v-model="question"
          label="Ask your agent a question"
          placeholder="Type your question here..."
          rows="3"
          class="mb-4"
        />
        <div class="d-flex justify-space-between align-center">
          <div class="d-flex gap-2 flex-wrap">
            <VChip
              v-for="sampleQ in sampleQuestions"
              :key="sampleQ"
              size="small"
              variant="outlined"
              clickable
              @click="useSampleQuestion(sampleQ)"
            >
              {{ sampleQ }}
            </VChip>
          </div>
          <VBtn color="primary" :loading="isTesting" :disabled="!question.trim()" @click="runTest">
            <VIcon icon="tabler-send" class="me-2" />
            Test Agent
          </VBtn>
        </div>
      </VCardText>
    </VCard>

    <!-- Test Results -->
    <div v-if="testResults.length > 0">
      <h3 class="text-h6 mb-4">Test Results</h3>
      <div class="test-results">
        <VCard v-for="(result, index) in testResults" :key="index" variant="outlined" class="mb-4">
          <VCardText class="pa-4">
            <div class="d-flex align-start gap-4">
              <VAvatar color="primary" variant="tonal" size="40">
                <VIcon icon="tabler-user" />
              </VAvatar>
              <div class="flex-grow-1">
                <h4 class="text-h6 mb-2">Question</h4>
                <p class="text-body-1 mb-4">{{ result.question }}</p>

                <div class="d-flex align-center gap-2 mb-3">
                  <VAvatar color="success" variant="tonal" size="32">
                    <VIcon icon="tabler-robot" />
                  </VAvatar>
                  <h4 class="text-h6">Agent Response</h4>
                  <VChip
                    size="small"
                    :color="result.confidence > 0.8 ? 'success' : result.confidence > 0.6 ? 'warning' : 'error'"
                    variant="tonal"
                  >
                    {{ Math.round(result.confidence * 100) }}% confidence
                  </VChip>
                </div>
                <p class="text-body-1 mb-3">{{ result.answer }}</p>

                <div class="d-flex align-center gap-4 text-caption text-medium-emphasis">
                  <span class="d-flex align-center gap-1">
                    <VIcon icon="tabler-clock" size="14" />
                    {{ new Date(result.timestamp).toLocaleString() }}
                  </span>
                </div>
              </div>
            </div>
          </VCardText>
        </VCard>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="testResults.length === 0" class="text-center pa-8">
      <VIcon icon="tabler-message-circle" size="64" class="mb-4 text-medium-emphasis" />
      <h3 class="text-h6 mb-2">No tests yet</h3>
      <p class="text-body-1 text-medium-emphasis mb-4">Ask your agent a question to see how it responds.</p>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.test-results {
  max-height: 600px;
  overflow-y: auto;
}
</style>
