<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { useReleaseStages } from '@/composables/queries/useReleaseStagesQuery'
// import { supabase } from '@/services/auth'
import { formatNumberWithSpaces } from '@/utils/formatters'
import APIToolBuilder from '@/components/admin/APIToolBuilder.vue'
import ComponentsManager from '@/components/admin/ComponentsManager.vue'
import GlobalSecretsManager from '@/components/admin/GlobalSecretsManager.vue'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { supabase } from '@/services/auth'
import { scopeoApi } from '@/api'
import type { CreditFields } from '@/types/credits'
import type { LLMModel } from '@/types/llmModels'
import type { OrganizationUsageResponse } from '@/types/organizationUsage'
import { convertEmptyToNull, initializeCreditForm, resetCreditForm } from '@/utils/credits'
import { TAB_STAGE_CONFIG, getTabMetadata } from '@/utils/tabStageConfig'

definePage({
  meta: {
    requiresSuperAdmin: true,
    action: 'manage',
    subject: 'SuperAdmin',
  },
})

// Super admin access is checked automatically via useSuperAdminQuery in useReleaseStages
const {
  isSuperAdmin,
  superAdminLoading,
  releaseStages,
  organizationReleaseStages,
  loading,
  fetchReleaseStages,
  fetchOrgReleaseStages,
  createReleaseStage,
  updateReleaseStage,
  deleteReleaseStage,
  assignOrgToReleaseStage,
  updateOrgReleaseStage,
  removeOrgFromReleaseStage,
  activeReleaseStages,
  RELEASE_STAGES,
  // User management functions
  fetchUsers,
  fetchSuperAdmins,
  addSuperAdmin,
  removeSuperAdmin,
} = useReleaseStages()

// Local state
const tab = ref('organizations')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const selectedStage = ref<any>(null)

// Organization management
const organizations = ref<any[]>([])
const organizationsLoading = ref(false)
const showAssignDialog = ref(false)
const selectedOrg = ref<any>(null)

// Organization limits - store limit value and limit_id from combined endpoint
const organizationLimits = ref<Record<string, { limit: number | null; limit_id: string | null }>>({})
const organizationLimitsLoading = ref(false)
const updatingLimits = ref<Record<string, boolean>>({})

// Organization usage
const organizationUsage = ref<Record<string, OrganizationUsageResponse>>({})
const organizationUsageLoading = ref(false)
const currentMonth = computed(() => new Date().getMonth() + 1)
const currentYear = computed(() => new Date().getFullYear())

// Enhanced organization management
const showBulkAssignDialog = ref(false)
const showOrgDetailsDialog = ref(false)
const selectedOrgForDetails = ref<any>(null)
const bulkSelectedOrgs = ref<string[]>([])
const bulkSelectedStage = ref('')
const organizationSearch = ref('')

// Computed property to combine organizations with their current stage assignments, limits, and usage
const allOrganizationsWithStages = computed(() => {
  const orgsWithStages = organizations.value.map(org => {
    const assignment = organizationReleaseStages.value.find(orgStage => orgStage.org_id === org.id)

    // Get limit data for this organization
    const limitData = organizationLimits.value[org.id]
    const currentLimit = limitData?.limit ?? null
    const currentLimitId = limitData?.limit_id ?? null

    // Get usage for the current month/year
    const usage = organizationUsage.value[org.id]

    return {
      ...org,
      current_stage: assignment?.release_stage_name || null,
      assigned_at: assignment?.assigned_at || null,
      current_limit: currentLimit,
      current_limit_id: currentLimitId,
      current_usage: usage?.total_credits_used ?? null,
      updating: updatingLimits.value[org.id] || false, // For loading state during updates
    }
  })

  // Filter by search term
  if (organizationSearch.value && organizationSearch.value.trim()) {
    const searchLower = organizationSearch.value.toLowerCase().trim()
    return orgsWithStages.filter(org => org.name.toLowerCase().includes(searchLower))
  }

  return orgsWithStages
})

// Stage select items for dropdowns
const stageSelectItems = computed(() => [
  { title: 'No Stage', value: null },
  ...activeReleaseStages.value.map(stage => ({
    title: stage.name.replace('_', ' ').toUpperCase(),
    value: stage.name,
  })),
])

// Table headers computed to include current month/year
const organizationTableHeaders = computed(() => [
  { title: 'Organization', key: 'name' },
  { title: 'Current Stage', key: 'current_stage' },
  { title: `Usage (${getMonthName(currentMonth.value)}/${currentYear.value})`, key: 'current_usage' },
  { title: 'Monthly Limit', key: 'current_limit' },
  { title: 'Last Updated', key: 'assigned_at' },
  { title: 'Actions', key: 'actions', sortable: false },
])

// Super Admin management
const superAdmins = ref<any[]>([])
const superAdminsLoading = ref(false)
const showAddSuperAdminDialog = ref(false)

// User management
const users = ref<any[]>([])
const usersLoading = ref(false)
const showUserDialog = ref(false)
const selectedUser = ref<any>(null)

// Form data for new super admin
const newSuperAdminEmail = ref('')
const newSuperAdminNotes = ref('')

// Error handling
const errorMessage = ref('')
const successMessage = ref('')
const { notify } = useNotifications()

// Confirmation dialog for deletion
const showDeleteConfirmDialog = ref(false)
const userToDelete = ref<any>(null)
const actionConfirmDialog = ref(false)
const actionConfirmTitle = ref('')
const actionConfirmMessage = ref('')
const actionConfirmLoading = ref(false)
const pendingConfirmedAction = ref<null | (() => Promise<void>)>(null)

// Tab Configuration management (using centralized config)
const tabConfiguration = computed(() => TAB_STAGE_CONFIG)

// Form data
const stageForm = ref({
  name: '',
  description: '',
  display_order: 0,
  is_active: true,
})

// LLM Models management
const { selectedOrgId } = useSelectedOrg()
const llmModels = ref<LLMModel[]>([])
const llmModelsLoading = ref(false)
const llmModelsError = ref('')
const showCreateLLMModelDialog = ref(false)
const showEditLLMModelDialog = ref(false)
const showDeleteLLMModelDialog = ref(false)
const createLLMModelLoading = ref(false)
const updateLLMModelLoading = ref(false)
const deleteLLMModelLoading = ref(false)
const capabilitiesLoading = ref(false)
const capabilities = ref<Array<{ value: string; label: string }>>([])
const selectedLLMModel = ref<LLMModel | null>(null)
const llmModelToDelete = ref<LLMModel | null>(null)

const llmModelForm = ref<
  {
    display_name: string
    model_name: string
    provider: string
    description: string
    model_capacity: string[]
    credits_per_input_token?: number | null
    credits_per_output_token?: number | null
  } & CreditFields
>({
  display_name: '',
  model_name: '',
  provider: '',
  description: '',
  model_capacity: [],
  credits_per_input_token: null,
  credits_per_output_token: null,
  ...resetCreditForm(),
})

// Fetch organizations using Supabase directly
const fetchOrganizations = async () => {
  organizationsLoading.value = true
  try {
    const { data, error } = await supabase.from('organizations').select('id, name').order('name', { ascending: true })

    if (error) throw error
    organizations.value = data || []

    // Fetch limits and usage for all organizations (non-blocking)
    fetchAllOrganizationLimitsAndUsage().catch(err => {
      logger.error('Error fetching organization data', { error: err })
    })
  } catch (err) {
    logger.error('Error fetching organizations', { error: err })
  } finally {
    organizationsLoading.value = false
  }
}

// Handler functions for multi-statement click actions
const refreshOrganizations = () => {
  fetchOrganizations()
  fetchOrgReleaseStages()
}

const openAddSuperAdminDialog = () => {
  showAddSuperAdminDialog.value = true
  clearMessages()
}

const viewUser = (item: any) => {
  selectedUser.value = item
  showUserDialog.value = true
}

const cancelEditLLMModel = () => {
  showEditLLMModelDialog.value = false
  selectedLLMModel.value = null
}

