<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import {
  useCreateWidgetMutation,
  useDeleteWidgetMutation,
  useRegenerateWidgetKeyMutation,
  useUpdateWidgetMutation,
  useWidgetByProjectQuery,
} from '@/composables/queries/useWidgetQuery'
import { useProjectQuery } from '@/composables/queries/useProjectsQuery'
import ChatPreview from '@/components/integration/ChatPreview.vue'
import type { UpdateWidgetData, WidgetConfig, WidgetTheme } from '@/api'

interface Props {
  projectId?: string
  projectName?: string
  organizationId?: string
}

const props = defineProps<Props>()

// Get project data to access graph_runners for the chat preview
const projectIdRef = computed(() => props.projectId)
const { data: project } = useProjectQuery(projectIdRef)

// Get production graph runner ID for authenticated chat
const productionGraphRunnerId = computed(() => {
  if (!project.value?.graph_runners) return undefined
  const prodRunner = project.value.graph_runners.find(gr => gr.env === 'production')
  return prodRunner?.graph_runner_id
})

// Query and mutations
const { data: widget, isLoading, refetch } = useWidgetByProjectQuery(projectIdRef)
const createWidgetMutation = useCreateWidgetMutation()
const updateWidgetMutation = useUpdateWidgetMutation()
const regenerateKeyMutation = useRegenerateWidgetKeyMutation()
const deleteWidgetMutation = useDeleteWidgetMutation()

// Local state for form
const localWidget = ref<{
  name: string
  is_enabled: boolean
  config: WidgetConfig
} | null>(null)

const isSaving = ref(false)
const showCopiedMessage = ref(false)
const showRegenerateConfirm = ref(false)
const showDeleteConfirm = ref(false)
const showPublicEndpointConfirm = ref(false)
const snackbar = ref({ show: false, message: '', color: 'success' })

// Accordion panel state (only one open at a time)
const openPanel = ref<number | undefined>(0)

// Right side tab state
const rightTab = ref('preview')

// Default theme
const defaultTheme: WidgetTheme = {
  primary_color: '#6366F1',
  secondary_color: '#4F46E5',
  background_color: '#FFFFFF',
  text_color: '#1F2937',
  border_radius: 12,
  font_family: 'Inter, system-ui, sans-serif',
  logo_url: null,
}

const defaultConfig: WidgetConfig = {
  theme: defaultTheme,
  header_message: null,
  first_messages: [],
  suggestions: [],
  placeholder_text: 'Type a message...',
  powered_by_visible: true,
  rate_limit_config: 10,
  rate_limit_chat: 5,
  allowed_origins: [],
}

// Watch widget data and sync to local state - only on first load
const hasInitialized = ref(false)

watch(
  widget,
  newWidget => {
    if (newWidget && !hasInitialized.value) {
      localWidget.value = {
        name: newWidget.name,
        is_enabled: newWidget.is_enabled,
        config: {
          ...defaultConfig,
          ...newWidget.config,
          theme: { ...defaultTheme, ...newWidget.config?.theme },
        },
      }
      hasInitialized.value = true
    }
  },
  { immediate: true }
)

// First messages as text (separated by blank lines, allows multiline within each message)
const firstMessagesText = computed({
  get: () => localWidget.value?.config.first_messages.join('\n\n---\n\n') || '',
  set: (value: string) => {
    if (localWidget.value) {
      // Split by the separator (---) to get individual messages
      localWidget.value.config.first_messages = value
        .split(/\n---\n/)
        .map(m => m.trim())
        .filter(m => m)
    }
  },
})

const suggestionsText = computed({
  get: () => localWidget.value?.config.suggestions.join('\n') || '',
  set: (value: string) => {
    if (localWidget.value) {
      localWidget.value.config.suggestions = value.split('\n').filter(s => s.trim())
    }
  },
})

const allowedOriginsText = computed({
  get: () => localWidget.value?.config.allowed_origins?.join('\n') || '',
  set: (value: string) => {
    if (localWidget.value) {
      localWidget.value.config.allowed_origins = value.split('\n').filter(o => o.trim())
    }
  },
})

// Embed code
const widgetUrl = import.meta.env.VITE_CHAT_WIDGET_URL || 'https://widget.draftnrun.com'

const embedCode = computed(() => {
  if (!widget.value?.widget_key) return ''
  return `<script src="${widgetUrl}/loader.js"
        data-widget-key="${widget.value.widget_key}"><\/script>`
})

// Open public endpoint confirmation dialog
function openPublicEndpointDialog() {
  showPublicEndpointConfirm.value = true
}

