<script setup lang="ts">
import { computed, ref } from 'vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import InfoPopover from '@/components/shared/InfoPopover.vue'
import { useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import {
  type VariableDefinition,
  useDeleteOrgVariableDefinitionMutation,
  useOrgVariableDefinitionsQuery,
  useUpsertOrgVariableDefinitionMutation,
} from '@/composables/queries/useVariableDefinitionsQuery'
import {
  type VariableSet,
  useDeleteVariableSetMutation,
  useUpsertVariableSetMutation,
  useVariableSetsQuery,
} from '@/composables/queries/useVariableSetsQuery'
import { logger } from '@/utils/logger'

const props = defineProps<{
  orgId: string
}>()

const orgIdRef = computed(() => props.orgId)

const { data: orgDefinitions } = useOrgVariableDefinitionsQuery(orgIdRef)
const upsertMutation = useUpsertOrgVariableDefinitionMutation(orgIdRef)
const deleteMutation = useDeleteOrgVariableDefinitionMutation(orgIdRef)

const { data: orgProjects } = useProjectsQuery(orgIdRef)

const projectMap = computed(() => {
  const map = new Map<string, string>()
  for (const p of orgProjects.value ?? []) {
    map.set(p.project_id, p.project_name)
  }
  return map
})

const projectItems = computed(() =>
  (orgProjects.value ?? []).map(p => ({ title: p.project_name, value: p.project_id }))
)

// Additive-only editing: locked projects can't be removed
const lockedProjectIds = ref<string[]>([])

const editableProjectItems = computed(() =>
  (orgProjects.value ?? [])
    .filter(p => !lockedProjectIds.value.includes(p.project_id))
    .map(p => ({ title: p.project_name, value: p.project_id }))
)

// Show all definitions except integration-managed oauth (those have a default_value and belong in the integration tab)
const definitions = computed(() =>
  ((orgDefinitions.value as VariableDefinition[] | undefined) ?? []).filter(
    d => !(d.type === 'oauth' && d.default_value)
  )
)

const hasDefinitions = computed(() => definitions.value.length > 0)
const definedNames = computed(() => new Set(definitions.value.map(d => d.name)))

const variableTypeOptions = ['string', 'number', 'boolean', 'oauth', 'secret']

// Dialog state
const dialog = ref(false)
const editingDef = ref<VariableDefinition | null>(null)

const providerOptions = [
  { title: 'Gmail', value: 'google-mail' },
  { title: 'Slack', value: 'slack' },
  { title: 'HubSpot', value: 'hubspot' },
]

const form = ref({
  name: '',
  type: 'string' as string,
  default_value: '',
  description: '',
  project_ids: [] as string[],
  provider: '',
})

const nameRules = [
  (v: string) => !!v || 'Name is required',
  (v: string) => /^\w+$/.test(v) || 'Only letters, numbers, and underscores allowed',
]

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Type', key: 'type', sortable: true },
  { title: 'Default', key: 'default_value', sortable: false },
  { title: 'Projects', key: 'project_ids', sortable: false },
  { title: 'Description', key: 'description', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

// Delete state
const deleteDialog = ref(false)
const defToDelete = ref('')

type VariableSetFormValue = string | boolean | { has_value: boolean }

function getProviderConfigKey(metadata: VariableDefinition['metadata']): string {
  if (!metadata || typeof metadata !== 'object') return ''
  const provider = (metadata as Record<string, unknown>).provider_config_key
  return typeof provider === 'string' ? provider : ''
}

function openAddDialog() {
  editingDef.value = null
  lockedProjectIds.value = []
  form.value = { name: '', type: 'string', default_value: '', description: '', project_ids: [], provider: '' }
  dialog.value = true
}

function openEditDialog(defn: VariableDefinition) {
  editingDef.value = defn
  lockedProjectIds.value = defn.project_ids ? [...defn.project_ids] : []
  form.value = {
    name: defn.name,
    type: defn.type,
    default_value: defn.type === 'secret' ? '' : defn.default_value || '',
    description: defn.description || '',
    project_ids: [],
    provider: getProviderConfigKey(defn.metadata),
  }
  dialog.value = true
}

async function save() {
  if (!form.value.name || !/^\w+$/.test(form.value.name)) return

  let mergedProjectIds: string[]
  if (editingDef.value) {
    // Re-read latest from query data to avoid stale locked IDs
    const latestDef = definitions.value.find(d => d.name === editingDef.value!.name)
    const currentLocked = latestDef?.project_ids ?? lockedProjectIds.value

    mergedProjectIds = [...currentLocked, ...form.value.project_ids]
  } else {
    mergedProjectIds = form.value.project_ids
  }

  try {
    const data: Record<string, any> = {
      type: form.value.type,
      default_value: form.value.type === 'oauth' ? null : form.value.default_value || null,
      description: form.value.description || null,
    }

    if (form.value.type === 'oauth' && form.value.provider) {
      data.metadata = { provider_config_key: form.value.provider }
    }

    await upsertMutation.mutateAsync({
      name: form.value.name,
      data,
      projectIds: mergedProjectIds.length > 0 ? mergedProjectIds : undefined,
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

  try {
    await deleteMutation.mutateAsync({ name: defToDelete.value })
    defToDelete.value = ''
    deleteDialog.value = false
  } catch (error) {
    logger.error('Failed to delete variable definition', { error })
  }
}

// ─── Variable Sets ───────────────────────────────────────────────────────────

const showVariableSets = ref(false)

const { data: setsData, isLoading: setsLoading } = useVariableSetsQuery(orgIdRef)
const upsertSetMutation = useUpsertVariableSetMutation(orgIdRef)
const deleteSetMutation = useDeleteVariableSetMutation(orgIdRef)

const variableSets = computed(() => setsData.value?.variable_sets ?? [])

// Set dialog state
const setDialog = ref(false)
const editingSet = ref<VariableSet | null>(null)

const setForm = ref({
  set_id: '',
  values: {} as Record<string, VariableSetFormValue>,
  selectedVarNames: [] as string[],
})

// Autocomplete picker for variable sets
const autocompleteSearch = ref<string | null>(null)

const availableDefinitions = computed(() =>
  definitions.value.filter(d => !setForm.value.selectedVarNames.includes(d.name))
)

const selectedDefinitions = computed(() =>
  setForm.value.selectedVarNames
    .map(name => definitions.value.find(d => d.name === name))
    .filter((d): d is VariableDefinition => !!d)
)

function addVarToSet(name: string | null) {
  if (!name) return
  if (!setForm.value.selectedVarNames.includes(name)) {
    setForm.value.selectedVarNames.push(name)
  }
  autocompleteSearch.value = null
}

function removeVarFromSet(name: string) {
  setForm.value.selectedVarNames = setForm.value.selectedVarNames.filter(n => n !== name)
  delete setForm.value.values[name]
}

const canSaveSet = computed(
  () =>
    !!setForm.value.set_id &&
    setIdPattern.test(setForm.value.set_id) &&
    hasDefinitions.value &&
    selectedDefinitions.value.length > 0
)

const setIdPattern = /^[\w-]+$/

const setIdRules = [
  (v: string) => !!v || 'Set Name is required',
  (v: string) => setIdPattern.test(v) || 'Only letters, numbers, underscores, and hyphens allowed',
]

const setHeaders = [
  { title: 'Set Name', key: 'set_id', sortable: true },
  { title: 'Values', key: 'values', sortable: false },
  { title: 'Updated', key: 'updated_at', sortable: true },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

// Set delete dialog state
const setDeleteDialog = ref(false)
const setToDelete = ref('')

function openAddSetDialog() {
  editingSet.value = null
  setForm.value = {
    set_id: '',
    values: {},
    selectedVarNames: [],
  }
  autocompleteSearch.value = null
  setDialog.value = true
}

function openEditSetDialog(set: VariableSet) {
  editingSet.value = set

  const parsedValues: Record<string, VariableSetFormValue> = {}
  for (const [key, val] of Object.entries(set.values || {})) {
    const defn = definitions.value.find(d => d.name === key)
    if (defn?.type === 'secret') {
      parsedValues[key] = ''
    } else if (defn?.type === 'boolean') {
      parsedValues[key] = typeof val === 'string' ? val === 'true' : false
    } else {
      parsedValues[key] = typeof val === 'string' ? val : ''
    }
  }
  setForm.value = {
    set_id: set.set_id,
    values: parsedValues,
    selectedVarNames: Object.keys(set.values || {}).filter(k => definedNames.value.has(k)),
  }
  autocompleteSearch.value = null
  setDialog.value = true
}

function buildSetValues(): Record<string, string | null> {
  const values: Record<string, string | null> = {}
  for (const defn of selectedDefinitions.value) {
    const val = setForm.value.values[defn.name]
    if (defn.type === 'secret') {
      values[defn.name] = typeof val === 'string' && val !== '' ? val : null
    } else if (val !== undefined && val !== '' && typeof val !== 'object') {
      values[defn.name] = String(val)
    }
  }
  return values
}

async function saveSet() {
  if (!setForm.value.set_id || !setIdPattern.test(setForm.value.set_id)) return
  if (!hasDefinitions.value) return
  const values = buildSetValues()

  try {
    await upsertSetMutation.mutateAsync({ setId: setForm.value.set_id, values })
    setDialog.value = false
  } catch (error) {
    logger.error('Failed to save variable set', { error })
  }
}

function confirmDeleteSet(setId: string) {
  setToDelete.value = setId
  setDeleteDialog.value = true
}

async function doDeleteSet() {
  if (!setToDelete.value) return

  try {
    await deleteSetMutation.mutateAsync({ setId: setToDelete.value })
    setToDelete.value = ''
    setDeleteDialog.value = false
  } catch (error) {
    logger.error('Failed to delete variable set', { error })
  }
}

function valuesCount(values: Record<string, string | boolean | { has_value: boolean }>): number {
  return Object.keys(values || {}).filter(k => definedNames.value.has(k)).length
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getDefinitionHint(defn: VariableDefinition): string {
  const parts: string[] = []
  if (defn.description) parts.push(defn.description)
  if (defn.required) parts.push('Required')
  if (defn.default_value) parts.push(defn.type === 'secret' ? 'Default: ••••••••' : `Default: ${defn.default_value}`)
  const meta = defn.metadata || {}
  if (meta.min !== undefined || meta.max !== undefined) {
    const range = [meta.min !== undefined ? `min: ${meta.min}` : '', meta.max !== undefined ? `max: ${meta.max}` : '']
      .filter(Boolean)
      .join(', ')

    parts.push(range)
  }
  return parts.join(' · ')
}
</script>

<template>
  <div class="org-variable-definitions">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <div class="d-flex align-center gap-2">
          <h3 class="text-h5">Variables</h3>
          <InfoPopover
            text="Variables are reusable named values that workflows can reference via @ autocomplete. Defining them here makes them available organization-wide across all projects and workflows."
          />
        </div>
        <p class="text-body-2 text-medium-emphasis">
          Manage variable definitions. Global variables are available to all projects; project-scoped variables only to
          their assigned projects.
        </p>
      </div>
      <VBtn color="primary" prepend-icon="tabler-plus" @click="openAddDialog"> Add Variable </VBtn>
    </div>

    <EmptyState
      v-if="definitions.length === 0"
      icon="tabler-variable"
      title="No organization variables yet"
      description="Add variables so workflows can reference them via @ autocomplete."
    />

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
        <span class="text-medium-emphasis">{{
          item.type === 'secret' ? (item.has_default_value ? '••••••••' : '—') : item.default_value || '—'
        }}</span>
      </template>
      <template #item.project_ids="{ item }">
        <template v-if="item.project_ids && item.project_ids.length > 0">
          <VChip v-for="pid in item.project_ids" :key="pid" size="small" variant="tonal" color="info" class="me-1">
            {{ projectMap.get(pid) || pid.slice(0, 8) }}
          </VChip>
        </template>
        <span v-else class="text-medium-emphasis">Global</span>
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

    <!-- Variable Sets Section -->
    <div class="mt-6">
      <div
        class="d-flex align-center justify-space-between variable-sets-header pa-3 rounded"
        style="cursor: pointer"
        @click="showVariableSets = !showVariableSets"
      >
        <div class="d-flex align-center gap-2">
          <VIcon :icon="showVariableSets ? 'tabler-chevron-down' : 'tabler-chevron-right'" size="20" />
          <span class="text-subtitle-1 font-weight-medium">Variable Sets</span>
          <InfoPopover
            text='Variable sets are named groups of values for your defined variables — e.g. a "production" set and a "staging" set, each providing different values for the same variables. They get injected at workflow runtime.'
          />
          <VChip size="x-small" variant="tonal" color="primary">{{ variableSets.length }}</VChip>
        </div>
        <VBtn color="primary" size="small" prepend-icon="tabler-plus" @click.stop="openAddSetDialog"> Add Set </VBtn>
      </div>

      <div v-if="showVariableSets" class="mt-3">
        <!-- Loading -->
        <div v-if="setsLoading" class="pa-6 text-center">
          <VProgressCircular indeterminate color="primary" />
        </div>

        <!-- Empty -->
        <EmptyState
          v-else-if="variableSets.length === 0"
          icon="tabler-stack-2"
          title="No variable sets yet"
          description='Click "Add Set" to create named sets of values for your variables.'
        />

        <!-- Data Table -->
        <VDataTable
          v-else
          :headers="setHeaders"
          :items="variableSets"
          :items-per-page="-1"
          density="comfortable"
          class="elevation-1"
        >
          <template #item.values="{ item }">
            <VChip size="small" color="primary" variant="tonal">
              {{ valuesCount(item.values) }} {{ valuesCount(item.values) === 1 ? 'value' : 'values' }}
            </VChip>
          </template>
          <template #item.updated_at="{ item }">
            <span class="text-medium-emphasis">{{ formatDate(item.updated_at) }}</span>
          </template>
          <template #item.actions="{ item }">
            <VBtn icon variant="text" size="small" @click="openEditSetDialog(item)">
              <VIcon icon="tabler-edit" size="18" />
            </VBtn>
            <VBtn icon variant="text" size="small" color="error" @click="confirmDeleteSet(item.set_id)">
              <VIcon icon="tabler-trash" size="18" />
            </VBtn>
          </template>
          <template #bottom />
        </VDataTable>
      </div>
    </div>

    <!-- Add/Edit Variable Dialog -->
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
            class="mb-4"
          />

          <VSelect v-model="form.type" :items="variableTypeOptions" label="Type" class="mb-4" />

          <VSelect
            v-if="form.type === 'oauth'"
            v-model="form.provider"
            :items="providerOptions"
            label="Provider"
            class="mb-4"
          />

          <VTextField
            v-if="form.type !== 'oauth'"
            v-model="form.default_value"
            :type="form.type === 'secret' ? 'password' : 'text'"
            :placeholder="
              form.type === 'secret' && editingDef?.has_default_value ? 'Already set — leave blank to keep' : ''
            "
            label="Default Value"
            class="mb-4"
          />

          <VTextField v-model="form.description" label="Description (optional)" class="mb-4" />

          <!-- Editing: show locked chips + additive autocomplete -->
          <template v-if="editingDef">
            <div v-if="lockedProjectIds.length > 0" class="mb-2">
              <VChip
                v-for="pid in lockedProjectIds"
                :key="pid"
                size="small"
                variant="tonal"
                color="info"
                class="me-1 mb-1"
                prepend-icon="tabler-lock"
              >
                {{ projectMap.get(pid) || pid.slice(0, 8) }}
              </VChip>
            </div>
            <VAutocomplete
              v-model="form.project_ids"
              :items="editableProjectItems"
              label="Add projects"
              hint="Existing projects cannot be removed. You can add more."
              persistent-hint
              multiple
              chips
              closable-chips
              clearable
            />
          </template>

          <!-- Creating: standard full autocomplete -->
          <VAutocomplete
            v-else
            v-model="form.project_ids"
            :items="projectItems"
            label="Projects (optional)"
            hint="Leave empty for a global variable available to all projects"
            persistent-hint
            multiple
            chips
            closable-chips
            clearable
          />
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="text" @click="dialog = false"> Cancel </VBtn>
          <VBtn color="primary" variant="elevated" :loading="upsertMutation.isPending.value" @click="save"> Save </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete Variable Confirmation -->
    <GenericConfirmDialog
      :is-dialog-visible="deleteDialog"
      title="Delete Variable"
      :message="`Are you sure you want to delete the variable <strong>${defToDelete}</strong>? Workflows referencing this variable will no longer resolve it.`"
      confirm-text="Delete"
      confirm-color="error"
      :loading="deleteMutation.isPending.value"
      @update:is-dialog-visible="deleteDialog = $event"
      @confirm="doDelete"
      @cancel="deleteDialog = false"
    />

    <!-- Add/Edit Variable Set Dialog -->
    <VDialog v-model="setDialog" max-width="var(--dnr-dialog-md)" persistent>
      <VCard>
        <VCardTitle class="text-h6">
          {{ editingSet ? 'Edit Variable Set' : 'Add Variable Set' }}
        </VCardTitle>

        <VCardText>
          <VTextField
            v-model="setForm.set_id"
            label="Set Name"
            :rules="setIdRules"
            :disabled="!!editingSet"
            hint="Unique name for this set"
            persistent-hint
            class="mb-4"
          />

          <!-- No definitions warning -->
          <VAlert v-if="!hasDefinitions" type="warning" variant="tonal" class="mb-4">
            No variable definitions found. Define variables first before adding values to a set.
          </VAlert>

          <!-- Variable picker for set -->
          <template v-if="hasDefinitions">
            <div class="text-subtitle-2 mb-2">Variables belonging to the set</div>

            <VAutocomplete
              v-model="autocompleteSearch"
              :items="availableDefinitions"
              item-title="name"
              item-value="name"
              label="Add a variable..."
              clearable
              no-data-text="No more variables to add"
              class="mb-3"
              @update:model-value="addVarToSet"
            />

            <template v-for="defn in selectedDefinitions" :key="defn.name">
              <div class="d-flex align-center gap-2 mb-3">
                <div class="flex-grow-1">
                  <!-- Secret -->
                  <VTextField
                    v-if="defn.type === 'secret'"
                    v-model="setForm.values[defn.name]"
                    type="password"
                    :label="defn.name + (defn.required ? ' *' : '')"
                    :placeholder="
                      (editingSet?.values[defn.name] as any)?.has_value ? 'Already set — leave blank to keep' : ''
                    "
                    :hint="getDefinitionHint(defn)"
                    persistent-hint
                    hide-details="auto"
                  />

                  <!-- String -->
                  <VTextField
                    v-else-if="defn.type === 'string'"
                    v-model="setForm.values[defn.name]"
                    :label="defn.name + (defn.required ? ' *' : '')"
                    :hint="getDefinitionHint(defn)"
                    persistent-hint
                    hide-details="auto"
                  />

                  <!-- Number -->
                  <VTextField
                    v-else-if="defn.type === 'number'"
                    v-model="setForm.values[defn.name]"
                    type="number"
                    :label="defn.name + (defn.required ? ' *' : '')"
                    :hint="getDefinitionHint(defn)"
                    persistent-hint
                    hide-details="auto"
                  />

                  <!-- OAuth -->
                  <VTextField
                    v-else-if="defn.type === 'oauth'"
                    v-model="setForm.values[defn.name]"
                    :label="defn.name + (defn.required ? ' *' : '')"
                    :hint="getDefinitionHint(defn)"
                    placeholder="OAuth Connection ID"
                    persistent-hint
                    hide-details="auto"
                  />

                  <!-- Boolean -->
                  <VSwitch
                    v-else
                    v-model="setForm.values[defn.name]"
                    :label="defn.name + (defn.required ? ' *' : '')"
                    color="primary"
                    :hint="getDefinitionHint(defn)"
                    persistent-hint
                    hide-details="auto"
                  />
                </div>
                <VBtn icon variant="text" size="small" color="error" @click="removeVarFromSet(defn.name)">
                  <VIcon icon="tabler-x" size="18" />
                </VBtn>
              </div>
            </template>
          </template>
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="text" @click="setDialog = false"> Cancel </VBtn>
          <VBtn
            color="primary"
            variant="elevated"
            :loading="upsertSetMutation.isPending.value"
            :disabled="!canSaveSet"
            @click="saveSet"
          >
            Save
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete Variable Set Confirmation -->
    <GenericConfirmDialog
      :is-dialog-visible="setDeleteDialog"
      title="Delete Variable Set"
      :message="`Are you sure you want to delete the variable set <strong>${setToDelete}</strong>? This action cannot be undone.`"
      confirm-text="Delete"
      confirm-color="error"
      :loading="deleteSetMutation.isPending.value"
      @update:is-dialog-visible="setDeleteDialog = $event"
      @confirm="doDeleteSet"
      @cancel="setDeleteDialog = false"
    />
  </div>
</template>

<style scoped>
.org-variable-definitions {
  padding: 24px;
}

.variable-sets-header {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
