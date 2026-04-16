<script setup lang="ts">
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import type { ComponentParameter } from '../data/component-definitions'
import type { PortConfiguration } from '../types/graph.types'
import FieldExpressionInput from '../inputs/FieldExpressionInput.vue'

interface Props {
  parameters: ComponentParameter[]
  portConfigurations: PortConfiguration[]
  componentInstanceId: string
  readonly?: boolean
  upstreamNodes?: any[]
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
  upstreamNodes: () => [],
})

const emit = defineEmits<{
  'update:port-configurations': [configs: PortConfiguration[]]
}>()

// Use computed property to access port configurations directly
const localConfigs = computed(() => props.portConfigurations || [])

// Track which port name is being edited
const editingPortName = ref<string | null>(null)
const editingNameValue = ref<string>('')

// Dialog for adding new parameter
const showAddParameterDialog = ref(false)

const newParameterForm = ref({
  name: '',
  description: '',
  type: 'string',
})

// Available parameter types
const parameterTypes = [
  { title: 'String', value: 'string' },
  { title: 'Integer', value: 'integer' },
  { title: 'Number', value: 'number' },
  { title: 'Boolean', value: 'boolean' },
  { title: 'JSON', value: 'json' },
  { title: 'Array', value: 'array' },
  { title: 'Object', value: 'object' },
]

// Get all ports - Only show parameters with kind="input" and is_tool_input=true
// If a parameter has no port configuration, it's "Discard" by default (user can activate it)
const allPorts = computed(() => {
  // Filter parameters to only show those with kind="input" and is_tool_input=true
  const inputParameters = props.parameters.filter(param => param.kind === 'input' && param.is_tool_input === true)

  const parameterPorts = inputParameters.map(param => {
    return {
      id: null, // No port definition ID needed
      parameter_id: param.id || null,
      name: param.name,
      description: param.description || '',
      port_type: 'INPUT' as const,
      parameter_type: param.type,
      nullable: param.nullable,
      is_canonical: false, // Not using port definitions
      is_custom: false,
    }
  })

  const customPorts = localConfigs.value
    .filter(c => c.parameter_id === null && c.ai_name_override)
    .map(c => ({
      id: null,
      parameter_id: null,
      name: c.ai_name_override!,
      description: c.ai_description_override || '',
      port_type: 'INPUT' as const,
      parameter_type: c.custom_parameter_type || 'string',
      nullable: !c.is_required_override,
      is_canonical: false,
      is_custom: true,
    }))

  return [...parameterPorts, ...customPorts]
})

// Get configuration for a port (by parameter_id or by name for custom ports)
// Returns undefined if no configuration exists (meaning "Discard")
function getPortConfig(parameterId: string | null, portName: string, isCustom: boolean): PortConfiguration | undefined {
  if (isCustom) {
    // Custom port - identified by ai_name_override (backend does not use custom_port_name)
    return localConfigs.value.find(c => c.ai_name_override === portName && c.parameter_id === null)
  } else if (parameterId) {
    // Input parameter with parameter_id
    return localConfigs.value.find(c => c.parameter_id === parameterId)
  }
  return undefined
}

// Create a new configuration for a port when activating it
function createConfig(parameterId: string | null, portName: string, isCustom: boolean): PortConfiguration {
  // Create new config when user activates a previously unused port
  const newConfig: PortConfiguration = {
    component_instance_id: props.componentInstanceId,
    parameter_id: parameterId,
    input_port_instance_id: null,
    setup_mode: 'ai_filled', // Default to AI fills when activating
    field_expression_id: null,
    expression_json: null,
    ai_name_override: isCustom ? portName : null,
    ai_description_override: isCustom ? '' : null,
    is_required_override: null,
    custom_parameter_type: isCustom ? 'string' : null,
    custom_ui_component_properties: null,
    json_schema_override: null,
  }

  emit('update:port-configurations', [...localConfigs.value, newConfig])
  return newConfig
}