const cancelDeleteLLMModel = () => {
  showDeleteLLMModelDialog.value = false
  llmModelToDelete.value = null
}

const cancelAddSuperAdmin = () => {
  showAddSuperAdminDialog.value = false
  clearMessages()
}

// Fetch organization limits and usage for all organizations using combined endpoint
const fetchAllOrganizationLimitsAndUsage = async () => {
  if (organizations.value.length === 0) return

  organizationLimitsLoading.value = true
  organizationUsageLoading.value = true

  try {
    // Fetch combined limits and usage from single endpoint
    const combinedData = await scopeoApi.organizationLimits.getAllLimitsAndUsage(currentMonth.value, currentYear.value)

    // Initialize structures
    const newLimits: Record<string, { limit: number | null; limit_id: string | null }> = {}
    const newUsage: Record<string, OrganizationUsageResponse> = {}

    // Initialize all organizations with null limits
    organizations.value.forEach(org => {
      newLimits[org.id] = { limit: null, limit_id: null }
    })

    // Transform combined response into separate structures
    combinedData.forEach(item => {
      const orgId = item.organization_id

      // Store limit value and limit_id from the combined endpoint
      newLimits[orgId] = {
        limit: item.limit ?? null,
        limit_id: item.limit_id ?? null,
      }

      // Handle usage
      const usageEntry: OrganizationUsageResponse = {
        organization_id: orgId,
        total_credits_used: item.total_credits_used ?? 0,
      }

      newUsage[orgId] = usageEntry
    })

    organizationLimits.value = newLimits
    organizationUsage.value = newUsage
  } catch (err: unknown) {
    logger.error('Error fetching organization limits and usage', { error: err })

    let userMessage = 'Failed to load organization limits and usage data. Please try again.'

    if (err instanceof Error) {
      if (err.message.includes('Access denied') || err.message.includes('permission')) {
        userMessage = 'You do not have permission to view organization limits and usage.'
      } else if (err.message.includes('not found')) {
        userMessage = 'Organization data not found.'
      } else {
        userMessage = err.message
      }
    }

    errorMessage.value = userMessage

    // Set empty structures on error
    const emptyLimits: Record<string, { limit: number | null; limit_id: string | null }> = {}

    organizations.value.forEach(org => {
      emptyLimits[org.id] = { limit: null, limit_id: null }
    })
    organizationLimits.value = emptyLimits
    organizationUsage.value = {}
  } finally {
    organizationLimitsLoading.value = false
    organizationUsageLoading.value = false
  }
}

const fetchLLMModels = async () => {
  if (!selectedOrgId.value) return

  llmModelsLoading.value = true
  llmModelsError.value = ''

  try {
    llmModels.value = await scopeoApi.llmModels.list(selectedOrgId.value)
  } catch (err) {
    logger.error('Error fetching LLM models', { error: err })
    llmModelsError.value = 'Failed to load LLM models. Please try again.'
  } finally {
    llmModelsLoading.value = false
  }
}

const fetchCapabilities = async () => {
  if (!selectedOrgId.value) return

  capabilitiesLoading.value = true
  try {
    const response = await scopeoApi.llmModels.getCapabilities(selectedOrgId.value)

    capabilities.value = response.capabilities
  } catch (err) {
    logger.error('Error fetching capabilities', { error: err })
    llmModelsError.value = 'Failed to load capabilities. Please try again.'
    capabilities.value = []
  } finally {
    capabilitiesLoading.value = false
  }
}

const openCreateLLMModelDialog = async () => {
  if (!selectedOrgId.value) {
    llmModelsError.value = 'Select an organization before creating a model.'
    return
  }

  // Reset form
  llmModelForm.value = {
    display_name: '',
    model_name: '',
    provider: '',
    description: '',
    model_capacity: [],
    credits_per_input_token: null,
    credits_per_output_token: null,
    ...resetCreditForm(),
  }
  llmModelsError.value = ''

  // Fetch capabilities
  await fetchCapabilities()

  showCreateLLMModelDialog.value = true
}

const handleCreateLLMModel = async () => {
  if (!selectedOrgId.value) {
    llmModelsError.value = 'Select an organization before creating a model.'
    return
  }

  if (!llmModelForm.value.display_name || !llmModelForm.value.model_name || !llmModelForm.value.provider) {
    llmModelsError.value = 'Display name, model name, and provider are required.'
    return
  }

  createLLMModelLoading.value = true
  llmModelsError.value = ''

  try {
    await scopeoApi.llmModels.create(selectedOrgId.value, {
      display_name: llmModelForm.value.display_name,
      model_name: llmModelForm.value.model_name,
      provider: llmModelForm.value.provider,
      description: llmModelForm.value.description || null,
      model_capacity: llmModelForm.value.model_capacity.length > 0 ? llmModelForm.value.model_capacity : null,
      credits_per_input_token: convertEmptyToNull(llmModelForm.value.credits_per_input_token),
      credits_per_output_token: convertEmptyToNull(llmModelForm.value.credits_per_output_token),
    })

    showCreateLLMModelDialog.value = false
    successMessage.value = 'LLM model created successfully.'
    await fetchLLMModels()
  } catch (err) {
    logger.error('Error creating LLM model', { error: err })
    llmModelsError.value = 'Failed to create LLM model. Please try again.'
  } finally {
    createLLMModelLoading.value = false
  }
}

const openEditLLMModelDialog = async (model: LLMModel) => {
  if (!selectedOrgId.value) {
    llmModelsError.value = 'Select an organization before editing a model.'
    return
  }

  selectedLLMModel.value = model

  // Populate form with model data
  llmModelForm.value = {
    display_name: model.display_name,
    model_name: model.model_name,
    provider: model.provider,
    description: model.description || '',
    model_capacity: model.model_capacity || [],
    credits_per_input_token: (model as any).credits_per_input_token ?? null,
    credits_per_output_token: (model as any).credits_per_output_token ?? null,
    ...initializeCreditForm(model),
  }
  llmModelsError.value = ''

  // Fetch capabilities
  await fetchCapabilities()

  showEditLLMModelDialog.value = true
}

const handleUpdateLLMModel = async () => {
  if (!selectedOrgId.value || !selectedLLMModel.value) {
    llmModelsError.value = 'Missing organization or model selection.'
    return
  }

  if (!llmModelForm.value.display_name || !llmModelForm.value.model_name || !llmModelForm.value.provider) {
    llmModelsError.value = 'Display name, model name, and provider are required.'
    return
  }

  updateLLMModelLoading.value = true
  llmModelsError.value = ''

  try {
    await scopeoApi.llmModels.update(selectedOrgId.value, selectedLLMModel.value.id, {
      display_name: llmModelForm.value.display_name,
      model_name: llmModelForm.value.model_name,
      provider: llmModelForm.value.provider,
      description: llmModelForm.value.description || null,
      model_capacity: llmModelForm.value.model_capacity.length > 0 ? llmModelForm.value.model_capacity : null,
      credits_per_input_token: convertEmptyToNull(llmModelForm.value.credits_per_input_token),
      credits_per_output_token: convertEmptyToNull(llmModelForm.value.credits_per_output_token),
    })

    showEditLLMModelDialog.value = false
    selectedLLMModel.value = null
    successMessage.value = 'LLM model updated successfully.'
    await fetchLLMModels()
  } catch (err) {
    logger.error('Error updating LLM model', { error: err })
    llmModelsError.value = 'Failed to update LLM model. Please try again.'
  } finally {
    updateLLMModelLoading.value = false
  }
}

const openDeleteLLMModelDialog = (model: LLMModel) => {
  llmModelToDelete.value = model
  llmModelsError.value = ''
  showDeleteLLMModelDialog.value = true
}

