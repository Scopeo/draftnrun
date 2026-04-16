<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { Icon } from '@iconify/vue'
import { isProviderLogo } from '../utils/node-factory.utils'
import EditSidebarParameterField from './EditSidebarParameterField.vue'
import EditSidebarGmail from './EditSidebarGmail.vue'
import EditSidebarOptionalTools from './EditSidebarOptionalTools.vue'
import EditSidebarConfigContent from './EditSidebarConfigContent.vue'
import ProjectSelectionDialog from './ProjectSelectionDialog.vue'
import { useEditSidebarForm } from '@/composables/useEditSidebarForm'
import { useEditSidebarPorts } from '@/composables/useEditSidebarPorts'
import { useEditSidebarSubmit } from '@/composables/useEditSidebarSubmit'
import { useEditSidebarOAuth } from '@/composables/useEditSidebarOAuth'
import { useEditSidebarComponentConfig } from '@/composables/useEditSidebarComponentConfig'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'
import { logger } from '@/utils/logger'

interface Props {
  modelValue: boolean
  componentData?: any | null
  componentId?: string | null
  componentDefinitions?: any[] | null
  projects?: any[] | null
  agents?: any[] | null
  isDraftMode?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits(['update:modelValue', 'save', 'add-tools', 'remove-tool'])

const drawer = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const componentData = computed(() => props.componentData || null)
const isWorker = computed(() => componentData.value?.type === 'worker')
const componentDefinitions = computed(() => props.componentDefinitions || [])
const projects = computed(() => props.projects || [])
const agents = computed(() => props.agents || [])

const ability = useAbility()
const isReadOnlyMode = computed(() => !ability.can('update', 'Project') || props.isDraftMode === false)

const currentComponentId = computed(() => {
  if (componentData.value) return componentData.value.component_version_id || componentData.value.component_id
  return props.componentId
})

const componentDefinition = computed(() => {
  if (!currentComponentId.value) return null
  const definition = getComponentDefinitionFromCache(componentDefinitions.value, currentComponentId.value)
  if (!definition)
    logger.error('EditSidebar - No component definition found for ID', { error: currentComponentId.value })
  return definition
})

const componentIdComputed = computed(() => props.componentId || null)

// --- Composables ---
const form = useEditSidebarForm(
  componentData,
  componentDefinition,
  componentDefinitions,
  currentComponentId,
  isReadOnlyMode,
  drawer,
  componentIdComputed
)

const emitAny = emit as (event: string, ...args: any[]) => void
const ports = useEditSidebarPorts(componentData)

const componentConfig = useEditSidebarComponentConfig(
  componentData,
  componentDefinition,
  componentDefinitions,
  form.formData,
  form.sources,
  isReadOnlyMode,
  isWorker,
  projects
)

const submit = useEditSidebarSubmit(
  componentData,
  componentDefinition,
  componentDefinitions,
  form.formData,
  form.portConfigurations,
  form.sources,
  form.isToolDescriptionEditable,
  {
    get: () => drawer.value,
    set: (v: boolean) => {
      drawer.value = v
    },
  },
  emitAny
)

const oauth = useEditSidebarOAuth(componentData)

const hasConfigurationContent = computed(() => componentData.value && form.isToolDescriptionEditable.value)

const getComponentIcon = computed(() => {
  if (componentData.value?.icon != null) return componentData.value.icon
  return isWorker.value ? 'tabler-cpu' : 'tabler-box'
})

const color = computed(() => (isWorker.value ? 'secondary' : 'primary'))
</script>

<template>
  <VDialog
    :model-value="drawer"
    class="edit-dialog"
    width="90vw"
    height="90vh"
    persistent
    @update:model-value="drawer = $event"
  >
    <VCard class="dialog-card">
      <!-- Header -->
      <VCardItem class="dialog-header">
        <VCardTitle>
          <div class="d-flex align-center justify-space-between w-100">
            <div class="d-flex align-center">
              <VAvatar
                size="32"
                :color="isProviderLogo(getComponentIcon) ? undefined : isWorker ? 'secondary' : 'primary'"
                :variant="isProviderLogo(getComponentIcon) ? 'flat' : 'tonal'"
                class="me-3"
              >
                <Icon v-if="isProviderLogo(getComponentIcon)" :icon="getComponentIcon" :width="20" :height="20" />
                <VIcon v-else :icon="getComponentIcon" size="20" />
              </VAvatar>
              <div class="d-flex flex-column">
                <span>{{ `${isReadOnlyMode ? 'View' : 'Edit'} ${isWorker ? 'Worker' : 'Component'}` }}</span>
                <span v-if="isReadOnlyMode" class="text-caption text-warning">
                  <VIcon icon="tabler-lock" size="14" class="me-1" />
                  Read-only mode
                </span>
              </div>
            </div>
            <VBtn icon variant="text" size="small" class="close-btn" @click="drawer = false">
              <VIcon icon="tabler-x" size="20" />
            </VBtn>
          </div>
        </VCardTitle>
      </VCardItem>
      <VDivider />