// Update configuration type
function updateConfigType(
  parameterId: string | null,
  portName: string,
  type: 'user_set' | 'ai_filled' | 'deactivated',
  nullable: boolean,
  isCustom: boolean
) {
  // Validate deactivated - custom ports can always be deactivated
  if (type === 'deactivated' && !nullable && !isCustom) {
    return // Can't deactivate required definition ports
  }

  const existingConfig = getPortConfig(parameterId, portName, isCustom)

  if (type === 'deactivated') {
    // Remove configuration if it exists - port becomes "Discard"
    if (existingConfig) {
      const newConfigs = localConfigs.value.filter(c =>
        isCustom ? !(c.ai_name_override === portName && c.parameter_id === null) : c.parameter_id !== parameterId
      )

      emit('update:port-configurations', newConfigs)
    }
    // If no config exists, port is already "Discard"
  } else {
    // Create or update configuration
    if (existingConfig) {
      // Update existing config
      const updatedConfig = { ...existingConfig }

      updatedConfig.setup_mode = type

      // Clear inappropriate fields based on type
      if (type === 'user_set') {
        updatedConfig.ai_name_override = null
        updatedConfig.ai_description_override = null
        updatedConfig.is_required_override = null
      } else if (type === 'ai_filled') {
        updatedConfig.expression_json = null
      }

      const newConfigs = localConfigs.value.map(c =>
        (isCustom ? c.ai_name_override === portName && c.parameter_id === null : c.parameter_id === parameterId)
          ? updatedConfig
          : c
      )

      emit('update:port-configurations', newConfigs)
    } else {
      // Create new config
      createConfig(parameterId, portName, isCustom)
    }
  }
}

// Update AI overrides
function updateAiOverride(parameterId: string | null, portName: string, field: string, value: any, isCustom: boolean) {
  const existingConfig = getPortConfig(parameterId, portName, isCustom)

  if (existingConfig) {
    // Update existing config
    const updatedConfig = { ...existingConfig, [field]: value }

    const newConfigs = localConfigs.value.map(c =>
      (isCustom ? c.ai_name_override === portName && c.parameter_id === null : c.parameter_id === parameterId)
        ? updatedConfig
        : c
    )

    emit('update:port-configurations', newConfigs)
  } else {
    // Create new config
    createConfig(parameterId, portName, isCustom)
  }
}

// Update expression
function updateExpression(parameterId: string | null, portName: string, expressionJson: any, isCustom: boolean) {
  const existingConfig = getPortConfig(parameterId, portName, isCustom)

  if (existingConfig) {
    // Update existing config
    const updatedConfig = { ...existingConfig, expression_json: expressionJson }

    const newConfigs = localConfigs.value.map(c =>
      (isCustom ? c.ai_name_override === portName && c.parameter_id === null : c.parameter_id === parameterId)
        ? updatedConfig
        : c
    )

    emit('update:port-configurations', newConfigs)
  } else {
    // Create new config
    createConfig(parameterId, portName, isCustom)
  }
}

// Open dialog to add custom port
function addCustomPort() {
  // Reset form
  newParameterForm.value = {
    name: '',
    description: '',
    type: 'string',
  }
  showAddParameterDialog.value = true
}

// Normalize parameter name (replace spaces with underscores)
function normalizeParameterName(name: string): string {
  return name.trim().replace(/\s+/g, '_')
}

// Create custom port from form
function createCustomPort() {
  // Validate
  if (!newParameterForm.value.name.trim()) {
    return
  }

  const newConfig: PortConfiguration = {
    component_instance_id: props.componentInstanceId,
    parameter_id: null,
    input_port_instance_id: null,
    setup_mode: 'ai_filled',
    field_expression_id: null,
    expression_json: null,
    ai_name_override: normalizeParameterName(newParameterForm.value.name),
    ai_description_override: newParameterForm.value.description.trim() || null,
    is_required_override: false,
    custom_parameter_type: newParameterForm.value.type,
    custom_ui_component_properties: null,
    json_schema_override: null,
  }

  emit('update:port-configurations', [...localConfigs.value, newConfig])
  showAddParameterDialog.value = false
}

// Cancel adding parameter
function cancelAddParameter() {
  showAddParameterDialog.value = false
}

// Remove custom port
function removeCustomPort(portName: string) {
  const newConfigs = localConfigs.value.filter(c => !(c.ai_name_override === portName && c.parameter_id === null))

  emit('update:port-configurations', newConfigs)
}

// Get chip color for configuration type
function getConfigTypeColor(type: string): string {
  switch (type) {
    case 'ai_filled':
      return 'primary'
    case 'user_set':
      return 'secondary'
    case 'deactivated':
      return 'grey'
    default:
      return 'default'
  }
}

