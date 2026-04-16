<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'
import { useGlobalComponentDefinitionsQuery } from '@/composables/queries/useComponentDefinitionsQuery'
import type { ComponentDefinition } from '@/components/studio/data/component-definitions'
import { RELEASE_STAGES } from '@/composables/queries/useReleaseStagesQuery'
import { logComponentMount, logComponentUnmount } from '@/utils/queryLogger'
import CreditFieldDisplay from '@/components/shared/CreditFieldDisplay.vue'
import CreditFieldsForm from '@/components/shared/CreditFieldsForm.vue'
import { convertEmptyToNull, updateCreditFields } from '@/utils/credits'
import { CREDIT_TABLE_COLUMNS } from '@/types/credits'
import { useCreditFields } from '@/composables/useCreditFields'
import {
  useComponentFieldsOptionsQuery,
  useUpdateComponentFieldsMutation,
} from '@/composables/queries/useComponentMetadataQuery'

interface Props {
  successMessage: string
  errorMessage: string
  organizationId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:successMessage': [value: string]
  'update:errorMessage': [value: string]
}>()

// Get global component definitions
const {
  components: globalComponentDefinitions,
  isLoading: globalLoading,
  refetch: fetchGlobalComponentDefinitions,
} = useGlobalComponentDefinitionsQuery()

// Get fields options (release stages, categories)
const { data: fieldsOptions, isLoading: fieldsOptionsLoading } = useComponentFieldsOptionsQuery()

// Update component fields mutation
const updateFieldsMutation = useUpdateComponentFieldsMutation()

// Component lifecycle logging
onMounted(() => {
  logComponentMount('ComponentsManager', [['global-component-definitions']])
})

onUnmounted(() => {
  logComponentUnmount('ComponentsManager')
})

const selectedComponent = ref<ComponentDefinition | null>(null)
const showComponentDrawer = ref(false)
const componentDrawerRef = ref<any>(null)
const drawerWidth = ref<number>(Math.min(Math.round(window.innerWidth * 0.6667), Math.round(window.innerWidth * 0.9)))
const maxDrawerWidth = computed(() => Math.round(window.innerWidth * 0.9))
const isResizingDrawer = ref(false)
let resizeStartX = 0
let resizeStartWidth = 0

// Delete component dialog state
const showDeleteComponentDialog = ref(false)
const deleteComponentInput = ref('')
const deleteTargetComponent = ref<ComponentDefinition | null>(null)
const deleteLoading = ref(false)
const deleteScope = ref<'version' | 'component'>('version')
const deleteDialogError = ref('')

// Update component fields dialog state
const showUpdateFieldsDialog = ref(false)
const updateFieldsTarget = ref<ComponentDefinition | null>(null)
const updateFieldsInput = ref('')
const selectedNewStage = ref<'internal' | 'early_access' | 'beta' | 'public' | ''>('')
const selectedIsAgent = ref(false)
const selectedFunctionCallable = ref(false)
const selectedCategoryIds = ref<string[]>([])
const updateFieldsLoading = ref(false)
const updateFieldsDialogError = ref('')
const updateMode = ref<'fields' | 'credits'>('fields')

// Cost form state using composable
const { creditFields: costForm, validate: validateCostForm, initialize: initializeCostForm } = useCreditFields()

const deleteCredits = ref(false)

// Enrich components with category objects mapped from category_ids
const enrichedComponents = computed(() => {
  if (!globalComponentDefinitions.value || !fieldsOptions.value?.categories) {
    return globalComponentDefinitions.value || []
  }

  return globalComponentDefinitions.value.map(component => {
    const categoryIds = (component as any).category_ids || []

    const categories = categoryIds
      .map((id: string) => fieldsOptions.value?.categories.find(cat => cat.id === id))
      .filter(Boolean)

    return {
      ...component,
      categories,
    }
  })
})

const getStageColor = (stageName: string) => {
  switch (stageName) {
    case RELEASE_STAGES.INTERNAL:
      return 'error'
    case RELEASE_STAGES.EARLY_ACCESS:
      return 'warning'
    case RELEASE_STAGES.BETA:
      return 'info'
    case RELEASE_STAGES.PUBLIC:
      return 'success'
    default:
      return 'primary'
  }
}