      <!-- Content -->
      <div class="dialog-content">
        <VForm @submit.prevent="submit.onSubmit">
          <VRow>
            <!-- Left Column: Parameters -->
            <VCol cols="12" :md="hasConfigurationContent ? 6 : 12">
              <div class="text-h6 mb-4">Parameters</div>
              <VCard variant="outlined" class="pa-4">
                <VTextField
                  v-model="form.formData.value.name"
                  label="Label"
                  variant="outlined"
                  :color="color"
                  :readonly="isReadOnlyMode"
                  class="mb-6"
                />

                <!-- Ungrouped Basic Parameters -->
                <EditSidebarParameterField
                  v-for="param in form.groupedParameters.value.ungrouped.basic"
                  :key="param.name"
                  v-model="form.formData.value.parameters[param.name]"
                  :param="param"
                  :component-config="componentConfig.getComponentConfig(param)"
                  :color="color"
                  :json-validation-state="form.jsonValidationState.value[param.name]"
                  @file-update="form.onFileModelUpdate(param.name, $event)"
                  @json-blur="form.handleJsonFieldBlur(param.name)"
                />

                <!-- Non-Advanced Parameter Groups -->
                <VCard
                  v-for="group in form.groupedParameters.value.groups.filter((g: any) => g.hasBasic)"
                  :key="group.group.id"
                  variant="outlined"
                  class="pa-4 mb-6 parameter-group-card"
                >
                  <div
                    class="d-flex align-center mb-4 group-header"
                    role="button"
                    @click="form.groupVisibility.value[group.group.id] = !form.groupVisibility.value[group.group.id]"
                  >
                    <VIcon
                      :icon="form.groupVisibility.value[group.group.id] ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      size="small"
                      class="me-2"
                      :color="color"
                    />
                    <span class="text-subtitle-1" :class="isWorker ? 'text-secondary' : 'text-primary'">
                      {{ group.group.name }}
                    </span>
                  </div>
                  <VExpandTransition>
                    <div v-show="form.groupVisibility.value[group.group.id]">
                      <EditSidebarParameterField
                        v-for="param in group.parameters.filter((p: any) => !p.is_advanced || form.showAdvanced.value)"
                        :key="param.name"
                        v-model="form.formData.value.parameters[param.name]"
                        :param="param"
                        :component-config="componentConfig.getComponentConfig(param)"
                        :color="color"
                        :json-validation-state="form.jsonValidationState.value[param.name]"
                        @file-update="form.onFileModelUpdate(param.name, $event)"
                        @json-blur="form.handleJsonFieldBlur(param.name)"
                      />
                    </div>
                  </VExpandTransition>
                </VCard>

