<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CronJobModal from '@/components/cron/CronJobModal.vue'
import EndpointPollingModal from '@/components/cron/EndpointPollingModal.vue'
import IntegrationTab from '@/components/integration/IntegrationTab.vue'
import InlineIconEditor from '@/components/projects/InlineIconEditor.vue'
import EditEntityModal from '@/components/shared/EditEntityModal.vue'
import ModificationHistoryDialog from '@/components/shared/ModificationHistoryDialog.vue'
import SharedTabContent from '@/components/shared/SharedTabContent.vue'
import VersionSelectorContainer from '@/components/shared/VersionSelectorContainer.vue'
import { useComponentDefinitionsQuery } from '@/composables/queries/useComponentDefinitionsQuery'
import {
  useCurrentProject,
  useOrgTagsQuery,
  useProjectQuery,
  useUpdateProjectMutation,
} from '@/composables/queries/useProjectsQuery'
import { getCurrentOrgReleaseStage, useOrgReleaseStagesQuery } from '@/composables/queries/useReleaseStagesQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { PANEL_SIZES } from '@/config/panelSizes'
import { logComponentMount, logComponentUnmount } from '@/utils/queryLogger'
import { TAB_STAGE_CONFIG, getTabMetadata, isTabVisibleForStage } from '@/utils/tabStageConfig'

// Lazy load heavy components with Vue Flow, TipTap, etc.
const StudioFlow = defineAsyncComponent(() => import('@/components/studio/StudioFlow.vue'))
const WorkflowFloatingActions = defineAsyncComponent(() => import('@/components/workflows/WorkflowFloatingActions.vue'))

const route = useRoute('org-org-id-projects-id')
const router = useRouter()

// Get selected org
const { selectedOrgId, orgChangeCounter } = useSelectedOrg()

// Project ID from route
const projectId = computed(() => route.params.id as string)

// Fetch project and org data
const { isLoading: isProjectLoading, refetch: refetchProject } = useProjectQuery(projectId)
const { data: orgReleaseStages } = useOrgReleaseStagesQuery(selectedOrgId)

// Get component definitions - these are needed for graph rendering
// They load in parallel with project data and are cached for 5 minutes
const { components: componentDefinitions, isLoading: isLoadingComponentDefs } =
  useComponentDefinitionsQuery(selectedOrgId)

const {
  currentProject: project,
  currentGraphRunner,
  graphLastEditedTime,
  graphLastEditedUserId,
  graphLastEditedUserEmail,
} = useCurrentProject()

const updateProjectMutation = useUpdateProjectMutation()
const { data: orgTags } = useOrgTagsQuery(selectedOrgId)

// Modification history dialog props
const historyProjectId = computed(() => project.value?.project_id)
const historyGraphRunnerId = computed(() => currentGraphRunner.value?.graph_runner_id)

// Component lifecycle logging
onMounted(() => {
  logComponentMount('ProjectsIdPage', [
    ['project', route.params.id],
    ['org-release-stages', selectedOrgId.value],
    ['component-definitions', selectedOrgId.value],
  ])
})

onUnmounted(() => {
  logComponentUnmount('ProjectsIdPage')
})

// Create separate loading states for different data
const isTabContentLoading = ref(false)

// Edit modal state
const showEditModal = ref(false)

// Cron modal state
const showCronModal = ref(false)
const showEndpointPollingModal = ref(false)
const showSaveSuccess = ref(false)

// Function to check if a tab should be visible based on release stage
const isTabVisible = (tabValue: string): boolean => {
  if (!selectedOrgId.value || !orgReleaseStages.value) return false

  const orgStage = getCurrentOrgReleaseStage(orgReleaseStages.value, selectedOrgId.value)
  const stageName = orgStage?.release_stage_name || null

  return isTabVisibleForStage(tabValue, stageName)
}

// Watch for route changes - refetch project when ID changes
watch(
  () => route.params.id,
  async newId => {
    if (!newId) {
      router.push(`/org/${selectedOrgId.value}/projects`)
    }
  }
)

