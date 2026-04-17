<script setup lang="ts">
import { computed, ref } from 'vue'
import ProjectListView from '@/components/projects/ProjectListView.vue'
import IconPicker from '@/components/projects/IconPicker.vue'
import { useCreateProjectMutation } from '@/composables/queries/useProjectsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { useProjectEntityEditor } from '@/composables/useProjectEntityEditor'
import { DEFAULT_PROJECT_ICON } from '@/composables/useProjectDefaults'
import { tagColor } from '@/utils/tagColor'

const { selectedOrgId } = useSelectedOrg()

// Prefetch component definitions
useComponentDefinitionsQuery(selectedOrgId)

const projectListRef = ref<InstanceType<typeof ProjectListView> | null>(null)
const createProjectMutation = useCreateProjectMutation()

const {
  isEditDialogVisible,
  editedName: editedProjectName,
  editedDescription: editedProjectDescription,
  editedIconSelection,
  editedTags,
  orgTags,
  isUpdating: isUpdatingProject,
  isCreating,
  editError,
  createError,
  openCreateDialog,
  handleTemplateClick,
  openEditModal,
  saveEntity: saveProjectName,
} = useProjectEntityEditor({
  entityType: 'project',
  defaultIcon: DEFAULT_PROJECT_ICON,
  routePrefix: 'projects',
  createMutation: async ({ orgId, data }) => {
    return await createProjectMutation.mutateAsync({ orgId, projectData: data })
  },
  projectListRef,
  selectedOrgId,
})

const showCreateError = computed(() => createError.value !== null)

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <ProjectListView
    ref="projectListRef"
    type="WORKFLOW"
    title="Workflows"
    route-name-prefix="projects"
    :is-creating="isCreating"
    @create-click="openCreateDialog"
    @template-click="handleTemplateClick"
    @edit-click="openEditModal"
  />

  <!-- Project Edit Dialog -->
  <VDialog v-model="isEditDialogVisible" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle class="d-flex justify-space-between align-center pa-4">
        <span class="text-h5">Edit Workflow</span>
        <VBtn icon variant="text" @click="isEditDialogVisible = false">
          <VIcon>tabler-x</VIcon>
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pt-4 px-4">
        <VTextField
          v-model="editedProjectName"
          label="Workflow Name"
          variant="outlined"
          :error-messages="editError"
          autofocus
          class="mb-4"
        />

        <VTextarea
          v-model="editedProjectDescription"
          label="Description"
          variant="outlined"
          rows="3"
          placeholder="Describe what this workflow does..."
          class="mb-4"
        />

        <IconPicker v-model="editedIconSelection" />

        <VCombobox
          v-model="editedTags"
          :items="orgTags || []"
          label="Tags"
          variant="outlined"
          multiple
          chips
          closable-chips
          class="mt-4"
          placeholder="Type to add a tag…"
          hide-details
        >
          <template #chip="{ props: chipProps, item }">
            <VChip v-bind="chipProps" size="small" variant="tonal" :color="tagColor(item.raw)" label closable>
              {{ item.raw }}
            </VChip>
          </template>
        </VCombobox>
      </VCardText>

      <VCardActions class="justify-end pa-4">
        <VBtn variant="text" @click="isEditDialogVisible = false"> Cancel </VBtn>
        <VBtn color="primary" :loading="isUpdatingProject" @click="saveProjectName"> Save Changes </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Error Snackbar -->
  <VSnackbar v-model="showCreateError" :timeout="5000" color="error" location="top">
    {{ createError }}
  </VSnackbar>
</template>