const loadComponents = async () => {
  await fetchGlobalComponentDefinitions()
}

const refreshComponents = async () => {
  await loadComponents()
}

const openComponentDetails = (comp: ComponentDefinition) => {
  showComponentDrawer.value = false
  selectedComponent.value = comp
  setTimeout(() => {
    showComponentDrawer.value = true
  }, 0)
}

const openDeleteComponentDialog = (comp: ComponentDefinition) => {
  logger.info('[ComponentsManager] Component data', { data: comp })
  deleteTargetComponent.value = comp
  deleteComponentInput.value = ''
  deleteScope.value = 'version'
  deleteDialogError.value = ''
  showDeleteComponentDialog.value = true
}

const canConfirmDelete = computed(() => {
  return (
    !!deleteTargetComponent.value &&
    deleteComponentInput.value.trim() === (deleteTargetComponent.value.name || '').trim()
  )
})

const confirmDeleteComponent = async () => {
  if (!deleteTargetComponent.value || !canConfirmDelete.value) return

  // Clear previous errors
  deleteDialogError.value = ''

  // Validate required IDs
  if (!deleteTargetComponent.value.component_version_id) {
    deleteDialogError.value = 'Missing component_version_id'
    return
  }
  if (!deleteTargetComponent.value.id && deleteScope.value === 'component') {
    deleteDialogError.value = 'Missing component id for deleting all versions'
    return
  }

  try {
    deleteLoading.value = true

    // Use different endpoints based on scope
    if (deleteScope.value === 'version') {
      await scopeoApi.components.deleteVersion(
        String(deleteTargetComponent.value.id),
        String(deleteTargetComponent.value.component_version_id)
      )
    } else {
      await scopeoApi.components.deleteComponent(String(deleteTargetComponent.value.id))
    }

    showDeleteComponentDialog.value = false

    // Close drawer if the deleted version is currently selected, or if deleting all versions
    if (selectedComponent.value) {
      const shouldCloseDrawer =
        deleteScope.value === 'component'
          ? selectedComponent.value.id === deleteTargetComponent.value.id
          : selectedComponent.value.component_version_id === deleteTargetComponent.value.component_version_id

      if (shouldCloseDrawer) {
        showComponentDrawer.value = false
        selectedComponent.value = null
      }
    }

    await fetchGlobalComponentDefinitions()

    const successMessage =
      deleteScope.value === 'version'
        ? `Component version ${deleteTargetComponent.value?.version_tag || 'N/A'} deleted successfully.`
        : `Component ${deleteTargetComponent.value?.name || ''} (all versions) deleted successfully.`

    emit('update:successMessage', successMessage)
  } catch (e: any) {
    const errorMsg = e?.message || 'Failed to delete component'

    deleteDialogError.value = errorMsg
    // Also emit for global error tracking
    emit('update:errorMessage', errorMsg)
  } finally {
    deleteLoading.value = false
  }
}

const openUpdateFieldsDialog = (comp: ComponentDefinition) => {
  updateFieldsTarget.value = comp
  updateFieldsInput.value = ''
  selectedNewStage.value = (comp.release_stage as any) || ''
  selectedIsAgent.value = (comp as any).is_agent || false
  selectedFunctionCallable.value = comp.function_callable || false
  selectedCategoryIds.value = ((comp as any).category_ids as string[]) || []
  updateFieldsDialogError.value = ''
  updateMode.value = 'fields' // Default to fields mode
  deleteCredits.value = false
  // Initialize cost form with current values
  initializeCostForm(comp)
  showUpdateFieldsDialog.value = true
}

const canConfirmUpdateFields = computed(() => {
  if (!updateFieldsTarget.value) return false

  // For both fields and credits mode, we just need name match
  return updateFieldsInput.value.trim() === (updateFieldsTarget.value.name || '').trim()
})

