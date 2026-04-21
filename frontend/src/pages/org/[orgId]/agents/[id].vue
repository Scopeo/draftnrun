<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { scopeoApi } from '@/api'
import AgentFloatingActions from '@/components/agents/AgentFloatingActions.vue'
import AgentStudioUnified from '@/components/agents/AgentStudioUnified.vue'
import CronJobModal from '@/components/cron/CronJobModal.vue'
import IntegrationTab from '@/components/integration/IntegrationTab.vue'
import InlineIconEditor from '@/components/projects/InlineIconEditor.vue'
import EditEntityModal from '@/components/shared/EditEntityModal.vue'
import ModificationHistoryDialog from '@/components/shared/ModificationHistoryDialog.vue'
import SharedTabContent from '@/components/shared/SharedTabContent.vue'
import VersionSelectorContainer from '@/components/shared/VersionSelectorContainer.vue'
import {
  type Agent,
  fetchAgentDetail,
  useAgentQuery,
  useAgentsQuery,
  useCurrentAgent,
  useUpdateAgentMutation,
} from '@/composables/queries/useAgentsQuery'
import { useComponentDefinitionsQuery } from '@/composables/queries/useComponentDefinitionsQuery'
import { useOrgTagsQuery } from '@/composables/queries/useProjectsQuery'
import { clearAllChatStates } from '@/composables/usePlaygroundChat'
import { useSaveVersion } from '@/composables/useSaveVersion'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { PANEL_SIZES } from '@/config/panelSizes'
import { findDraftGraphRunner } from '@/utils/agentUtils'
import { logger } from '@/utils/logger'
import { logComponentMount, logComponentUnmount } from '@/utils/queryLogger'

const route = useRoute('org-org-id-agents-id')
const router = useRouter()

// Set meta on current route for navigation active state
onMounted(() => {
  if (route.meta) {
    route.meta.navActiveLink = 'agents'
  }
})

const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
const { data: orgTags } = useOrgTagsQuery(selectedOrgId)

const {
  components: componentDefinitions,
  categories,
  isLoading: isLoadingComponentDefs,
} = useComponentDefinitionsQuery(selectedOrgId)

// Component lifecycle logging
onMounted(() => {
  logComponentMount('AgentsIdPage', [['component-definitions', selectedOrgId.value]])
})

onUnmounted(() => {
  logComponentUnmount('AgentsIdPage')
})

// AI Agent component definition
const aiAgentComponent = computed(() => {
  if (!componentDefinitions.value) return null

  return (
    componentDefinitions.value.find(component => {
      const name = component.name?.toLowerCase() || ''
      return (
        name.includes('ai agent') ||
        name.includes('ai-agent') ||
        name === 'agent' ||
        name.includes('chat agent') ||
        name.includes('assistant')
      )
    }) || null
  )
})

// Tab management
const activeTab = ref('studio')

// Edit modal state
const showEditModal = ref(false)

// Cron modal state
const showCronModal = ref(false)
const showCronJobCreated = ref(false)

const handleCronJobCreated = () => {
  showCronJobCreated.value = true
}

// Track panel states - playground always visible, only observability toggles
const observabilityOpen = ref(false)
const playgroundWidth = ref<number>(PANEL_SIZES.DEFAULT_WIDTH)

// Check if playground should be visible (hidden on integration and qa tabs)
const isPlaygroundVisible = computed(() => activeTab.value !== 'integration' && activeTab.value !== 'qa')

// Calculate available space - main window shifts when panels open
const availableSpace = computed(() => {
  // Only account for playground width if it's visible
  const chatPanelWidth = isPlaygroundVisible.value ? playgroundWidth.value + 16 : 0

  return {
    width: chatPanelWidth > 0 ? `calc(100% - ${chatPanelWidth}px)` : '100%',
    marginRight: '0px',
    marginLeft: '0px',
    marginTop: '0px',
    marginBottom: '0px',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
  }
})