// Convert JSON schema object to formatted string for display
function jsonSchemaToString(schema: any): string {
  if (!schema) return ''
  if (typeof schema === 'string') return schema
  try {
    return JSON.stringify(schema, null, 2)
  } catch (e) {
    return ''
  }
}

// Parse JSON schema string to object
function parseJsonSchema(schemaString: string): any {
  if (!schemaString || !schemaString.trim()) return null
  try {
    return JSON.parse(schemaString)
  } catch (e) {
    // Payload requires an object; keep null if invalid JSON.
    return null
  }
}

// Start editing port name
function startEditingName(port: any, event: Event) {
  if (props.readonly) return

  event.stopPropagation()

  const currentName = port.is_custom
    ? port.name
    : getPortConfig(port.parameter_id, port.name, port.is_custom)?.ai_name_override || port.name

  editingPortName.value = port.name
  editingNameValue.value = currentName
}

// Save edited port name
function saveEditedName(port: any) {
  if (editingNameValue.value && editingNameValue.value !== port.name) {
    const normalizedName = normalizeParameterName(editingNameValue.value)

    updateAiOverride(port.parameter_id, port.name, 'ai_name_override', normalizedName, port.is_custom)
  }

  editingPortName.value = null
  editingNameValue.value = ''
}

// Cancel editing
function cancelEditing() {
  editingPortName.value = null
  editingNameValue.value = ''
}
</script>

