<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import type {
  ApiKey,
  ApiKeysResponse,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  RevokeKeyResponse,
} from '@/types/apiKeys'

const route = useRoute()
const projectId = route.params.id as string
const { notify } = useNotifications()

const apiKeys = ref<ApiKey[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const newKeyDialog = ref(false)
const newKeyName = ref('')
const generatedKey = ref('')
const ability = useAbility()

// Refs for revoke confirmation
const showRevokeConfirmation = ref(false)
const keyToRevoke = ref<ApiKey | null>(null)

// Fetch API keys
const fetchApiKeys = async () => {
  loading.value = true
  error.value = null

  try {
    const response = await scopeoApi.apiKeys.getAll(projectId)

    apiKeys.value = (response as ApiKeysResponse).api_keys
  } catch (err) {
    logger.error('Failed to fetch API keys', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to fetch API keys'
  } finally {
    loading.value = false
  }
}

// Function to close the new key dialog and reset state
const closeAndResetNewKeyDialog = () => {
  newKeyDialog.value = false
  generatedKey.value = '' // Reset the generated key
  newKeyName.value = '' // Reset the input name
}

const generateNewKey = async () => {
  try {
    const request: CreateApiKeyRequest = {
      key_name: newKeyName.value,
      project_id: projectId,
    }

    const response = await scopeoApi.apiKeys.create(projectId, request)
    const data = response as CreateApiKeyResponse

    generatedKey.value = data.private_key
    await fetchApiKeys() // Refresh the list
    // Don't reset newKeyName here, keep dialog open
    newKeyDialog.value = true // Ensure dialog stays open to show the key
  } catch (err) {
    logger.error('Failed to generate API key', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to generate API key'
  }
}

// Prepare for revoke confirmation
const requestRevokeKey = (key: ApiKey) => {
  keyToRevoke.value = key
  showRevokeConfirmation.value = true
}

// Actual revoke function (called on confirm)
const confirmRevokeKey = async () => {
  if (!keyToRevoke.value) return

  try {
    const response = await scopeoApi.apiKeys.revoke(projectId, { key_id: keyToRevoke.value.key_id })
    const data = response as RevokeKeyResponse

    if (data.message) {
      notify.success('API key revoked successfully')
    }

    await fetchApiKeys()
  } catch (err) {
    logger.error('Failed to revoke API key', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to revoke API key'
    notify.error(error.value)
  } finally {
    keyToRevoke.value = null // Clear the key after attempt
    // Dialog closes automatically via v-model
  }
}

const cancelRevoke = () => {
  keyToRevoke.value = null // Clear the key on cancel
  // Dialog closes automatically via v-model
}

const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(generatedKey.value)
  } catch (err) {
    logger.error('Failed to copy to clipboard', { error: err })
  }
}

// Fetch API keys on component mount
onMounted(() => {
  fetchApiKeys()
})
</script>

<template>
  <VCard>
    <VCardTitle class="text-h6 pt-6 px-6">API Keys</VCardTitle>
    <VCardText>
      <div class="d-flex justify-space-between align-center mb-4">
        <h5 class="text-h5">API Keys</h5>
        <VTooltip text="You need admin or developer permissions to generate API keys">
          <template #activator="{ props }">
            <VBtn
              color="primary"
              prepend-icon="tabler-plus"
              :disabled="!ability.can('create', 'Project')"
              v-bind="props"
              @click="ability.can('create', 'Project') ? (newKeyDialog = true) : null"
            >
              Generate New Key
            </VBtn>
          </template>
        </VTooltip>
      </div>

      <!-- API Keys Table -->
      <VProgressCircular v-if="loading" indeterminate color="primary" />
      <VAlert v-else-if="error" type="error" variant="tonal" class="mb-4">
        {{ error }}
      </VAlert>
      <VTable v-else class="api-keys-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in apiKeys" :key="key.key_id">
            <td>{{ key.key_name }}</td>
            <td>
              <VBtn
                v-if="ability.can('delete', 'Project')"
                size="x-small"
                color="error"
                variant="tonal"
                @click="requestRevokeKey(key)"
              >
                Revoke
              </VBtn>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCardText>

    <!-- New API Key Dialog -->
    <VDialog v-model="newKeyDialog" max-width="var(--dnr-dialog-md)" persistent>
      <VCard>
        <VCardTitle class="d-flex justify-space-between align-center">
          <span>Generate New API Key</span>
          <VBtn icon variant="text" @click="closeAndResetNewKeyDialog">
            <VIcon>tabler-x</VIcon>
          </VBtn>
        </VCardTitle>
        <VCardText>
          <VTextField
            v-if="!generatedKey"
            v-model="newKeyName"
            label="Key Name"
            placeholder="e.g., Production API Key"
            class="mb-4"
          />

          <VAlert v-if="generatedKey" color="warning" class="mb-4">
            <p class="mb-2">Make sure to copy your API key now. You won't be able to see it again!</p>
            <VTextField :model-value="generatedKey" readonly variant="outlined" density="compact">
              <template #append>
                <VBtn size="small" variant="text" color="primary" @click="copyToClipboard"> Copy </VBtn>
              </template>
            </VTextField>
          </VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn v-if="generatedKey" color="primary" @click="closeAndResetNewKeyDialog"> Done </VBtn>
          <VBtn v-else color="primary" :disabled="!newKeyName" @click="generateNewKey"> Generate </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Revoke Confirmation Dialog -->
    <GenericConfirmDialog
      v-if="keyToRevoke"
      v-model:is-dialog-visible="showRevokeConfirmation"
      title="Confirm Revoke"
      :message="`Are you sure you want to revoke the API key <strong>${keyToRevoke.key_name}</strong>? This action cannot be undone.`"
      confirm-text="Revoke"
      confirm-color="error"
      @confirm="confirmRevokeKey"
      @cancel="cancelRevoke"
    />
  </VCard>
</template>

<style lang="scss" scoped>
.api-keys-table {
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(th) {
    font-weight: 600;
    text-transform: uppercase;
    white-space: nowrap;
  }

  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(td) {
    block-size: 3.5rem;
    vertical-align: middle;
  }
}
</style>
