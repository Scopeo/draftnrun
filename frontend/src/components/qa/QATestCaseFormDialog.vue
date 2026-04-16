<script setup lang="ts">
// 1. Vue/core imports
import { computed } from 'vue'

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types
import type { QATestCaseUI } from '@/types/qa'

interface Props {
  modelValue: boolean
  mode: 'add' | 'edit'
  testCase?: QATestCaseUI | null
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
  additionalFields: Array<{ key: string; value: string }>
  groundtruth: string
  customColumns: Record<string, string>
  allCustomColumns: Array<{ column_id: string; column_name: string }>
  isColumnVisible: (columnId: string) => boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  testCase: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:messages': [messages: Array<{ role: 'user' | 'assistant'; content: string }>]
  'update:additionalFields': [fields: Array<{ key: string; value: string }>]
  'update:groundtruth': [groundtruth: string]
  'update:customColumns': [columns: Record<string, string>]
  save: []
}>()

const showDialog = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const visibleCustomColumns = computed(() => {
  return props.allCustomColumns.filter(col => props.isColumnVisible(col.column_id))
})

const canSave = computed(() => {
  return props.messages.some(m => m.content.trim())
})

const addMessage = () => {
  const newMessages = [...props.messages, { role: 'user' as const, content: '' }]

  emit('update:messages', newMessages)
}

const removeMessage = (index: number) => {
  if (props.messages.length > 1) {
    const newMessages = [...props.messages]

    newMessages.splice(index, 1)
    emit('update:messages', newMessages)
  }
}

const addAdditionalField = () => {
  const newFields = [...props.additionalFields, { key: '', value: '' }]

  emit('update:additionalFields', newFields)
}

const removeAdditionalField = (index: number) => {
  const newFields = [...props.additionalFields]

  newFields.splice(index, 1)
  emit('update:additionalFields', newFields)
}

const updateMessageRole = (index: number, role: 'user' | 'assistant') => {
  const newMessages = [...props.messages]

  newMessages[index] = { ...newMessages[index], role }
  emit('update:messages', newMessages)
}

const updateMessageContent = (index: number, content: string) => {
  const newMessages = [...props.messages]

  newMessages[index] = { ...newMessages[index], content }
  emit('update:messages', newMessages)
}

const updateAdditionalFieldKey = (index: number, key: string) => {
  const newFields = [...props.additionalFields]

  newFields[index] = { ...newFields[index], key }
  emit('update:additionalFields', newFields)
}

const updateAdditionalFieldValue = (index: number, value: string) => {
  const newFields = [...props.additionalFields]

  newFields[index] = { ...newFields[index], value }
  emit('update:additionalFields', newFields)
}

const updateGroundtruth = (value: string) => {
  emit('update:groundtruth', value)
}

const updateCustomColumn = (columnId: string, value: string) => {
  const newColumns = { ...props.customColumns, [columnId]: value }

  emit('update:customColumns', newColumns)
}

const handleSave = () => {
  if (canSave.value) {
    emit('save')
  }
}
</script>

<template>
  <VDialog
    :model-value="showDialog"
    max-width="var(--dnr-dialog-lg)"
    scrollable
    @update:model-value="showDialog = $event"
  >
    <VCard>
      <VCardTitle>{{ mode === 'add' ? 'Add Test Case' : 'Edit Test Case' }}</VCardTitle>
      <VCardText style="max-block-size: 70vh">
        <!-- Messages Section -->
        <div class="mb-4">
          <div class="d-flex align-center justify-space-between mb-2">
            <div class="text-subtitle-1 font-weight-medium">Messages</div>
            <VBtn size="small" variant="outlined" prepend-icon="tabler-plus" @click="addMessage"> Add Message </VBtn>
          </div>

          <div v-for="(message, index) in messages" :key="index" class="mb-3">
            <VCard variant="outlined">
              <VCardText>
                <div class="d-flex align-start gap-2">
                  <VSelect
                    :model-value="message.role"
                    :items="[
                      { title: 'User', value: 'user' },
                      { title: 'Assistant', value: 'assistant' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="Role"
                    variant="outlined"
                    density="compact"
                    hide-details
                    class="role-select"
                    @update:model-value="updateMessageRole(index, $event)"
                  />
                  <VTextarea
                    :model-value="message.content"
                    label="Content"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    auto-grow
                    hide-details
                    placeholder="Enter message content..."
                    class="flex-grow-1"
                    @update:model-value="updateMessageContent(index, $event)"
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
          </div>
        </div>

        <!-- Additional Fields Section -->
        <div class="mb-4">
          <div class="d-flex align-center justify-space-between mb-2">
            <div class="text-subtitle-1 font-weight-medium">Additional Fields</div>
            <VBtn size="small" variant="outlined" prepend-icon="tabler-plus" @click="addAdditionalField">
              Add Field
            </VBtn>
          </div>

          <div v-for="(field, index) in additionalFields" :key="index" class="mb-2">
            <div class="d-flex align-start gap-2">
              <VTextField
                :model-value="field.key"
                label="Key"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="e.g., file, metadata..."
                class="field-key"
                @update:model-value="updateAdditionalFieldKey(index, $event)"
              />
              <VTextarea
                :model-value="field.value"
                label="Value"
                variant="outlined"
                density="compact"
                rows="2"
                auto-grow
                hide-details
                placeholder="Enter value..."
                class="flex-grow-1"
                @update:model-value="updateAdditionalFieldValue(index, $event)"
              />
              <VBtn
                icon="tabler-trash"
                size="small"
                variant="text"
                color="error"
                class="mt-1"
                @click="removeAdditionalField(index)"
              />
            </div>
          </div>

          <div v-if="additionalFields.length === 0" class="text-caption text-medium-emphasis">
            No additional fields. Click "Add Field" to add custom fields to your input.
          </div>
        </div>

        <!-- Expected Output Section (only shown in add mode, edit mode edits inline) -->
        <div v-if="mode === 'add'" class="mb-4">
          <div class="text-subtitle-1 font-weight-medium mb-2">Expected Output (Groundtruth)</div>
          <VTextarea
            :model-value="groundtruth"
            label="Expected Output"
            placeholder="Enter the expected output for this test case..."
            variant="outlined"
            rows="4"
            auto-grow
            @update:model-value="updateGroundtruth"
          />
        </div>

        <!-- Custom Columns Section (only shown in add mode, edit mode edits inline) -->
        <div v-if="mode === 'add' && visibleCustomColumns.length > 0">
          <div class="text-subtitle-1 font-weight-medium mb-2">Custom Columns</div>
          <div v-for="col in visibleCustomColumns" :key="col.column_id" class="mb-3">
            <VTextarea
              :model-value="customColumns[col.column_id] || ''"
              :label="col.column_name"
              :placeholder="`Enter value for ${col.column_name}...`"
              variant="outlined"
              rows="2"
              auto-grow
              hide-details
              @update:model-value="updateCustomColumn(col.column_id, $event)"
            />
          </div>
        </div>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="showDialog = false"> Cancel </VBtn>
        <VBtn color="primary" :loading="loading" :disabled="!canSave" @click="handleSave">
          <VIcon icon="tabler-check" class="me-1" />
          {{ mode === 'add' ? 'Add Test Case' : 'Save Changes' }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.role-select {
  max-inline-size: 150px;
}

.field-key {
  max-inline-size: 200px;
}
</style>
