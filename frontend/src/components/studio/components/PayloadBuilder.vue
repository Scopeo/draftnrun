<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

interface Message {
  role: string
  content: string
}

interface InputData {
  messages?: Message[]
  [key: string]: any
}

interface Props {
  modelValue: Record<string, any>
  readonly?: boolean
  color?: string
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
  color: 'primary',
})

const emit = defineEmits<{
  'update:modelValue': [value: InputData]
}>()

// Messages list - default with one user message if none provided
const messages = ref<Message[]>(
  props.modelValue?.messages?.length ? props.modelValue.messages : [{ role: 'user', content: '' }]
)

// Additional fields - always start empty, users can add new fields
const additionalFields = ref<Array<{ id: string; key: string; value: string }>>([])

// Advanced mode
const isAdvancedMode = ref(false)
const jsonInput = ref('')
const jsonError = ref('')

// Flag to prevent recursive updates
const isInternalUpdate = ref(false)

const roleOptions = [
  { title: 'User', value: 'user' },
  { title: 'Assistant', value: 'assistant' },
  { title: 'System', value: 'system' },
]

// Generate unique ID for fields
const generateId = () => `field_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

const updateMessagesFromJson = (jsonString: string) => {
  try {
    const parsed = JSON.parse(jsonString)
    if (Array.isArray(parsed)) {
      messages.value = parsed
      jsonError.value = ''
    } else {
      jsonError.value = 'Messages must be an array'
    }
  } catch (e: any) {
    jsonError.value = `Invalid JSON: ${e.message}`
  }
}

const addMessage = () => {
  messages.value.push({ role: 'user', content: '' })
}

const removeMessage = (index: number) => {
  if (messages.value.length > 1) {
    messages.value.splice(index, 1)
  }
}

const addField = () => {
  additionalFields.value.push({ id: generateId(), key: '', value: '' })
}

const removeField = (id: string) => {
  const index = additionalFields.value.findIndex(f => f.id === id)
  if (index !== -1) {
    additionalFields.value.splice(index, 1)
  }
}

// Computed input data - includes messages AND additional fields
const inputData = computed<InputData>(() => {
  const data: InputData = {}

  // Add messages if any
  const validMessages = messages.value.filter(m => m.content.trim() !== '')
  if (validMessages.length > 0) {
    data.messages = validMessages
  }

  // Add additional fields - try to parse as JSON, otherwise keep as string
  additionalFields.value.forEach(field => {
    if (field.key.trim() !== '') {
      const value = field.value

      // Try to parse as JSON (for objects, arrays, numbers, booleans)
      // If it fails, keep as raw string
      try {
        data[field.key] = JSON.parse(value)
      } catch (error: unknown) {
        data[field.key] = value
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

    // Only populate additional fields if user explicitly added them in JSON mode
    // This allows advanced users to add fields via JSON, but keeps form mode clean
    const additionalFieldsFromJson = Object.entries(parsed)
      .filter(([key]) => key !== 'messages')
      .map(([key, value]) => ({
        id: generateId(),
        key,
        value: typeof value === 'string' ? value : JSON.stringify(value),
      }))

    // Only update if there are additional fields in the JSON
    if (additionalFieldsFromJson.length > 0) {
      additionalFields.value = additionalFieldsFromJson
    }

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

// Watch for changes and emit (with safeguard against recursion)
watch(
  inputData,
  newValue => {
    if (!isInternalUpdate.value) {
      isInternalUpdate.value = true
      emit('update:modelValue', newValue)
      nextTick(() => {
        isInternalUpdate.value = false
      })
    }
  },
  { deep: true }
)

// Watch for prop changes to initialize (skip if internal update)
watch(
  () => props.modelValue,
  (newVal, oldVal) => {
    if (isInternalUpdate.value) {
      return // Skip if this is from our own emit
    }

    if (newVal && Object.keys(newVal).length > 0) {
      // Initialize messages
      if (newVal.messages && Array.isArray(newVal.messages)) {
        messages.value = newVal.messages
      } else {
        messages.value = [{ role: 'user', content: '' }]
      }

      // Populate additional fields from saved data
      const fieldsFromData = Object.entries(newVal)
        .filter(([key]) => key !== 'messages')
        .map(([key, value]) => ({
          id: generateId(),
          key,
          value: typeof value === 'object' ? JSON.stringify(value) : String(value),
        }))

      additionalFields.value = fieldsFromData

      // Update JSON view if in advanced mode
      if (isAdvancedMode.value) {
        jsonInput.value = JSON.stringify(newVal, null, 2)
      }
    }
  },
  { immediate: true }
)

// Emit initial value
emit('update:modelValue', inputData.value)

// JSON preview
const jsonPreview = computed(() => JSON.stringify(inputData.value, null, 2))
const showJsonPreview = ref(false)
</script>

<template>
  <VCard variant="outlined">
    <!-- Header Section -->
    <VCardTitle>
      <div class="d-flex justify-space-between align-center w-100">
        <div>
          <div class="text-h6">Input Fields</div>
          <div class="text-caption text-medium-emphasis">Configure the input data for your workflow</div>
        </div>

        <div class="d-flex gap-2">
          <VBtn
            size="small"
            :variant="isAdvancedMode ? 'flat' : 'text'"
            :color="isAdvancedMode ? color : 'default'"
            :disabled="readonly"
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
    </VCardTitle>

    <VDivider />

    <!-- Content Section -->
    <VCardText>
      <VAlert v-if="jsonError" type="error" variant="tonal" class="mb-4" closable @click:close="jsonError = ''">
        {{ jsonError }}
      </VAlert>

      <!-- JSON Preview (toggleable in Simple Mode) -->
      <VExpandTransition>
        <VCard v-if="showJsonPreview && !isAdvancedMode" variant="tonal" class="mb-4">
          <VCardText>
            <div class="text-caption font-weight-medium mb-2">Preview Payload:</div>
            <pre class="text-caption">{{ jsonPreview }}</pre>
          </VCardText>
        </VCard>
      </VExpandTransition>

      <!-- Simple Mode -->
      <div v-if="!isAdvancedMode">
        <!-- Messages Field (always present) -->
        <VCard variant="outlined" class="mb-3">
          <VCardText>
            <div class="d-flex gap-2 align-start">
              <VTextField
                model-value="messages"
                label="Field Name"
                variant="outlined"
                density="compact"
                hide-details
                readonly
                :color="color"
                style="max-width: 200px"
              />
              <VTextarea
                :model-value="JSON.stringify(messages, null, 2)"
                label="Default Value"
                variant="outlined"
                density="compact"
                rows="4"
                auto-grow
                :readonly="readonly"
                :color="color"
                placeholder='[{"role": "user", "content": "Hello"}]'
                class="flex-grow-1 messages-json-input"
                hide-details
                @update:model-value="updateMessagesFromJson"
              />
            </div>
          </VCardText>
        </VCard>

        <!-- Additional Fields -->
        <VCard v-for="field in additionalFields" :key="field.id" class="mb-3" variant="outlined">
          <VCardText>
            <div class="d-flex gap-2 align-start">
              <VTextField
                v-model="field.key"
                label="Field Name"
                variant="outlined"
                density="compact"
                hide-details
                :readonly="readonly"
                :color="color"
                placeholder="field_name"
                style="max-width: 200px"
              />
              <VTextField
                v-model="field.value"
                label="Default Value"
                variant="outlined"
                density="compact"
                hide-details
                :readonly="readonly"
                :color="color"
                placeholder='Text, number, JSON object {"key":"val"}, or array [1,2,3]'
                class="flex-grow-1"
              />
              <VBtn
                v-if="!readonly"
                icon="tabler-trash"
                size="small"
                variant="text"
                color="error"
                @click="removeField(field.id)"
              />
            </div>
          </VCardText>
        </VCard>

        <!-- Add Additional Field Button -->
        <VBtn
          v-if="!readonly"
          variant="outlined"
          prepend-icon="tabler-plus"
          size="small"
          :color="color"
          @click="addField"
        >
          Add Additional Field
        </VBtn>
      </div>

      <!-- Advanced Mode (JSON Editor) -->
      <div v-else class="json-editor">
        <VTextarea
          v-model="jsonInput"
          label="JSON Payload"
          variant="outlined"
          rows="15"
          auto-grow
          :error-messages="jsonError"
          :readonly="readonly"
          :color="color"
          placeholder='{"messages": [{"role": "user", "content": "Hello"}], "custom_field": "value"}'
        />

        <VBtn v-if="!readonly" :color="color" block class="mt-2" @click="applyJsonChanges"> Apply Changes </VBtn>
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
.json-editor :deep(textarea),
.messages-json-input :deep(textarea) {
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
