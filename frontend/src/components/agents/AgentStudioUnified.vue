<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { debounce } from 'lodash-es'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { VCheckbox } from 'vuetify/components/VCheckbox'
import { VSelect } from 'vuetify/components/VSelect'
import { VSlider } from 'vuetify/components/VSlider'
import { VTextarea } from 'vuetify/components/VTextarea'
import { VTextField } from 'vuetify/components/VTextField'
import AgentSaveDeployButtons from './AgentSaveDeployButtons.vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import ParameterLabel from '@/components/shared/ParameterLabel.vue'
import ComponentSelectionCarousel from '@/components/studio/components/ComponentSelectionCarousel.vue'
import EditSidebar from '@/components/studio/components/EditSidebar.vue'
import StudioShell from '@/components/studio/StudioShell.vue'
import { isProviderLogo } from '@/components/studio/utils/node-factory.utils'
import { type Agent, useCurrentAgent } from '@/composables/queries/useAgentsQuery'
import { useLLMCredits } from '@/composables/useLLMCredits'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { logComponentMount, logComponentUnmount } from '@/utils/queryLogger'

interface Props {
  componentDefinitions?: any[] | null // Passed from parent (centralized fetching)
  categories?: any[] | null // Categories from components response
  agent?: Agent | null // Direct agent reference for parameter access
  agentProjectId?: string // The project_id for API calls
  onSave?: (create_snapshot?: boolean) => Promise<void> // Manual save function from parent
  isLoading?: boolean // Whether agent data is currently loading
}

const props = defineProps<Props>()

const emit = defineEmits<{
  toolAdded: [toolData: any]
  openCronModal: []
  parameterChange: [payload: { name: string; value: any }]
}>()

const { currentGraphRunner } = useCurrentAgent()

const { selectedOrgId } = useSelectedOrg()
const { getLLMModelItems } = useLLMCredits()

// Use component definitions from parent props (centralized fetching)
const functionCallableComponents = computed(() => {
  return props.componentDefinitions?.filter(comp => comp.function_callable) || []
})

// Component lifecycle logging
onMounted(() => {
  logComponentMount('AgentStudioUnified', [['component-definitions', selectedOrgId.value]])
})

onUnmounted(() => {
  logComponentUnmount('AgentStudioUnified')
})

// Ref to the save/deploy buttons component
const saveDeployButtons = ref<InstanceType<typeof AgentSaveDeployButtons> | null>(null)

// Check if in draft mode
// Any graph runner with env=draft is editable
const isDraftMode = computed(() => currentGraphRunner.value?.env === 'draft')

// Settings state - collapsed by default
const settingsExpanded = ref(false)

// Local state for editing
const editedParameters = ref({
  initial_prompt: '',
})

// Tools state
const showAddToolDialog = ref(false)
const showEditSidebar = ref(false)
const editingToolId = ref<string | null>(null)
const editingToolParameters = ref<Record<string, any>>({})
const showDeleteConfirm = ref(false)
const toolToDelete = ref<any | null>(null)

// Get all function callable components (these are the available tools)
const availableTools = functionCallableComponents

// Get current agent tools with version info
// Tools are stored as objects: { component_id, component_version_id, version_tag }
// We use component_version_id as the primary identifier
const currentToolsMap = computed(() => {
  if (!props.agent?.tools || props.agent.tools.length === 0) return new Map()

  const toolsMap = new Map()

  props.agent.tools.forEach(tool => {
    if (tool && typeof tool === 'object') {
      const componentVersionId = tool.component_version_id
      if (componentVersionId) {
        toolsMap.set(componentVersionId, {
          component_id: tool.component_id,
          component_version_id: tool.component_version_id,
          version_tag: tool.version_tag,
        })
      }
    }
  })

  return toolsMap
})

// Get added tools with their version info
const addedTools = computed(() => {
  return availableTools.value
    .filter(tool => currentToolsMap.value.has(tool.component_version_id))
    .map(tool => {
      const savedSchema = props.agent?.toolSchemas?.[tool.component_version_id]

      return {
        ...tool,
        name: savedSchema?.name || tool.name,
        description: savedSchema?.component_description || tool.description,
      }
    })
})

// Get excluded tools as a Set (for ComponentSelectionCarousel)
const excludedToolsSet = computed(() => {
  return new Set(currentToolsMap.value.keys())
})