                <!-- Advanced Parameters Toggle -->
                <div v-if="form.hasAdvancedParameters.value">
                  <div
                    class="d-flex align-center mb-6 advanced-toggle"
                    role="button"
                    @click="form.showAdvanced.value = !form.showAdvanced.value"
                  >
                    <VIcon
                      :icon="form.showAdvanced.value ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      size="small"
                      class="me-2"
                      :color="color"
                    />
                    <span class="text-h6" :class="isWorker ? 'text-secondary' : 'text-primary'">
                      Advanced Parameters
                    </span>
                  </div>

                  <VExpandTransition>
                    <div v-show="form.showAdvanced.value">
                      <!-- Ungrouped Advanced Parameters -->
                      <EditSidebarParameterField
                        v-for="param in form.groupedParameters.value.ungrouped.advanced"
                        :key="param.name"
                        v-model="form.formData.value.parameters[param.name]"
                        :param="param"
                        :component-config="componentConfig.getComponentConfig(param)"
                        :color="color"
                        :json-validation-state="form.jsonValidationState.value[param.name]"
                        @file-update="form.onFileModelUpdate(param.name, $event)"
                        @json-blur="form.handleJsonFieldBlur(param.name)"
                      />

                      <!-- Advanced-Only Parameter Groups -->
                      <VCard
                        v-for="group in form.groupedParameters.value.groups.filter(
                          (g: any) => !g.hasBasic && g.hasAdvanced
                        )"
                        :key="`adv-${group.group.id}`"
                        variant="outlined"
                        class="pa-4 mb-6 parameter-group-card"
                      >
                        <div
                          class="d-flex align-center mb-4 group-header"
                          role="button"
                          @click="
                            form.groupVisibility.value[group.group.id] = !form.groupVisibility.value[group.group.id]
                          "
                        >
                          <VIcon
                            :icon="
                              form.groupVisibility.value[group.group.id] ? 'mdi-chevron-down' : 'mdi-chevron-right'
                            "
                            size="small"
                            class="me-2"
                            :color="color"
                          />
                          <span class="text-subtitle-1" :class="isWorker ? 'text-secondary' : 'text-primary'">
                            {{ group.group.name }}
                          </span>
                        </div>
                        <VExpandTransition>
                          <div v-show="form.groupVisibility.value[group.group.id]">
                            <EditSidebarParameterField
                              v-for="param in group.parameters"
                              :key="param.name"
                              v-model="form.formData.value.parameters[param.name]"
                              :param="param"
                              :component-config="componentConfig.getComponentConfig(param)"
                              :color="color"
                              :json-validation-state="form.jsonValidationState.value[param.name]"
                              @file-update="form.onFileModelUpdate(param.name, $event)"
                              @json-blur="form.handleJsonFieldBlur(param.name)"
                            />
                          </div>
                        </VExpandTransition>
                      </VCard>
                    </div>
                  </VExpandTransition>
                </div>
              </VCard>

              <!-- Optional Tools -->
              <EditSidebarOptionalTools
                :optional-subcomponents="submit.optionalSubcomponents.value"
                :enabled-optional-tools="submit.enabledOptionalTools.value"
                :component-definitions="componentDefinitions"
                :color="color"
                :is-read-only-mode="isReadOnlyMode"
                @toggle="submit.handleOptionalToolToggle"
              />

              <!-- Gmail Integration Section -->
              <EditSidebarGmail
                v-if="oauth.isGmailIntegration.value"
                v-model:show-gmail-connect-dialog="oauth.showGmailConnectDialog.value"
                v-model:show-gmail-disconnect-dialog="oauth.showGmailDisconnectDialog.value"
                :is-integration-connected="!!oauth.isIntegrationConnected.value"
                :is-read-only-mode="isReadOnlyMode"
                :is-worker="isWorker"
                :gmail-connecting="oauth.gmailConnecting.value"
                @connect-gmail="oauth.connectGmail"
                @disconnect-gmail="oauth.disconnectGmail"
                @cancel-disconnect="oauth.cancelDisconnectGmail"
              />
            </VCol>

            <!-- Right Column: Configuration -->
            <VCol v-if="hasConfigurationContent" cols="12" md="6">
              <EditSidebarConfigContent
                v-model:tool-description-name="form.formData.value.toolDescription.name"
                v-model:tool-description-description="form.formData.value.toolDescription.description"
                :color="color"
                :is-read-only-mode="isReadOnlyMode"
                :component-definition="componentDefinition"
                :component-data-id="componentData?.id || null"
                :port-configurations="form.portConfigurations.value"
                :upstream-nodes="ports.upstreamNodes.value"
                @update:port-configurations="form.handlePortConfigurationsUpdate"
              />
            </VCol>
          </VRow>
        </VForm>
      </div>

      <!-- Footer -->
      <VDivider />
      <VCardActions class="dialog-footer pa-6">
        <div v-if="componentDefinition" class="text-overline text-disabled" style="font-size: 10px; line-height: 1.2">
          name: {{ componentDefinition.name }}<br />
          ID: {{ componentDefinition.id }}<br />
          <span v-if="componentDefinition.version_tag || componentDefinition.component_version_id">
            Component version: {{ componentDefinition.version_tag || componentDefinition.component_version_id }}
          </span>
        </div>
        <VSpacer />
        <template v-if="isReadOnlyMode">
          <VBtn variant="outlined" :color="color" min-width="120" @click="drawer = false">Close</VBtn>
        </template>
        <template v-else>
          <VBtn variant="outlined" color="error" min-width="120" @click="drawer = false">Cancel</VBtn>
          <VBtn type="submit" :color="color" min-width="120" class="ms-4" @click="submit.onSubmit">Save Changes</VBtn>
        </template>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Project Selection Dialog -->
  <ProjectSelectionDialog
    v-model="componentConfig.showProjectSelectionDialog.value"
    :projects="projects"
    :agents="agents"
    @select="componentConfig.handleProjectSelection"
  />

  <!-- Save Error Snackbar -->
  <VSnackbar v-model="submit.showSaveError.value" color="error" :timeout="5000" location="bottom">
    {{ submit.saveErrorMessage.value }}
    <template #actions>
      <VBtn color="white" variant="text" @click="submit.showSaveError.value = false">Close</VBtn>
    </template>
  </VSnackbar>