const confirmUpdateFields = async () => {
  if (!updateFieldsTarget.value || !canConfirmUpdateFields.value) return

  // Clear previous errors
  updateFieldsDialogError.value = ''

  // Validate required IDs
  if (!updateFieldsTarget.value.id) {
    updateFieldsDialogError.value = 'Missing component id'
    return
  }
  if (!updateFieldsTarget.value.component_version_id) {
    updateFieldsDialogError.value = 'Missing component_version_id'
    return
  }

  try {
    updateFieldsLoading.value = true

    if (updateMode.value === 'fields') {
      // Update fields (release stage, is_agent, function_callable, categories)
      await updateFieldsMutation.mutateAsync({
        componentId: String(updateFieldsTarget.value.id),
        componentVersionId: String(updateFieldsTarget.value.component_version_id),
        data: {
          release_stage: selectedNewStage.value,
          is_agent: selectedIsAgent.value,
          function_callable: selectedFunctionCallable.value,
          category_ids: selectedCategoryIds.value,
        },
      })

      showUpdateFieldsDialog.value = false
      if (
        selectedComponent.value &&
        selectedComponent.value.component_version_id === updateFieldsTarget.value.component_version_id
      ) {
        selectedComponent.value.release_stage = selectedNewStage.value as any
        selectedComponent.value.function_callable = selectedFunctionCallable.value
        ;(selectedComponent.value as any).is_agent = selectedIsAgent.value
        ;(selectedComponent.value as any).category_ids = selectedCategoryIds.value
      }
      await fetchGlobalComponentDefinitions()
      emit('update:successMessage', `Fields for ${updateFieldsTarget.value?.name || ''} updated successfully.`)
    } else {
      // Update or delete credits
      if (!props.organizationId) {
        updateFieldsDialogError.value = 'Organization ID is required to update costs'
        return
      }

      if (deleteCredits.value) {
        // Delete credits
        await scopeoApi.components.deleteCosts(
          props.organizationId,
          String(updateFieldsTarget.value.component_version_id)
        )

        showUpdateFieldsDialog.value = false
        if (
          selectedComponent.value &&
          selectedComponent.value.component_version_id === updateFieldsTarget.value.component_version_id
        ) {
          updateCreditFields(selectedComponent.value, null)
        }
        await fetchGlobalComponentDefinitions()
        emit('update:successMessage', `Credits for ${updateFieldsTarget.value?.name || ''} deleted successfully.`)
      } else {
        // Validate credit fields before updating
        if (!validateCostForm()) {
          updateFieldsDialogError.value = 'Invalid credit values. All values must be non-negative.'
          return
        }

        // Update credits
        await scopeoApi.components.updateCosts(
          props.organizationId,
          String(updateFieldsTarget.value.component_version_id),
          {
            credits_per_call: convertEmptyToNull(costForm.value.credits_per_call),
            credits_per: costForm.value.credits_per,
          }
        )

        showUpdateFieldsDialog.value = false
        if (
          selectedComponent.value &&
          selectedComponent.value.component_version_id === updateFieldsTarget.value.component_version_id
        ) {
          updateCreditFields(selectedComponent.value, costForm.value)
        }
        await fetchGlobalComponentDefinitions()
        emit('update:successMessage', `Credits for ${updateFieldsTarget.value?.name || ''} updated successfully.`)
      }
    }
  } catch (e: any) {
    const errorMsg =
      e?.message || (updateMode.value === 'fields' ? 'Failed to update fields' : 'Failed to update credits')

    updateFieldsDialogError.value = errorMsg
    // Also emit for global error tracking
    emit('update:errorMessage', errorMsg)
  } finally {
    updateFieldsLoading.value = false
  }
}

const onResizeStart = (e: MouseEvent) => {
  isResizingDrawer.value = true
  resizeStartX = e.clientX
  resizeStartWidth = drawerWidth.value
  window.addEventListener('mousemove', onResizing)
  window.addEventListener('mouseup', onResizeEnd)
}