const advancedParametersData = ref<Record<string, any>>({})

// Get agent parameters (for Settings section)
const agentParameters = computed(() => {
  if (!props.agent?.parameters) return []

  return props.agent.parameters.filter(
    p =>
      p.name !== 'initial_prompt' &&
      (p.is_advanced ||
        p.name === 'completion_model' ||
        p.name === 'default_temperature' ||
        p.name === 'max_tokens' ||
        p.name.includes('model') ||
        p.name.includes('temperature') ||
        p.name.includes('token'))
  )
})

// Get agent data - direct access to agent parameters
const agentParametersData = computed(() => props.agent?.parameters || [])

const initialPromptParam = computed(() =>
  agentParametersData.value.find((p: { name: string }) => p.name === 'initial_prompt')
)

// Initialize edited parameters from props (read-only — never mutate props)
const initializeEditedParameters = () => {
  if (!props.agent) return

  editedParameters.value = {
    initial_prompt: initialPromptParam.value?.value || props.agent.system_prompt || '',
  }

  advancedParametersData.value = {}
  agentParameters.value.forEach((param: any) => {
    advancedParametersData.value[param.name] = param.value
  })
}

// Reinitialize only when switching to a different agent or version, not on every deep mutation
watch(
  () => `${props.agent?.id}:${props.agent?.version_id}`,
  () => {
    if (props.agent) initializeEditedParameters()
  },
  { immediate: true }
)

// Watch for sidebar closing - if user cancels without saving, reset editing state
watch(
  () => showEditSidebar.value,
  isOpen => {
    if (!isOpen && editingToolId.value) {
      // Sidebar was closed - if this was for adding a new tool (not editing existing), clear the state
      const toolId = editingToolId.value
      const toolExists = currentToolsMap.value.has(toolId)

      if (!toolExists) {
        // This was a new tool that was never saved, clear the editing state
        editingToolId.value = null
        editingToolParameters.value = {}
      }
    }
  }
)

// Handle parameter change — emit to parent instead of mutating readonly props
const handleParameterChange = async (paramName: string, value: any) => {
  ;(editedParameters.value as any)[paramName] = value
  emit('parameterChange', { name: paramName, value })
  saveDeployButtons.value?.markAsChanged()
}

// Handle tool selection from ComponentSelectionCarousel
const handleToolSelected = async (tool: any) => {
  const toolId = tool.component_version_id

  // Check if tool already exists
  if (currentToolsMap.value.has(toolId)) return

  editingToolId.value = toolId

  const componentDef = availableTools.value.find(t => t.component_version_id === toolId)

  if (!componentDef) return

  // Build full component object with default parameter values
  editingToolParameters.value = {
    component_id: componentDef.component_id,
    component_version_id: toolId,
    name: componentDef.name,
    description: componentDef.description,
    parameters:
      componentDef.parameters?.map((param: any) => ({
        ...param,
        value: param.default ?? null,
        is_tool_input: param.is_tool_input ?? true,
      })) || [],
    function_callable: componentDef.function_callable,
    canEditToolDescription: componentDef.function_callable === true,
    tool_description: componentDef.tool_description || {
      name: componentDef.name,
      description: componentDef.description || '',
      tool_properties: {},
      required_tool_properties: [],
    },
  }

  showEditSidebar.value = true
}

// Remove tool from agent
const handleRemoveTool = async (tool: any) => {
  if (!props.agent?.tools) return

  const toolId = tool.component_version_id

  // Find and remove the tool
  const index = props.agent.tools.findIndex(t => t && typeof t === 'object' && t.component_version_id === toolId)

  if (index > -1) {
    props.agent.tools.splice(index, 1)
    saveDeployButtons.value?.markAsChanged()
  }
}

// Request remove tool
const requestRemoveTool = (tool: any, event?: Event) => {
  if (event) event.stopPropagation()
  toolToDelete.value = tool
  showDeleteConfirm.value = true
}

// Confirm delete
const handleDeleteConfirmed = async () => {
  if (toolToDelete.value) await handleRemoveTool(toolToDelete.value)

  toolToDelete.value = null
  showDeleteConfirm.value = false
}

// Cancel delete
const handleDeleteCancelled = () => {
  toolToDelete.value = null
  showDeleteConfirm.value = false
}