// Handle playground width change from floating actions
const handlePlaygroundWidthChanged = (width: number) => {
  playgroundWidth.value = width
}

// Handle window state changes - only observability toggles
const handleWindowsChanged = (observability: boolean, _expandedMode?: boolean, _widthPx?: number) => {
  observabilityOpen.value = observability
}

// Use TanStack Query for agent data
const { currentGraphRunner, setCurrentGraphRunner } = useCurrentAgent()
const updateAgentMutation = useUpdateAgentMutation()
const { data: agentsList, refetch: refetchAgents } = useAgentsQuery(selectedOrgId)

// Shared save version composable (same as StudioFlow)
const projectId = computed(() => route.params.id as string)

// Derive version ID: prefer explicit selection, fall back to draft runner from agents list
const effectiveVersionId = computed(() => {
  if (currentGraphRunner.value?.graph_runner_id) return currentGraphRunner.value.graph_runner_id
  const agentInfo = agentsList.value?.find(a => a.id === projectId.value)
  return agentInfo?.graph_runners ? findDraftGraphRunner(agentInfo.graph_runners)?.graph_runner_id : undefined
})

const { data: agentData } = useAgentQuery(projectId, effectiveVersionId)

const { saveVersion: saveVersionAction } = useSaveVersion({
  projectId,
  currentGraphRunner,
  onAfterSave: async () => {
    await refetchAgents()

    if (agent.value) {
      const agentInfo = agentsList.value?.find(a => a.id === agent.value!.id)
      if (agentInfo?.graph_runners) {
        const newDraftRunner = findDraftGraphRunner(agentInfo.graph_runners)
        if (newDraftRunner) {
          setCurrentGraphRunner(newDraftRunner)
        }
      }
    }
  },
})

const manualSave = async (agentId: string, data: any): Promise<boolean> => {
  const versionId = currentGraphRunner.value?.graph_runner_id
  if (!versionId) {
    logger.error('No version ID for save')
    return false
  }

  await updateAgentMutation.mutateAsync({
    agentId,
    versionId,
    data,
    cachedAgent: agent.value,
  })
  return true
}

// Local mutable agent state, synced from query
const agent = ref<Agent | null>(null)
const isAgentLoading = computed(() => !agent.value)
const skipNextQuerySync = ref(false)

// Sync query data to local state, merging list-level fields (icon, graph_runners).
// Skipped once after a manual save to avoid overwriting local edits with a stale refetch.
watch(
  agentData,
  newData => {
    if (!newData) return
    if (skipNextQuerySync.value) {
      skipNextQuerySync.value = false
      return
    }
    const merged = { ...newData }
    const agentInfo = agentsList.value?.find((a: any) => a.id === merged.id)
    if (agentInfo) {
      if (!merged.graph_runners?.length && agentInfo.graph_runners?.length) {
        merged.graph_runners = agentInfo.graph_runners
      }
      merged.icon ??= (agentInfo as any).icon
      merged.icon_color ??= (agentInfo as any).icon_color
    }
    agent.value = merged

    if (!currentGraphRunner.value && merged.version_id) {
      const runner = merged.graph_runners?.find(r => r.graph_runner_id === merged.version_id)
      if (runner) setCurrentGraphRunner(runner)
    }
  },
  { immediate: true }
)

// Clear stale data when navigating to a different agent
watch(
  () => route.params.id,
  () => {
    agent.value = null
    clearAllChatStates()
  }
)

