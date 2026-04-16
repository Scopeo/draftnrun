<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'

// Props
interface Props {
  successMessage: string
  errorMessage: string
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'update:successMessage': [value: string]
  'update:errorMessage': [value: string]
}>()

// Types
type JsonSchemaType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array'

interface SchemaPropertyFormItem {
  name: string
  type: JsonSchemaType
  description?: string
  required?: boolean
  enumValues?: string[]
  defaultValue?: string
  itemsType?: Exclude<JsonSchemaType, 'array'>
  itemsEnumValues?: string[]
}

// Local state
const apiToolsForm = ref({
  tool_display_name: 'Linkup Search',
  endpoint: 'https://api.linkup.so/v1/search',
  method: 'POST',
  headers: [
    { key: 'Authorization', value: 'Bearer @{ENV:LINKUP_API_KEY}' },
    { key: 'Content-Type', value: 'application/json' },
  ] as { key: string; value: string }[],
  timeout: 30 as number | null,
  fixed_parameters: [
    { key: 'depth', value: 'standard' },
    { key: 'outputType', value: 'sourcedAnswer' },
    { key: 'includeImages', value: 'false' },
    { key: 'includeInlineCitations', value: 'false' },
  ] as { key: string; value: string }[],
  tool_description_name: 'linkup_search',
  tool_description: 'Search Linkup API for sourced answers',
  tool_properties_text:
    '{\n  "type": "object",\n  "properties": {\n    "q": {\n      "type": "string",\n      "description": "Search query",\n      "default": "who is prime minister of France ?"\n    }\n  },\n  "required": ["q"]\n}',
  required_tool_properties: [] as string[],
})

const apiToolsLoading = ref(false)

const apiToolsResult = ref<{
  component_instance_id?: string
  tool_description_id?: string
  name?: string
  ref?: string
} | null>(null)

const toolPropsMode = ref<'form' | 'json'>('form')

const toolPropertiesForm = ref<{ properties: SchemaPropertyFormItem[] }>({
  properties: [],
})

// Typed view for template to avoid unknown inference in v-for
const propsList = computed<SchemaPropertyFormItem[]>(() => toolPropertiesForm.value.properties)

// Constants
const httpMethods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const DEFAULT_TOOL_DISPLAY_NAME = 'API Tool'
const DEFAULT_TOOL_DESC_NAME = 'api_tool'
const DEFAULT_TOOL_DESCRIPTION = 'Execute a specific HTTP API call'

// Methods
const parseKeyValueArrayToObject = (arr: { key: string; value: string }[]) => {
  const obj: Record<string, any> = {}

  arr.forEach(({ key, value }) => {
    if (!key) return
    try {
      obj[key] = JSON.parse(value)
    } catch (error: unknown) {
      obj[key] = value
    }
  })
  return Object.keys(obj).length ? obj : undefined
}

const buildSchemaFromForm = (): Record<string, any> => {
  const properties: Record<string, any> = {}
  const required: string[] = []

  for (const p of toolPropertiesForm.value.properties) {
    if (!p.name || !p.type) continue
    const propSchema: Record<string, any> = { type: p.type }
    if (p.description) propSchema.description = p.description
    if (p.enumValues && p.enumValues.length) propSchema.enum = p.enumValues
    if (p.defaultValue && p.defaultValue.trim() !== '') {
      try {
        propSchema.default = JSON.parse(p.defaultValue)
      } catch (error: unknown) {
        propSchema.default = p.defaultValue
      }
    }
    if (p.type === 'array') {
      const item: Record<string, any> = { type: p.itemsType || 'string' }
      if (p.itemsEnumValues && p.itemsEnumValues.length) item.enum = p.itemsEnumValues
      propSchema.items = item
    }
    properties[p.name] = propSchema
    if (p.required) required.push(p.name)
  }

  return { type: 'object', properties, required }
}

const parseJsonToForm = (jsonText: string) => {
  try {
    const parsed: any = JSON.parse(jsonText)
    const properties: SchemaPropertyFormItem[] = []

    if (parsed.properties) {
      const entries = Object.entries(parsed.properties as Record<string, any>) as [string, any][]
      for (const [key, def] of entries) {
        properties.push({
          name: key,
          type: def?.type || 'string',
          description: def?.description || '',
          required: Array.isArray(parsed.required) ? parsed.required.includes(key) : false,
          enumValues: def?.enum || [],
          defaultValue: def?.default !== undefined ? JSON.stringify(def.default) : '',
          itemsType: def?.items?.type || 'string',
          itemsEnumValues: def?.items?.enum || [],
        })
      }
    }

    toolPropertiesForm.value.properties = properties
  } catch (e) {
    logger.warn('Failed to parse JSON to form', { error: e })
  }
}