// Open edit dialog for a tool
const handleEditTool = (tool: any) => {
  const toolId = tool.component_version_id

  editingToolId.value = toolId

  // Build component data from tool + saved parameters
  const existingParams = props.agent?.toolParameters?.[toolId] || {}

  // Check if we have a saved schema for this tool (existing tool)
  const savedToolSchema = props.agent?.toolSchemas?.[toolId]

  if (savedToolSchema) {
    // EXISTING TOOL: Use saved schema, only update values from existingParams
    editingToolParameters.value = {
      component_id: tool.component_id,
      component_version_id: toolId,
      name: savedToolSchema.name,
      description: savedToolSchema.component_description,
      tool_description: savedToolSchema.tool_description,
      parameters: savedToolSchema.parameters.map((param: any) => ({
        ...param,
        value: existingParams[param.name] !== undefined ? existingParams[param.name] : param.value,
        is_tool_input: param.is_tool_input ?? true,
      })),
      function_callable: true, // Tools in agent are function-callable
      canEditToolDescription: true, // Enable tool description editing
    }
  } else {
    // NEW TOOL or legacy (no schema saved): Use component definition
    const toolDef = availableTools.value.find(t => t.component_version_id === toolId)
    if (!toolDef) return

    editingToolParameters.value = {
      component_id: toolDef.component_id,
      component_version_id: toolId,
      name: toolDef.name,
      description: toolDef.description,
      parameters:
        toolDef.parameters?.map((param: any) => ({
          ...param,
          value: existingParams[param.name] !== undefined ? existingParams[param.name] : param.default,
          is_tool_input: param.is_tool_input ?? true,
        })) || [],
      function_callable: toolDef.function_callable,
      canEditToolDescription: toolDef.function_callable === true,
      tool_description: toolDef.tool_description || {
        name: toolDef.name,
        description: toolDef.description || '',
        tool_properties: {},
        required_tool_properties: [],
      },
    }
  }

  showEditSidebar.value = true
}

// Save tool component
const handleSaveToolComponent = async (component: any) => {
  if (!editingToolId.value || !props.agent) return

  // Initialize agent data structures if needed
  if (!props.agent.tools) props.agent.tools = []
  if (!props.agent.toolParameters) props.agent.toolParameters = {}
  if (!props.agent.toolSchemas) props.agent.toolSchemas = {}

  // Add tool to agent's tools array if not already present
  if (!currentToolsMap.value.has(editingToolId.value)) {
    const componentDef = availableTools.value.find(t => t.component_version_id === editingToolId.value)
    if (componentDef) {
      const toolData = {
        component_id: componentDef.id,
        component_version_id: editingToolId.value,
      }

      props.agent.tools.push(toolData)
      emit('toolAdded', toolData)
    }
  }

  // Extract and save tool parameters
  if (component.parameters) {
    const params: Record<string, any> = {}

    component.parameters.forEach((param: any) => {
      params[param.name] = param.value
    })
    props.agent.toolParameters[editingToolId.value] = params
  }

  // Save the complete tool schema
  props.agent.toolSchemas[editingToolId.value] = {
    name: component.name,
    component_description: component.description,
    parameters: component.parameters || [],
    tool_description: component.tool_description || null,
  }

  saveDeployButtons.value?.markAsChanged()

  editingToolId.value = null
  editingToolParameters.value = {}
  showEditSidebar.value = false
}

// Generate human-readable label from parameter name
const getParamLabel = (param: any, uiProps: any) => {
  return uiProps.label || param.name.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())
}