// Watch for organization changes - navigate to projects list in new org
watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/projects`)
  }
})

// Manual save function for EditEntityModal
const manualSave = async (
  projectId: string,
  data: { name?: string; description?: string; tags?: string[] }
) => {
  await updateProjectMutation.mutateAsync({ projectId, data })
}

const handleProjectUpdate = (data: { name: string; description: string; tags: string[] }) => {
  if (project.value) {
    project.value.project_name = data.name
    project.value.description = data.description
    project.value.tags = data.tags
  }
}

const handleIconUpdated = (data: { icon: string; iconColor: string }) => {
  if (project.value) {
    project.value.icon = data.icon
    project.value.icon_color = data.iconColor

    updateProjectMutation.mutate({
      projectId: project.value.project_id,
      data: { icon: data.icon, icon_color: data.iconColor },
    })
  }
}

const activeTab = ref('studio')

// Track overlay panel widths
const playgroundWidth = ref<number>(PANEL_SIZES.DEFAULT_WIDTH)
const observabilityOpen = ref(false)

// Check if playground should be visible (hidden on integration and qa tabs)
const isPlaygroundVisible = computed(() => activeTab.value !== 'integration' && activeTab.value !== 'qa')

// Calculate available space based on floating panels
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

const handleWindowsChanged = (observability: boolean, _expandedMode?: boolean, _widthPx?: number) => {
  observabilityOpen.value = observability
}

const handlePlaygroundWidthChanged = (width: number) => {
  playgroundWidth.value = width
}

// Pre-fetch initial tab data
onMounted(async () => {
  isTabContentLoading.value = true
  try {
    // Load initial tab data in parallel
    await Promise.all([
      // Add your API calls here for initial tab
      // Example: loadStudioData(),
    ])
  } finally {
    isTabContentLoading.value = false
  }
})

const tabs = computed(() => {
  const allTabs = Object.keys(TAB_STAGE_CONFIG).map(tabKey => {
    const metadata = getTabMetadata(tabKey)
    return {
      title: metadata.title,
      value: tabKey,
      icon: metadata.icon,
      disabled: false,
    }
  })

  // Filter tabs based on release stage access
  return allTabs.filter(tab => isTabVisible(tab.value))
})

// Computed: Show loading state if project or component definitions are loading
// This prevents studio from rendering with incomplete data
const isStudioReady = computed(() => {
  return !isProjectLoading.value && !isLoadingComponentDefs.value && !!project.value && !!componentDefinitions.value
})

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <AppPage width="editor">
    <div class="project-container" :style="availableSpace">
      <!-- Show skeleton loader while project or component definitions load -->
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
        <VCard class="mb-2 tab-header">
          <div class="d-flex align-center gap-4 pa-3">
            <div class="d-flex align-center flex-wrap gap-4 header-left-group">
              <div v-if="project" class="d-flex align-center gap-3">
                <InlineIconEditor
                  :project-id="project.project_id"
                  :current-icon="project.icon"
                  :current-color="project.icon_color"
                  entity-type="project"
                  @updated="handleIconUpdated"
                />
                <span class="text-h5">{{ project.project_name }}</span>
                <VBtn icon variant="text" size="small" @click="showEditModal = true">
                  <VIcon icon="tabler-edit" size="18" />
                </VBtn>
              </div>
              <div v-if="project" class="version-info-group">
                <VersionSelectorContainer
                  :entity="project as any"
                  entity-type="project"
                  @refresh-project="refetchProject"
                />
                <ModificationHistoryDialog
                  :project-id="historyProjectId"
                  :graph-runner-id="historyGraphRunnerId"
                  :org-id="selectedOrgId"
                  :last-edited-time="graphLastEditedTime"
                  :last-edited-user-id="graphLastEditedUserId"
                  :last-edited-user-email="graphLastEditedUserEmail"
                />
              </div>
            </div>

            <VTabs v-model="activeTab" class="v-tabs-pill" fixed-tabs>
              <VTab v-for="tab in tabs" :key="tab.value" :value="tab.value" :disabled="tab.disabled">
                <VIcon :icon="tab.icon" size="18" class="me-2" />
                {{ tab.title }}
              </VTab>
            </VTabs>
          </div>
        </VCard>

        <VWindow v-model="activeTab">
          <VWindowItem v-for="tab in tabs" :key="tab.value" :value="tab.value">
            <!-- Integration Tab Content -->
            <VCard v-if="activeTab === 'integration'" class="tab-card">
              <VCardText class="tab-card-content">
                <IntegrationTab
                  :project-id="project?.project_id"
                  :project-name="project?.project_name"
                  :organization-id="project?.organization_id"
                />
              </VCardText>
            </VCard>

            <!-- Studio Tab Content -->
            <VCard v-if="activeTab === 'studio'" class="tab-card">
              <VCardText class="tab-card-content">
                <StudioFlow
                  v-if="project?.project_id"
                  :key="project.project_id"
                  flow="{}"
                  @open-cron-modal="showCronModal = true"
                  @open-endpoint-polling-modal="showEndpointPollingModal = true"
                />
              </VCardText>
            </VCard>

            <!-- Shared Tab Content (QA only) -->
            <SharedTabContent
              v-else-if="activeTab === 'qa' && project"
              :tab-value="tab.value"
              :project-id="project.project_id"
              :graph-runners="project.graph_runners || []"
            />
          </VWindowItem>
        </VWindow>

        <!-- Add loading indicator for tab content -->
        <VOverlay v-model="isTabContentLoading" contained persistent class="align-center justify-center">
          <VProgressCircular indeterminate color="primary" />
        </VOverlay>
      </template>

      <!-- Floating Actions - hidden on Integration and QA tabs -->
      <WorkflowFloatingActions
        v-if="project && isPlaygroundVisible"
        :project-id="project.project_id"
        @windows-changed="handleWindowsChanged"
        @width-changed="handlePlaygroundWidthChanged"
      />

      <!-- Edit Project Modal -->
      <EditEntityModal
        v-if="project"
        v-model="showEditModal"
        :entity-id="project.project_id"
        :entity-name="project.project_name"
        :entity-description="project.description"
        :entity-tags="project.tags || []"
        :available-tags="orgTags || []"
        entity-type="project"
        :save-function="manualSave"
        @updated="handleProjectUpdate"
      />

      <!-- Cron Job Modal -->
      <CronJobModal
        v-if="project"
        v-model:is-dialog-visible="showCronModal"
        :project-id="project.project_id"
        @created="
          () => {
            showSaveSuccess = true
          }
        "
      />

      <!-- Endpoint Polling Modal -->
      <EndpointPollingModal
        v-if="project"
        v-model:is-dialog-visible="showEndpointPollingModal"
        :project-id="project.project_id"
        @created="
          () => {
            showSaveSuccess = true
          }
        "
      />
    </div>
  </AppPage>
</template>

<style lang="scss" scoped>
.project-container {
  display: flex;
  overflow: hidden;
  flex-direction: column;
  border-radius: 12px;
  block-size: calc(100vh - 2 * var(--dnr-page-padding));
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
</style>
