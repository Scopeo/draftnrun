<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { Background, BackgroundVariant } from '@vue-flow/background'
import { type GraphNode, VueFlow } from '@vue-flow/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ComponentSelectionCarousel from './components/ComponentSelectionCarousel.vue'
import EditSidebar from './components/EditSidebar.vue'
import RouterNode from './components/RouterNode.vue'
import SpecialEdge from './components/SpecialEdge.vue'
import SpecialNode from './components/SpecialNode.vue'
import StudioShell from './StudioShell.vue'
import { logger } from '@/utils/logger'
import { logComponentMount, logComponentUnmount } from '@/utils/queryLogger'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { useSavingState } from '@/composables/useSavingState'
import { useSaveVersion } from '@/composables/useSaveVersion'
import { useCurrentProject, useProjectQuery, useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import { useComponentDefinitionsQuery } from '@/composables/queries/useComponentDefinitionsQuery'
import { useAgentsQuery } from '@/composables/queries/useAgentsQuery'
import SaveDeployButtons from '@/components/shared/SaveDeployButtons.vue'
import { useStudioGraph } from '@/composables/useStudioGraph'
import { useStudioBreadcrumbs } from '@/composables/useStudioBreadcrumbs'
import { useGraphDisplayStream } from '@/composables/useGraphDisplayStream'

const emit = defineEmits<{
  openCronModal: []
  openEndpointPollingModal: []
}>()

// ─── External dependencies ───────────────────────────────────────────
const { selectedOrgId } = useSelectedOrg()

const { currentGraphRunner, currentProject, setCurrentGraphRunner, setGraphLastEditedInfo, setPlaygroundConfig } =
  useCurrentProject()

const ability = useAbility()
const route = useRoute()

const projectId = computed(() => route.params.id as string)
const { refetch: refreshProjectData } = useProjectQuery(projectId)
const { components: componentDefinitions, categories } = useComponentDefinitionsQuery(selectedOrgId)
const { data: projects } = useProjectsQuery(selectedOrgId)
const { data: agents } = useAgentsQuery(selectedOrgId)

// ─── UI-only state ───────────────────────────────────────────────────
const showEditDrawer = ref(false)
const selectedNode = ref<GraphNode | null>(null)
const showComponentDialog = ref(false)
const dialogMode = ref<'component' | 'tool'>('component')

// ─── Graph composable ────────────────────────────────────────────────
const graph = useStudioGraph({
  projectId,
  selectedOrgId,
  componentDefinitions,
  currentGraphRunner,
  currentProject,
  setCurrentGraphRunner,
  setGraphLastEditedInfo,
  setPlaygroundConfig,
  refreshProjectData,
  selectedNode,
})

// ─── Graph display stream (auto-refreshes canvas on external changes) ─
const { wsDisconnected, refreshing: streamRefreshing, manualRefresh } = useGraphDisplayStream(
  projectId,
  () => graph.loadGraphData(projectId.value),
  graph.hasUnsavedChanges,
)

// ─── Breadcrumb composable ───────────────────────────────────────────
const crumbs = useStudioBreadcrumbs({
  activeComponentId: graph.activeComponentId,
  setActiveComponent: graph.setActiveComponent,
  getNodeName: graph.getNodeName,
  getNodeType: graph.getNodeType,
  getActiveName: graph.getActiveName,
})

graph.setOnBeforeLoad(() => {
  crumbs.resetState()
  showEditDrawer.value = false
  selectedNode.value = null
})

// ─── Save version (snapshot) ─────────────────────────────────────────
interface SaveVersionResponse {
  last_edited_time?: string | null
  last_edited_user_id?: string | null
}
function asSaveVersionResponse(response: unknown): SaveVersionResponse {
  if (!response || typeof response !== 'object') return {}
  const typed = response as Record<string, unknown>
  return {
    last_edited_time: typeof typed.last_edited_time === 'string' ? typed.last_edited_time : null,
    last_edited_user_id: typeof typed.last_edited_user_id === 'string' ? typed.last_edited_user_id : null,
  }
}

const {
  validationStatus: saveVersionValidationStatus,
  saveError: saveVersionError,
  isSaving: isSavingVersion,
  saveVersion: saveVersionAction,
} = useSaveVersion({
  projectId,
  currentGraphRunner,
  onAfterSave: async response => {
    const parsed = asSaveVersionResponse(response)
    if (parsed.last_edited_time) {
      setGraphLastEditedInfo(
        parsed.last_edited_time,
        parsed.last_edited_user_id || null,
        selectedOrgId.value || undefined
      )
    }
    await refreshProjectData()
  },
})

const isSavingComputed = useSavingState(isSavingVersion, graph.isSaving)

async function onSaveVersion() {
  if (!graph.isDraftMode.value || !currentGraphRunner.value || isSavingVersion.value) return
  await saveVersionAction()
  graph.validationStatus.value = saveVersionValidationStatus.value
  graph.saveError.value = saveVersionError.value
  graph.hasUnsavedChanges.value = false
}

// ─── Thin UI handlers ────────────────────────────────────────────────
function handleNodeEdit(node: any) {
  const enhanced = graph.getEnhancedNode(node.id)
  if (enhanced) {
    selectedNode.value = enhanced
    showEditDrawer.value = true
  }
}

function onNodeClick(event: any) {
  if (showEditDrawer.value) return
  const node = event.node

  if (graph.activeComponentId.value === node.id) {
    handleNodeEdit(node)
    return
  }

  if (graph.nodeHasChildren(node.id)) {
    crumbs.navigateToNode(node.id)
  } else {
    handleNodeEdit(node)
  }
}

function handleComponentSave(updatedComponent: any) {
  if (!graph.isDraftMode.value || !selectedNode.value) return
  const updated = graph.updateNodeData(selectedNode.value.id, updatedComponent)
  if (updated) selectedNode.value = { ...updated } as GraphNode
}

async function handleToolSelection(selectedTool: any) {
  const nodeData = await graph.createNodeFromTemplate(selectedTool)

  graph.addComponentToGraph(nodeData, dialogMode.value === 'tool')
  dialogMode.value = 'component'
}

function openDialog(mode: 'component' | 'tool') {
  if (mode === 'tool' && !graph.activeComponentId.value) {
    logger.error("Cannot open dialog in 'tool' mode without an active component.")
    return
  }
  if (!ability.can('update', 'Project')) {
    logger.warn('User does not have permission to add components/tools.')
    return
  }
  dialogMode.value = mode
  showComponentDialog.value = true
}

function handleAddToolFromNode({ nodeId }: { nodeId: string }) {
  if (graph.activeComponentId.value !== nodeId) crumbs.navigateToNode(nodeId)
  openDialog('tool')
}

// ─── Lifecycle ───────────────────────────────────────────────────────
onMounted(async () => {
  logComponentMount('StudioFlow', [['project', projectId.value]])
  if (projectId.value) await graph.loadGraphData(projectId.value)
  else logger.error('No project ID found in route on mount.')
})

onUnmounted(() => {
  logComponentUnmount('StudioFlow')
  graph.cleanup()
})

// ─── Template aliases (keep template bindings clean) ─────────────────
const {
  activeComponentId,
  isLoadingGraph,
  isTransformingGraph,
  hasUnsavedChanges,
  isDraftMode,
  hasProductionDeployment,
  isDeploying,
  saveError,
  validationStatus,
  handleEdgeClick,
  handleNodeDelete,
  handleEdgeDelete,
  handleAddTools,
  handleRemoveTool,
  handleDeployConfirm,
  resetLayout,
  nodeHasChildren,
} = graph

const { breadcrumbs, handleBreadcrumbClick, goToOverviewAndClearHistory, resetView } = crumbs
</script>

<template>
  <StudioShell
    :loading="isLoadingGraph || isTransformingGraph"
    :loading-text="isLoadingGraph ? 'Loading workflow...' : 'Preparing graph...'"
  >
    <template #toolbar-right>
      <SaveDeployButtons
        v-if="ability.can('update', 'Project')"
        :current-graph-runner="currentGraphRunner"
        :has-unsaved-changes="hasUnsavedChanges"
        :is-saving="isSavingComputed"
        :is-deploying="isDeploying"
        :validation-status="validationStatus"
        :save-error="saveError"
        :has-production-deployment="hasProductionDeployment"
        :show-status-indicator="true"
        :show-schedule="true"
        :show-endpoint-polling="true"
        :on-save-version="onSaveVersion"
        :on-deploy="handleDeployConfirm"
        :on-schedule-click="() => emit('openCronModal')"
        :on-endpoint-polling-click="() => emit('openEndpointPollingModal')"
      />
      <VBtn
        icon
        variant="text"
        size="x-small"
        :loading="streamRefreshing"
        @click="manualRefresh"
      >
        <VIcon icon="tabler-refresh" size="18" />
        <VTooltip activator="parent">Refresh graph</VTooltip>
      </VBtn>
    </template>

    <VueFlow
      id="studio-flow"
      :default-viewport="{ x: 0, y: 0, zoom: 1 }"
      :connection-radius="80"
      :fit-view-on-init="true"
      :auto-connect="false"
      :edges-focusable="isDraftMode && !activeComponentId"
      :delete-key-code="isDraftMode && !activeComponentId ? 'Backspace' : null"
      class="vue-flow-updating"
      :class="{ 'read-only': !isDraftMode }"
      @node-click="onNodeClick"
      @edge-click="handleEdgeClick"
    >
      <Background :variant="BackgroundVariant.Dots" :gap="20" :size="1" color="#ddd" />

      <template #node-component="props">
        <SpecialNode
          v-bind="props"
          :is-draft-mode="isDraftMode"
          :is-zoomed-in="!!activeComponentId"
          :active-component-id="activeComponentId"
          :has-children="nodeHasChildren(props.id)"
          :prevent-click-propagation="showEditDrawer"
          @delete="handleNodeDelete"
          @add-tool="handleAddToolFromNode"
        />
      </template>
      <template #node-worker="props">
        <SpecialNode
          v-bind="props"
          :is-draft-mode="isDraftMode"
          :is-zoomed-in="!!activeComponentId"
          :active-component-id="activeComponentId"
          :has-children="nodeHasChildren(props.id)"
          :prevent-click-propagation="showEditDrawer"
          @delete="handleNodeDelete"
          @add-tool="handleAddToolFromNode"
        />
      </template>
      <template #node-router="props">
        <RouterNode
          v-bind="props"
          :is-draft-mode="isDraftMode"
          :is-zoomed-in="!!activeComponentId"
          :active-component-id="activeComponentId"
          @delete="handleNodeDelete"
        />
      </template>

      <template #edge-smoothstep="props">
        <SpecialEdge
          v-bind="props"
          :is-draft-mode="isDraftMode"
          :is-root-level="!activeComponentId"
          @delete="handleEdgeDelete"
        />
      </template>

      <template #edge-default="props">
        <SpecialEdge
          v-bind="props"
          :is-draft-mode="isDraftMode"
          :is-root-level="!activeComponentId"
          @delete="handleEdgeDelete"
        />
      </template>

      <template #connection-line="{ sourceX, sourceY, targetX, targetY }">
        <path
          :d="`M${sourceX},${sourceY} L${targetX},${targetY}`"
          class="vue-flow__connection-path"
          stroke="rgb(var(--v-theme-primary))"
          stroke-width="2"
          stroke-dasharray="5"
        />
      </template>
    </VueFlow>

    <div v-if="activeComponentId" class="studio-breadcrumbs-float">
      <div v-if="breadcrumbs.length > 0" class="studio-breadcrumbs">
        <span class="studio-breadcrumbs__item" @click="goToOverviewAndClearHistory">Overview</span>
        <template v-for="(crumb, index) in breadcrumbs" :key="index">
          <VIcon icon="tabler-chevron-right" size="14" class="mx-1" />
          <span
            class="studio-breadcrumbs__item"
            :class="{ 'studio-breadcrumbs__item--active': index === breadcrumbs.length - 1 }"
            @click="handleBreadcrumbClick(index)"
          >
            {{ crumb }}
          </span>
        </template>
      </div>
      <VBtn variant="tonal" color="primary" size="small" @click="resetView">
        <VIcon icon="tabler-arrow-back" size="18" class="me-2" />
        Back
      </VBtn>
    </div>

    <EditSidebar
      v-model="showEditDrawer"
      :component-data="selectedNode ? { id: selectedNode.id, ...selectedNode.data } : null"
      :component-definitions="componentDefinitions"
      :projects="projects"
      :agents="agents"
      :is-draft-mode="isDraftMode"
      @save="handleComponentSave"
      @add-tools="handleAddTools"
      @remove-tool="handleRemoveTool"
    />

    <ComponentSelectionCarousel
      v-model="showComponentDialog"
      :mode="dialogMode"
      :component-definitions="componentDefinitions"
      :categories="categories"
      @tool-selected="handleToolSelection"
    />

    <template #bottom-bar>
      <VBtn
        v-if="!activeComponentId && ability.can('update', 'Project') && isDraftMode"
        color="success"
        @click="openDialog('component')"
      >
        <VIcon icon="tabler-plus" class="me-2" />
        Add Component
      </VBtn>
      <span v-else />
      <VBtn v-if="isDraftMode && ability.can('update', 'Project')" color="warning" variant="tonal" @click="resetLayout">
        <VIcon icon="tabler-refresh" class="me-2" />
        Reset Layout
      </VBtn>
    </template>
  </StudioShell>
</template>

<style lang="scss">
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';

.vue-flow-wrapper {
  flex-grow: 1;
  block-size: 100%;
  inline-size: 100%;
}

.vue-flow__edge-path {
  stroke-width: 2;
}

.vue-flow__edge.animated path {
  animation: dashdraw 0.5s linear infinite;
  stroke-dasharray: 5;
}

.vue-flow__connection-path {
  stroke-width: 3;
}

.vue-flow__handle {
  transition:
    transform 0.2s ease,
    background-color 0.2s ease;
}

.vue-flow__handle:hover {
  cursor: crosshair;
  transform: scale(1.2);
}

.vue-flow__handle.valid {
  background-color: rgb(var(--v-theme-success));
}

.vue-flow__handle.invalid {
  background-color: rgb(var(--v-theme-error));
}

@keyframes dashdraw {
  from {
    stroke-dashoffset: 10;
  }
}

.hidden {
  display: none;
}

.studio-breadcrumbs-float {
  position: absolute;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: var(--dnr-radius-md);
  background: rgb(var(--v-theme-surface));
  box-shadow: var(--dnr-elevation-2);
  inset-block-start: 12px;
  inset-inline-start: 12px;
}

.studio-breadcrumbs {
  display: flex;
  align-items: center;
  font-size: 12px;

  &__item {
    overflow: hidden;
    color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
    max-inline-size: 150px;
    text-overflow: ellipsis;
    white-space: nowrap;

    &--active {
      color: rgb(var(--v-theme-primary));
      font-weight: 500;
    }

    &:not(&--active) {
      cursor: pointer;
    }

    &:not(&--active):hover {
      text-decoration: underline;
    }
  }
}

.vue-flow-updating .vue-flow__edge {
  pointer-events: all;
}

.vue-flow__edge .vue-flow__edge-interaction {
  stroke: transparent;
  pointer-events: all;
}

.vue-flow-updating .vue-flow__edge .vue-flow__edge-path {
  stroke-width: 2;
  transition: d 0.2s ease;
}

.vue-flow.read-only .vue-flow__handle {
  cursor: not-allowed;
  opacity: 0.5;
  pointer-events: none;
}

.vue-flow.read-only .vue-flow__node {
  cursor: default !important;
}

</style>
