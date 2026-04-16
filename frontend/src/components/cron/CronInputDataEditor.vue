<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Message {
  role: string
  content: string
}

interface InputData {
  messages?: Message[]
  [key: string]: any
}

const props = defineProps<{
  modelValue?: InputData
}>()

const emit = defineEmits<{
  'update:modelValue': [value: InputData]
}>()

// Messages list
const messages = ref<Message[]>(
  props.modelValue?.messages?.length ? props.modelValue.messages : [{ role: 'user', content: '' }]
)

// Additional fields (non-messages keys)
const additionalFields = ref<Array<{ key: string; value: string }>>(
  Object.entries(props.modelValue || {})
    .filter(([key]) => key !== 'messages')
    .map(([key, value]) => ({
      key,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }))
)

// Advanced mode
const isAdvancedMode = ref(false)
const jsonInput = ref('')
const jsonError = ref('')

const roleOptions = [
  { title: 'User', value: 'user' },
  { title: 'Assistant', value: 'assistant' },
  { title: 'System', value: 'system' },
]

const addMessage = () => {
  messages.value.push({ role: 'user', content: '' })
}

const removeMessage = (index: number) => {
  if (messages.value.length > 1) {
    messages.value.splice(index, 1)
  }
}

const addField = () => {
  additionalFields.value.push({ key: '', value: '' })
}

const removeField = (index: number) => {
  additionalFields.value.splice(index, 1)
}

// Computed input data - includes messages AND additional fields
const inputData = computed<InputData>(() => {
  const data: InputData = {}

  // Add messages if any
  const validMessages = messages.value.filter(m => m.content.trim() !== '')
  if (validMessages.length > 0) {
    data.messages = validMessages
  }

  // Add additional fields
  additionalFields.value.forEach(field => {
    if (field.key.trim() !== '') {
      try {
        // Try to parse as JSON, otherwise keep as string
        data[field.key] = JSON.parse(field.value)
      } catch (error: unknown) {
        data[field.key] = field.value
      }
    }
  })

  return data
})

// Synchronize JSON input with current data
const syncJsonInput = () => {
  jsonInput.value = JSON.stringify(inputData.value, null, 2)
  jsonError.value = ''
}

// Apply changes from JSON editor
const applyJsonChanges = () => {
  try {
    const parsed = JSON.parse(jsonInput.value)

    // Update messages if present
    if (parsed.messages && Array.isArray(parsed.messages)) {
      messages.value = parsed.messages
    } else {
      messages.value = []
    }

    // Update additional fields
    additionalFields.value = Object.entries(parsed)
      .filter(([key]) => key !== 'messages')
      .map(([key, value]) => ({
        key,
        value: typeof value === 'string' ? value : JSON.stringify(value),
      }))

    jsonError.value = ''
  } catch (err) {
    jsonError.value = err instanceof Error ? err.message : 'Invalid JSON format'
  }
}

// Toggle advanced mode
const toggleAdvancedMode = () => {
  if (!isAdvancedMode.value) {
    // Switching to advanced mode - sync JSON
    syncJsonInput()
  } else {
    // Switching to simple mode - apply JSON changes
    applyJsonChanges()
  }
  isAdvancedMode.value = !isAdvancedMode.value
}

// Watch for changes and emit
watch(
  inputData,
  newValue => {
    emit('update:modelValue', newValue)
  },
  { deep: true }
)

// Emit initial value
emit('update:modelValue', inputData.value)

// JSON preview
const jsonPreview = computed(() => JSON.stringify(inputData.value, null, 2))
const showJsonPreview = ref(false)
</script>