<template>
  <div class="port-configuration-editor">
    <!-- Header -->
    <div class="text-subtitle-2 mb-4">Tool Parameters</div>

    <!-- Port List -->
    <VExpansionPanels v-if="allPorts.length > 0" variant="accordion" class="mb-4">
      <VExpansionPanel v-for="port in allPorts" :key="port.id || port.name">
        <template #title>
          <div
            class="d-flex align-center justify-space-between w-100"
            @click.stop="editingPortName === port.name ? null : undefined"
          >
            <div class="d-flex align-center ga-2">
              <!-- Editable name -->
              <div v-if="editingPortName === port.name" class="d-flex align-center ga-2" @click.stop>
                <VTextField
                  v-model="editingNameValue"
                  density="compact"
                  variant="outlined"
                  hide-details
                  autofocus
                  class="flex-grow-0"
                  style="min-width: 200px"
                  @input="(e: any) => (editingNameValue = normalizeParameterName(e.target.value))"
                  @blur="saveEditedName(port)"
                  @keydown.enter="saveEditedName(port)"
                  @keydown.esc="cancelEditing"
                  @click.stop
                />
              </div>

              <div v-else class="d-flex align-center ga-2">
                <span
                  class="font-weight-bold editable-text"
                  :class="{ 'readonly-text': readonly || !port.is_custom }"
                  @click.stop="readonly || !port.is_custom ? null : startEditingName(port, $event)"
                >
                  {{
                    port.is_custom
                      ? port.name
                      : getPortConfig(port.parameter_id, port.name, port.is_custom)?.ai_name_override || port.name
                  }}
                  <span
                    v-if="
                      !port.nullable ||
                      getPortConfig(port.parameter_id, port.name, port.is_custom)?.is_required_override
                    "
                    class="text-primary text-caption ms-1"
                    style="opacity: 0.8"
                    >(required)</span
                  >
                </span>
              </div>

              <VChip
                :color="
                  getConfigTypeColor(
                    getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode || 'deactivated'
                  )
                "
                size="x-small"
                variant="tonal"
              >
                {{
                  (getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode || 'deactivated') ===
                  'ai_filled'
                    ? 'AI'
                    : (getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode || 'deactivated') ===
                        'user_set'
                      ? 'Set value'
                      : 'Discard'
                }}
              </VChip>
            </div>

            <span
              v-if="port.is_custom && !readonly"
              class="delete-icon-wrapper me-2"
              @click.stop="removeCustomPort(port.name)"
            >
              <Icon icon="mdi-delete" class="delete-icon" width="18" />
            </span>
          </div>
        </template>

        <template #text>
          <VCard flat>
            <VCardText class="pt-2">
              <!-- Description (default from port, editable) -->
              <VTextarea
                :model-value="
                  getPortConfig(port.parameter_id, port.name, port.is_custom)?.ai_description_override ??
                  port.description
                "
                label="Description"
                density="compact"
                variant="outlined"
                rows="2"
                :disabled="readonly"
                :placeholder="port.description"
                class="mb-2"
                @update:model-value="
                  (val: any) =>
                    updateAiOverride(
                      port.parameter_id,
                      port.name,
                      'ai_description_override',
                      val || null,
                      port.is_custom
                    )
                "
              />

              <!-- Parameter Type -->
              <VSelect
                :model-value="
                  port.is_custom
                    ? (getPortConfig(port.parameter_id, port.name, port.is_custom)?.custom_parameter_type ??
                      port.parameter_type)
                    : port.parameter_type
                "
                :items="parameterTypes"
                label="Parameter type"
                density="compact"
                variant="outlined"
                :disabled="readonly || !port.is_custom"
                class="mb-2"
                @update:model-value="
                  (val: any) =>
                    port.is_custom &&
                    updateAiOverride(port.parameter_id, port.name, 'custom_parameter_type', val, port.is_custom)
                "
              />

              <!-- Configuration Type Selector -->
              <VRadioGroup
                :model-value="getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode || 'deactivated'"
                :disabled="readonly"
                @update:model-value="
                  (val: any) => updateConfigType(port.parameter_id, port.name, val, port.nullable, port.is_custom)
                "
              >
                <VRadio value="ai_filled" color="primary">
                  <template #label>
                    <div>
                      <div class="font-weight-medium">Let AI Agent decide the value</div>
                    </div>
                  </template>
                </VRadio>

                <VRadio value="user_set" color="secondary">
                  <template #label>
                    <div>
                      <div class="font-weight-medium">Set value</div>
                    </div>
                  </template>
                </VRadio>

                <VRadio value="deactivated" color="grey" :disabled="!port.nullable && !port.is_custom">
                  <template #label>
                    <div>
                      <div class="font-weight-medium">Discard Parameter</div>
                    </div>
                  </template>
                </VRadio>
              </VRadioGroup>

              <!-- AI Filled Configuration -->
              <div
                v-if="getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode === 'ai_filled'"
                class="mt-4"
              >
                <!-- Required Toggle -->
                <VCheckbox
                  :model-value="
                    getPortConfig(port.parameter_id, port.name, port.is_custom)?.is_required_override ?? false
                  "
                  label="Make this parameter required for AI"
                  density="compact"
                  :disabled="readonly || (!port.nullable && !port.is_custom)"
                  hide-details
                  @update:model-value="
                    (val: any) =>
                      updateAiOverride(port.parameter_id, port.name, 'is_required_override', val, port.is_custom)
                  "
                />

                <div v-if="!port.nullable && !port.is_custom" class="text-caption mt-1" style="color: orange">
                  <Icon icon="mdi-information" class="me-1" />
                  This parameter is required by the component and cannot be made optional
                </div>

                <!-- JSON Schema Override (for complex types) -->
                <VTextarea
                  v-if="['json', 'array', 'object'].includes(port.parameter_type)"
                  :model-value="
                    jsonSchemaToString(
                      getPortConfig(port.parameter_id, port.name, port.is_custom)?.json_schema_override
                    )
                  "
                  label="JSON Schema"
                  density="compact"
                  variant="outlined"
                  rows="8"
                  :disabled="readonly"
                  placeholder="Define the schema structure..."
                  hint="Define a complete JSON Schema for complex types (arrays, nested objects, etc.)"
                  persistent-hint
                  class="mt-3"
                  @update:model-value="
                    (val: any) =>
                      updateAiOverride(
                        port.parameter_id,
                        port.name,
                        'json_schema_override',
                        parseJsonSchema(val),
                        port.is_custom
                      )
                  "
                />
              </div>

              <!-- User Set Configuration -->
              <div
                v-if="getPortConfig(port.parameter_id, port.name, port.is_custom)?.setup_mode === 'user_set'"
                class="mt-4"
              >
                <div class="text-subtitle-2 mb-2">Value</div>
                <FieldExpressionInput
                  :model-value="
                    getPortConfig(port.parameter_id, port.name, port.is_custom)?.expression_json || undefined
                  "
                  :placeholder="`Set value for ${port.name}`"
                  :disabled="readonly"
                  :graph-nodes="upstreamNodes"
                  @update:model-value="
                    (val: any) => updateExpression(port.parameter_id, port.name, val, port.is_custom)
                  "
                />
              </div>
            </VCardText>
          </VCard>
        </template>
      </VExpansionPanel>
    </VExpansionPanels>

    <!-- Empty State -->
    <div v-if="allPorts.length === 0" class="text-center py-8 text-medium-emphasis">
      <Icon icon="mdi-information-outline" width="48" class="mb-2" />
      <div>No ports available for this component</div>
    </div>

    <!-- Add Parameter Button -->
    <div v-if="!readonly" class="mt-4 d-flex align-center ga-2">
      <VBtn prepend-icon="mdi-plus" variant="outlined" size="small" class="flex-grow-1" @click="addCustomPort">
        Add Parameter
      </VBtn>
      <VTooltip max-width="400">
        <template #activator="{ props: tooltipProps }">
          <span v-bind="tooltipProps">
            <Icon icon="mdi-help-circle-outline" width="20" class="help-icon" />
          </span>
        </template>
        <span>
          You can add parameters so the AI agent can handle them dynamically. This is useful for the API tool runner to
          define query inputs, or for the AI agent to inject values into the prompt using {{}}.
        </span>
      </VTooltip>
    </div>

    <!-- Add Parameter Dialog -->
    <VDialog v-model="showAddParameterDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardText class="pa-6">
          <h3 class="text-h6 mb-4">Add New Parameter</h3>

          <VTextField
            v-model="newParameterForm.name"
            label="Parameter name"
            density="compact"
            variant="outlined"
            placeholder="e.g., api_key, user_id"
            class="mb-3"
            autofocus
            :rules="[v => !!v || 'Name is required']"
            @input="(e: any) => (newParameterForm.name = normalizeParameterName(e.target.value))"
          />

          <VTextarea
            v-model="newParameterForm.description"
            label="Description"
            density="compact"
            variant="outlined"
            rows="2"
            placeholder="Describe what this parameter does"
            class="mb-3"
          />

          <VSelect
            v-model="newParameterForm.type"
            :items="parameterTypes"
            label="Parameter type"
            density="compact"
            variant="outlined"
            class="mb-4"
          />

          <div class="d-flex ga-2 justify-end">
            <VBtn variant="text" @click="cancelAddParameter">Cancel</VBtn>
            <VBtn color="primary" variant="flat" :disabled="!newParameterForm.name.trim()" @click="createCustomPort">
              Add Parameter
            </VBtn>
          </div>
        </VCardText>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.port-configuration-editor {
  :deep(.v-expansion-panel-title) {
    min-height: 48px;
  }

  :deep(.v-radio) {
    margin-bottom: 8px;
  }

  .editable-text {
    position: relative;
    transition: all 0.2s;
    padding: 2px 4px;
    border-radius: 4px;

    &:not(.readonly-text) {
      cursor: pointer;

      &:hover {
        background-color: rgba(var(--v-theme-primary), 0.08);
      }

      &::after {
        content: '✏️';
        font-size: 10px;
        margin-left: 4px;
        opacity: 0;
        transition: opacity 0.2s;
      }

      &:hover::after {
        opacity: 0.6;
      }
    }
  }

  .readonly-text {
    cursor: default;
  }

  .edit-icon-wrapper {
    cursor: pointer;
    padding: 6px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: background-color 0.2s;

    &:hover {
      background-color: rgba(var(--v-theme-surface), 0.12);
    }
  }

  .edit-icon {
    opacity: 0.8;
    transition: opacity 0.2s;

    .edit-icon-wrapper:hover & {
      opacity: 1;
    }
  }

  .delete-icon-wrapper {
    cursor: pointer;
    padding: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: background-color 0.2s;

    &:hover {
      background-color: rgba(var(--v-theme-error), 0.08);
    }
  }

  .delete-icon {
    color: rgb(var(--v-theme-error));
    opacity: 0.7;
    transition: opacity 0.2s;

    .delete-icon-wrapper:hover & {
      opacity: 1;
    }
  }

  .help-icon {
    cursor: help;
    color: rgb(var(--v-theme-primary));
    opacity: 0.6;
    transition: opacity 0.2s;

    &:hover {
      opacity: 1;
    }
  }
}
</style>