</template>

<style lang="scss" scoped>
.edit-dialog {
  .dialog-card {
    display: flex;
    overflow: hidden;
    flex-direction: column;
    border-radius: 12px;
    block-size: 90vh;
  }

  .dialog-header {
    flex: 0 0 auto;
  }

  .close-btn {
    margin-block: -4px;
    margin-inline: 0 -4px;
    min-block-size: 32px;
    min-inline-size: 32px;
  }

  .dialog-content {
    flex: 1 1 auto;
    padding: 16px;
    overflow-y: auto;

    &::-webkit-scrollbar {
      inline-size: 8px;
    }

    &::-webkit-scrollbar-track {
      border-radius: 4px;
      background: rgba(var(--v-border-color), 0.1);
    }

    &::-webkit-scrollbar-thumb {
      border-radius: 4px;
      background: rgba(var(--v-border-color), 0.3);

      &:hover {
        background: rgba(var(--v-border-color), 0.5);
      }
    }
  }

  .dialog-footer {
    flex: 0 0 auto;
    background: rgb(var(--v-theme-surface));
  }

  .advanced-toggle {
    cursor: pointer;
    user-select: none;

    &:hover {
      opacity: 0.8;
    }
  }
}

.edit-dialog .v-textarea textarea {
  min-block-size: 100px;
  resize: vertical;
}

.group-header {
  cursor: pointer;
  user-select: none;

  &:hover {
    opacity: 0.8;
  }
}

.v-field--readonly .v-field__input {
  color: rgb(var(--v-theme-on-surface)) !important;
  opacity: 1 !important;
}

.v-switch--disabled {
  opacity: 0.8 !important;
}
</style>