const saveAgent = async (create_snapshot = false) => {
  if (!agent.value) return

  try {
    if (create_snapshot) {
      await saveVersionAction()
      return
    }

    const saveData: any = {
      name: agent.value.name,
      description: agent.value.description,
      initial_prompt: agent.value.parameters?.find(p => p.name === 'initial_prompt')?.value || '',
      model_config: {
        model: agent.value.model_config?.model || 'gpt-4',
        temperature: agent.value.model_config?.temperature || 0.7,
        max_tokens: agent.value.model_config?.max_tokens || 2000,
      },
      parameters: agent.value.parameters,
      toolParameters: agent.value.toolParameters,
    }

    saveData.tools = agent.value.tools || []
    skipNextQuerySync.value = true

    const success = await manualSave(agent.value.id, saveData)

    if (success) {
      const versionId = currentGraphRunner.value?.graph_runner_id || agent.value.version_id
      if (versionId) {
        const refreshedAgent = await fetchAgentDetail(agent.value.id, versionId)
        if (refreshedAgent) {
          agent.value = {
            ...agent.value,
            tools: refreshedAgent.tools,
            toolInstanceIds: refreshedAgent.toolInstanceIds,
            toolParameters: refreshedAgent.toolParameters,
            toolSchemas: refreshedAgent.toolSchemas,
            last_edited_time: refreshedAgent.last_edited_time,
            last_edited_user_id: refreshedAgent.last_edited_user_id,
            last_edited_user_email: refreshedAgent.last_edited_user_email,
          }
        }
      }
    }
  } catch (error) {
    logger.error('Error saving agent', { error })
    throw error
  }
}

// Watch for both agent and component to initialize parameters
watch(
  [() => agent.value, () => aiAgentComponent.value],
  ([newAgent, newComponent]) => {
    if (newAgent && newComponent && (!(newAgent as any).parameters || (newAgent as any).parameters.length === 0)) {
      const graphRunners = newAgent.graph_runners

      if ((newAgent as any).model_parameters && (newAgent as any).model_parameters.length > 0) {
        ;(newAgent as any).parameters = (newAgent as any).model_parameters
      } else {
        ;(newAgent as any).parameters = (newComponent as any).parameters.map((componentParam: any) => ({
          ...componentParam,
          value:
            componentParam.name === 'completion_model'
              ? newAgent.model_config?.model?.includes(':')
                ? newAgent.model_config.model
                : `openai:${newAgent.model_config?.model || componentParam.default}`
              : componentParam.name === 'default_temperature'
                ? newAgent.model_config?.temperature || componentParam.default
                : componentParam.name === 'max_tokens'
                  ? newAgent.model_config?.max_tokens || componentParam.default
                  : componentParam.name === 'initial_prompt'
                    ? newAgent.system_prompt || componentParam.default
                    : componentParam.default,
        }))
      }

      if (graphRunners) {
        newAgent.graph_runners = graphRunners
      }
    }
  },
  { immediate: true, deep: true }
)