// Get component config for parameter rendering
const getComponentConfig = (param: any) => {
  const uiComponent = param.ui_component || 'TextField'
  const uiProps = param.ui_component_properties || {}
  const label = getParamLabel(param, uiProps)

  switch (uiComponent) {
    case 'Checkbox':
      return {
        component: VCheckbox,
        props: {
          label,
          color: 'primary',
          readonly: !isDraftMode.value,
          disabled: !isDraftMode.value,
          ...uiProps,
        },
      }

    case 'Slider':
      return {
        component: VSlider,
        props: {
          label,
          thumbLabel: true,
          showTicks: uiProps.marks || false,
          min: uiProps.min || 0,
          max: uiProps.max || 100,
          step: uiProps.step || 1,
          readonly: !isDraftMode.value,
          disabled: !isDraftMode.value,
          ...uiProps,
        },
      }

    case 'Select':
      // Special handling for llm_model type - include credit information
      if (param.type === 'llm_model') {
        const items = getLLMModelItems(uiProps.options || [])

        return {
          component: VSelect,
          props: {
            label,
            items,
            itemTitle: 'title',
            itemSubtitle: 'subtitle',
            itemValue: 'value',
            variant: 'outlined',
            readonly: !isDraftMode.value,
            disabled: !isDraftMode.value,
            ...uiProps,
          },
        }
      }

      return {
        component: VSelect,
        props: {
          label,
          items:
            uiProps.options?.map((opt: any) => ({
              title: opt.label,
              value: opt.value,
            })) || [],
          variant: 'outlined',
          readonly: !isDraftMode.value,
          disabled: !isDraftMode.value,
          ...uiProps,
        },
      }

    case 'Textarea':
      return {
        component: VTextarea,
        props: {
          label,
          variant: 'outlined',
          rows: 3,
          readonly: !isDraftMode.value,
          ...uiProps,
        },
      }

    default: {
      const inputProps: any = {
        label,
        variant: 'outlined' as const,
        readonly: !isDraftMode.value,
        ...uiProps,
      }

      if (param.type === 'integer') {
        inputProps.type = 'number'
        inputProps.step = '1'
      } else if (param.type === 'number') {
        inputProps.type = 'number'
        inputProps.step = '0.1'
      }

      return {
        component: VTextField,
        props: inputProps,
      }
    }
  }
}

// Debounced save trigger - lodash debounce resets timer on each call
const debouncedMarkAsChanged = debounce(() => {
  saveDeployButtons.value?.markAsChanged()
}, 1000)

// Handle parameter update in settings — emit to parent instead of mutating readonly props
const handleParameterUpdate = (paramName: string, value: any) => {
  if (!props.agent) return

  advancedParametersData.value[paramName] = value
  emit('parameterChange', { name: paramName, value })
  debouncedMarkAsChanged()
}
</script>

