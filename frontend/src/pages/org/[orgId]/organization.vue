<script setup lang="ts">
import { format } from 'date-fns'
import { useRouter } from 'vue-router'
import { logger } from '@/utils/logger'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import {
  useCreateOrgApiKeyMutation,
  useOrgApiKeysQuery,
  useOrgCreditUsageQuery,
  useRevokeOrgApiKeyMutation,
} from '@/composables/queries/useOrganizationQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import { scopeoApi } from '@/api'
import type { OrgApiKey } from '@/types/organization'

interface OrganizationMember {
  id: string
  email: string
  role: string
  created_at?: string
}

interface Organization {
  id: string
  name: string
  created_at?: string
}

interface Invitation {
  id: string
  email: string
  role: string
  created_at: string
}

interface OrganizationSecret {
  key: string
}

const members = ref<OrganizationMember[]>([])
const invitations = ref<Invitation[]>([])
const secrets = ref<OrganizationSecret[]>([])
const authStore = useAuthStore()
const userData = computed(() => authStore.userData)
const { notify } = useNotifications()
const loading = ref(false)
const membersLoading = ref(false)
const invitationsLoading = ref(false)
const secretsLoading = ref(false)
const { selectedOrgId, selectedOrgRole, isOrgAdmin, orgChangeCounter } = useSelectedOrg()
const router = useRouter()

// Credit Usage data via TanStack Query
interface Chart {
  id: string
  type: 'line' | 'bar' | 'doughnut' | 'radar' | 'polarArea' | 'bubble' | 'table'
  title: string
  data: {
    labels?: string[]
    datasets: any[]
  }
  progress_percentage?: number | null
}

const {
  data: creditUsageChart,
  isLoading: creditUsageLoading,
  isError: creditUsageError,
} = useOrgCreditUsageQuery(selectedOrgId)

// Tab management
const activeTab = ref('general')

const tabs = [
  { title: 'General', value: 'general', icon: 'tabler-settings' },
  { title: 'Members', value: 'members', icon: 'tabler-users' },
  { title: 'Secrets', value: 'secrets', icon: 'tabler-key' },
  { title: 'Org API Keys', value: 'org-api-keys', icon: 'tabler-lock' },
]

// Form data for adding new members
const newMemberEmail = ref('')
const newMemberRole = ref('member')
const addingMember = ref(false)
const memberRoles = ['admin', 'developer', 'member', 'user']

// Form data for editing organization
const editingOrg = ref(false)
const editOrgName = ref('')
const selectedOrg = ref<Organization | null>(null)

// API Keys/Secrets management
const dialog = ref(false)
const editingSecret = ref<OrganizationSecret | null>(null)
const deleteDialog = ref(false)
const secretToDelete = ref<string>('')

// Form data for secrets
const secretForm = ref({
  key: '',
  value: '',
})

// Track if custom key is selected
const isCustomKey = ref(false)

// Common secret key presets
const secretPresets = [
  { label: 'OpenAI API Key', value: 'openai_api_key' },
  { label: 'Anthropic API Key', value: 'anthropic_api_key' },
  { label: 'Mistral API Key', value: 'mistral_api_key' },
  { label: 'Cohere API Key', value: 'cohere_api_key' },
  { label: 'Google AI API Key', value: 'google_ai_api_key' },
  { label: 'Azure OpenAI Key', value: 'azure_openai_api_key' },
  { label: 'AWS Bedrock Key', value: 'aws_bedrock_api_key' },
  { label: 'Custom Key', value: '' },
]

// Fetch the currently selected organization
const fetchSelectedOrg = async () => {
  if (!selectedOrgId.value) return

  loading.value = true
  try {
    const { data, error } = await supabase
      .from('organizations')
      .select('id, name, created_at')
      .eq('id', selectedOrgId.value)
      .single()

    if (error) throw error

    selectedOrg.value = data
    editOrgName.value = data.name
  } catch (error) {
    logger.error('Error fetching organization', { error })
  } finally {
    loading.value = false
  }
}