// Create widget after confirmation
async function handleCreateWidget() {
  if (!props.organizationId || !props.projectId) return

  showPublicEndpointConfirm.value = false
  try {
    await createWidgetMutation.mutateAsync({
      organizationId: props.organizationId,
      data: {
        project_id: props.projectId,
        name: props.projectName || 'Chat Widget',
        is_enabled: true,
        config: defaultConfig,
      },
    })
    await refetch()
  } catch (error: unknown) {
    logger.warn('Failed to create widget', { error })
    snackbar.value = { show: true, message: 'Failed to create widget', color: 'error' }
  }
}

// Save widget changes
async function handleSaveWidget() {
  if (!widget.value?.id || !localWidget.value) return

  isSaving.value = true
  try {
    const data: UpdateWidgetData = {
      name: localWidget.value.name,
      is_enabled: localWidget.value.is_enabled,
      config: localWidget.value.config,
    }

    await updateWidgetMutation.mutateAsync({
      widgetId: widget.value.id,
      data,
    })
    snackbar.value = { show: true, message: 'Widget saved successfully', color: 'success' }
  } catch (error: unknown) {
    logger.warn('Failed to save widget', { error })
    snackbar.value = { show: true, message: 'Failed to save widget', color: 'error' }
  } finally {
    isSaving.value = false
  }
}

// Copy embed code
function copyEmbedCode() {
  navigator.clipboard.writeText(embedCode.value)
  showCopiedMessage.value = true
  setTimeout(() => {
    showCopiedMessage.value = false
  }, 2000)
}

// Regenerate widget key
async function handleRegenerateKey() {
  if (!widget.value?.id) return

  try {
    await regenerateKeyMutation.mutateAsync(widget.value.id)
    showRegenerateConfirm.value = false
    await refetch()
    snackbar.value = { show: true, message: 'Widget key regenerated', color: 'success' }
  } catch (error: unknown) {
    logger.warn('Failed to regenerate widget key', { error })
    snackbar.value = { show: true, message: 'Failed to regenerate widget key', color: 'error' }
  }
}

// Delete widget
async function handleDeleteWidget() {
  if (!widget.value?.id) return

  try {
    await deleteWidgetMutation.mutateAsync(widget.value.id)
    showDeleteConfirm.value = false
    hasInitialized.value = false
    localWidget.value = null
    snackbar.value = { show: true, message: 'Widget deleted', color: 'success' }
  } catch (error: unknown) {
    logger.warn('Failed to delete widget', { error })
    snackbar.value = { show: true, message: 'Failed to delete widget', color: 'error' }
  }
}

// Reset chat preview
const previewKey = ref(0)
function resetPreview() {
  previewKey.value++
}
</script>