<template>
  <VCard flat>
    <VCardText>
      <div class="d-flex justify-space-between align-center mb-4">
        <div>
          <div class="text-sm font-weight-medium">Input Data</div>
          <div class="text-caption text-medium-emphasis">Configure the input data that will be sent to the agent</div>
        </div>

        <!-- Control Buttons -->
        <div class="d-flex gap-2">
          <VBtn
            size="small"
            :variant="isAdvancedMode ? 'flat' : 'text'"
            :color="isAdvancedMode ? 'primary' : 'default'"
            @click="toggleAdvancedMode"
          >
            <VIcon icon="tabler-code" start size="18" />
            {{ isAdvancedMode ? 'Simple Mode' : 'Advanced Mode' }}
          </VBtn>
          <VBtn v-if="!isAdvancedMode" size="small" variant="text" @click="showJsonPreview = !showJsonPreview">
            {{ showJsonPreview ? 'Hide' : 'Show' }} JSON
          </VBtn>
        </div>
      </div>

      <!-- Advanced Mode - JSON Editor -->
      <div v-if="isAdvancedMode">
        <VTextarea
          v-model="jsonInput"
          label="JSON Input Data"
          variant="outlined"
          rows="15"
          auto-grow
          placeholder='{"messages": [{"role": "user", "content": "Hello"}], "custom_key": "value"}'
          class="json-editor mb-3"
          :error="!!jsonError"
          :error-messages="jsonError"
          @blur="applyJsonChanges"
        />

        <VAlert type="info" variant="tonal" density="compact">
          <template #text>
            <div class="text-caption">
              <strong>Tips:</strong> Edit the JSON directly. You can include any custom fields in addition to
              <code>messages</code>. Changes will be applied when you click outside the editor or switch modes.
            </div>
          </template>
        </VAlert>
      </div>

      <!-- Simple Mode - Structured Editor -->
      <div v-else>
        <!-- JSON Preview (read-only) -->
        <VExpandTransition>
          <VCard v-if="showJsonPreview" variant="tonal" class="mb-4">
            <VCardText>
              <pre class="text-caption">{{ jsonPreview }}</pre>
            </VCardText>
          </VCard>
        </VExpandTransition>

        <!-- Messages Section -->
        <div class="mb-6">
          <div class="d-flex align-center mb-3">
            <VIcon icon="tabler-message" size="20" class="me-2" />
            <span class="text-sm font-weight-medium">Messages</span>
          </div>

          <VCard v-for="(message, index) in messages" :key="index" class="mb-3" variant="outlined">
            <VCardText>
              <div class="d-flex align-start gap-2">
                <VSelect
                  v-model="message.role"
                  :items="roleOptions"
                  item-title="title"
                  item-value="value"
                  label="Role"
                  variant="outlined"
                  density="compact"
                  hide-details
                  style="max-width: 150px"
                />
                <VTextarea
                  v-model="message.content"
                  label="Content"
                  variant="outlined"
                  density="compact"
                  rows="3"
                  auto-grow
                  hide-details
                  placeholder="Enter message content..."
                  class="flex-grow-1"
                />
                <VBtn
                  icon="tabler-trash"
                  size="small"
                  variant="text"
                  color="error"
                  :disabled="messages.length === 1"
                  @click="removeMessage(index)"
                />
              </div>
            </VCardText>
          </VCard>

          <VBtn variant="outlined" prepend-icon="tabler-plus" size="small" @click="addMessage"> Add Message </VBtn>
        </div>

        <!-- Additional Fields Section -->
        <VDivider class="my-4" />

        <div>
          <div class="d-flex align-center justify-space-between mb-3">
            <div class="d-flex align-center">
              <VIcon icon="tabler-key" size="20" class="me-2" />
              <span class="text-sm font-weight-medium">Additional Fields</span>
              <VChip v-if="additionalFields.length > 0" size="x-small" color="primary" class="ms-2">
                {{ additionalFields.length }}
              </VChip>
            </div>
          </div>

          <VCard v-for="(field, index) in additionalFields" :key="index" class="mb-3" variant="outlined">
            <VCardText>
              <div class="d-flex align-start gap-2">
                <VTextField
                  v-model="field.key"
                  label="Key"
                  variant="outlined"
                  density="compact"
                  hide-details
                  placeholder="field_name"
                  style="max-width: 200px"
                />
                <VTextarea
                  v-model="field.value"
                  label="Value (JSON or string)"
                  variant="outlined"
                  density="compact"
                  rows="2"
                  auto-grow
                  hide-details
                  placeholder='Enter value or JSON (e.g., "text" or {"key": "value"})'
                  class="flex-grow-1"
                />
                <VBtn icon="tabler-trash" size="small" variant="text" color="error" @click="removeField(index)" />
              </div>
            </VCardText>
          </VCard>

          <VBtn variant="outlined" prepend-icon="tabler-plus" size="small" @click="addField"> Add Field </VBtn>
        </div>
      </div>
    </VCardText>
  </VCard>
</template>

<style scoped>
pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

/* JSON Editor styles */
.json-editor :deep(textarea) {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

code {
  background-color: rgba(var(--v-theme-on-surface), 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
}
</style>