const fetchOrgMembers = async () => {
  if (!selectedOrgId.value) return

  membersLoading.value = true
  try {
    // Check if offline mode is enabled (defaults to false if not set)
    const isOfflineMode = import.meta.env.VITE_OFFLINE_MODE === 'true'

    if (isOfflineMode) {
      // Direct database query for offline mode
      const { data, error } = await supabase
        .from('organization_members')
        .select('user_id, role, created_at')
        .eq('org_id', selectedOrgId.value)

      if (error) throw error

      // Transform data to match expected format (using user_id as email since we can't access auth.users)
      members.value = (data || []).map(member => ({
        id: member.user_id,
        email: `User ${member.user_id.substring(0, 8)}...`, // Fallback since we can't access real emails
        role: member.role || 'user',
        created_at: member.created_at,
      }))
      return
    }

    // Call the Edge Function for online mode
    const { data: functionData, error: functionError } = await supabase.functions.invoke(
      'get-organization-members-details', // Ensure this matches your deployed function name
      {
        body: { orgId: selectedOrgId.value },
      }
    )

    if (functionError) {
      // Log the full error for debugging
      logger.error('Supabase function invocation error', { error: functionError })

      // Check for specific error messages or statuses from the function
      let userMessage = 'Failed to load organization members.'
      if (functionError.message.includes('Access denied')) {
        userMessage = 'Access denied: You are not authorized to view these members.'
      } else if (functionError.message.includes('User not authenticated')) {
        userMessage = 'Authentication error. Please log in again.'
      }
      // You could add more specific handling here based on function's error responses

      notify.error(userMessage)
      members.value = [] // Clear members on error
      return // Exit the function
    }

    // The function should return the array of members directly
    // or an object with an error property if the function itself caught an error (though we try to throw for functionError to catch)
    if (functionData && Array.isArray(functionData)) {
      members.value = functionData
    } else if (functionData && (functionData as any).error) {
      // This case handles if the function returns a JSON with an error key, e.g. { error: "some message" }
      logger.error('Error from get-organization-members-details function', (functionData as any).error)
      notify.error(`Failed to load members: ${(functionData as any).error}`)
      members.value = []
    } else {
      logger.warn('Unexpected response format from get-organization-members-details', { data: functionData })
      if (functionData === null || (Array.isArray(functionData) && functionData.length === 0)) {
        members.value = []
      } else {
        notify.error('Received an unexpected data format for members.')
        members.value = []
      }
    }
  } catch (error) {
    // Catch errors from the .invoke() call itself or network issues
    logger.error('Error invoking get-organization-members-details function', { error })
    notify.error((error as Error).message || 'An unexpected error occurred while fetching members.')
    members.value = []
  } finally {
    membersLoading.value = false
  }
}

const fetchInvitations = async () => {
  if (!selectedOrgId.value) return

  invitationsLoading.value = true
  try {
    const { data, error } = await supabase
      .from('organization_invitations')
      .select('id, email, role, created_at')
      .eq('org_id', selectedOrgId.value)
      .eq('accepted', false)

    if (error) throw error

    invitations.value = data || []
  } catch (error) {
    logger.error('Error fetching invitations', { error })
    invitations.value = []
  } finally {
    invitationsLoading.value = false
  }
}

const inviteMember = async () => {
  if (!newMemberEmail.value || !selectedOrgId.value) return

  addingMember.value = true
  try {
    // Use the Supabase Edge Function for invitation
    logger.info('Sending invitation with params', {
      email: newMemberEmail.value,
      orgId: selectedOrgId.value,
      orgName: selectedOrg.value?.name,
      role: newMemberRole.value,
      invitedBy: userData.value?.id,
    })

    const { data: functionData, error: functionError } = await supabase.functions.invoke('invite-member', {
      body: {
        email: newMemberEmail.value,
        orgId: selectedOrgId.value,
        orgName: selectedOrg.value?.name,
        role: newMemberRole.value,
        invitedBy: userData.value?.id,
      },
    })

    logger.info('Invitation response', { functionData, functionError })
    if (functionError) {
      throw functionError
    }

    logger.info('Invitation result', { data: functionData })

    // Notify the user of success
    notify.success(`Invitation sent to ${newMemberEmail.value}`)

    // Refresh invitations list
    await fetchInvitations()

    // Clear form
    newMemberEmail.value = ''
    newMemberRole.value = 'member'
  } catch (error) {
    logger.error('Error inviting member', { error })
    notify.error((error as Error).message || 'Failed to invite member')
  } finally {
    addingMember.value = false
  }
}