const onResizing = (e: MouseEvent) => {
  const delta = resizeStartX - e.clientX
  const next = Math.min(Math.max(resizeStartWidth + delta, 360), Math.round(window.innerWidth * 0.9))

  drawerWidth.value = next
}

const onResizeEnd = () => {
  isResizingDrawer.value = false
  window.removeEventListener('mousemove', onResizing)
  window.removeEventListener('mouseup', onResizeEnd)
}

onMounted(async () => {
  await loadComponents()
  window.addEventListener('resize', () => {
    drawerWidth.value = Math.min(drawerWidth.value, Math.round(window.innerWidth * 0.9))
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onResizing)
  window.removeEventListener('mouseup', onResizeEnd)
})
</script>

<template>
  <VCard>
    <VCardTitle class="d-flex align-center justify-space-between">
      <span>Available Components</span>
      <div class="d-flex gap-2">
        <VBtn color="primary" :loading="globalLoading" @click="refreshComponents">
          <VIcon icon="tabler-refresh" class="me-2" />
          Refresh
        </VBtn>
      </div>
    </VCardTitle>
    <VDivider />
    <VCardText>
      <VDataTable
        :items="enrichedComponents"
        :loading="globalLoading || fieldsOptionsLoading"
        item-value="component_version_id"
        :items-per-page="50"
        :headers="[
          { title: 'Name', key: 'name' },
          { title: 'Version', key: 'version_tag' },
          { title: 'Release Stage', key: 'release_stage' },
          { title: 'Is Agent', key: 'is_agent' },
          { title: 'Function Callable', key: 'function_callable' },
          { title: 'Categories', key: 'categories' },
          ...CREDIT_TABLE_COLUMNS,
          { title: 'Actions', key: 'actions', sortable: false },
        ]"
        :sort-by="[
          { key: 'name', order: 'asc' },
          { key: 'version_tag', order: 'desc' },
        ]"
        hover
        @click:row="(e: MouseEvent, r: any) => openComponentDetails(r.item as any)"
      >
        <template #item.version_tag="{ item }">
          <VChip size="small" color="primary" variant="tonal">
            {{ item.version_tag || item.component_version_id?.substring(0, 8) || 'N/A' }}
          </VChip>
        </template>
        <template #item.release_stage="{ item }">
          <VChip :color="getStageColor(String(item.release_stage))" size="small">
            {{ String(item.release_stage).replace('_', ' ').toUpperCase() }}
          </VChip>
        </template>
        <template #item.is_agent="{ item }">
          <VChip :color="(item as any).is_agent ? 'success' : 'grey'" size="small">
            {{ (item as any).is_agent ? 'Yes' : 'No' }}
          </VChip>
        </template>
        <template #item.function_callable="{ item }">
          <VChip :color="item.function_callable ? 'success' : 'grey'" size="small">
            {{ item.function_callable ? 'Yes' : 'No' }}
          </VChip>
        </template>
        <template #item.categories="{ item }">
          <div v-if="(item as any).categories && (item as any).categories.length > 0" class="d-flex flex-wrap gap-1">
            <VChip
              v-for="category in (item as any).categories"
              :key="category.id"
              size="small"
              color="primary"
              variant="tonal"
            >
              {{ category.name }}
            </VChip>
          </div>
          <span v-else class="text-medium-emphasis text-caption">—</span>
        </template>
        <template #item.credits_per_call="{ item }">
          <CreditFieldDisplay :value="item.credits_per_call" />
        </template>
        <template #item.credits_per="{ item }">
          <CreditFieldDisplay :value="item.credits_per" />
        </template>
        <template #item.actions="{ item }">
          <VBtn icon="tabler-edit" size="small" variant="text" @click.stop="openUpdateFieldsDialog(item as any)" />
          <VBtn
            icon="tabler-trash"
            size="small"
            variant="text"
            color="error"
            @click.stop="openDeleteComponentDialog(item as any)"
          />
        </template>
        <template #no-data>
          <EmptyState size="sm" icon="tabler-puzzle" title="No components found" />
        </template>
      </VDataTable>
    </VCardText>
  </VCard>

  <!-- Right Drawer for Component Details -->
  <VNavigationDrawer
    v-if="showComponentDrawer"
    ref="componentDrawerRef"
    v-model="showComponentDrawer"
    location="end"
    temporary
    class="scrollable-content"
    :style="{ width: `${drawerWidth}px`, maxWidth: `${maxDrawerWidth}px` }"
    :scrim="true"
    @update:model-value="
      (val: boolean) => {
        if (!val) {
          selectedComponent = null
          showComponentDrawer = false
        }
      }
    "
  >
    <VCard flat>
      <VCardTitle class="d-flex align-center justify-space-between">
        <div class="d-flex align-center">
          <VIcon icon="tabler-cube" class="me-2" />
          <span>{{ selectedComponent?.name || 'Component' }}</span>
        </div>
        <VBtn icon="tabler-x" variant="text" @click="showComponentDrawer = false" />
      </VCardTitle>
      <VDivider />
      <div class="resize-handle" @mousedown="onResizeStart"></div>
      <VCardText>
        <div class="mb-4 d-flex flex-wrap gap-2">
          <VChip size="small" :color="getStageColor(String(selectedComponent?.release_stage || 'public'))">
            Stage:
            {{
              String(selectedComponent?.release_stage || 'public')
                .replace('_', ' ')
                .toUpperCase()
            }}
          </VChip>
          <VChip size="small" :color="(selectedComponent as any)?.is_agent ? 'success' : 'grey'">
            Is Agent: {{ (selectedComponent as any)?.is_agent ? 'Yes' : 'No' }}
          </VChip>
        </div>
        <div
          v-if="(selectedComponent as any)?.categories && (selectedComponent as any).categories.length > 0"
          class="mb-4"
        >
          <div class="text-caption text-medium-emphasis mb-2">Categories</div>
          <div class="d-flex flex-wrap gap-2">
            <VChip
              v-for="category in (selectedComponent as any).categories"
              :key="category.id"
              size="small"
              color="primary"
              variant="tonal"
            >
              {{ category.name }}
            </VChip>
          </div>
        </div>
        <div v-if="selectedComponent?.description" class="mb-4">
          <div class="text-caption text-medium-emphasis mb-1">Description</div>
          <div class="text-body-2">{{ selectedComponent?.description }}</div>
        </div>
        <div class="d-flex flex-wrap gap-2 mb-6">
          <VChip size="small" :color="selectedComponent?.function_callable ? 'success' : 'grey'">
            Function Callable: {{ selectedComponent?.function_callable ? 'Yes' : 'No' }}
          </VChip>
          <VChip size="small" :color="selectedComponent?.can_use_function_calling ? 'info' : 'grey'">
            Can Use Function Calling: {{ selectedComponent?.can_use_function_calling ? 'Yes' : 'No' }}
          </VChip>
        </div>
        <h4 class="text-h6 mb-2">Parameters</h4>
        <VDataTable
          :items="selectedComponent?.parameters || []"
          :headers="[
            { title: 'Name', key: 'name' },
            { title: 'Type', key: 'type' },
            { title: 'Nullable', key: 'nullable' },
            { title: 'Default', key: 'default' },
            { title: 'UI', key: 'ui_component' },
          ]"
          density="compact"
          class="param-table"
        >
          <template #item.nullable="{ item }">
            <VChip :color="item.nullable ? 'warning' : 'success'" size="x-small">
              {{ item.nullable ? 'Nullable' : 'Required' }}
            </VChip>
          </template>
          <template #item.default="{ item }">
            <code>{{
              typeof item.default === 'object' ? JSON.stringify(item.default) : String(item.default ?? '')
            }}</code>
          </template>
          <template #no-data>
            <div class="text-caption text-medium-emphasis">No parameters</div>
          </template>
        </VDataTable>
      </VCardText>
    </VCard>
  </VNavigationDrawer>

  <!-- Delete Component Confirmation Dialog -->
  <VDialog v-model="showDeleteComponentDialog" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle class="d-flex align-center">
        <VIcon icon="tabler-alert-triangle" color="warning" class="me-2" />
        Confirm Delete Component
      </VCardTitle>
      <VDivider />
      <VCardText>
        <div class="mb-4">
          <div class="mb-3"><strong>Component:</strong> {{ deleteTargetComponent?.name }}</div>
          <div class="mb-3">
            <strong>Version:</strong>
            {{
              deleteTargetComponent?.version_tag ||
              deleteTargetComponent?.component_version_id?.substring(0, 8) ||
              'N/A'
            }}
          </div>
        </div>

        <VRadioGroup v-model="deleteScope" class="mb-4">
          <VRadio value="version" color="warning">
            <template #label>
              <div>
                <div class="font-weight-medium">Delete only this version</div>
                <div class="text-caption text-medium-emphasis">
                  Only version {{ deleteTargetComponent?.version_tag || 'N/A' }} will be deleted
                </div>
              </div>
            </template>
          </VRadio>
          <VRadio value="component" color="error">
            <template #label>
              <div>
                <div class="font-weight-medium">Delete all versions of this component</div>
                <div class="text-caption text-medium-emphasis">
                  ⚠️ All versions of {{ deleteTargetComponent?.name }} will be permanently deleted
                </div>
              </div>
            </template>
          </VRadio>
        </VRadioGroup>

        <VAlert
          v-if="deleteDialogError"
          type="error"
          variant="tonal"
          class="mb-4"
          closable
          @click:close="deleteDialogError = ''"
        >
          {{ deleteDialogError }}
        </VAlert>

        <VAlert type="warning" variant="tonal" class="mb-4">
          <div class="font-weight-medium mb-1">This action cannot be undone!</div>
          Please type the component name exactly to confirm.
        </VAlert>
        <VTextField
          v-model="deleteComponentInput"
          :label="`Type: ${deleteTargetComponent?.name || ''}`"
          :disabled="deleteLoading"
          autofocus
        />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="deleteLoading" @click="showDeleteComponentDialog = false">Cancel</VBtn>
        <VBtn
          color="error"
          :loading="deleteLoading"
          :disabled="!canConfirmDelete || deleteLoading"
          @click="confirmDeleteComponent"
        >
          Delete
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Update Component Fields / Credits Dialog -->
  <VDialog v-model="showUpdateFieldsDialog" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle class="d-flex align-center">
        <VIcon icon="tabler-exchange" class="me-2" />
        Update Component
      </VCardTitle>
      <VDivider />
      <VCardText class="update-component-card-text">
        <div class="mb-4">
          You are updating
          <strong>{{ updateFieldsTarget?.name }}</strong
          >.
        </div>

        <!-- Tabs -->
        <VTabs v-model="updateMode" :disabled="updateFieldsLoading" class="mb-4">
          <VTab value="fields">Fields</VTab>
          <VTab value="credits">Credits</VTab>
        </VTabs>

        <VWindow v-model="updateMode" class="mt-4">
          <!-- Fields Tab -->
          <VWindowItem value="fields">
            <VAlert v-if="fieldsOptionsLoading" type="info" variant="tonal" class="mb-4">
              Loading fields options...
            </VAlert>

            <div class="d-flex flex-column gap-4">
              <div>
                <div class="text-subtitle-2 mb-2">Release Stage</div>
                <VSelect
                  v-model="selectedNewStage"
                  :items="
                    fieldsOptions?.release_stages?.map(stage => ({
                      title: stage.replace('_', ' ').toUpperCase(),
                      value: stage,
                    })) || []
                  "
                  item-title="title"
                  item-value="value"
                  variant="outlined"
                  :disabled="updateFieldsLoading || fieldsOptionsLoading"
                  hide-details
                />
              </div>

              <div>
                <VCheckbox
                  v-model="selectedIsAgent"
                  label="Is Agent"
                  :disabled="updateFieldsLoading"
                  hide-details
                  color="primary"
                >
                  <template #label>
                    <div>
                      <div class="font-weight-medium">Is Agent</div>
                      <div class="text-caption text-medium-emphasis">Component represents an AI agent workflow</div>
                    </div>
                  </template>
                </VCheckbox>
              </div>

              <div>
                <VCheckbox
                  v-model="selectedFunctionCallable"
                  label="Function Callable"
                  :disabled="updateFieldsLoading"
                  hide-details
                  color="primary"
                >
                  <template #label>
                    <div>
                      <div class="font-weight-medium">Function Callable</div>
                      <div class="text-caption text-medium-emphasis">
                        Component can be invoked as a function by LLMs
                      </div>
                    </div>
                  </template>
                </VCheckbox>
              </div>

              <div>
                <div class="text-subtitle-2 mb-2">Categories</div>
                <VSelect
                  v-model="selectedCategoryIds"
                  :items="
                    fieldsOptions?.categories?.map(cat => ({
                      title: cat.name,
                      value: cat.id,
                      subtitle: cat.description,
                    })) || []
                  "
                  item-title="title"
                  item-value="value"
                  variant="outlined"
                  :disabled="updateFieldsLoading || fieldsOptionsLoading"
                  multiple
                  chips
                  closable-chips
                  hide-details
                  placeholder="Select categories"
                >
                  <template #chip="{ item }">
                    <VChip
                      :key="item.value"
                      size="small"
                      closable
                      @click:close="selectedCategoryIds = selectedCategoryIds.filter(id => id !== item.value)"
                    >
                      {{ item.title }}
                    </VChip>
                  </template>
                </VSelect>
              </div>
            </div>
          </VWindowItem>

          <!-- Credits Tab -->
          <VWindowItem value="credits">
            <VCheckbox
              v-model="deleteCredits"
              label="Delete all credits for this component"
              color="error"
              :disabled="updateFieldsLoading"
              class="mb-4"
            >
              <template #label>
                <div>
                  <div>Delete all credits for this component</div>
                  <div class="text-caption text-medium-emphasis mt-1">
                    Removes all cost fields and resets credit usage to zero. This action cannot be undone.
                  </div>
                </div>
              </template>
            </VCheckbox>

            <div v-if="!deleteCredits">
              <div class="text-subtitle-2 mb-3">Component Costs</div>
              <CreditFieldsForm v-model="costForm" :disabled="updateFieldsLoading" />
            </div>
            <VAlert v-else type="warning" variant="tonal" class="mb-4">
              This will permanently delete all credits for this component version.
            </VAlert>
          </VWindowItem>
        </VWindow>

        <VAlert
          v-if="updateFieldsDialogError"
          type="error"
          variant="tonal"
          class="mb-4 mt-4"
          closable
          @click:close="updateFieldsDialogError = ''"
        >
          {{ updateFieldsDialogError }}
        </VAlert>

        <VAlert type="warning" variant="tonal" class="mb-4 mt-4">
          <div class="font-weight-medium mb-1">Confirmation required</div>
          <div>Type "{{ updateFieldsTarget?.name || '' }}" to confirm this change.</div>
        </VAlert>

        <div class="mb-4">
          <div class="text-subtitle-2 mb-2">Confirm component name</div>
          <VTextField
            v-model="updateFieldsInput"
            variant="outlined"
            :disabled="updateFieldsLoading"
            hide-details
            autofocus
          />
        </div>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="updateFieldsLoading" @click="showUpdateFieldsDialog = false">Cancel</VBtn>
        <VBtn
          :color="updateMode === 'credits' && deleteCredits ? 'error' : 'primary'"
          :loading="updateFieldsLoading"
          :disabled="!canConfirmUpdateFields || updateFieldsLoading"
          @click="confirmUpdateFields"
        >
          {{ updateMode === 'fields' ? 'Update Fields' : deleteCredits ? 'Delete Credits' : 'Update Credits' }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.scrollable-content {
  display: flex;
  flex-direction: column;
}
.scrollable-content :deep(.v-card-text) {
  overflow: auto;
}
.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 2;
}
.param-table :deep(table) {
  table-layout: fixed;
  width: 100%;
}
.param-table :deep(th),
.param-table :deep(td) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.v-window-item) {
  overflow: visible;
}
</style>