const handleDeleteLLMModel = async () => {
  if (!selectedOrgId.value || !llmModelToDelete.value) {
    llmModelsError.value = 'Missing organization or model selection.'
    return
  }

  deleteLLMModelLoading.value = true
  llmModelsError.value = ''

  try {
    await scopeoApi.llmModels.delete(selectedOrgId.value, llmModelToDelete.value.id)

    showDeleteLLMModelDialog.value = false
    llmModelToDelete.value = null
    successMessage.value = 'LLM model deleted successfully.'
    await fetchLLMModels()
  } catch (err) {
    logger.error('Error deleting LLM model', { error: err })
    llmModelsError.value = 'Failed to delete LLM model. Please try again.'
  } finally {
    deleteLLMModelLoading.value = false
  }
}

// Super Admin management functions
const fetchSuperAdminsData = async () => {
  superAdminsLoading.value = true
  try {
    superAdmins.value = await fetchSuperAdmins()
  } catch (err) {
    logger.error('Error fetching super admins', { error: err })
  } finally {
    superAdminsLoading.value = false
  }
}

const addSuperAdminUser = async (email: string, notes: string = '') => {
  try {
    await addSuperAdmin(email, notes)
    // Refresh the list
    await fetchSuperAdminsData()
    return true
  } catch (err) {
    logger.error('Error adding super admin', { error: err })
    throw err
  }
}

const removeSuperAdminUser = async (userId: string) => {
  try {
    await removeSuperAdmin(userId)
    // Refresh the list
    await fetchSuperAdminsData()
    return true
  } catch (err) {
    logger.error('Error removing super admin', { error: err })
    throw err
  }
}

// User management functions
const fetchUsersData = async () => {
  usersLoading.value = true
  try {
    users.value = await fetchUsers()
  } catch (err) {
    logger.error('Error fetching users', { error: err })
  } finally {
    usersLoading.value = false
  }
}

// Initialize data - wait for super admin check to complete before loading data
watch(
  isSuperAdmin,
  async newValue => {
    if (newValue && !superAdminLoading.value) {
      await Promise.all([
        fetchReleaseStages(),
        fetchOrgReleaseStages(),
        fetchOrganizations(),
        fetchSuperAdminsData(),
        fetchUsersData(),
      ])

      // Fetch LLM models if we're on that tab and have an organization selected
      if (tab.value === 'llm-models' && selectedOrgId.value) {
        fetchLLMModels()
      }
    }
  },
  { immediate: true }
)

// Stage management functions
const openCreateDialog = () => {
  stageForm.value = {
    name: '',
    description: '',
    display_order: releaseStages.value.length,
    is_active: true,
  }
  showCreateDialog.value = true
}

const openEditDialog = (stage: any) => {
  selectedStage.value = stage
  stageForm.value = { ...stage }
  showEditDialog.value = true
}

const handleCreateStage = async () => {
  try {
    await createReleaseStage(stageForm.value)
    showCreateDialog.value = false
  } catch (err) {
    // Error handling is done in the composable
  }
}

const handleUpdateStage = async () => {
  if (!selectedStage.value) return

  try {
    await updateReleaseStage(selectedStage.value.id, stageForm.value)
    showEditDialog.value = false
    selectedStage.value = null
  } catch (err) {
    // Error handling is done in the composable
  }
}

const handleDeleteStage = (stage: any) => {
  actionConfirmTitle.value = 'Delete release stage'
  actionConfirmMessage.value = `Are you sure you want to delete the "${stage.name}" release stage?`
  pendingConfirmedAction.value = async () => {
    try {
      await deleteReleaseStage(stage.id)
    } catch (error: unknown) {
      logger.warn('Failed to delete release stage', { error })
    }
  }
  actionConfirmDialog.value = true
}

// Organization assignment functions
const openAssignDialog = (org: any) => {
  selectedOrg.value = org
  showAssignDialog.value = true
}

const handleAssignOrg = async (releaseStageId: string) => {
  if (!selectedOrg.value) return

  try {
    await assignOrgToReleaseStage(selectedOrg.value.id, releaseStageId)
    showAssignDialog.value = false
    selectedOrg.value = null
  } catch (err) {
    // Error handling is done in the composable
  }
}

const handleRemoveOrgStage = (orgId: string) => {
  actionConfirmTitle.value = 'Remove release stage assignment'
  actionConfirmMessage.value = 'Are you sure you want to remove this organization from its release stage?'
  pendingConfirmedAction.value = async () => {
    try {
      await removeOrgFromReleaseStage(orgId)
    } catch (error: unknown) {
      logger.warn('Failed to remove org from release stage', { error })
    }
  }
  actionConfirmDialog.value = true
}

const handleDeleteLimit = async (organizationId: string, limitId: string | null, inputElement?: HTMLInputElement) => {
  if (!limitId) {
    return
  }

  updatingLimits.value[organizationId] = true

  try {
    // Use the real limit_id from the combined endpoint
    await scopeoApi.organizationLimits.delete(organizationId, limitId)

    if (inputElement) {
      inputElement.value = ''
    }

    await fetchAllOrganizationLimitsAndUsage()
  } catch (error: unknown) {
    logger.warn('Failed to delete organization limit', { error })
    await fetchAllOrganizationLimitsAndUsage()
  } finally {
    updatingLimits.value[organizationId] = false
  }
}

const handleUpdateLimit = async (organizationId: string, limitId: string | null, newLimit: number) => {
  if (isNaN(newLimit) || newLimit < 0) {
    return
  }

  updatingLimits.value[organizationId] = true

  try {
    if (limitId) {
      // Update existing limit using the real limit_id from the combined endpoint
      await scopeoApi.organizationLimits.update(organizationId, limitId, newLimit)
    } else {
      // No limit exists, create a new one instead
      await scopeoApi.organizationLimits.create(organizationId, { limit: newLimit })
    }
    await fetchAllOrganizationLimitsAndUsage()
  } catch (error: unknown) {
    logger.warn('Failed to update organization limit', { error })
    await fetchAllOrganizationLimitsAndUsage()
  } finally {
    updatingLimits.value[organizationId] = false
  }
}

const handleCreateLimit = async (organizationId: string, newLimit: number, inputElement?: HTMLInputElement) => {
  if (isNaN(newLimit) || newLimit < 0) {
    if (inputElement) {
      inputElement.value = ''
    }
    return
  }

  updatingLimits.value[organizationId] = true

  try {
    await scopeoApi.organizationLimits.create(organizationId, {
      limit: newLimit,
    })

    await fetchAllOrganizationLimitsAndUsage()
  } catch (error: unknown) {
    logger.warn('Failed to create organization limit', { error })
    if (inputElement) {
      inputElement.value = ''
    }
    await fetchAllOrganizationLimitsAndUsage()
  } finally {
    updatingLimits.value[organizationId] = false
  }
}

const handleLimitChange = async (item: any, event: Event) => {
  const target = event.target as HTMLInputElement
  // Remove spaces from input before parsing
  const inputValue = target.value.replace(/\s/g, '').trim()

  // Handle empty input - delete limit if it exists
  if (inputValue === '') {
    if (item.current_limit_id) {
      // Delete existing limit
      await handleDeleteLimit(item.id, item.current_limit_id, target)
    } else {
      // No limit exists, just ensure field is empty
      target.value = ''
    }
    return
  }

  const numValue = Number.parseFloat(inputValue)
  if (!isNaN(numValue) && numValue >= 0) {
    if (item.current_limit_id) {
      // Update existing limit
      if (numValue !== item.current_limit) {
        await handleUpdateLimit(item.id, item.current_limit_id, numValue)
      }
    } else {
      // Try to create new limit (will fail if user doesn't have access)
      await handleCreateLimit(item.id, numValue, target)
    }
  } else {
    // Reset to current limit if invalid value (formatted)
    target.value = item.current_limit != null ? formatNumberWithSpaces(item.current_limit) : ''
  }
}

// Clear messages
const clearMessages = () => {
  errorMessage.value = ''
  successMessage.value = ''
}