const cancelInvitation = async (invitationId: string) => {
  if (!invitationId || !selectedOrgId.value) return

  requestActionConfirmation('Cancel Invitation', 'Are you sure you want to cancel this invitation?', async () => {
    try {
      const { error } = await supabase
        .from('organization_invitations')
        .delete()
        .eq('id', invitationId)
        .eq('org_id', selectedOrgId.value)

      if (error) throw error

      await fetchInvitations()
      notify.success('Invitation cancelled')
    } catch (error) {
      logger.error('Error canceling invitation', { error })
      notify.error('Failed to cancel invitation')
    }
  })
}

const updateOrgName = async () => {
  if (!editOrgName.value || !selectedOrgId.value) return

  try {
    const { error } = await supabase
      .from('organizations')
      .update({ name: editOrgName.value })
      .eq('id', selectedOrgId.value)

    if (error) throw error

    // Update local data
    if (selectedOrg.value) {
      selectedOrg.value.name = editOrgName.value
    }

    editingOrg.value = false
  } catch (error) {
    logger.error('Error updating organization name', { error })
    notify.error('Failed to update organization name')
  }
}

const removeMember = async (userId: string) => {
  if (!userId || !selectedOrgId.value) return

  requestActionConfirmation('Remove Member', 'Are you sure you want to remove this member?', async () => {
    try {
      const { error } = await supabase
        .from('organization_members')
        .delete()
        .eq('user_id', userId)
        .eq('org_id', selectedOrgId.value)

      if (error) throw error

      await fetchOrgMembers()
      notify.success('Member removed')
    } catch (error) {
      logger.error('Error removing member', { error })
      notify.error('Failed to remove member')
    }
  })
}

const updateMemberRole = async (userId: string, newRole: string) => {
  if (!userId || !selectedOrgId.value) return

  try {
    const { error } = await supabase
      .from('organization_members')
      .update({ role: newRole })
      .eq('user_id', userId)
      .eq('org_id', selectedOrgId.value)

    if (error) throw error

    // Refresh members list
    await fetchOrgMembers()
  } catch (error) {
    logger.error('Error updating member role', { error })
    notify.error('Failed to update member role')
  }
}

// API Secrets management methods
const fetchSecrets = async () => {
  if (!selectedOrgId.value) return

  secretsLoading.value = true
  try {
    const response = await scopeoApi.organizationSecrets.getAll(selectedOrgId.value)

    logger.info('Secrets API response', { data: response }) // Debug log

    // Handle the actual API response format: { organization_id: "uuid", secret_keys: ["string"] }
    if (response && response.secret_keys && Array.isArray(response.secret_keys)) {
      secrets.value = response.secret_keys.map((key: string) => ({ key }))
    } else {
      secrets.value = []
    }

    logger.info('Processed secrets', { data: secrets.value }) // Debug log
  } catch (error) {
    logger.error('Error fetching secrets', { error })
    secrets.value = []
    // Show a user-friendly error message
    notify.error('Failed to load API keys. Please check your permissions and try again.')
  } finally {
    secretsLoading.value = false
  }
}

const openSecretDialog = (secret?: OrganizationSecret) => {
  if (secret) {
    editingSecret.value = secret
    secretForm.value = {
      key: secret.key,
      value: '', // Don't pre-fill for security
    }
    // Check if it's a known preset or custom
    isCustomKey.value = !secretPresets.some(preset => preset.value === secret.key)
  } else {
    editingSecret.value = null
    secretForm.value = {
      key: '',
      value: '',
    }
    isCustomKey.value = false
  }
  dialog.value = true
}

const closeSecretDialog = () => {
  dialog.value = false
  editingSecret.value = null
  secretForm.value = {
    key: '',
    value: '',
  }
  isCustomKey.value = false
}