<template>
  <div class="agent-studio-unified">
    <StudioShell>
      <template #toolbar-right>
        <AgentSaveDeployButtons
          ref="saveDeployButtons"
          :agent="agent || null"
          :on-save="onSave"
          :is-loading="isLoading"
          @open-cron-modal="emit('openCronModal')"
        />
      </template>

      <div class="studio-content">
        <div class="studio-container">
          <VRow class="main-content">
            <VCol cols="12" md="8" class="instructions-column">
              <div class="h-100">
                <div class="pa-0">
                  <div class="d-flex align-center justify-space-between mb-4">
                    <div>
                      <h2 class="text-h5 mb-1">Instructions</h2>
                      <p class="text-body-2 text-medium-emphasis">
                        Define how the agent should behave and what its role is.
                      </p>
                    </div>
                  </div>
                  <p v-if="!isDraftMode" class="text-caption text-warning mb-4">
                    <VIcon icon="tabler-lock" size="16" class="me-1" />
                    Read-only: Switch to draft version to edit instructions
                  </p>

                  <VTextarea
                    v-model="editedParameters.initial_prompt"
                    variant="outlined"
                    rows="5"
                    auto-grow
                    class="instructions-textarea"
                    :readonly="!isDraftMode"
                    :placeholder="isDraftMode ? 'You are a helpful AI assistant...' : ''"
                    @blur="() => handleParameterChange('initial_prompt', editedParameters.initial_prompt)"
                  />
                </div>
              </div>
            </VCol>

            <VCol cols="12" md="4" class="tools-column">
              <div class="h-100">
                <div class="pa-0">
                  <div class="d-flex align-center justify-space-between mb-4">
                    <div>
                      <h2 class="text-h5 mb-1">Tools</h2>
                      <p class="text-body-2 text-medium-emphasis">Extend agent capabilities</p>
                    </div>
                  </div>

                  <div class="tools-list">
                    <div v-if="addedTools.length > 0" class="tools-items">
                      <VCard
                        v-for="tool in addedTools"
                        :key="tool.component_version_id || tool.component_id || tool.id"
                        variant="outlined"
                        class="tool-card-compact mb-2"
                        :class="[{ 'tool-card-readonly': !isDraftMode }]"
                        @click="handleEditTool(tool)"
                      >
                        <VCardText class="pa-3">
                          <div class="d-flex gap-2">
                            <VAvatar
                              size="32"
                              :color="isProviderLogo(tool.icon) ? undefined : 'success'"
                              :variant="isProviderLogo(tool.icon) ? 'flat' : 'tonal'"
                              class="flex-shrink-0"
                            >
                              <Icon v-if="isProviderLogo(tool.icon)" :icon="tool.icon" :width="18" :height="18" />
                              <VIcon v-else :icon="tool.icon || 'tabler-tool'" size="18" />
                            </VAvatar>
                            <div class="flex-grow-1 text-center">
                              <div class="text-h6 font-weight-bold mb-1">
                                {{ tool.name }}
                              </div>
                              <div class="text-caption text-medium-emphasis tool-description">
                                {{ tool.description || 'No description' }}
                              </div>
                            </div>
                            <VBtn
                              v-if="isDraftMode"
                              icon
                              variant="text"
                              size="x-small"
                              color="error"
                              class="flex-shrink-0"
                              @click.stop="requestRemoveTool(tool)"
                            >
                              <VIcon icon="tabler-x" size="16" />
                            </VBtn>
                          </div>
                        </VCardText>
                      </VCard>

                      <VBtn
                        v-if="isDraftMode"
                        block
                        size="small"
                        color="primary"
                        variant="tonal"
                        class="mt-2"
                        @click="showAddToolDialog = true"
                      >
                        <VIcon icon="tabler-plus" class="me-1" size="18" />
                        Add Tool
                      </VBtn>
                    </div>

                    <div v-else class="text-center pa-4">
                      <VIcon icon="tabler-tools" size="48" class="mb-2 text-medium-emphasis" />
                      <p class="text-body-2 text-medium-emphasis mb-2">No tools added</p>
                      <VBtn
                        v-if="isDraftMode"
                        size="small"
                        color="primary"
                        variant="tonal"
                        @click="showAddToolDialog = true"
                      >
                        <VIcon icon="tabler-plus" class="me-1" size="18" />
                        Add Tool
                      </VBtn>
                    </div>
                  </div>
                </div>
              </div>
            </VCol>
          </VRow>

          <div class="mt-6">
            <div
              class="settings-toggle d-flex align-center justify-space-between pa-4 cursor-pointer mb-4"
              @click="settingsExpanded = !settingsExpanded"
            >
              <div>
                <h2 class="text-h5 mb-1">Settings</h2>
                <p class="text-body-2 text-medium-emphasis mb-0">Configure advanced model parameters</p>
              </div>
              <VBtn icon variant="text" size="small">
                <VIcon :icon="settingsExpanded ? 'tabler-chevron-up' : 'tabler-chevron-down'" />
              </VBtn>
            </div>

            <VExpandTransition>
              <div v-show="settingsExpanded" class="settings-content">
                <div v-if="agentParameters.length > 0">
                  <div class="d-flex align-center justify-space-between mb-3">
                    <div class="d-flex align-center gap-2">
                      <VIcon icon="tabler-adjustments" size="18" />
                      <h3 class="text-subtitle-2 font-weight-medium">Advanced Parameters</h3>
                    </div>
                    <p v-if="!isDraftMode" class="text-caption text-warning mb-0">
                      <VIcon icon="tabler-lock" size="16" class="me-1" />
                      Read-only: Switch to draft version to edit
                    </p>
                  </div>

                  <VRow>
                    <VCol v-for="param in agentParameters" :key="param.name" cols="12" md="6">
                      <ParameterLabel
                        :label="getComponentConfig(param).props.label"
                        :required="param.nullable === false"
                      />
                      <VSelect
                        v-if="param.type === 'llm_model'"
                        :model-value="advancedParametersData[param.name]"
                        v-bind="{ ...getComponentConfig(param).props, label: undefined }"
                        @update:model-value="value => handleParameterUpdate(param.name, value)"
                      >
                        <template #item="{ item, props: itemProps }">
                          <VListItem v-bind="itemProps" :title="item.raw.title">
                            <template #subtitle>
                              <span class="text-medium-emphasis text-caption">{{ item.raw.subtitle }}</span>
                            </template>
                          </VListItem>
                        </template>
                      </VSelect>
                      <component
                        :is="getComponentConfig(param).component"
                        v-else
                        :model-value="advancedParametersData[param.name]"
                        v-bind="{ ...getComponentConfig(param).props, label: undefined }"
                        @update:model-value="(value: any) => handleParameterUpdate(param.name, value)"
                      />

                      <p v-if="param.description" class="text-caption text-medium-emphasis mt-1">
                        {{ param.description }}
                      </p>
                    </VCol>
                  </VRow>
                </div>

                <div v-else class="text-center py-8">
                  <VIcon icon="tabler-settings-x" size="48" color="disabled" class="mb-4" />
                  <h3 class="text-h6 mb-2">No Advanced Parameters</h3>
                  <p class="text-body-2 text-medium-emphasis">This agent has no additional configurable parameters.</p>
                </div>
              </div>
            </VExpandTransition>
          </div>
        </div>
      </div>
    </StudioShell>

    <ComponentSelectionCarousel
      v-model="showAddToolDialog"
      mode="agent-tool"
      :component-definitions="componentDefinitions"
      :categories="categories"
      :excluded-tools="excludedToolsSet"
      @tool-selected="handleToolSelected"
    />

    <EditSidebar
      v-if="editingToolId"
      v-model="showEditSidebar"
      :component-data="editingToolParameters"
      :component-definitions="componentDefinitions"
      :projects="[]"
      :is-draft-mode="isDraftMode"
      @save="handleSaveToolComponent"
    />

    <GenericConfirmDialog
      v-if="toolToDelete"
      v-model:is-dialog-visible="showDeleteConfirm"
      title="Remove Tool"
      :message="`Are you sure you want to remove the tool <strong>${toolToDelete.name || toolToDelete.component_name || toolToDelete.id}</strong>?<br><br>This action cannot be undone.`"
      confirm-text="Remove"
      confirm-color="error"
      @confirm="handleDeleteConfirmed"
      @cancel="handleDeleteCancelled"
    />
  </div>