const handleAddSuperAdmin = async () => {
  if (!newSuperAdminEmail.value?.trim()) {
    errorMessage.value = 'Email is required'
    return
  }

  clearMessages()

  try {
    await addSuperAdminUser(newSuperAdminEmail.value, newSuperAdminNotes.value)
    showAddSuperAdminDialog.value = false
    newSuperAdminEmail.value = ''
    newSuperAdminNotes.value = ''
    successMessage.value = 'Super admin added successfully!'

    // Clear success message after 3 seconds
    setTimeout(() => {
      successMessage.value = ''
    }, 3000)
  } catch (err: unknown) {
    logger.error('Failed to add super admin', { error: err })

    let userMessage = 'Failed to add super admin. Please try again.'

    if (err instanceof Error) {
      if (err.message.includes('User not found')) {
        userMessage = 'User with this email not found. Please check the email address.'
      } else if (err.message.includes('already a super admin')) {
        userMessage = 'This user is already a super admin.'
      } else if (err.message.includes('Invalid email format')) {
        userMessage = 'Please enter a valid email address.'
      } else if (err.message.includes('Access denied')) {
        userMessage = 'You do not have permission to add super admins.'
      }
    }

    errorMessage.value = userMessage
  }
}

// Confirmation dialog functions
const confirmDeleteSuperAdmin = (user: any) => {
  userToDelete.value = user
  showDeleteConfirmDialog.value = true
}

const cancelDelete = () => {
  userToDelete.value = null
  showDeleteConfirmDialog.value = false
}

const confirmDelete = async () => {
  if (!userToDelete.value) return

  clearMessages()

  try {
    await removeSuperAdminUser(userToDelete.value.user_id)
    successMessage.value = `Super admin ${userToDelete.value.email} removed successfully!`

    // Clear success message after 3 seconds
    setTimeout(() => {
      successMessage.value = ''
    }, 3000)
  } catch (err: unknown) {
    logger.error('Failed to remove super admin', { error: err })

    let userMessage = 'Failed to remove super admin. Please try again.'

    if (err instanceof Error) {
      if (err.message.includes('Cannot remove yourself')) {
        userMessage = 'You cannot remove yourself as a super admin.'
      } else if (err.message.includes('Super admin not found')) {
        userMessage = 'Super admin not found or already removed.'
      } else if (err.message.includes('Access denied')) {
        userMessage = 'You do not have permission to remove super admins.'
      }
    }

    errorMessage.value = userMessage
  } finally {
    cancelDelete()
  }
}

// Tab Configuration helpers
const getTabIcon = (tabKey: string): string => {
  return getTabMetadata(tabKey).icon
}

const getTabTitle = (tabKey: string): string => {
  return getTabMetadata(tabKey).title
}

const editTabStages = (tabKey: string, currentStages: string[]) => {
  const metadata = getTabMetadata(tabKey)

  const message =
    currentStages.length === 0
      ? `${metadata.title} tab is currently visible to ALL organizations.`
      : `${metadata.title} tab is currently visible only to organizations with these release stages: ${currentStages.join(', ')}`

  notify.info(`${message} To modify this configuration, update TAB_STAGE_CONFIG in src/utils/tabStageConfig.ts.`)
}

// Enhanced organization management functions
const handleQuickStageAssign = async (orgId: string, stageValue: string | null) => {
  try {
    if (stageValue === null) {
      // Remove stage assignment
      await removeOrgFromReleaseStage(orgId)
    } else {
      // Find the stage ID for the stage name
      const stage = activeReleaseStages.value.find(s => s.name === stageValue)
      if (!stage) {
        throw new Error('Release stage not found')
      }

      // Check if org already has a stage assigned
      const existingAssignment = organizationReleaseStages.value.find(orgStage => orgStage.org_id === orgId)

      if (existingAssignment) {
        // Update existing assignment
        await updateOrgReleaseStage(orgId, stage.id)
      } else {
        // Create new assignment
        await assignOrgToReleaseStage(orgId, stage.id)
      }
    }

    // Refresh data
    await fetchOrgReleaseStages()
  } catch (err) {
    logger.error('Error updating organization stage', { error: err })
    notify.error('Failed to update organization stage. Please try again.')
  }
}

const viewOrgDetails = (org: any) => {
  selectedOrgForDetails.value = org
  showOrgDetailsDialog.value = true
}

const handleBulkAssign = async () => {
  if (!bulkSelectedStage.value || bulkSelectedOrgs.value.length === 0) {
    notify.error('Please select organizations and a release stage.')
    return
  }

  try {
    const selectedOrgCount = bulkSelectedOrgs.value.length
    const stage = activeReleaseStages.value.find(s => s.name === bulkSelectedStage.value)
    if (!stage) {
      throw new Error('Release stage not found')
    }

    // Assign stage to all selected organizations
    await Promise.all(bulkSelectedOrgs.value.map(orgId => assignOrgToReleaseStage(orgId, stage.id)))

    // Reset and refresh
    bulkSelectedOrgs.value = []
    bulkSelectedStage.value = ''
    showBulkAssignDialog.value = false
    await fetchOrgReleaseStages()

    notify.success(`Successfully assigned ${selectedOrgCount} organizations to ${stage.name} stage.`)
  } catch (err) {
    logger.error('Error bulk assigning stages', { error: err })
    notify.error('Failed to bulk assign stages. Please try again.')
  }
}

const cancelActionConfirm = () => {
  actionConfirmDialog.value = false
  actionConfirmTitle.value = ''
  actionConfirmMessage.value = ''
  pendingConfirmedAction.value = null
}

const confirmAction = async () => {
  if (!pendingConfirmedAction.value) return

  actionConfirmLoading.value = true
  try {
    await pendingConfirmedAction.value()
  } finally {
    actionConfirmLoading.value = false
    cancelActionConfirm()
  }
}

// Get organization name helper
const getOrgName = (orgId: string) => {
  const org = organizations.value.find(o => o.id === orgId)
  return org?.name || 'Unknown Organization'
}

// Get release stage badge color
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

// Get month name from month number
const getMonthName = (month: number) => {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return months[month - 1] || ''
}

// Watch for organization changes and fetch models
watch(selectedOrgId, newOrgId => {
  if (newOrgId && tab.value === 'llm-models') {
    fetchLLMModels()
  }
})

// Watch for tab changes and fetch data when tabs are opened
watch(tab, (newTab, oldTab) => {
  if (newTab === 'llm-models' && selectedOrgId.value) {
    fetchLLMModels()
  } else if (newTab === 'organizations') {
    // Refresh organizations data when switching back to organizations tab
    fetchOrganizations()
  } else if (oldTab === 'organizations' && newTab !== 'organizations') {
    // Clear search when leaving organizations tab
    organizationSearch.value = ''
  }
})
</script>