const saveSecret = async () => {
  if (!selectedOrgId.value || !secretForm.value.key || !secretForm.value.value) return

  try {
    secretsLoading.value = true
    await scopeoApi.organizationSecrets.addOrUpdate(selectedOrgId.value, secretForm.value.key, {
      value: secretForm.value.value,
    })

    await fetchSecrets()
    closeSecretDialog()
  } catch (error) {
    logger.error('Error saving secret', { error })
    notify.error('Failed to save API key. Please try again.')
  } finally {
    secretsLoading.value = false
  }
}

const confirmDeleteSecret = (secretKey: string) => {
  secretToDelete.value = secretKey
  deleteDialog.value = true
}

const deleteSecret = async () => {
  if (!selectedOrgId.value || !secretToDelete.value) return

  try {
    secretsLoading.value = true
    await scopeoApi.organizationSecrets.delete(selectedOrgId.value, secretToDelete.value)
    await fetchSecrets()
    deleteDialog.value = false
    secretToDelete.value = ''
  } catch (error) {
    logger.error('Error deleting secret', { error })
    notify.error('Failed to delete API key. Please try again.')
  } finally {
    secretsLoading.value = false
  }
}

const selectPreset = (preset: any) => {
  if (preset?.value) {
    // Preset selected - fill in the key and disable editing
    secretForm.value.key = preset.value
    isCustomKey.value = false
  } else {
    // Custom key selected - clear the key and enable editing
    secretForm.value.key = ''
    isCustomKey.value = true
  }
}

// Organization API Keys management via TanStack Query
const { data: orgApiKeysData, isLoading: orgApiKeysLoading } = useOrgApiKeysQuery(selectedOrgId)
const orgApiKeys = computed(() => orgApiKeysData.value?.api_keys ?? [])

const createOrgApiKeyMutation = useCreateOrgApiKeyMutation()
const revokeOrgApiKeyMutation = useRevokeOrgApiKeyMutation()

const orgKeyDialog = ref(false)
const newOrgKeyName = ref('')
const generatedOrgKey = ref('')
const orgKeyDeleteDialog = ref(false)
const orgKeyToDelete = ref<OrgApiKey | null>(null)

// Snackbar for org API key feedback
const orgSnackbar = ref(false)
const orgSnackbarMessage = ref('')
const orgSnackbarColor = ref<'error' | 'success'>('error')

const actionConfirmDialog = ref(false)
const actionConfirmMessage = ref('')
const actionConfirmTitle = ref('Confirm Action')
const pendingConfirmedAction = ref<null | (() => Promise<void> | void)>(null)

const requestActionConfirmation = (title: string, message: string, action: () => Promise<void> | void) => {
  actionConfirmTitle.value = title
  actionConfirmMessage.value = message
  pendingConfirmedAction.value = action
  actionConfirmDialog.value = true
}

const onActionConfirmed = async () => {
  if (!pendingConfirmedAction.value) return
  const action = pendingConfirmedAction.value

  pendingConfirmedAction.value = null
  await action()
}

const generateOrgApiKey = async () => {
  if (!selectedOrgId.value || !newOrgKeyName.value) return

  try {
    const data = await createOrgApiKeyMutation.mutateAsync({
      key_name: newOrgKeyName.value,
      org_id: selectedOrgId.value,
    })

    generatedOrgKey.value = data.private_key
  } catch (error: unknown) {
    logger.warn('Failed to generate organization API key', { error })
    orgSnackbarMessage.value = 'Failed to generate organization API key.'
    orgSnackbarColor.value = 'error'
    orgSnackbar.value = true
  }
}

const closeOrgKeyDialog = () => {
  orgKeyDialog.value = false
  generatedOrgKey.value = ''
  newOrgKeyName.value = ''
}

const confirmDeleteOrgKey = (key: OrgApiKey) => {
  orgKeyToDelete.value = key
  orgKeyDeleteDialog.value = true
}