const previewPayload = computed(() => {
  const headersObj = parseKeyValueArrayToObject(apiToolsForm.value.headers)
  const fixedParamsObj = parseKeyValueArrayToObject(apiToolsForm.value.fixed_parameters)

  let propertiesOnly: any = {}
  let requiredFromSchema: string[] = []

  if (toolPropsMode.value === 'form') {
    const schema = buildSchemaFromForm()

    propertiesOnly = schema.properties || {}
    requiredFromSchema = schema.required || []
  } else {
    try {
      if (apiToolsForm.value.tool_properties_text) {
        const parsed = JSON.parse(apiToolsForm.value.tool_properties_text)

        propertiesOnly = parsed.properties || {}
        requiredFromSchema = parsed.required || []
      }
    } catch (e) {
      logger.warn('Invalid JSON in tool properties')
    }
  }

  return {
    tool_display_name: (apiToolsForm.value.tool_display_name || DEFAULT_TOOL_DISPLAY_NAME).trim(),
    endpoint: apiToolsForm.value.endpoint || undefined,
    method: apiToolsForm.value.method,
    headers: headersObj,
    timeout: apiToolsForm.value.timeout ?? undefined,
    fixed_parameters: fixedParamsObj,
    tool_description_name: (apiToolsForm.value.tool_description_name || DEFAULT_TOOL_DESC_NAME).trim(),
    tool_description: (apiToolsForm.value.tool_description || DEFAULT_TOOL_DESCRIPTION).trim(),
    tool_properties: propertiesOnly || {},
    required_tool_properties:
      (toolPropsMode.value === 'form' ? buildSchemaFromForm().required : requiredFromSchema) || undefined,
  }
})

const validateJson = () => {
  try {
    if (apiToolsForm.value.tool_properties_text) JSON.parse(apiToolsForm.value.tool_properties_text)
    emit('update:errorMessage', '')
    return true
  } catch (e: any) {
    emit('update:errorMessage', `Invalid JSON in tool properties: ${e.message}`)
    return false
  }
}

const isApiToolsFormValid = computed(() => {
  return (
    !!apiToolsForm.value.tool_display_name &&
    !!apiToolsForm.value.endpoint &&
    !!apiToolsForm.value.method &&
    !!apiToolsForm.value.tool_description_name &&
    validateJson()
  )
})

const submitApiTool = async () => {
  emit('update:successMessage', '')
  emit('update:errorMessage', '')
  apiToolsResult.value = null

  if (!isApiToolsFormValid.value) {
    if (!props.errorMessage) emit('update:errorMessage', 'Please fill all required fields.')
    return
  }

  apiToolsLoading.value = true
  try {
    const payload = previewPayload.value as any
    const res = await scopeoApi.adminTools.createSpecificApiTool(payload)

    apiToolsResult.value = res as any
    emit('update:successMessage', `Created successfully. ID: ${res.component_instance_id} — Name: ${res.name || 'N/A'}`)
  } catch (e: any) {
    emit('update:errorMessage', e?.message || 'Failed to create API tool')
  } finally {
    apiToolsLoading.value = false
  }
}

const addHeaderRow = () => {
  apiToolsForm.value.headers.push({ key: '', value: '' })
}

const removeHeaderRow = (index: number) => {
  apiToolsForm.value.headers.splice(index, 1)
}

const addParameterRow = () => {
  apiToolsForm.value.fixed_parameters.push({ key: '', value: '' })
}

const removeParameterRow = (index: number) => {
  apiToolsForm.value.fixed_parameters.splice(index, 1)
}

const addPropertyRow = () => {
  toolPropertiesForm.value.properties.push({
    name: '',
    type: 'string',
    description: '',
    required: false,
    enumValues: [],
    defaultValue: '',
  })
}

const removePropertyRow = (index: number) => {
  toolPropertiesForm.value.properties.splice(index, 1)
}

// Watch for mode changes
const onModeChange = () => {
  if (toolPropsMode.value === 'form') {
    parseJsonToForm(apiToolsForm.value.tool_properties_text)
  } else {
    const schema = buildSchemaFromForm()

    apiToolsForm.value.tool_properties_text = JSON.stringify(schema, null, 2)
  }
}

