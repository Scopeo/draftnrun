<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ProjectCard from './ProjectCard.vue'
import TemplateCard from './TemplateCard.vue'
import { logger } from '@/utils/logger'
import { tagColor } from '@/utils/tagColor'
import {
  fetchProject,
  useDeleteProjectMutation,
  useDuplicateProjectMutation,
  useOrgTagsQuery,
  useProjectsQuery,
} from '@/composables/queries/useProjectsQuery'
import { fetchAgentDetail, useDeleteAgentMutation } from '@/composables/queries/useAgentsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'

interface GraphRunner {
  graph_runner_id: string
  env: string | null
  tag_name: string | null
}

interface Project {
  project_id: string
  project_name: string
  description: string | null
  created_at?: string
  updated_at?: string
  graph_runners?: GraphRunner[]
  project_type?: 'AGENT' | 'WORKFLOW'
  is_template?: boolean
  tags?: string[]
}

interface Props {
  type: 'AGENT' | 'WORKFLOW'
  title: string
  routeNamePrefix: string // e.g., 'agents' or 'projects'
  isCreating?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isCreating: false,
})

const emit = defineEmits<{
  'create-click': []
  'template-click': [template: Project]
  'edit-click': [project: Project]
}>()

const router = useRouter()
const ability = useAbility()
const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
const queryClient = useQueryClient()
const duplicateProjectMutation = useDuplicateProjectMutation()
const deleteProjectMutation = useDeleteProjectMutation()
const deleteAgentMutation = useDeleteAgentMutation()

const projectType = computed(() => props.type)
const selectedTags = ref<string[]>([])

const { data: orgTags } = useOrgTagsQuery(selectedOrgId)

const selectedTagsRef = computed(() => (selectedTags.value.length > 0 ? selectedTags.value : undefined))

const {
  data: allProjects,
  isLoading: loading,
  error: queryError,
  refetch,
} = useProjectsQuery(selectedOrgId, projectType, true, selectedTagsRef)

const projects = ref<Project[]>([])
const templates = ref<Project[]>([])
const error = ref<string | null>(null)
const isRefreshing = ref(false)
const isDeleting = ref(false)
const templatesExpanded = ref(false)
const projectToDelete = ref<Project | null>(null)
const isDeleteDialogVisible = ref(false)
const templatesGridRef = ref<HTMLElement | null>(null)
const templatesPerRow = ref(4) // Default estimate
const loadingProjectId = ref<string | null>(null) // Track which project is being navigated to
const projectToDuplicate = ref<Project | null>(null)
const isDuplicateDialogVisible = ref(false)
const duplicateProjectName = ref('')
const isDuplicating = ref(false)

const isLoading = computed(() => loading.value || isRefreshing.value)

// Watch query data and separate templates/projects
watch(
  allProjects,
  data => {
    if (data) {
      templates.value = data.filter(p => p.is_template)
      projects.value = data.filter(p => !p.is_template)
    } else {
      templates.value = []
      projects.value = []
    }
  },
  { immediate: true }
)

// Watch query error
watch(queryError, err => {
  if (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch projects'
  } else {
    error.value = null
  }
})

// Refresh projects using TanStack Query refetch
const refreshProjects = async (force = true) => {
  isRefreshing.value = true
  try {
    await refetch()
  } catch (err) {
    logger.error('[ProjectListView] Error refreshing projects', { error: err })
  } finally {
    isRefreshing.value = false
  }
}

// Handle template click
const handleTemplateClick = (template: any) => {
  emit('template-click', template)
}

// Handle project click
const handleProjectClick = (project: any) => {
  loadingProjectId.value = project.project_id
  router.push({
    name: `org-org-id-${props.routeNamePrefix}-id`,
    params: { orgId: selectedOrgId.value, id: project.project_id },
  })
}

// Prefetch detail data on hover for instant navigation
const prefetchProjectDetail = (project: Project) => {
  if (props.type === 'WORKFLOW') {
    queryClient.prefetchQuery({
      queryKey: ['project', project.project_id],
      queryFn: () => fetchProject(project.project_id),
      staleTime: 1000 * 60 * 5,
    })
  } else {
    const draftRunner = project.graph_runners?.find(r => r.env === 'draft')
    const versionId = draftRunner?.graph_runner_id || project.graph_runners?.[0]?.graph_runner_id
    if (versionId) {
      queryClient.prefetchQuery({
        queryKey: ['agent', project.project_id, versionId],
        queryFn: () => fetchAgentDetail(project.project_id, versionId),
        staleTime: 1000 * 60,
      })
    }
  }
}