<template>
  <div class="config-wrapper">
    <!-- Loading State -->
    <VCard v-if="isLoading" class="pa-4">
      <VSkeletonLoader type="article" />
    </VCard>

    <!-- No Widget Yet -->
    <VCard v-else-if="!widget" class="pa-6 text-center">
      <VCardText>
        <VIcon icon="tabler-message-circle-off" size="64" class="mb-4 text-disabled" />
        <h3 class="text-h5 mb-2">No Chat Widget Configured</h3>
        <p class="text-body-1 text-medium-emphasis mb-4">
          Create a chat widget to allow users to interact with this project through an embeddable chat interface.
        </p>
        <VBtn
          color="primary"
          prepend-icon="tabler-plus"
          :loading="createWidgetMutation.isPending.value"
          @click="openPublicEndpointDialog"
        >
          Create Chat Widget
        </VBtn>
      </VCardText>
    </VCard>

    <!-- Widget Configuration -->
    <div v-else-if="localWidget" class="config-container">
      <!-- Left: Configuration Form with Accordion -->
      <div class="left-panel">
        <VCard class="config-card" flat>
          <VCardTitle class="d-flex align-center justify-space-between config-header">
            <span class="d-flex align-center">
              <VIcon icon="tabler-settings" class="me-2" />
              Widget Configuration
            </span>
            <VChip v-if="!localWidget.is_enabled" color="warning" size="small"> Disabled </VChip>
          </VCardTitle>

          <div class="accordion-container">
            <VExpansionPanels v-model="openPanel" variant="accordion">
              <!-- Basic Settings -->
              <VExpansionPanel value="0">
                <VExpansionPanelTitle>
                  <VIcon icon="tabler-adjustments" class="me-2" size="20" />
                  Basic Settings
                </VExpansionPanelTitle>
                <VExpansionPanelText>
                  <VTextField
                    v-model="localWidget.name"
                    label="Widget Name"
                    placeholder="e.g., Customer Support Chat"
                    density="compact"
                  />
                </VExpansionPanelText>
              </VExpansionPanel>

              <!-- Theme Settings -->
              <VExpansionPanel value="1">
                <VExpansionPanelTitle>
                  <VIcon icon="tabler-palette" class="me-2" size="20" />
                  Theme
                </VExpansionPanelTitle>
                <VExpansionPanelText>
                  <div class="mb-4">
                    <label class="text-body-2 mb-2 d-block">Primary Color</label>
                    <VMenu :close-on-content-click="false" location="bottom start">
                      <template #activator="{ props }">
                        <div class="color-picker-trigger" v-bind="props">
                          <div
                            class="color-swatch"
                            :style="{ backgroundColor: localWidget.config.theme.primary_color }"
                          />
                          <span class="color-value">{{ localWidget.config.theme.primary_color }}</span>
                        </div>
                      </template>
                      <VColorPicker
                        v-model="localWidget.config.theme.primary_color"
                        mode="hex"
                        :modes="['hex']"
                        elevation="0"
                      />
                    </VMenu>
                  </div>
                  <VTextField
                    v-model="localWidget.config.theme.logo_url"
                    label="Logo URL (optional)"
                    placeholder="https://example.com/logo.png"
                    hint="Image displayed in the chat header"
                    persistent-hint
                    clearable
                    density="compact"
                  />
                </VExpansionPanelText>
              </VExpansionPanel>

              <!-- Content Settings -->
              <VExpansionPanel value="2">
                <VExpansionPanelTitle>
                  <VIcon icon="tabler-message-2" class="me-2" size="20" />
                  Content
                </VExpansionPanelTitle>
                <VExpansionPanelText>
                  <VTextarea
                    v-model="localWidget.config.header_message"
                    label="Header Message (optional)"
                    placeholder="By using this chat, you agree to our Terms of Service."
                    rows="2"
                    hint="Fixed message shown at the top of the chat. Useful for terms & conditions or disclaimers."
                    persistent-hint
                    clearable
                    class="mb-4"
                    density="compact"
                  />

                  <VTextarea
                    v-model="firstMessagesText"
                    label="Welcome Messages"
                    placeholder="Hello! How can I help you today?&#10;&#10;---&#10;&#10;I'm here to answer your questions."
                    rows="4"
                    hint="Separate multiple messages with --- on its own line. Messages can be multiline."
                    persistent-hint
                    class="mb-3"
                    density="compact"
                  />

                  <VTextarea
                    v-model="suggestionsText"
                    label="Suggested Questions (one per line)"
                    placeholder="What can you do?&#10;Tell me about your features"
                    rows="2"
                    class="mb-3"
                    density="compact"
                  />

                  <VTextField
                    v-model="localWidget.config.placeholder_text"
                    label="Input Placeholder"
                    placeholder="e.g., Ask me anything..."
                    class="mb-3"
                    density="compact"
                  />

                  <div class="d-flex align-center gap-2">
                    <VSwitch
                      v-model="localWidget.config.powered_by_visible"
                      label="Show 'Powered by Draft'n run'"
                      color="primary"
                      hide-details
                      density="compact"
                      disabled
                    />
                    <VChip color="primary" variant="outlined" size="small" href="mailto:sales@draftnrun.com" tag="a">
                      Contact Sales
                    </VChip>
                  </div>
                </VExpansionPanelText>
              </VExpansionPanel>

              <!-- Security Settings -->
              <VExpansionPanel value="3">
                <VExpansionPanelTitle>
                  <VIcon icon="tabler-shield" class="me-2" size="20" />
                  Security (Advanced)
                </VExpansionPanelTitle>
                <VExpansionPanelText>
                  <VTextField
                    v-model.number="localWidget.config.rate_limit_config"
                    label="Config Rate Limit (per minute)"
                    type="number"
                    min="1"
                    max="100"
                    placeholder="e.g., 10"
                    hint="Max requests per minute for loading widget configuration"
                    persistent-hint
                    class="mb-4"
                    density="compact"
                  />
                  <VTextField
                    v-model.number="localWidget.config.rate_limit_chat"
                    label="Chat Rate Limit (per minute)"
                    type="number"
                    min="1"
                    max="60"
                    placeholder="e.g., 5"
                    hint="Max chat messages per minute per user"
                    persistent-hint
                    class="mb-4"
                    density="compact"
                  />
                  <VTextarea
                    v-model="allowedOriginsText"
                    label="Allowed Origins (one per line)"
                    placeholder="example.com&#10;*.mysite.com&#10;app.company.com"
                    rows="3"
                    hint="Leave empty to allow all origins. Use *.domain.com for wildcard subdomains."
                    persistent-hint
                    density="compact"
                  />
                </VExpansionPanelText>
              </VExpansionPanel>
            </VExpansionPanels>
          </div>

          <VCardActions class="config-actions justify-space-between">
            <VBtn variant="text" color="error" prepend-icon="tabler-trash" @click="showDeleteConfirm = true">
              Delete Widget
            </VBtn>
            <div class="d-flex gap-2">
              <VBtn variant="text" @click="resetPreview"> Reset Preview </VBtn>
              <VBtn color="primary" :loading="isSaving" @click="handleSaveWidget"> Save Changes </VBtn>
            </div>
          </VCardActions>
        </VCard>
      </div>

      <!-- Right: Preview / Embed Code Toggle -->
      <div class="right-panel">
        <VCard class="preview-card" flat>
          <VTabs v-model="rightTab" class="preview-tabs">
            <VTab value="preview">
              <VIcon icon="tabler-eye" class="me-2" size="18" />
              Preview
            </VTab>
            <VTab value="embed">
              <VIcon icon="tabler-code" class="me-2" size="18" />
              Embed Code
            </VTab>
          </VTabs>

          <VWindow v-model="rightTab" class="preview-window">
            <VWindowItem value="preview" class="preview-window-item">
              <div class="preview-container">
                <ChatPreview
                  :key="previewKey"
                  :project-id="projectId"
                  :graph-runner-id="productionGraphRunnerId"
                  :config="{ ...localWidget.config, name: localWidget.name }"
                />
              </div>
            </VWindowItem>

            <VWindowItem value="embed" class="preview-window-item">
              <div class="embed-container">
                <h4 class="text-h6 mb-3">Embed Code</h4>
                <p class="text-body-2 text-medium-emphasis mb-3">
                  Copy and paste this code into your website to display the chat widget.
                </p>
                <VTextarea :model-value="embedCode" readonly rows="4" class="mb-3 font-monospace" />
                <div class="d-flex gap-2">
                  <VBtn variant="outlined" prepend-icon="tabler-copy" @click="copyEmbedCode">
                    {{ showCopiedMessage ? 'Copied!' : 'Copy Code' }}
                  </VBtn>
                  <VBtn
                    variant="text"
                    prepend-icon="tabler-refresh"
                    color="warning"
                    @click="showRegenerateConfirm = true"
                  >
                    Regenerate Key
                  </VBtn>
                </div>
              </div>
            </VWindowItem>
          </VWindow>
        </VCard>
      </div>
    </div>

    <!-- Regenerate Key Confirmation Dialog -->
    <VDialog v-model="showRegenerateConfirm" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6"> Regenerate Widget Key? </VCardTitle>
        <VCardText>
          This will invalidate all existing embeds. Any websites using the current embed code will need to be updated
          with the new code.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showRegenerateConfirm = false"> Cancel </VBtn>
          <VBtn color="warning" :loading="regenerateKeyMutation.isPending.value" @click="handleRegenerateKey">
            Regenerate
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete Widget Confirmation Dialog -->
    <VDialog v-model="showDeleteConfirm" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6"> Delete Widget? </VCardTitle>
        <VCardText>
          This will permanently delete the widget. Any websites using the embed code will no longer work.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showDeleteConfirm = false"> Cancel </VBtn>
          <VBtn color="error" :loading="deleteWidgetMutation.isPending.value" @click="handleDeleteWidget">
            Delete
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Public Endpoint Confirmation Dialog -->
    <VDialog v-model="showPublicEndpointConfirm" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6"> Make Endpoint Public? </VCardTitle>
        <VCardText>
          This action will make your endpoint publicly accessible. Anyone with the embed code snippet will be able to
          interact with it.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showPublicEndpointConfirm = false"> Cancel </VBtn>
          <VBtn color="primary" :loading="createWidgetMutation.isPending.value" @click="handleCreateWidget">
            Publish
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Snackbar for feedback -->
    <VSnackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.message }}
    </VSnackbar>
  </div>
</template>

<style scoped>
.config-wrapper {
  height: calc(100vh - 250px);
  display: flex;
  flex-direction: column;
}

.config-container {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
  gap: 16px;
}

.left-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.config-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.config-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.accordion-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.config-actions {
  flex-shrink: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 12px 16px;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.preview-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.preview-tabs {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.preview-window {
  flex: 1;
  overflow: hidden;
}

.preview-window-item {
  height: 100%;
}

.preview-container {
  height: 100%;
  overflow: hidden;
}

.embed-container {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}

.font-monospace {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
}

.color-picker-trigger {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.color-picker-trigger:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}

.color-swatch {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.color-value {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  text-transform: uppercase;
}
</style>
