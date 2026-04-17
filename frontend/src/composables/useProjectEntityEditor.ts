import { type Ref, ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { generateProjectNameAndAvatar } from '@/utils/randomNameGenerator'
import { scopeoApi } from '@/api'
import { DEFAULT_PROJECT_COLOR } from '@/composables/useProjectDefaults'
import { useOrgTagsQuery } from '@/composables/queries/useProjectsQuery'
import { logger } from '@/utils/logger'

type ProjectListViewInstance = InstanceType<(typeof import('@/components/projects/ProjectListView.vue'))['default']>

export interface ProjectEntity {
  project_id: string
  project_name: string
  description?: string | null
  icon?: string
  icon_color?: string
  tags?: string[]
  graph_runners?: Array<{ graph_runner_id: string; env: string | null; tag_name: string | null }>
}

export interface IconSelection {
  icon: string
  iconColor: string
}

export interface UseProjectEntityEditorOptions {
  entityType: 'project' | 'agent'
  defaultIcon: string
  routePrefix: string
  createMutation: (params: { orgId: string; data: any }) => Promise<{ project_id?: string; id?: string }>
  projectListRef: Ref<ProjectListViewInstance | null>
  selectedOrgId: Ref<string | undefined>
  onError?: (error: string) => void
}

export function useProjectEntityEditor(options: UseProjectEntityEditorOptions) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { entityType, defaultIcon, routePrefix, createMutation, projectListRef, selectedOrgId, onError } = options

  const isEditDialogVisible = ref(false)
  const entityToEdit = ref<ProjectEntity | null>(null)
  const editedName = ref('')
  const editedDescription = ref('')
  const editedIconSelection = ref<IconSelection>({ icon: defaultIcon, iconColor: DEFAULT_PROJECT_COLOR })
  const editedTags = ref<string[]>([])
  const isUpdating = ref(false)
  const isCreating = ref(false)
  const editError = ref<string | null>(null)
  const createError = ref<string | null>(null)

  const { data: orgTags } = useOrgTagsQuery(selectedOrgId)

  const showError = (message: string) => {
    createError.value = message
    if (onError) {
      onError(message)
    }
    setTimeout(() => {
      createError.value = null
    }, 5000)
  }

  const openCreateDialog = async () => {
    if (!selectedOrgId.value) {
      showError('No organization selected')
      return
    }

    if (isCreating.value) {
      return
    }

    try {
      isCreating.value = true

      const avatar = generateProjectNameAndAvatar()

      const entityData = {
        [entityType === 'project' ? 'project_id' : 'id']: crypto.randomUUID(),
        [entityType === 'project' ? 'project_name' : 'name']: avatar.name,
        description: '',
        icon: avatar.icon,
        icon_color: avatar.iconColor,
      }

      const createdEntity = await createMutation({
        orgId: selectedOrgId.value,
        data: entityData,
      })

      await projectListRef.value?.refreshProjects(true)

      const entityId = createdEntity.project_id || createdEntity.id

      router.push(`/org/${selectedOrgId.value}/${routePrefix}/${entityId}`)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : `Failed to create ${entityType}`

      showError(errorMessage)
      logger.error(`Failed to create ${entityType}`, { error: err })
    } finally {
      isCreating.value = false
    }
  }

  const handleTemplateClick = async (template: ProjectEntity) => {
    if (!selectedOrgId.value) {
      showError('No organization selected')
      return
    }

    if (isCreating.value) {
      return
    }

    try {
      isCreating.value = true

      const entityData = {
        [entityType === 'project' ? 'project_id' : 'id']: crypto.randomUUID(),
        [entityType === 'project' ? 'project_name' : 'name']: `${template.project_name} (from template)`,
        description: template.description || '',
        icon: template.icon,
        icon_color: template.icon_color,
        template: {
          template_graph_runner_id: template.graph_runners?.[0]?.graph_runner_id || null,
          template_project_id: template.project_id,
        },
      }

      const createdEntity = await createMutation({
        orgId: selectedOrgId.value,
        data: entityData,
      })

      await projectListRef.value?.refreshProjects(true)

      const entityId = createdEntity.project_id || createdEntity.id

      router.push(`/org/${selectedOrgId.value}/${routePrefix}/${entityId}`)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : `Failed to create ${entityType} from template`

      showError(errorMessage)
      logger.error(`Failed to create ${entityType} from template`, { error: err })
    } finally {
      isCreating.value = false
    }
  }

  const openEditModal = (entity: ProjectEntity) => {
    entityToEdit.value = entity
    editedName.value = entity.project_name
    editedDescription.value = entity.description || ''
    editedIconSelection.value = {
      icon: entity.icon || defaultIcon,
      iconColor: entity.icon_color || DEFAULT_PROJECT_COLOR,
    }
    editedTags.value = [...(entity.tags || [])]
    editError.value = null
    isEditDialogVisible.value = true
  }

  const tagsChanged = () => {
    const original = [...(entityToEdit.value?.tags || [])].sort()
    const current = [...editedTags.value].sort()
    return JSON.stringify(original) !== JSON.stringify(current)
  }

  const saveEntity = async () => {
    if (!entityToEdit.value || !editedName.value.trim()) {
      editError.value = `${entityType === 'project' ? 'Project' : 'Agent'} name cannot be empty`
      return
    }

    const hasChanges =
      editedName.value !== entityToEdit.value.project_name ||
      editedDescription.value !== (entityToEdit.value.description || '') ||
      editedIconSelection.value.icon !== entityToEdit.value.icon ||
      editedIconSelection.value.iconColor !== entityToEdit.value.icon_color ||
      tagsChanged()

    if (!hasChanges) {
      isEditDialogVisible.value = false
      return
    }

    try {
      isUpdating.value = true
      editError.value = null

      const normalizedTags = editedTags.value.map(t => t.toLowerCase().trim()).filter(Boolean)

      await scopeoApi.projects.updateProject(entityToEdit.value.project_id, {
        project_name: editedName.value.trim(),
        description: editedDescription.value.trim() || undefined,
        icon: editedIconSelection.value.icon,
        icon_color: editedIconSelection.value.iconColor,
        tags: normalizedTags,
      })

      if (tagsChanged()) {
        queryClient.invalidateQueries({ queryKey: ['org-tags'] })
      }

      isEditDialogVisible.value = false
      await projectListRef.value?.refreshProjects(true)
    } catch (err: unknown) {
      logger.error(`Error updating ${entityType}`, { error: err })
      editError.value = err instanceof Error ? err.message : `Failed to update ${entityType}`
    } finally {
      isUpdating.value = false
    }
  }

  return {
    isEditDialogVisible,
    entityToEdit,
    editedName,
    editedDescription,
    editedIconSelection,
    editedTags,
    orgTags,
    isUpdating,
    isCreating,
    editError,
    createError,
    openCreateDialog,
    handleTemplateClick,
    openEditModal,
    saveEntity,
  }
}