// Watch for organization changes - navigate to agents list in new org
watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/agents`)
  }
})

// Save agent name/description using the correct API endpoint
const saveAgentNameAndDescription = async (
  agentId: string,
  data: { name: string; description: string; tags?: string[] }
) => {
  if (!agent.value) return

  const updatePayload: Record<string, any> = {
    project_name: data.name,
    description: data.description,
  }
  if (data.tags !== undefined) {
    updatePayload.tags = data.tags
  }

  await scopeoApi.projects.updateProject(agentId, updatePayload)
}

const handleAgentUpdate = (data: { name: string; description: string; tags: string[] }) => {
  if (agent.value) {
    agent.value = { ...agent.value, name: data.name, description: data.description }
  }
}

const handleAgentParameterChange = ({ name, value }: { name: string; value: any }) => {
  if (!agent.value) return
  if (!agent.value.parameters) agent.value.parameters = []

  const idx = agent.value.parameters.findIndex(p => p.name === name)
  if (idx !== -1) {
    agent.value.parameters[idx] = { ...agent.value.parameters[idx], value }
  } else {
    agent.value.parameters.push({ name, type: 'string', value, nullable: true, default: null })
  }
}

const handleIconUpdated = (data: { icon: string; iconColor: string }) => {
  if (agent.value) {
    agent.value = { ...agent.value, icon: data.icon, icon_color: data.iconColor }
  }
}

const handleUpdateGraphRunners = (
  updatedGraphRunners: Array<{
    graph_runner_id: string
    env: string | null
    tag_name: string | null
  }>
) => {
  if (agent.value) {
    agent.value.graph_runners = updatedGraphRunners
  }
}

// Tab configuration
const tabs = computed(() => [
  {
    title: 'Studio',
    value: 'studio',
    icon: 'tabler-wand',
  },
  {
    title: 'QA',
    value: 'qa',
    icon: 'tabler-test-pipe',
  },
  {
    title: 'Integration',
    value: 'integration',
    icon: 'tabler-plug',
  },
])

const showVersionSelector = computed(() => {
  return agent.value && agent.value.graph_runners && agent.value.graph_runners.length > 0
})

// Computed: Show loading state if agent or component definitions are loading
// This prevents studio from rendering with incomplete data
const isStudioReady = computed(() => {
  return !isAgentLoading.value && !isLoadingComponentDefs.value && !!agent.value && !!componentDefinitions.value
})

// History dialog computed values
const historyProjectId = computed(() => agent.value?.id)
const historyGraphRunnerId = computed(() => currentGraphRunner.value?.graph_runner_id || agent.value?.version_id)

definePage({
  meta: {
    action: 'read',
    subject: 'Agent',
    layoutWrapperClasses: 'layout-content-height-fixed layout-footer-hidden',
    pageContentContainerClass: 'h-100',
  },
})
</script>

<template>
  <AppPage width="editor">
    <div class="agent-container" :class="{ 'observability-open': observabilityOpen }" :style="availableSpace">
      <!-- Show skeleton loader while agent or component definitions load -->
      <template v-if="!isStudioReady">
        <VCard class="mb-6">
          <VCardText>
            <VSkeletonLoader type="text" class="text-h4" width="200px" />
          </VCardText>
        </VCard>

        <VCard>
          <VCardText>
            <VSkeletonLoader type="text" class="mb-4" />
            <VSkeletonLoader type="text" class="mb-4" />
            <VSkeletonLoader type="text" />
          </VCardText>
        </VCard>
      </template>

      <!-- Show actual content once all data is loaded -->
      <template v-else>
        <!-- Agent Header with Tabs -->
        <VCard class="mb-2 tab-header">
          <div v-if="agent" class="d-flex align-center gap-4 pa-3">
            <div class="d-flex align-center flex-wrap gap-4 header-left-group">
              <div class="d-flex align-center gap-3">
                <InlineIconEditor
                  :project-id="(agent as any).project_id || agent.id"
                  :current-icon="agent.icon"
                  :current-color="agent.icon_color"
                  entity-type="agent"
                  @updated="handleIconUpdated"
                />
                <span class="text-h5">{{ agent.name }}</span>
                <VBtn icon variant="text" size="small" @click="showEditModal = true">
                  <VIcon icon="tabler-edit" size="18" />
                </VBtn>
              </div>
              <div v-if="showVersionSelector" class="version-info-group">
                <VersionSelectorContainer
                  :entity="{ id: agent.id, name: agent.name, graph_runners: agent.graph_runners || [] }"
                  entity-type="agent"
                  @update-graph-runners="handleUpdateGraphRunners"
                />
                <ModificationHistoryDialog
                  v-if="agent"
                  :project-id="historyProjectId"
                  :graph-runner-id="historyGraphRunnerId"
                  :org-id="selectedOrgId"
                  :last-edited-time="agent.last_edited_time"
                  :last-edited-user-id="agent.last_edited_user_id"
                  :last-edited-user-email="agent.last_edited_user_email"
                />
              </div>
              <VChip v-if="agent?.is_template" size="small" color="secondary" variant="tonal">
                <VIcon icon="tabler-template" size="16" class="me-1" />
                Template
              </VChip>
            </div>

            <VTabs v-model="activeTab" class="v-tabs-pill" fixed-tabs>
              <VTab v-for="tab in tabs" :key="tab.value" :value="tab.value">
                <VIcon :icon="tab.icon" size="18" class="me-2" />
                {{ tab.title }}
              </VTab>
            </VTabs>
          </div>
        </VCard>

        <VWindow v-model="activeTab">
          <VWindowItem v-for="tab in tabs" :key="tab.value" :value="tab.value">
            <VCard v-if="tab.value === 'studio'" class="tab-card">
              <VCardText class="tab-card-content">
                <AgentStudioUnified
                  :ai-agent-component="aiAgentComponent"
                  :component-definitions="componentDefinitions"
                  :categories="categories"
                  :agent="agent"
                  :agent-project-id="route.params.id as string"
                  :on-save="saveAgent"
                  :is-loading="isAgentLoading"
                  @open-cron-modal="showCronModal = true"
                  @parameter-change="handleAgentParameterChange"
                />
              </VCardText>
            </VCard>

            <VCard v-else-if="tab.value === 'integration' && agent" class="tab-card">
              <VCardText class="tab-card-content">
                <IntegrationTab :agent-id="agent.id" :agent-name="agent.name" :organization-id="selectedOrgId" />
              </VCardText>
            </VCard>

            <SharedTabContent
              v-else-if="tab.value === 'qa' && agent"
              :tab-value="tab.value"
              :project-id="agent.id"
              :graph-runners="agent.graph_runners || []"
            />
          </VWindowItem>
        </VWindow>
      </template>

      <!-- Floating Actions - hidden on Integration and QA tabs -->
      <AgentFloatingActions
        v-if="agent && activeTab !== 'integration' && activeTab !== 'qa'"
        :agent-id="agent.id"
        :project-id="(agent as any).project_id || agent.id"
        @windows-changed="handleWindowsChanged"
        @width-changed="handlePlaygroundWidthChanged"
      />

      <!-- Edit Agent Modal -->
      <EditEntityModal
        v-if="agent"
        v-model="showEditModal"
        :entity-id="(agent as any).project_id || agent.id"
        :entity-name="agent.name"
        :entity-description="agent.description"
        :entity-tags="agent.tags || []"
        :available-tags="orgTags || []"
        entity-type="agent"
        :save-function="saveAgentNameAndDescription"
        @updated="handleAgentUpdate"
      />

      <!-- Cron Job Modal -->
      <CronJobModal
        v-if="agent"
        v-model:is-dialog-visible="showCronModal"
        :project-id="agent.id"
        @created="handleCronJobCreated"
      />

      <!-- Cron job created success notification -->
      <VSnackbar v-model="showCronJobCreated" :timeout="3000" color="success" location="bottom">
        <VIcon icon="tabler-check" class="me-2" />
        Cron job created successfully
      </VSnackbar>
    </div>
  </AppPage>
</template>

<style lang="scss" scoped>
.agent-container {
  display: flex;
  overflow: hidden;
  flex-direction: column;
  border-radius: 12px;
  block-size: 100%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-window) {
    overflow: hidden;
    flex: 1;

    .v-window__container {
      block-size: 100%;
    }

    .v-window-item {
      overflow: hidden;
      block-size: 100%;

      > .v-card {
        display: flex;
        overflow: hidden;
        flex-direction: column;
        block-size: 100%;

        > .v-card-text {
          flex: 1;
          padding: 1rem;
          min-block-size: 0;
          overflow-y: auto;
        }
      }
    }
  }

  .tab-header {
    flex-shrink: 0;
  }
}

.tab-card {
  display: flex;
  overflow: hidden;
  flex-direction: column;
  block-size: 100%;
}

.tab-card-content {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
}

.header-left-group {
  flex: 1 1 0;
  min-inline-size: 0;
}

.version-info-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding-inline-start: 8px;
}

.tab-header {
  position: relative;
  z-index: 1;

  &::before {
    position: absolute;
    z-index: -1;
    backdrop-filter: blur(10px);
    content: '';
    inset: 0;
  }

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-tabs) {
    margin-inline-start: auto;
  }
}
</style>