const deleteOrgApiKey = async () => {
  if (!orgKeyToDelete.value || !selectedOrgId.value) return

  try {
    await revokeOrgApiKeyMutation.mutateAsync({
      organizationId: selectedOrgId.value,
      keyId: orgKeyToDelete.value.key_id,
    })

    orgKeyDeleteDialog.value = false
    orgKeyToDelete.value = null
  } catch (error: unknown) {
    logger.warn('Failed to revoke organization API key', { error })
    orgSnackbarMessage.value = 'Failed to revoke organization API key.'
    orgSnackbarColor.value = 'error'
    orgSnackbar.value = true
  }
}

const copyOrgKeyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(generatedOrgKey.value)
  } catch (error: unknown) {
    logger.warn('Clipboard API not available', { error })
  }
}

// Watch for changes in selectedOrgId
watch(
  () => selectedOrgId.value,
  () => {
    if (selectedOrgId.value) {
      fetchSelectedOrg()
      fetchOrgMembers()
      fetchInvitations()
      fetchSecrets()
    } else {
      selectedOrg.value = null
      members.value = []
      invitations.value = []
      secrets.value = []
    }
  },
  { immediate: true }
)

// Watch for organization changes - stay on organization page in new org
watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/organization`)
  }
})

definePage({
  meta: {
    action: 'read',
    subject: 'Organization',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Organization Settings" />

    <VRow v-if="isOrgAdmin || userData?.super_admin">
      <VCol cols="12">
        <VCard v-if="loading">
          <VCardText>
            <VProgressLinear indeterminate color="primary" />
            <div class="text-center mt-4">Loading organization details...</div>
          </VCardText>
        </VCard>

        <template v-else-if="selectedOrg">
          <!-- Tabs outside the card -->
          <VTabs v-model="activeTab">
            <VTab v-for="tab in tabs" :key="tab.value" :value="tab.value">
              <VIcon size="20" start :icon="tab.icon" />
              {{ tab.title }}
            </VTab>
          </VTabs>

          <!-- Tab content in window -->
          <VWindow v-model="activeTab" class="mt-6 disable-tab-transition" :touch="false">
            <!-- General Tab -->
            <VWindowItem value="general">
              <VCard title="General Settings">
                <VCardText>
                  <VRow>
                    <VCol cols="12" md="6">
                      <VForm @submit.prevent="updateOrgName">
                        <VTextField
                          v-model="editOrgName"
                          label="Organization Name"
                          :readonly="!editingOrg"
                          :append-inner-icon="editingOrg ? 'tabler-check' : 'tabler-edit'"
                          @click:append-inner="editingOrg ? updateOrgName() : (editingOrg = true)"
                        />
                        <VBtn
                          v-if="editingOrg"
                          variant="outlined"
                          color="secondary"
                          class="mt-2"
                          @click="editingOrg = false"
                        >
                          Cancel
                        </VBtn>
                      </VForm>
                    </VCol>
                  </VRow>
                </VCardText>
              </VCard>

              <!-- Credit Usage Card -->
              <VCard title="Credit Usage" class="mt-8">
                <VCardText>
                  <VProgressLinear v-if="creditUsageLoading" indeterminate color="primary" class="mb-4" />

                  <VAlert v-else-if="creditUsageError" type="error" text="Failed to fetch credit usage data" />

                  <template v-else-if="creditUsageChart">
                    <!-- Progress Bar -->
                    <div
                      v-if="
                        creditUsageChart.progress_percentage !== null &&
                        creditUsageChart.progress_percentage !== undefined
                      "
                      class="mb-4"
                    >
                      <div class="d-flex align-center justify-space-between mb-1">
                        <span class="text-caption text-medium-emphasis"></span>
                        <span class="text-caption font-weight-medium"
                          >{{ Math.round(creditUsageChart.progress_percentage) }}%</span
                        >
                      </div>
                      <VProgressLinear
                        :model-value="creditUsageChart.progress_percentage"
                        :color="
                          creditUsageChart.progress_percentage >= 90
                            ? 'error'
                            : creditUsageChart.progress_percentage >= 75
                              ? 'warning'
                              : 'primary'
                        "
                        height="8"
                        rounded
                      />
                    </div>

                    <!-- Credit Usage Table -->
                    <VTable>
                      <thead>
                        <tr>
                          <th class="text-left">Metric</th>
                          <th class="text-left">Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(label, index) in creditUsageChart.data.labels || []" :key="index">
                          <td class="font-weight-medium">{{ label }}</td>
                          <td>{{ creditUsageChart.data.datasets[0]?.data?.[index] ?? 'N/A' }}</td>
                        </tr>
                      </tbody>
                    </VTable>
                  </template>

                  <EmptyState
                    v-else
                    icon="tabler-credit-card"
                    title="No Credit Usage Data"
                    description="Credit usage data will appear here once available."
                  />
                </VCardText>
              </VCard>
            </VWindowItem>

            <!-- Members Tab -->
            <VWindowItem value="members">
              <VCard title="Members Management">
                <VCardText>
                  <!-- Invite Member Form -->
                  <VRow>
                    <VCol cols="12" md="4">
                      <VTextField
                        v-model="newMemberEmail"
                        label="Email"
                        placeholder="user@example.com"
                        :disabled="addingMember"
                      />
                    </VCol>
                    <VCol cols="12" md="4">
                      <VSelect v-model="newMemberRole" :items="memberRoles" label="Role" :disabled="addingMember" />
                    </VCol>
                    <VCol cols="12" md="4" class="d-flex align-center">
                      <VBtn color="primary" :loading="addingMember" :disabled="!newMemberEmail" @click="inviteMember">
                        Invite Member
                      </VBtn>
                    </VCol>
                  </VRow>

                  <!-- Pending Invitations -->
                  <h4 class="text-h6 mt-6 mb-2">Pending Invitations</h4>
                  <VProgressLinear v-if="invitationsLoading" indeterminate color="primary" class="mb-4" />

                  <VTable v-else-if="invitations.length">
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Invited</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="invitation in invitations" :key="invitation.id">
                        <td>{{ invitation.email }}</td>
                        <td>
                          <VChip
                            size="small"
                            :color="
                              invitation.role === 'admin'
                                ? 'primary'
                                : invitation.role === 'developer'
                                  ? 'success'
                                  : invitation.role === 'member'
                                    ? 'info'
                                    : 'secondary'
                            "
                          >
                            {{ invitation.role }}
                          </VChip>
                        </td>
                        <td>{{ format(new Date(invitation.created_at), 'MMM dd, yyyy HH:mm') }}</td>
                        <td>
                          <VBtn
                            size="small"
                            variant="text"
                            color="error"
                            icon="tabler-trash"
                            @click="cancelInvitation(invitation.id)"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </VTable>
                  <EmptyState v-else icon="tabler-mail-off" title="No pending invitations" size="sm" />

                  <!-- Members List -->
                  <h4 class="text-h6 mt-6 mb-2">Current Members</h4>
                  <VProgressLinear v-if="membersLoading" indeterminate color="primary" class="mb-4" />

                  <VTable v-else-if="members.length">
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Joined</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="member in members" :key="member.id">
                        <td>{{ member.email }}</td>
                        <td>
                          <VSelect
                            v-model="member.role"
                            :items="memberRoles"
                            density="compact"
                            variant="plain"
                            hide-details
                            @update:model-value="updateMemberRole(member.id, $event)"
                          />
                        </td>
                        <td>
                          {{ member.created_at ? format(new Date(member.created_at), 'MMM dd, yyyy HH:mm') : '—' }}
                        </td>
                        <td>
                          <VBtn
                            size="small"
                            variant="text"
                            color="error"
                            icon="tabler-trash"
                            @click="removeMember(member.id)"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </VTable>
                  <EmptyState v-else icon="tabler-users" title="No members found" size="sm" />
                </VCardText>
              </VCard>
            </VWindowItem>

            <!-- API Keys Tab -->
            <VWindowItem value="secrets">
              <VCard title="API Keys">
                <VCardText>
                  <div class="d-flex justify-space-between align-center mb-4">
                    <div>
                      <p class="text-body-2 text-medium-emphasis">
                        Manage your external service API keys for AI models and services.
                      </p>
                    </div>
                    <VBtn color="primary" prepend-icon="tabler-plus" @click="openSecretDialog"> Add API Key </VBtn>
                  </div>

                  <VProgressLinear v-if="secretsLoading" indeterminate color="primary" class="mb-4" />

                  <!-- Secrets List -->
                  <VCard v-else-if="secrets.length" elevation="0" class="bordered-card">
                    <VList>
                      <VListItem
                        v-for="secret in secrets"
                        :key="secret.key"
                        :prepend-icon="
                          secret.key.includes('OPENAI')
                            ? 'logos-openai-icon'
                            : secret.key.includes('ANTHROPIC')
                              ? 'tabler-robot'
                              : secret.key.includes('MISTRAL')
                                ? 'tabler-wand'
                                : secret.key.includes('COHERE')
                                  ? 'tabler-hexagon'
                                  : secret.key.includes('GOOGLE')
                                    ? 'logos-google-icon'
                                    : secret.key.includes('AZURE')
                                      ? 'logos-azure-icon'
                                      : secret.key.includes('AWS')
                                        ? 'logos-aws'
                                        : 'tabler-key'
                        "
                      >
                        <VListItemTitle>{{ secret.key }}</VListItemTitle>
                        <VListItemSubtitle class="text-caption"> Value: •••••••••••••••••••• </VListItemSubtitle>

                        <template #append>
                          <VBtn icon="tabler-edit" size="small" variant="text" @click="openSecretDialog(secret)" />
                          <VBtn
                            icon="tabler-trash"
                            size="small"
                            variant="text"
                            color="error"
                            @click="confirmDeleteSecret(secret.key)"
                          />
                        </template>
                      </VListItem>
                    </VList>
                  </VCard>

                  <EmptyState
                    v-else
                    icon="tabler-key"
                    title="No API Keys"
                    description="Add your first API key to start using external AI services."
                    action-text="Add API Key"
                    @action="openSecretDialog"
                  />
                </VCardText>
              </VCard>
            </VWindowItem>

            <!-- Org API Keys Tab -->
            <VWindowItem value="org-api-keys">
              <VCard title="Organization API Keys">
                <VCardText>
                  <div class="d-flex justify-space-between align-center mb-4">
                    <div>
                      <p class="text-body-2 text-medium-emphasis">
                        Organization API keys grant access to all projects in this organization via the API.
                      </p>
                    </div>
                    <VBtn color="primary" prepend-icon="tabler-plus" @click="orgKeyDialog = true">
                      Generate New Key
                    </VBtn>
                  </div>

                  <VProgressLinear v-if="orgApiKeysLoading" indeterminate color="primary" class="mb-4" />

                  <!-- Org API Keys List -->
                  <VTable v-else-if="orgApiKeys.length" class="mb-4">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="key in orgApiKeys" :key="key.key_id">
                        <td>{{ key.key_name }}</td>
                        <td>
                          <VBtn size="x-small" color="error" variant="tonal" @click="confirmDeleteOrgKey(key)">
                            Revoke
                          </VBtn>
                        </td>
                      </tr>
                    </tbody>
                  </VTable>

                  <EmptyState
                    v-else
                    icon="tabler-lock"
                    title="No Organization API Keys"
                    description="Generate an organization-scoped API key to access all projects via the API."
                    action-text="Generate New Key"
                    @action="orgKeyDialog = true"
                  />
                </VCardText>
              </VCard>
            </VWindowItem>
          </VWindow>
        </template>

        <EmptyState
          v-else
          icon="tabler-building"
          title="No Organization Selected"
          description="Please select an organization from the dropdown in the sidebar."
        />
      </VCol>
    </VRow>

    <VRow v-else>
      <VCol cols="12">
        <EmptyState
          icon="tabler-lock"
          title="Access Restricted"
          description="You need to be an administrator of this organization to view this page."
        />
      </VCol>
    </VRow>
  </AppPage>

  <!-- Add/Edit Secret Dialog -->
  <VDialog v-model="dialog" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle>
        {{ editingSecret ? 'Edit API Key' : 'Add API Key' }}
      </VCardTitle>

      <VCardText>
        <VRow>
          <VCol cols="12">
            <VSelect
              label="Select Preset or Custom"
              :items="secretPresets"
              item-title="label"
              item-value="value"
              @update:model-value="selectPreset(secretPresets.find(p => p.value === $event))"
            />
          </VCol>

          <VCol v-if="isCustomKey" cols="12">
            <VTextField
              v-model="secretForm.key"
              label="Key Name"
              placeholder="Enter your custom key name"
              hint="Enter a unique identifier for your API key"
              persistent-hint
              :rules="[v => !!v || 'Key name is required']"
            />
          </VCol>

          <VCol cols="12">
            <VTextField
              v-model="secretForm.value"
              label="API Key Value"
              type="password"
              placeholder="Enter your API key"
              autocomplete="off"
              :rules="[v => !!v || 'API key value is required']"
            />
          </VCol>
        </VRow>
      </VCardText>

      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="closeSecretDialog"> Cancel </VBtn>
        <VBtn
          color="primary"
          :loading="secretsLoading"
          :disabled="!secretForm.key || !secretForm.value"
          @click="saveSecret"
        >
          {{ editingSecret ? 'Update' : 'Add' }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Delete Confirmation Dialog -->
  <VDialog v-model="deleteDialog" max-width="var(--dnr-dialog-sm)">
    <VCard>
      <VCardTitle>Confirm Delete</VCardTitle>
      <VCardText>
        Are you sure you want to delete the API key "{{ secretToDelete }}"? This action cannot be undone.
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="deleteDialog = false"> Cancel </VBtn>
        <VBtn color="error" :loading="secretsLoading" @click="deleteSecret"> Delete </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Generate Org API Key Dialog -->
  <VDialog v-model="orgKeyDialog" max-width="var(--dnr-dialog-md)" persistent>
    <VCard>
      <VCardTitle class="d-flex justify-space-between align-center">
        <span>Generate Organization API Key</span>
        <VBtn icon variant="text" @click="closeOrgKeyDialog">
          <VIcon>tabler-x</VIcon>
        </VBtn>
      </VCardTitle>
      <VCardText>
        <VTextField
          v-if="!generatedOrgKey"
          v-model="newOrgKeyName"
          label="Key Name"
          placeholder="e.g., NeverDrop Production Key"
          class="mb-4"
        />

        <VAlert v-if="generatedOrgKey" color="warning" class="mb-4">
          <p class="mb-2">Make sure to copy your API key now. You won't be able to see it again!</p>
          <VTextField :model-value="generatedOrgKey" readonly variant="outlined" density="compact">
            <template #append>
              <VBtn size="small" variant="text" color="primary" @click="copyOrgKeyToClipboard"> Copy </VBtn>
            </template>
          </VTextField>
        </VAlert>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn v-if="generatedOrgKey" color="primary" @click="closeOrgKeyDialog"> Done </VBtn>
        <VBtn
          v-else
          color="primary"
          :disabled="!newOrgKeyName"
          :loading="createOrgApiKeyMutation.isPending.value"
          @click="generateOrgApiKey"
        >
          Generate
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Revoke Org API Key Confirmation Dialog -->
  <GenericConfirmDialog
    v-if="orgKeyToDelete"
    v-model:is-dialog-visible="orgKeyDeleteDialog"
    title="Confirm Revoke"
    :message="`Are you sure you want to revoke the API key <strong>${orgKeyToDelete.key_name}</strong>? This action cannot be undone.`"
    confirm-text="Revoke"
    confirm-color="error"
    :loading="revokeOrgApiKeyMutation.isPending.value"
    @confirm="deleteOrgApiKey"
    @cancel="orgKeyDeleteDialog = false"
  />

  <GenericConfirmDialog
    v-model:is-dialog-visible="actionConfirmDialog"
    :title="actionConfirmTitle"
    :message="actionConfirmMessage"
    confirm-text="Confirm"
    confirm-color="error"
    @confirm="onActionConfirmed"
    @cancel="actionConfirmDialog = false"
  />

  <!-- Org API Key Snackbar -->
  <VSnackbar v-model="orgSnackbar" :color="orgSnackbarColor" :timeout="5000">
    {{ orgSnackbarMessage }}
  </VSnackbar>
</template>

<style scoped>
.bordered-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