</template>

<style lang="scss" scoped>
// Mixin for consistent custom scrollbar styling
@mixin custom-scrollbar($thumb-opacity: 0.2) {
  &::-webkit-scrollbar {
    inline-size: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), $thumb-opacity);

    &:hover {
      background: rgba(var(--v-theme-on-surface), calc($thumb-opacity + 0.1));
    }
  }
}

.agent-studio-unified {
  display: flex;
  flex-direction: column;
  block-size: 100%;

  .studio-content {
    overflow-y: auto;
    block-size: 100%;
  }

  .studio-container {
    padding: 1.5rem;
  }

  .main-content {
    align-items: flex-start;
    margin-block-start: 0;
  }

  .instructions-column,
  .tools-column {
    > div {
      block-size: 100%;
    }
  }

  .tools-column {
    .tools-list {
      margin-block-start: 0;
    }
  }

  .tools-list {
    max-block-size: calc(100vh - 400px);
    overflow: hidden auto;
    @include custom-scrollbar(0.2);
  }

  .tool-card-compact {
    background: rgb(var(--v-theme-surface));
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      border-color: rgb(var(--v-theme-primary));
      background: rgba(var(--v-theme-primary), 0.05);
    }

    &.tool-card-readonly {
      // Still allow clicking to view in read-only mode
      opacity: 0.9;

      &:hover {
        border-color: rgba(var(--v-theme-primary), 0.5);
        // Lighter hover effect for read-only mode
        background: rgba(var(--v-theme-on-surface), 0.03);
      }
    }
  }

  .settings-toggle {
    border-radius: 8px;
    margin-block: 0;
    margin-inline: -1rem;
    transition: background-color 0.2s ease;
    user-select: none;

    &:hover {
      background-color: rgba(var(--v-theme-on-surface), 0.05);
    }

    &:active {
      background-color: rgba(var(--v-theme-on-surface), 0.08);
    }

    h2 {
      font-size: 1.25rem;
      font-weight: 500;
    }

    p {
      font-size: 0.875rem;
    }
  }

  .cursor-pointer {
    cursor: pointer;
  }

  .tool-description {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    line-height: 1.4;
    min-block-size: 2.8em;
    text-overflow: ellipsis;
  }

  .instructions-textarea :deep(.v-field__field) {
    max-block-size: 60vh;
    overflow-y: auto;
    @include custom-scrollbar(0.15);
  }
}
</style>