<template>
  <AppPage>
    <!-- Loading state for super admin check -->
    <div v-if="superAdminLoading" class="d-flex justify-center pa-8">
      <VProgressCircular indeterminate color="primary" />
      <span class="ms-3">Verifying super admin access...</span>
    </div>

    <!-- Access denied -->
    <div v-else-if="!isSuperAdmin" class="text-center pa-8">
      <VIcon icon="tabler-shield-x" size="64" color="error" class="mb-4" />
      <h2 class="text-h4 mb-2">Access Denied</h2>
      <p class="text-body-1">You don't have super admin privileges to access this page.</p>
    </div>

    <!-- Super admin dashboard -->
    <div v-else>
      <AppPageHeader title="Super Admin" description="Manage release stages and organization assignments">
        <template #badge>
          <VChip color="error" size="small">
            <VIcon icon="tabler-shield-check" size="16" class="me-1" />
            Super Admin
          </VChip>
        </template>
      </AppPageHeader>

      <!-- Success/Error Messages -->
      <VAlert
        v-if="successMessage"
        type="success"
        variant="tonal"
        class="mb-4"
        closable
        @click:close="successMessage = ''"
      >
        {{ successMessage }}
      </VAlert>

      <VAlert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable @click:close="errorMessage = ''">
        {{ errorMessage }}
      </VAlert>

      <!-- Tabs -->
      <VTabs v-model="tab" class="mb-6">
        <VTab value="organizations">Organizations</VTab>
        <VTab value="stages">Release Stages</VTab>
        <VTab value="superadmins">Super Admins</VTab>
        <VTab value="users">Users</VTab>
        <VTab value="llm-models">LLM Models</VTab>
        <VTab value="tabconfig">Tab Configuration</VTab>
        <VTab value="components">Components</VTab>
        <VTab value="api-tools">API Tool builder</VTab>
        <VTab value="global-secrets">Global Secrets</VTab>
      </VTabs>

      <!-- Organizations Tab -->
      <VWindow v-model="tab">
        <VWindowItem value="organizations">
          <!-- All Organizations Management -->
          <VCard class="mb-6">
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>All Organizations</span>
              <div class="d-flex align-center gap-2">
                <VTextField
                  v-model="organizationSearch"
                  placeholder="Search organizations..."
                  variant="outlined"
                  hide-details
                  clearable
                  style="min-width: 250px"
                >
                  <template #prepend-inner>
                    <VIcon icon="tabler-search" />
                  </template>
                </VTextField>
                <VBtn color="secondary" variant="outlined" @click="showBulkAssignDialog = true">
                  <VIcon icon="tabler-users" class="me-2" />
                  Bulk Assign
                </VBtn>
                <VBtn color="primary" :loading="organizationsLoading" @click="refreshOrganizations">
                  <VIcon icon="tabler-refresh" class="me-2" />
                  Refresh
                </VBtn>
              </div>
            </VCardTitle>

            <VDivider />

            <VCardText>
              <VDataTable
                :items="allOrganizationsWithStages"
                :loading="organizationsLoading || organizationLimitsLoading || organizationUsageLoading"
                :headers="organizationTableHeaders"
                item-value="id"
              >
                <template #item.current_stage="{ item }">
                  <VSelect
                    :model-value="item.current_stage"
                    :items="stageSelectItems"
                    item-title="title"
                    item-value="value"
                    density="compact"
                    variant="outlined"
                    :loading="item.updating"
                    @update:model-value="value => handleQuickStageAssign(String(item.id), value)"
                  >
                    <template #selection="{ item: selectedItem }">
                      <VChip v-if="selectedItem.raw.value" :color="getStageColor(selectedItem.raw.value)" size="small">
                        {{ selectedItem.raw.title }}
                      </VChip>
                      <VChip v-else color="grey" size="small" variant="outlined"> No Stage </VChip>
                    </template>
                  </VSelect>
                </template>

                <template #item.current_usage="{ item }">
                  <span v-if="item.current_usage != null">
                    {{ formatNumberWithSpaces(item.current_usage) }}
                  </span>
                  <span v-else class="text-grey">—</span>
                </template>

                <template #item.current_limit="{ item }">
                  <VTextField
                    :key="`limit-${item.id}`"
                    :model-value="item.current_limit != null ? formatNumberWithSpaces(item.current_limit) : ''"
                    type="text"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Set limit"
                    class="limit-input"
                    :loading="item.updating"
                    @blur="(e: Event) => handleLimitChange(item, e)"
                    @keyup.enter="(e: Event) => (e.target as HTMLInputElement).blur()"
                  />
                </template>

                <template #item.assigned_at="{ item }">
                  {{ item.assigned_at ? new Date(item.assigned_at).toLocaleDateString() : 'Never' }}
                </template>

                <template #item.actions="{ item }">
                  <VBtn icon="tabler-eye" size="small" variant="text" @click="viewOrgDetails(item)" />
                  <VBtn
                    v-if="item.current_stage"
                    icon="tabler-trash"
                    size="small"
                    variant="text"
                    color="error"
                    @click="handleRemoveOrgStage(String(item.id))"
                  />
                </template>

                <template #no-data>
                  <EmptyState size="sm" icon="tabler-building" title="No organizations found" />
                </template>
              </VDataTable>
            </VCardText>
          </VCard>

          <!-- Current Assignments (Legacy View) -->
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>Current Release Stage Assignments</span>
              <VBtn color="primary" :loading="loading" @click="fetchOrgReleaseStages">
                <VIcon icon="tabler-refresh" class="me-2" />
                Refresh
              </VBtn>
            </VCardTitle>

            <VDivider />

            <VCardText>
              <VDataTable
                :items="organizationReleaseStages"
                :loading="loading"
                :headers="[
                  {
                    title: 'Organization',
                    key: 'organizations.name',
                    value: (item: any) => getOrgName(String(item.org_id)),
                  },
                  { title: 'Release Stage', key: 'release_stage_name' },
                  { title: 'Assigned Date', key: 'assigned_at' },
                  { title: 'Actions', key: 'actions', sortable: false },
                ]"
                item-value="id"
              >
                <template #item.release_stage_name="{ item }">
                  <VChip :color="getStageColor(item.release_stage_name)" size="small">
                    {{ item.release_stage_name.replace('_', ' ').toUpperCase() }}
                  </VChip>
                </template>

                <template #item.assigned_at="{ item }">
                  {{ new Date(item.assigned_at).toLocaleDateString() }}
                </template>

                <template #item.actions="{ item }">
                  <VBtn
                    icon="tabler-edit"
                    size="small"
                    variant="text"
                    @click="openAssignDialog({ id: String(item.org_id), name: getOrgName(String(item.org_id)) })"
                  />
                  <VBtn
                    icon="tabler-trash"
                    size="small"
                    variant="text"
                    color="error"
                    @click="handleRemoveOrgStage(String(item.org_id))"
                  />
                </template>

                <template #no-data>
                  <EmptyState size="sm" icon="tabler-inbox" title="No organization assignments found" />
                </template>
              </VDataTable>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- Release Stages Tab -->
        <VWindowItem value="stages">
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>Release Stages</span>
              <VBtn color="primary" @click="openCreateDialog">
                <VIcon icon="tabler-plus" class="me-2" />
                Create Stage
              </VBtn>
            </VCardTitle>

            <VDivider />

            <VCardText>
              <VDataTable
                :items="releaseStages"
                :loading="loading"
                :headers="[
                  { title: 'Name', key: 'name' },
                  { title: 'Description', key: 'description' },
                  { title: 'Order', key: 'display_order' },
                  { title: 'Status', key: 'is_active' },
                  { title: 'Created', key: 'created_at' },
                  { title: 'Actions', key: 'actions', sortable: false },
                ]"
                item-value="id"
              >
                <template #item.name="{ item }">
                  <VChip :color="getStageColor(item.name)" size="small">
                    {{ item.name.replace('_', ' ').toUpperCase() }}
                  </VChip>
                </template>

                <template #item.is_active="{ item }">
                  <VChip :color="item.is_active ? 'success' : 'error'" size="small">
                    {{ item.is_active ? 'Active' : 'Inactive' }}
                  </VChip>
                </template>

                <template #item.created_at="{ item }">
                  {{ new Date(item.created_at).toLocaleDateString() }}
                </template>

                <template #item.actions="{ item }">
                  <VBtn icon="tabler-edit" size="small" variant="text" @click="openEditDialog(item)" />
                  <VBtn
                    icon="tabler-trash"
                    size="small"
                    variant="text"
                    color="error"
                    :disabled="!item.is_active"
                    @click="handleDeleteStage(item)"
                  />
                </template>

                <template #no-data>
                  <EmptyState size="sm" icon="tabler-inbox" title="No release stages found" />
                </template>
              </VDataTable>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- Super Admins Tab -->
        <VWindowItem value="superadmins">
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>Super Admin Users</span>
              <VBtn color="primary" @click="openAddSuperAdminDialog"> Add Super Admin </VBtn>
            </VCardTitle>
            <VDivider />
            <VCardText>
              <VDataTable
                :headers="[
                  { title: 'Email', key: 'email' },
                  { title: 'Notes', key: 'notes' },
                  { title: 'Added', key: 'created_at' },
                  { title: 'Actions', key: 'actions', sortable: false },
                ]"
                :items="superAdmins"
                :loading="superAdminsLoading"
              >
                <template #item.created_at="{ item }">
                  {{ new Date(item.created_at).toLocaleDateString() }}
                </template>
                <template #item.actions="{ item }">
                  <VBtn size="small" color="error" variant="outlined" @click="confirmDeleteSuperAdmin(item)">
                    Remove
                  </VBtn>
                </template>
              </VDataTable>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- Users Tab -->
        <VWindowItem value="users">
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>All Users</span>
              <VBtn color="primary" @click="fetchUsers"> Refresh </VBtn>
            </VCardTitle>
            <VDivider />
            <VCardText>
              <VDataTable
                :headers="[
                  { title: 'Email', key: 'email' },
                  { title: 'Verified', key: 'email_confirmed_at' },
                  { title: 'Last Sign In', key: 'last_sign_in_at' },
                  { title: 'Created', key: 'created_at' },
                  { title: 'Actions', key: 'actions', sortable: false },
                ]"
                :items="users"
                :loading="usersLoading"
              >
                <template #item.email_confirmed_at="{ item }">
                  <VChip :color="item.email_confirmed_at ? 'success' : 'warning'" size="small">
                    {{ item.email_confirmed_at ? 'Verified' : 'Pending' }}
                  </VChip>
                </template>
                <template #item.last_sign_in_at="{ item }">
                  {{ item.last_sign_in_at ? new Date(item.last_sign_in_at).toLocaleDateString() : 'Never' }}
                </template>
                <template #item.created_at="{ item }">
                  {{ new Date(item.created_at).toLocaleDateString() }}
                </template>
                <template #item.actions="{ item }">
                  <VBtn size="small" variant="outlined" @click="viewUser(item)"> View </VBtn>
                </template>
              </VDataTable>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- LLM Models Tab -->
        <VWindowItem value="llm-models">
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between flex-wrap" style="gap: 12px">
              <span>LLM Models</span>
              <div class="d-flex flex-wrap align-center" style="gap: 12px">
                <VBtn color="primary" :disabled="!selectedOrgId" :loading="llmModelsLoading" @click="fetchLLMModels">
                  <VIcon icon="tabler-refresh" class="me-2" />
                  Refresh
                </VBtn>
                <VBtn color="secondary" variant="tonal" :disabled="!selectedOrgId" @click="openCreateLLMModelDialog">
                  <VIcon icon="tabler-plus" class="me-2" />
                  Add Model
                </VBtn>
              </div>
            </VCardTitle>
            <VDivider />
            <VCardText>
              <VAlert
                v-if="llmModelsError"
                type="error"
                variant="tonal"
                class="mb-4"
                closable
                @click:close="llmModelsError = ''"
              >
                {{ llmModelsError }}
              </VAlert>

              <VAlert v-if="!selectedOrgId" type="info" variant="tonal">
                Please select an organization to manage LLM models.
              </VAlert>

              <VDataTable
                v-else
                :headers="[
                  { title: 'Display Name', key: 'display_name' },
                  { title: 'Provider', key: 'provider' },
                  { title: 'Model Name', key: 'model_name' },
                  { title: 'Capacity', key: 'model_capacity' },
                  { title: 'Credits per 1M Input Tokens', key: 'credits_per_input_token' },
                  { title: 'Credits per 1M Output Tokens', key: 'credits_per_output_token' },
                  { title: 'Description', key: 'description' },
                  { title: 'Created', key: 'created_at' },
                  { title: 'Updated', key: 'updated_at' },
                  { title: 'Actions', key: 'actions', sortable: false },
                ]"
                :items="llmModels"
                :loading="llmModelsLoading"
              >
                <template #item.model_capacity="{ item }">
                  <div class="d-flex flex-wrap" style="gap: 6px">
                    <VChip
                      v-for="capability in item.model_capacity || []"
                      :key="`${item.id}-${capability}`"
                      size="small"
                      color="primary"
                      variant="tonal"
                    >
                      {{ capability }}
                    </VChip>
                    <span v-if="!item.model_capacity || item.model_capacity.length === 0" class="text-medium-emphasis"
                      >—</span
                    >
                  </div>
                </template>
                <template #item.credits_per_input_token="{ item }">
                  <span v-if="(item as any).credits_per_input_token != null">
                    {{ formatNumberWithSpaces((item as any).credits_per_input_token) }}
                  </span>
                  <span v-else class="text-grey">—</span>
                </template>
                <template #item.credits_per_output_token="{ item }">
                  <span v-if="(item as any).credits_per_output_token != null">
                    {{ formatNumberWithSpaces((item as any).credits_per_output_token) }}
                  </span>
                  <span v-else class="text-grey">—</span>
                </template>
                <template #item.description="{ item }">
                  {{ item.description || '—' }}
                </template>
                <template #item.created_at="{ item }">
                  {{ new Date(item.created_at).toLocaleString() }}
                </template>
                <template #item.updated_at="{ item }">
                  {{ new Date(item.updated_at).toLocaleString() }}
                </template>
                <template #item.actions="{ item }">
                  <VBtn icon="tabler-edit" size="small" variant="text" @click="openEditLLMModelDialog(item)" />
                  <VBtn
                    icon="tabler-trash"
                    size="small"
                    variant="text"
                    color="error"
                    @click="openDeleteLLMModelDialog(item)"
                  />
                </template>
                <template #no-data>
                  <EmptyState
                    size="sm"
                    icon="tabler-database-search"
                    title="No LLM models found for this organization"
                  />
                </template>
              </VDataTable>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- Tab Configuration Tab -->
        <VWindowItem value="tabconfig">
          <VCard>
            <VCardTitle class="d-flex align-center justify-space-between">
              <span>Tab Configuration</span>
              <VChip color="info" size="small">
                <VIcon icon="tabler-settings" size="16" class="me-1" />
                Configure which tabs are visible for each release stage
              </VChip>
            </VCardTitle>
            <VDivider />
            <VCardText>
              <VAlert type="info" variant="tonal" class="mb-6">
                <VIcon icon="tabler-info-circle" class="me-2" />
                Configure which tabs are visible for organizations based on their release stage. Empty stage list means
                the tab is visible to all organizations.
              </VAlert>

              <div class="d-flex flex-column gap-6">
                <VCard v-for="(tab, tabKey) in tabConfiguration" :key="tabKey" variant="outlined">
                  <VCardText>
                    <div class="d-flex align-center justify-space-between mb-4">
                      <div class="d-flex align-center">
                        <VIcon :icon="getTabIcon(String(tabKey))" size="24" class="me-3" />
                        <div>
                          <h4 class="text-h6">{{ getTabTitle(String(tabKey)) }}</h4>
                          <p class="text-caption text-medium-emphasis">
                            {{
                              tab.length === 0 ? 'Visible to all organizations' : `Visible only to: ${tab.join(', ')}`
                            }}
                          </p>
                        </div>
                      </div>

                      <VBtn variant="outlined" size="small" @click="editTabStages(String(tabKey), tab)">
                        Edit Access
                      </VBtn>
                    </div>

                    <div v-if="tab.length > 0" class="d-flex gap-2">
                      <VChip v-for="stage in tab" :key="stage" size="small" :color="getStageColor(stage)">
                        {{ stage.replace('_', ' ').toUpperCase() }}
                      </VChip>
                    </div>
                    <VChip v-else size="small" color="success"> All Organizations </VChip>
                  </VCardText>
                </VCard>
              </div>
            </VCardText>
          </VCard>
        </VWindowItem>

        <!-- Components Tab -->
        <VWindowItem value="components">
          <ComponentsManager
            v-model:success-message="successMessage"
            v-model:error-message="errorMessage"
            :organization-id="selectedOrgId"
          />
        </VWindowItem>

        <!-- API Tool Builder Tab -->
        <VWindowItem value="api-tools">
          <APIToolBuilder v-model:success-message="successMessage" v-model:error-message="errorMessage" />
        </VWindowItem>

        <!-- Global Secrets Tab -->
        <VWindowItem value="global-secrets">
          <GlobalSecretsManager v-model:success-message="successMessage" v-model:error-message="errorMessage" />
        </VWindowItem>
      </VWindow>
    </div>

    <!-- Create Stage Dialog -->
    <VDialog v-model="showCreateDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Create Release Stage</VCardTitle>
        <VDivider />

        <VCardText>
          <VTextField v-model="stageForm.name" label="Name" placeholder="e.g., beta, early_access" required />
          <VTextField
            v-model="stageForm.description"
            label="Description"
            placeholder="Describe this release stage"
            class="mt-4"
          />
          <VTextField
            v-model.number="stageForm.display_order"
            label="Display Order"
            type="number"
            min="0"
            class="mt-4"
          />
          <VCheckbox v-model="stageForm.is_active" label="Active" class="mt-2" />
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn @click="showCreateDialog = false">Cancel</VBtn>
          <VBtn color="primary" :loading="loading" @click="handleCreateStage"> Create </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Edit Stage Dialog -->
    <VDialog v-model="showEditDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Edit Release Stage</VCardTitle>
        <VDivider />

        <VCardText>
          <VTextField v-model="stageForm.name" label="Name" required />
          <VTextField v-model="stageForm.description" label="Description" class="mt-4" />
          <VTextField
            v-model.number="stageForm.display_order"
            label="Display Order"
            type="number"
            min="0"
            class="mt-4"
          />
          <VCheckbox v-model="stageForm.is_active" label="Active" class="mt-2" />
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn @click="showEditDialog = false">Cancel</VBtn>
          <VBtn color="primary" :loading="loading" @click="handleUpdateStage"> Update </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Create LLM Model Dialog -->
    <VDialog v-model="showCreateLLMModelDialog" max-width="var(--dnr-dialog-md)">
      <VCard>
        <VCardTitle>Create LLM Model</VCardTitle>
        <VDivider />
        <VCardText>
          <VAlert
            v-if="llmModelsError"
            type="error"
            variant="tonal"
            class="mb-4"
            closable
            @click:close="llmModelsError = ''"
          >
            {{ llmModelsError }}
          </VAlert>

          <VForm class="d-flex flex-column gap-4" @submit.prevent="handleCreateLLMModel">
            <VTextField v-model="llmModelForm.display_name" label="Display Name" required />
            <VTextField v-model="llmModelForm.model_name" label="Model Name / Identifier" required />
            <VTextField v-model="llmModelForm.provider" label="Provider" required />
            <VTextarea v-model="llmModelForm.description" label="Description" auto-grow rows="2" />
            <VSelect
              v-model="llmModelForm.model_capacity"
              :items="capabilities"
              item-title="label"
              item-value="value"
              label="Capabilities"
              multiple
              chips
              closable-chips
              :loading="capabilitiesLoading"
              hint="Select one or more capabilities for this model"
              persistent-hint
            >
              <template #selection="{ item, index }">
                <VChip
                  v-if="index < 2"
                  :key="item.value"
                  size="small"
                  closable
                  @click:close="llmModelForm.model_capacity = llmModelForm.model_capacity.filter(c => c !== item.value)"
                >
                  {{ item.title }}
                </VChip>
                <span v-else-if="index === 2" class="text-grey text-caption align-self-center">
                  (+{{ llmModelForm.model_capacity.length - 2 }} others)
                </span>
              </template>
            </VSelect>
            <VDivider />
            <div class="text-subtitle-2 mb-2">Credit Settings</div>
            <VTextField
              v-model.number="llmModelForm.credits_per_input_token"
              type="number"
              label="Credits per 1M Input Tokens"
              :step="0.0001"
              :min="0"
              hint="Number of credits charged for 1M tokens the user sends into the model."
              persistent-hint
            />
            <VTextField
              v-model.number="llmModelForm.credits_per_output_token"
              type="number"
              label="Credits per 1M Output Tokens"
              :step="0.0001"
              :min="0"
              hint="Number of credits charged for 1M tokens the model generates in its response."
              persistent-hint
            />
          </VForm>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="showCreateLLMModelDialog = false">Cancel</VBtn>
          <VBtn color="primary" :loading="createLLMModelLoading" @click="handleCreateLLMModel"> Create Model </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Edit LLM Model Dialog -->
    <VDialog v-model="showEditLLMModelDialog" max-width="var(--dnr-dialog-md)">
      <VCard>
        <VCardTitle>Edit LLM Model</VCardTitle>
        <VDivider />
        <VCardText>
          <VAlert
            v-if="llmModelsError"
            type="error"
            variant="tonal"
            class="mb-4"
            closable
            @click:close="llmModelsError = ''"
          >
            {{ llmModelsError }}
          </VAlert>

          <VForm class="d-flex flex-column gap-4" @submit.prevent="handleUpdateLLMModel">
            <VTextField v-model="llmModelForm.display_name" label="Display Name" required />
            <VTextField v-model="llmModelForm.model_name" label="Model Name / Identifier" required />
            <VTextField v-model="llmModelForm.provider" label="Provider" required />
            <VTextarea v-model="llmModelForm.description" label="Description" auto-grow rows="2" />
            <VSelect
              v-model="llmModelForm.model_capacity"
              :items="capabilities"
              item-title="label"
              item-value="value"
              label="Capabilities"
              multiple
              chips
              closable-chips
              :loading="capabilitiesLoading"
              hint="Select one or more capabilities for this model"
              persistent-hint
            >
              <template #selection="{ item, index }">
                <VChip
                  v-if="index < 2"
                  :key="item.value"
                  size="small"
                  closable
                  @click:close="llmModelForm.model_capacity = llmModelForm.model_capacity.filter(c => c !== item.value)"
                >
                  {{ item.title }}
                </VChip>
                <span v-else-if="index === 2" class="text-grey text-caption align-self-center">
                  (+{{ llmModelForm.model_capacity.length - 2 }} others)
                </span>
              </template>
            </VSelect>
            <VDivider />
            <div class="text-subtitle-2 mb-2">Credit Settings</div>
            <VTextField
              v-model.number="llmModelForm.credits_per_input_token"
              type="number"
              label="Credits per 1M Input Tokens"
              :step="0.0001"
              :min="0"
              hint="Number of credits charged for 1M tokens the user sends into the model."
              persistent-hint
            />
            <VTextField
              v-model.number="llmModelForm.credits_per_output_token"
              type="number"
              label="Credits per 1M Output Tokens"
              :step="0.0001"
              :min="0"
              hint="Number of credits charged for 1M tokens the model generates in its response."
              persistent-hint
            />
          </VForm>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="cancelEditLLMModel">Cancel</VBtn>
          <VBtn color="primary" :loading="updateLLMModelLoading" @click="handleUpdateLLMModel"> Update Model </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete LLM Model Confirmation Dialog -->
    <VDialog v-model="showDeleteLLMModelDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h5 d-flex align-center">
          <VIcon icon="tabler-alert-triangle" color="warning" class="me-2" />
          Confirm Deletion
        </VCardTitle>

        <VCardText>
          <p class="mb-4">
            Are you sure you want to delete the LLM model <strong>{{ llmModelToDelete?.display_name }}</strong
            >?
          </p>

          <VAlert
            v-if="llmModelsError"
            type="error"
            variant="tonal"
            class="mb-4"
            closable
            @click:close="llmModelsError = ''"
          >
            {{ llmModelsError }}
          </VAlert>

          <VAlert type="warning" variant="tonal" class="mb-0">
            <VIcon icon="tabler-info-circle" class="me-2" />
            This action cannot be undone. The model will be permanently deleted.
          </VAlert>
        </VCardText>

        <VCardActions class="justify-end">
          <VBtn @click="cancelDeleteLLMModel">Cancel</VBtn>
          <VBtn color="error" variant="flat" :loading="deleteLLMModelLoading" @click="handleDeleteLLMModel">
            Delete Model
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Assign Organization Dialog -->
    <VDialog v-model="showAssignDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Assign to Release Stage</VCardTitle>
        <VDivider />

        <VCardText>
          <p class="mb-4">
            Assign <strong>{{ selectedOrg?.name }}</strong> to a release stage:
          </p>

          <div class="d-flex flex-column gap-2">
            <VBtn
              v-for="stage in activeReleaseStages"
              :key="stage.id"
              variant="outlined"
              :color="getStageColor(stage.name)"
              block
              @click="handleAssignOrg(stage.id)"
            >
              {{ stage.name.replace('_', ' ').toUpperCase() }}
              <VChip size="x-small" class="ms-2">{{ stage.description }}</VChip>
            </VBtn>
          </div>
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn @click="showAssignDialog = false">Cancel</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Add Super Admin Dialog -->
    <VDialog v-model="showAddSuperAdminDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Add Super Admin</VCardTitle>
        <VDivider />
        <VCardText>
          <!-- Error in Dialog -->
          <VAlert
            v-if="errorMessage"
            type="error"
            variant="tonal"
            class="mb-4"
            closable
            @click:close="errorMessage = ''"
          >
            {{ errorMessage }}
          </VAlert>

          <VForm @submit.prevent="handleAddSuperAdmin">
            <VTextField
              v-model="newSuperAdminEmail"
              label="Email"
              type="email"
              required
              class="mb-4"
              :error="!!errorMessage"
            />
            <VTextarea v-model="newSuperAdminNotes" label="Notes (optional)" rows="3" />
          </VForm>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="cancelAddSuperAdmin">Cancel</VBtn>
          <VBtn color="primary" :loading="superAdminsLoading" @click="handleAddSuperAdmin"> Add Super Admin </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- User Detail Dialog -->
    <VDialog v-model="showUserDialog" max-width="var(--dnr-dialog-md)">
      <VCard v-if="selectedUser">
        <VCardTitle>User Details</VCardTitle>
        <VDivider />
        <VCardText>
          <div class="mb-4"><strong>Email:</strong> {{ selectedUser.email }}</div>
          <div class="mb-4"><strong>User ID:</strong> {{ selectedUser.id }}</div>
          <div class="mb-4"><strong>Created:</strong> {{ new Date(selectedUser.created_at).toLocaleString() }}</div>
          <div class="mb-4">
            <strong>Last Sign In:</strong>
            {{ selectedUser.last_sign_in_at ? new Date(selectedUser.last_sign_in_at).toLocaleString() : 'Never' }}
          </div>
          <div class="mb-4">
            <strong>Email Verified:</strong>
            <VChip :color="selectedUser.email_confirmed_at ? 'success' : 'warning'" size="small">
              {{ selectedUser.email_confirmed_at ? 'Yes' : 'No' }}
            </VChip>
          </div>
          <div v-if="selectedUser.user_metadata && Object.keys(selectedUser.user_metadata).length">
            <strong>Metadata:</strong>
            <pre class="text-caption mt-2">{{ JSON.stringify(selectedUser.user_metadata, null, 2) }}</pre>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="showUserDialog = false">Close</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Bulk Assignment Dialog -->
    <VDialog v-model="showBulkAssignDialog" max-width="var(--dnr-dialog-md)">
      <VCard>
        <VCardTitle>Bulk Assign Release Stage</VCardTitle>
        <VDivider />
        <VCardText>
          <VAlert type="info" variant="tonal" class="mb-6">
            <VIcon icon="tabler-info-circle" class="me-2" />
            Select multiple organizations and assign them all to the same release stage.
          </VAlert>

          <div class="mb-6">
            <VSelect
              v-model="bulkSelectedStage"
              :items="stageSelectItems.filter(s => s.value !== null)"
              item-title="title"
              item-value="value"
              label="Select Release Stage"
              variant="outlined"
              required
            />
          </div>

          <div class="mb-4">
            <h4 class="text-h6 mb-3">Select Organizations:</h4>
            <VCheckbox
              v-for="org in organizations"
              :key="org.id"
              v-model="bulkSelectedOrgs"
              :value="org.id"
              :label="org.name"
              density="compact"
            />
          </div>

          <div v-if="bulkSelectedOrgs.length > 0" class="mt-4">
            <VAlert type="success" variant="tonal">
              <VIcon icon="tabler-check" class="me-2" />
              {{ bulkSelectedOrgs.length }} organization(s) selected for assignment.
            </VAlert>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="showBulkAssignDialog = false">Cancel</VBtn>
          <VBtn
            color="primary"
            :disabled="!bulkSelectedStage || bulkSelectedOrgs.length === 0"
            @click="handleBulkAssign"
          >
            Assign to {{ bulkSelectedOrgs.length }} Organizations
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Organization Details Dialog -->
    <VDialog v-model="showOrgDetailsDialog" max-width="var(--dnr-dialog-md)">
      <VCard v-if="selectedOrgForDetails">
        <VCardTitle class="d-flex align-center">
          <VIcon icon="tabler-building" class="me-2" />
          {{ selectedOrgForDetails.name }}
        </VCardTitle>
        <VDivider />
        <VCardText>
          <div class="d-flex flex-column gap-4">
            <div><strong>Organization ID:</strong> {{ selectedOrgForDetails.id }}</div>
            <div>
              <strong>Current Release Stage:</strong>
              <VChip
                v-if="selectedOrgForDetails.current_stage"
                :color="getStageColor(selectedOrgForDetails.current_stage)"
                size="small"
                class="ms-2"
              >
                {{ selectedOrgForDetails.current_stage.replace('_', ' ').toUpperCase() }}
              </VChip>
              <VChip v-else color="grey" size="small" variant="outlined" class="ms-2"> No Stage Assigned </VChip>
            </div>
            <div v-if="selectedOrgForDetails.assigned_at">
              <strong>Stage Assigned:</strong> {{ new Date(selectedOrgForDetails.assigned_at).toLocaleString() }}
            </div>
            <div>
              <strong>Current Limit:</strong>
              <div class="mt-2">
                <VChip
                  v-if="
                    selectedOrgForDetails.current_limit !== null && selectedOrgForDetails.current_limit !== undefined
                  "
                  color="primary"
                  size="small"
                  variant="tonal"
                >
                  {{ formatNumberWithSpaces(selectedOrgForDetails.current_limit) }}
                </VChip>
                <span v-else class="text-grey">No limit set</span>
              </div>
            </div>
            <VDivider />
            <div>
              <strong>Quick Actions:</strong>
              <div class="mt-2">
                <VSelect
                  :model-value="selectedOrgForDetails.current_stage"
                  :items="stageSelectItems"
                  item-title="title"
                  item-value="value"
                  label="Change Release Stage"
                  variant="outlined"
                  @update:model-value="value => handleQuickStageAssign(String(selectedOrgForDetails.id), value)"
                />
              </div>
            </div>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="showOrgDetailsDialog = false">Close</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Confirmation Dialog for Super Admin Deletion -->
    <VDialog v-model="showDeleteConfirmDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h5 d-flex align-center">
          <VIcon icon="tabler-alert-triangle" color="warning" class="me-2" />
          Confirm Deletion
        </VCardTitle>

        <VCardText>
          <p class="mb-4">
            Are you sure you want to remove <strong>{{ userToDelete?.email }}</strong> as a super admin?
          </p>

          <VAlert type="warning" variant="tonal" class="mb-0">
            <VIcon icon="tabler-info-circle" class="me-2" />
            This action cannot be undone. The user will lose all super admin privileges immediately.
          </VAlert>
        </VCardText>

        <VCardActions class="justify-end">
          <VBtn @click="cancelDelete">Cancel</VBtn>
          <VBtn color="error" variant="flat" @click="confirmDelete"> Remove Super Admin </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <GenericConfirmDialog
      v-model:is-dialog-visible="actionConfirmDialog"
      :title="actionConfirmTitle || 'Confirm Action'"
      :message="actionConfirmMessage"
      confirm-text="Confirm"
      cancel-text="Cancel"
      confirm-color="error"
      :loading="actionConfirmLoading"
      @confirm="confirmAction"
      @cancel="cancelActionConfirm"
    />
  </AppPage>
</template>

<style scoped>
.gap-2 > * + * {
  margin-block-start: 8px;
}

.limit-input {
  max-width: 120px;
}
</style>