// Handle edit click
const handleEditClick = (project: any) => {
  emit('edit-click', project)
}

// Handle delete click
const confirmDelete = (project: any) => {
  projectToDelete.value = project
  isDeleteDialogVisible.value = true
}

// Delete project
const handleDeleteProject = async () => {
  if (!projectToDelete.value || !selectedOrgId.value) return

  isDeleting.value = true
  try {
    if (props.type === 'AGENT') {
      await deleteAgentMutation.mutateAsync({
        agentId: projectToDelete.value.project_id,
        orgId: selectedOrgId.value,
      })
    } else {
      await deleteProjectMutation.mutateAsync(projectToDelete.value.project_id)
    }
  } catch (err: unknown) {
    logger.error('[ProjectListView] Failed to delete project', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to delete project'
  } finally {
    isDeleting.value = false
    isDeleteDialogVisible.value = false
    projectToDelete.value = null
  }
}

// Cancel delete
const cancelDelete = () => {
  projectToDelete.value = null
  isDeleteDialogVisible.value = false
}

// Handle duplicate click
const confirmDuplicate = (project: Project) => {
  projectToDuplicate.value = project
  duplicateProjectName.value = `Copy of ${project.project_name}`
  isDuplicateDialogVisible.value = true
}

// Duplicate project
const handleDuplicateProject = async () => {
  if (!projectToDuplicate.value || !duplicateProjectName.value.trim()) {
    error.value = 'Please provide a valid project name'
    return
  }

  // Try to get production runner first, then fall back to draft, then any runner
  let runnerToUse = projectToDuplicate.value.graph_runners?.find((runner: GraphRunner) => runner.env === 'production')

  if (!runnerToUse) {
    runnerToUse = projectToDuplicate.value.graph_runners?.find((runner: GraphRunner) => runner.env === 'draft')
  }

  if (!runnerToUse && projectToDuplicate.value.graph_runners && projectToDuplicate.value.graph_runners.length > 0) {
    runnerToUse = projectToDuplicate.value.graph_runners[0]
  }

  if (!runnerToUse) {
    error.value = 'No version found to duplicate'
    return
  }

  if (!selectedOrgId.value) {
    error.value = 'No organization selected'
    return
  }

  isDuplicating.value = true
  try {
    await duplicateProjectMutation.mutateAsync({
      orgId: selectedOrgId.value,
      projectId: projectToDuplicate.value.project_id,
      graphRunnerId: runnerToUse.graph_runner_id,
      name: duplicateProjectName.value.trim(),
    })
    await refreshProjects()
  } catch (err: unknown) {
    logger.error('[ProjectListView] Failed to duplicate project', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to duplicate project'
  } finally {
    isDuplicating.value = false
    isDuplicateDialogVisible.value = false
    projectToDuplicate.value = null
    duplicateProjectName.value = ''
  }
}

// Cancel duplicate
const cancelDuplicate = () => {
  projectToDuplicate.value = null
  duplicateProjectName.value = ''
  isDuplicateDialogVisible.value = false
}

// Calculate templates per row based on container width
const calculateTemplatesPerRow = () => {
  if (!templatesGridRef.value) return

  const containerWidth = templatesGridRef.value.offsetWidth
  const gap = 16 // Grid gap in pixels
  const minCardWidth = 200 // Minimum card width from grid-template-columns

  // Calculate how many cards fit: floor((containerWidth + gap) / (minCardWidth + gap))
  const cardsPerRow = Math.floor((containerWidth + gap) / (minCardWidth + gap))

  templatesPerRow.value = Math.max(1, cardsPerRow)
}

// Toggle templates expansion
const toggleTemplates = () => {
  templatesExpanded.value = !templatesExpanded.value
}

// Display only first row when collapsed, +1 for the "Blank" card
const displayedTemplates = computed(() => {
  const totalCards = templates.value.length + 1 // +1 for blank card
  if (templatesExpanded.value || totalCards <= templatesPerRow.value) {
    return templates.value
  }
  // Show one row minus the blank card
  return templates.value.slice(0, Math.max(0, templatesPerRow.value - 1))
})

const hasMoreTemplates = computed(() => {
  // +1 for the blank card in total count
  return templates.value.length + 1 > templatesPerRow.value
})

// Setup resize observer
let resizeObserver: ResizeObserver | null = null

const setupResizeObserver = async () => {
  await nextTick()
  if (templatesGridRef.value && !resizeObserver) {
    calculateTemplatesPerRow()

    // Watch for container resize
    resizeObserver = new ResizeObserver(() => {
      calculateTemplatesPerRow()
    })
    resizeObserver.observe(templatesGridRef.value)
  }
}

// Watch for templates to be loaded
watch(
  templates,
  async () => {
    if (templates.value.length > 0) {
      await setupResizeObserver()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await setupResizeObserver()
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})

// Handle create button click
const handleCreateClick = () => {
  emit('create-click')
}

// Can user create/edit/delete
const canCreate = computed(() => ability.can('create', 'Project'))
const canUpdate = computed(() => ability.can('update', 'Project'))
const canDelete = computed(() => ability.can('delete', 'Project'))

// Expose methods for parent components
defineExpose({
  refreshProjects,
})
</script>

<template>
  <AppPage width="full">
    <AppPageHeader :title="title">
      <template v-if="projects.length > 0 || templates.length > 0" #actions>
        <VBtn
          icon
          variant="text"
          color="default"
          size="small"
          :loading="isRefreshing"
          :disabled="isLoading"
          @click="refreshProjects"
        >
          <VIcon icon="tabler-refresh" size="18" />
        </VBtn>
      </template>
    </AppPageHeader>

    <!-- Error Alert -->
    <VAlert v-if="error" type="error" variant="tonal" class="mb-4" closable @click:close="error = null">
      {{ error }}
    </VAlert>

    <!-- Skeleton loading — mirrors the two-section populated layout -->
    <template v-if="isLoading && projects.length === 0 && templates.length === 0">
      <div class="mb-6">
        <div class="skeleton-bone skeleton-section-label mb-3" />
        <div class="templates-grid">
          <div v-for="i in 4" :key="`t-${i}`" class="skeleton-template-card">
            <div class="skeleton-template-row">
              <div class="skeleton-bone skeleton-avatar-sm" />
              <div class="skeleton-bone skeleton-chip" />
            </div>
            <div class="skeleton-bone skeleton-line-md" />
            <div class="skeleton-bone skeleton-line-sm" />
          </div>
        </div>
      </div>

      <div>
        <div class="skeleton-bone skeleton-section-label mb-3" />
        <div class="projects-grid">
          <div v-for="i in 3" :key="`p-${i}`" class="skeleton-project-card">
            <div class="skeleton-project-row">
              <div class="skeleton-bone skeleton-avatar" />
              <div class="skeleton-project-text">
                <div class="skeleton-bone skeleton-line-md" />
                <div class="skeleton-bone skeleton-line-sm" />
              </div>
            </div>
            <div class="skeleton-project-footer">
              <div class="skeleton-bone skeleton-chip" />
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Empty state — no projects yet -->
    <EmptyState
      v-else-if="projects.length === 0 && !isLoading"
      :icon="type === 'AGENT' ? 'tabler-robot' : 'tabler-route'"
      :title="`Create your first ${type === 'AGENT' ? 'AI Agent' : 'Workflow'}`"
      :description="
        type === 'AGENT'
          ? 'Agents handle conversations, process data, and automate tasks for your organization.'
          : 'Workflows chain multiple steps together to automate complex processes.'
      "
      size="lg"
    >
      <template #actions>
        <div class="d-flex flex-column align-center gap-6">
          <VBtn
            v-if="canCreate"
            color="primary"
            size="large"
            :prepend-icon="isCreating ? undefined : 'tabler-plus'"
            :loading="isCreating"
            @click="handleCreateClick"
          >
            Create {{ type === 'AGENT' ? 'agent' : 'workflow' }}
          </VBtn>

          <div v-if="canCreate && templates.length > 0" class="empty-state__templates">
            <p class="text-body-2 text-medium-emphasis mb-3">Or start from a template</p>
            <div ref="templatesGridRef" class="templates-grid">
              <TemplateCard
                v-for="template in displayedTemplates"
                :key="template.project_id"
                :template="template"
                :disabled="isCreating"
                @click="handleTemplateClick"
              />
            </div>
            <VBtn v-if="hasMoreTemplates" variant="text" size="small" class="mt-3" @click="toggleTemplates">
              {{ templatesExpanded ? 'Show less' : 'See more templates' }}
              <VIcon :icon="templatesExpanded ? 'tabler-chevron-up' : 'tabler-chevron-down'" class="ms-1" size="14" />
            </VBtn>
          </div>
        </div>
      </template>
    </EmptyState>

    <!-- Populated state -->
    <template v-else>
      <!-- Create Section -->
      <div v-if="canCreate" class="mb-6">
        <div class="d-flex align-center justify-space-between mb-3">
          <span
            class="text-body-2 text-medium-emphasis font-weight-medium text-uppercase"
            style="letter-spacing: 0.05em"
          >
            New
          </span>
          <VBtn v-if="hasMoreTemplates" variant="text" size="x-small" @click="toggleTemplates">
            {{ templatesExpanded ? 'Show less' : 'See more' }}
            <VIcon :icon="templatesExpanded ? 'tabler-chevron-up' : 'tabler-chevron-down'" class="ms-1" size="12" />
          </VBtn>
        </div>

        <div ref="templatesGridRef" class="templates-grid">
          <VCard
            class="create-blank-card"
            :class="{ 'is-disabled': isCreating }"
            :ripple="false"
            elevation="0"
            @click="!isCreating && handleCreateClick()"
          >
            <VCardText class="pa-3 d-flex align-center gap-3" style="block-size: 100%">
              <VProgressCircular v-if="isCreating" indeterminate color="primary" size="24" />
              <VAvatar v-else color="primary" variant="tonal" size="36" rounded="lg">
                <VIcon icon="tabler-plus" size="20" />
              </VAvatar>
              <span class="text-body-2 font-weight-medium"> Blank {{ type === 'AGENT' ? 'agent' : 'workflow' }} </span>
            </VCardText>
          </VCard>

          <TemplateCard
            v-for="template in displayedTemplates"
            :key="template.project_id"
            :template="template"
            :disabled="isCreating"
            @click="handleTemplateClick"
          />
        </div>
      </div>

      <!-- Projects Grid -->
      <div v-if="projects.length > 0 || selectedTags.length > 0">
        <span
          class="text-body-2 text-medium-emphasis font-weight-medium text-uppercase d-block mb-3"
          style="letter-spacing: 0.05em"
        >
          Your {{ type === 'AGENT' ? 'agents' : 'workflows' }}
        </span>
        <VAutocomplete
          v-if="(orgTags && orgTags.length > 0) || selectedTags.length > 0"
          v-model="selectedTags"
          :items="orgTags"
          placeholder="Filter by tags…"
          variant="solo-filled"
          flat
          density="compact"
          multiple
          chips
          closable-chips
          hide-details
          clearable
          single-line
          class="tags-filter mb-4"
        >
          <template #prepend-inner>
            <VIcon icon="tabler-filter" size="14" class="me-1 text-medium-emphasis" />
          </template>
          <template #chip="{ props: chipProps, item }">
            <VChip v-bind="chipProps" size="x-small" variant="tonal" :color="tagColor(item.raw)" label closable>
              {{ item.raw }}
            </VChip>
          </template>
        </VAutocomplete>

        <div v-if="projects.length === 0 && selectedTags.length > 0" class="text-body-2 text-medium-emphasis pa-4">
          No {{ type === 'AGENT' ? 'agents' : 'workflows' }} match the selected tags.
        </div>
        <div v-else class="projects-grid">
          <ProjectCard
            v-for="project in projects"
            :key="project.project_id"
            :project="project"
            :project-type="type"
            :can-edit="canUpdate"
            :can-delete="canDelete"
            :is-loading="loadingProjectId === project.project_id"
            @mouseenter="prefetchProjectDetail(project)"
            @click="handleProjectClick"
            @edit="handleEditClick"
            @delete="confirmDelete"
            @duplicate="confirmDuplicate"
          />
        </div>
      </div>
    </template>

    <!-- Delete Confirmation Dialog -->
    <GenericConfirmDialog
      v-if="projectToDelete"
      v-model:is-dialog-visible="isDeleteDialogVisible"
      title="Confirm Delete"
      :message="`Are you sure you want to delete <strong>${projectToDelete.project_name}</strong>?<br><br>This action cannot be undone.`"
      confirm-text="Delete"
      confirm-color="error"
      :loading="isDeleting"
      @confirm="handleDeleteProject"
      @cancel="cancelDelete"
    />

    <!-- Duplicate Project Dialog -->
    <VDialog v-model="isDuplicateDialogVisible" max-width="var(--dnr-dialog-sm)" persistent>
      <VCard>
        <VCardTitle class="text-h5 pt-5"> Duplicate Project </VCardTitle>
        <VCardText>
          <p class="text-body-1 mb-4">Enter a name for the duplicated project:</p>
          <VTextField
            v-model="duplicateProjectName"
            label="Project Name"
            variant="outlined"
            autofocus
            :disabled="isDuplicating"
            @keyup.enter="handleDuplicateProject"
          />
        </VCardText>
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn variant="text" :disabled="isDuplicating" @click="cancelDuplicate"> Cancel </VBtn>
          <VBtn
            color="primary"
            variant="flat"
            :loading="isDuplicating"
            :disabled="!duplicateProjectName.trim()"
            @click="handleDuplicateProject"
          >
            Duplicate
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </AppPage>
</template>

<style lang="scss">
.is-disabled {
  cursor: not-allowed !important;
  opacity: 0.6 !important;
  pointer-events: none !important;
}
</style>

<style lang="scss" scoped>
.templates-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}

.projects-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.tags-filter {
  max-inline-size: 220px;

  :deep(.v-field) {
    --v-field-padding-start: 8px;
    --v-field-padding-end: 4px;
    --v-input-padding-top: 4px;
    min-block-size: 32px;
    font-size: 0.8125rem;
    border-radius: 8px;
  }

  :deep(.v-field__input) {
    padding-block: 2px;
    min-block-size: unset;
  }
}

.create-blank-card {
  border: 1px dashed rgba(var(--v-theme-primary), 0.25);
  background: rgba(var(--v-theme-primary), 0.02);
  border-radius: var(--dnr-radius-lg);
  block-size: 136px;
  cursor: pointer;
  transition:
    border-color 0.2s ease-out,
    background-color 0.2s ease-out;

  &:hover:not(.is-disabled) {
    border-color: rgba(var(--v-theme-primary), 0.45);
    background: rgba(var(--v-theme-primary), 0.04);
  }
}

.skeleton-bone {
  background: rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-section-label {
  inline-size: 80px;
  block-size: 12px;
}

.skeleton-template-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  block-size: 136px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: var(--dnr-radius-lg);
}

.skeleton-template-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skeleton-project-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: var(--dnr-radius-lg);
}

.skeleton-project-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.skeleton-project-text {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-grow: 1;
}

.skeleton-project-footer {
  display: flex;
  justify-content: flex-end;
}

.skeleton-avatar {
  inline-size: 40px;
  block-size: 40px;
  flex-shrink: 0;
  border-radius: 10px;
}

.skeleton-avatar-sm {
  inline-size: 36px;
  block-size: 36px;
  flex-shrink: 0;
  border-radius: 8px;
}

.skeleton-chip {
  inline-size: 56px;
  block-size: 18px;
  border-radius: 10px;
}

.skeleton-line-md {
  inline-size: 65%;
  block-size: 14px;
}

.skeleton-line-sm {
  inline-size: 90%;
  block-size: 12px;
}

@keyframes skeleton-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

.empty-state__templates {
  inline-size: 100%;
  max-inline-size: 720px;
}

@media (max-width: 960px) {
  .projects-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 600px) {
  .templates-grid {
    grid-template-columns: 1fr;
  }

  .projects-grid {
    grid-template-columns: 1fr;
  }
}
</style>