// Initialize form properties from existing JSON on mount so defaults show by default
onMounted(() => {
  try {
    if (apiToolsForm.value.tool_properties_text) {
      parseJsonToForm(apiToolsForm.value.tool_properties_text)
    }
  } catch (error: unknown) {
    logger.warn('Failed to parse tool properties on mount', { error })
  }
})
</script>

<template>
  <VAlert type="info" variant="tonal" class="mb-4"> Tools created via this builder are released as INTERNAL. </VAlert>
  <VCard style="overflow: hidden">
    <VCardTitle class="d-flex align-center justify-space-between">
      <span>API Tool Builder</span>
    </VCardTitle>
    <VDivider />
    <VCardText>
      <div class="d-flex flex-column gap-4">
        <VAlert
          v-if="props.successMessage"
          type="success"
          variant="tonal"
          closable
          @click:close="emit('update:successMessage', '')"
        >
          {{ props.successMessage }}
        </VAlert>
        <VAlert
          v-if="props.errorMessage"
          type="error"
          variant="tonal"
          closable
          @click:close="emit('update:errorMessage', '')"
        >
          {{ props.errorMessage }}
        </VAlert>

        <div class="d-flex flex-wrap gap-4">
          <VTextField v-model="apiToolsForm.tool_display_name" label="Tool Display Name" required class="flex-grow-1" />
        </div>

        <div class="d-flex flex-wrap gap-4">
          <VTextField
            v-model="apiToolsForm.endpoint"
            label="Endpoint URL"
            placeholder="https://api.example.com/resource"
            required
            class="flex-grow-1"
          />
        </div>

        <div class="d-flex flex-wrap gap-4">
          <VSelect v-model="apiToolsForm.method" :items="httpMethods" label="HTTP Method" required />
          <VTextField v-model.number="apiToolsForm.timeout" type="number" min="0" label="Timeout (seconds)" />
        </div>

        <VCard variant="outlined">
          <VCardTitle>Headers (key-value)</VCardTitle>
          <VDivider />
          <VCardText>
            <div class="d-flex flex-column gap-2">
              <div v-for="(item, idx) in apiToolsForm.headers" :key="`hdr-${idx}`" class="d-flex gap-2">
                <VTextField v-model="item.key" label="Key" density="comfortable" class="flex-grow-1" />
                <VTextField
                  v-model="item.value"
                  label="Value (JSON or text)"
                  density="comfortable"
                  class="flex-grow-1"
                />
                <VBtn icon="tabler-trash" color="error" variant="text" @click="removeHeaderRow(idx)" />
              </div>
              <div>
                <VBtn variant="tonal" size="small" @click="addHeaderRow"> Add Header </VBtn>
              </div>
              <div>
                <VAlert type="info" variant="tonal">
                  Use @{ENV:KEY} to prefer organization secret KEY and fallback to env (e.g., Authorization: Bearer
                  @{ENV:LINKUP_API_KEY}).
                </VAlert>
              </div>
            </div>
          </VCardText>
        </VCard>

        <VCard variant="outlined">
          <VCardTitle>Fixed Parameters (key-value)</VCardTitle>
          <VDivider />
          <VCardText>
            <div class="d-flex flex-column gap-2">
              <div v-for="(item, idx) in apiToolsForm.fixed_parameters" :key="`fp-${idx}`" class="d-flex gap-2">
                <VTextField v-model="item.key" label="Key" density="comfortable" class="flex-grow-1" />
                <VTextField
                  v-model="item.value"
                  label="Value (JSON or text)"
                  density="comfortable"
                  class="flex-grow-1"
                />
                <VBtn icon="tabler-trash" color="error" variant="text" @click="removeParameterRow(idx)" />
              </div>
              <div>
                <VBtn variant="tonal" size="small" @click="addParameterRow"> Add Parameter </VBtn>
              </div>
              <div>
                <VAlert type="info" variant="tonal">
                  Placeholders @{ENV:KEY} resolve to org secret KEY, else env from backend.
                </VAlert>
              </div>
            </div>
          </VCardText>
        </VCard>

        <div class="d-flex flex-wrap gap-4">
          <VTextField
            v-model="apiToolsForm.tool_description_name"
            label="Tool Description Name"
            required
            class="flex-grow-1"
          />
          <VTextField v-model="apiToolsForm.tool_description" label="Tool Description (optional)" class="flex-grow-1" />
        </div>

        <VCard variant="outlined">
          <VCardTitle class="d-flex align-center justify-space-between">
            <div class="d-flex align-center gap-3">
              <span>Tool Properties</span>
              <VBtnToggle
                v-model="toolPropsMode"
                divided
                density="comfortable"
                color="primary"
                mandatory
                @update:model-value="onModeChange"
              >
                <VBtn value="form">Form</VBtn>
                <VBtn value="json">JSON</VBtn>
              </VBtnToggle>
            </div>
            <div class="d-flex gap-2">
              <VBtn size="small" variant="tonal" @click="validateJson">Validate JSON</VBtn>
            </div>
          </VCardTitle>
          <VDivider />
          <VCardText>
            <div v-if="toolPropsMode === 'form'" class="d-flex flex-column gap-4">
              <div class="d-flex justify-end">
                <VBtn size="small" variant="outlined" @click="addPropertyRow"> Add Property </VBtn>
              </div>
              <VCard v-for="(prop, idx) in propsList" :key="`prop-${idx}`" variant="outlined">
                <VCardText>
                  <div class="d-flex flex-wrap gap-4 align-start">
                    <VTextField v-model="prop.name" label="Name" placeholder="q" class="flex-grow-1" />
                    <VSelect
                      v-model="prop.type"
                      :items="['string', 'number', 'integer', 'boolean', 'object', 'array']"
                      label="Type"
                      class="flex-grow-1"
                    />
                    <VCheckbox v-model="prop.required" label="Required" />
                    <VBtn icon="tabler-trash" color="error" variant="text" @click="removePropertyRow(idx)" />
                  </div>
                  <div class="d-flex flex-wrap gap-4 mt-2">
                    <VTextField
                      v-model="prop.description"
                      label="Description"
                      placeholder="Search query"
                      class="flex-grow-1"
                    />
                    <VTextField
                      v-model="prop.defaultValue"
                      label="Default (JSON or text)"
                      placeholder="who is prime minister of France ?"
                      class="flex-grow-1"
                    />
                  </div>
                  <div class="d-flex flex-wrap gap-4 mt-2">
                    <VCombobox
                      v-model="prop.enumValues"
                      label="Enum Values (optional)"
                      multiple
                      chips
                      clearable
                      class="flex-grow-1"
                    />
                  </div>
                  <div v-if="prop.type === 'array'" class="mt-2">
                    <div class="text-subtitle-2 mb-2">Array Item Schema</div>
                    <div class="d-flex flex-wrap gap-4">
                      <VSelect
                        v-model="prop.itemsType"
                        :items="['string', 'number', 'integer', 'boolean', 'object']"
                        label="Items Type"
                      />
                      <VCombobox
                        v-model="prop.itemsEnumValues"
                        label="Items Enum Values (optional)"
                        multiple
                        chips
                        clearable
                        class="flex-grow-1"
                      />
                    </div>
                  </div>
                </VCardText>
              </VCard>
              <VAlert type="info" variant="tonal">
                Define tool properties using the form. Switch to JSON to fine-tune or paste a schema.
              </VAlert>
            </div>

            <div v-else>
              <VTextarea
                v-model="apiToolsForm.tool_properties_text"
                rows="8"
                auto-grow
                placeholder='{"type":"object"}'
              />
            </div>
          </VCardText>
        </VCard>

        <div class="d-flex justify-end">
          <VBtn color="primary" :loading="apiToolsLoading" :disabled="!isApiToolsFormValid" @click="submitApiTool">
            Create Tool
          </VBtn>
        </div>
        <div v-if="apiToolsResult" class="mt-2">
          <VAlert type="success" variant="tonal">
            Created successfully. ID: {{ apiToolsResult.component_instance_id }} — Name:
            {{ apiToolsResult.name || 'N/A' }}
          </VAlert>
        </div>

        <VCard variant="outlined">
          <VCardTitle>Preview Payload</VCardTitle>
          <VDivider />
          <VCardText>
            <pre class="text-caption preview-json">{{ JSON.stringify(previewPayload, null, 2) }}</pre>
          </VCardText>
        </VCard>
      </div>
    </VCardText>
  </VCard>
</template>

<style scoped>
:deep(.flex-grow-1) {
  min-width: 0;
}

.preview-json {
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
