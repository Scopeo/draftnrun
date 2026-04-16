<script setup lang="ts">
import { computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import {
  type VariableDefinition,
  useOrgVariableDefinitionsQuery,
  useUpsertOrgVariableDefinitionMutation,
} from '@/composables/queries/useVariableDefinitionsQuery'

const props = defineProps<{
  projectId: string
  orgId: string
}>()

const orgIdRef = computed(() => props.orgId)

const { data: orgDefinitions } = useOrgVariableDefinitionsQuery(orgIdRef)
const upsertMutation = useUpsertOrgVariableDefinitionMutation(orgIdRef)

// Definitions visible on this project: scoped to this project + global (no project_ids)
const definitions = computed(() =>
  ((orgDefinitions.value as VariableDefinition[] | undefined) ?? []).filter(
    d => !d.project_ids || d.project_ids.length === 0 || d.project_ids.includes(props.projectId)
  )
)

const variableTypeOptions = ['string', 'number', 'boolean', 'oauth']

// Dialog state
const dialog = ref(false)
const editingDef = ref<VariableDefinition | null>(null)

const form = ref({
  name: '',
  type: 'string' as string,
  default_value: '',
  description: '',
})

const nameRules = [
  (v: string) => !!v || 'Name is required',
  (v: string) => /^\w+$/.test(v) || 'Only letters, numbers, and underscores allowed',
]

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Type', key: 'type', sortable: true },
  { title: 'Default', key: 'default_value', sortable: false },
  { title: 'Description', key: 'description', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

// Delete state
const deleteDialog = ref(false)
const defToDelete = ref('')

const deleteMessage = computed(() => {
  const defn = (orgDefinitions.value as VariableDefinition[] | undefined)?.find(d => d.name === defToDelete.value)
  const otherProjects = (defn?.project_ids ?? []).filter(id => id !== props.projectId).length
  if (otherProjects === 0) {
    return `Are you sure you want to remove <strong>${defToDelete.value}</strong> from this project? It is the only project — the variable will become <strong>global</strong> (available to all projects).`
  }
  return `Are you sure you want to remove <strong>${defToDelete.value}</strong> from this project? The variable will still exist in the organization.`
})

function openAddDialog() {
  editingDef.value = null
  form.value = { name: '', type: 'string', default_value: '', description: '' }
  dialog.value = true
}

function openEditDialog(defn: VariableDefinition) {
  editingDef.value = defn
  form.value = {
    name: defn.name,
    type: defn.type,
    default_value: defn.default_value || '',
    description: defn.description || '',
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name || !/^\w+$/.test(form.value.name)) return

  let projectIds: string[]
  if (editingDef.value) {
    // Preserve existing project associations, ensure current project is included
    const existing = editingDef.value.project_ids ?? []

    projectIds = existing.includes(props.projectId) ? [...existing] : [...existing, props.projectId]
  } else {
    projectIds = [props.projectId]
  }

  try {
    await upsertMutation.mutateAsync({
      name: form.value.name,
      data: {
        type: form.value.type,
        default_value: form.value.default_value || null,
        description: form.value.description || null,
      },
      projectIds,
    })
    dialog.value = false
  } catch (error) {
    logger.error('Failed to save variable definition', { error })
  }
}

function confirmDelete(name: string) {
  defToDelete.value = name
  deleteDialog.value = true
}

async function doDelete() {
  if (!defToDelete.value) return
  const defn = (orgDefinitions.value as VariableDefinition[] | undefined)?.find(d => d.name === defToDelete.value)
  if (!defn) return

  const remainingProjectIds = (defn.project_ids ?? []).filter(id => id !== props.projectId)

  try {
    await upsertMutation.mutateAsync({
      name: defn.name,
      data: {
        type: defn.type,
        default_value: defn.default_value || null,
        description: defn.description || null,
      },
      projectIds: remainingProjectIds,
    })
    defToDelete.value = ''
    deleteDialog.value = false
  } catch (error) {
    logger.error('Failed to remove variable from project', { error })
  }
}
</script>

<template>
  <div class="project-variable-definitions">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h3 class="text-h5">Project Variables</h3>
        <p class="text-body-2 text-medium-emphasis">Variables scoped to this project, available in its workflows.</p>
      </div>
      <VBtn color="primary" prepend-icon="tabler-plus" @click="openAddDialog"> Add Variable </VBtn>
    </div>

    <VCard v-if="definitions.length === 0" class="pa-6 text-center">
      <VCardText>
        <VIcon icon="tabler-variable" size="48" class="mb-3 text-medium-emphasis" />
        <p class="text-body-1 text-medium-emphasis">No project variables yet.</p>
        <p class="text-body-2 text-medium-emphasis">
          Add variables so workflows in this project can reference them via <code>@</code> autocomplete.
        </p>
      </VCardText>
    </VCard>

    <VDataTable
      v-else
      :headers="headers"
      :items="definitions"
      :items-per-page="-1"
      density="comfortable"
      class="elevation-1"
    >
      <template #item.type="{ item }">
        <VChip size="small" variant="tonal">{{ item.type }}</VChip>
      </template>
      <template #item.default_value="{ item }">
        <span class="text-medium-emphasis">{{ item.default_value || '—' }}</span>
      </template>
      <template #item.description="{ item }">
        <span class="text-medium-emphasis">{{ item.description || '—' }}</span>
      </template>
      <template #item.actions="{ item }">
        <VBtn icon variant="text" size="small" @click="openEditDialog(item)">
          <VIcon icon="tabler-edit" size="18" />
        </VBtn>
        <VBtn icon variant="text" size="small" color="error" @click="confirmDelete(item.name)">
          <VIcon icon="tabler-trash" size="18" />
        </VBtn>
      </template>
      <template #bottom />
    </VDataTable>

    <!-- Add/Edit Dialog -->
    <VDialog v-model="dialog" max-width="var(--dnr-dialog-sm)" persistent>
      <VCard>
        <VCardTitle class="text-h6">
          {{ editingDef ? 'Edit Variable' : 'Add Variable' }}
        </VCardTitle>

        <VCardText>
          <VTextField
            v-model="form.name"
            label="Variable Name"
            :rules="nameRules"
            :disabled="!!editingDef"
            hint="Lowercase identifier used in @{{name}} expressions"
            persistent-hint
            class="mb-4"
          />

          <VSelect v-model="form.type" :items="variableTypeOptions" label="Type" class="mb-4" />

          <VTextField
            v-model="form.default_value"
            label="Default Value"
            hint="Fallback when the configuration doesn't provide a value"
            persistent-hint
            class="mb-4"
          />

          <VTextField
            v-model="form.description"
            label="Description"
            hint="Shown in autocomplete to help users understand this variable"
            persistent-hint
          />
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="text" @click="dialog = false"> Cancel </VBtn>
          <VBtn color="primary" variant="elevated" :loading="upsertMutation.isPending.value" @click="save"> Save </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete Confirmation -->
    <GenericConfirmDialog
      :is-dialog-visible="deleteDialog"
      title="Remove Variable from Project"
      :message="deleteMessage"
      confirm-text="Remove"
      confirm-color="warning"
      :loading="upsertMutation.isPending.value"
      @update:is-dialog-visible="deleteDialog = $event"
      @confirm="doDelete"
      @cancel="deleteDialog = false"
    />
  </div>
</template>

<style scoped>
.project-variable-definitions {
  padding: 24px;
}
</style>
