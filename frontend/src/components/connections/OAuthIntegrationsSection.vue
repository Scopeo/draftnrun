<script setup lang="ts">
import { computed, ref } from 'vue'
import { useNotifications } from '@/composables/useNotifications'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import {
  type VariableDefinition,
  useOrgVariableDefinitionsQuery,
} from '@/composables/queries/useVariableDefinitionsQuery'
import { useDeleteOAuthConnectionMutation } from '@/composables/queries/useOAuthConnectionsQuery'
import { useOAuthFlow } from '@/composables/useOAuthFlow'
import { useSelectedOrg } from '@/composables/useSelectedOrg'

const { selectedOrgId } = useSelectedOrg()
const { notify } = useNotifications()

const {
  data: orgDefinitions,
  isLoading,
  refetch: refetchDefinitions,
} = useOrgVariableDefinitionsQuery(selectedOrgId, { type: 'oauth' })

const deleteMutation = useDeleteOAuthConnectionMutation(selectedOrgId)

const {
  state: oauthState,
  errorMessage,
  startOAuthFlow,
  confirmConnection,
  cancelFlow,
} = useOAuthFlow(() => selectedOrgId.value)

const activeConnections = computed(() => (orgDefinitions.value as VariableDefinition[] | undefined) ?? [])

const AVAILABLE_INTEGRATIONS = [
  { key: 'slack', name: 'Slack', icon: 'logos-slack-icon', description: 'Slack messaging and notifications' },
  { key: 'google-mail', name: 'Gmail', icon: 'logos-google-gmail', description: 'Gmail email integration' },
  { key: 'hubspot', name: 'HubSpot', icon: 'logos-hubspot', description: 'CRM and marketing automation' },
]

const selectedIntegration = ref<(typeof AVAILABLE_INTEGRATIONS)[0] | null>(null)
const isConfirming = ref(false)

const deleteDialog = ref(false)
const defToDelete = ref('')

const headers = [
  { title: 'Connection Name', key: 'name', sortable: true },
  { title: 'Provider', key: 'provider', sortable: true },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

function getProvider(defn: VariableDefinition): string {
  return ((defn.metadata as Record<string, unknown>)?.provider_config_key as string) || '—'
}

async function openConnectDialog(integration: (typeof AVAILABLE_INTEGRATIONS)[0]) {
  selectedIntegration.value = integration
  await startOAuthFlow(integration.key)
}

async function handleConfirm() {
  if (!selectedIntegration.value) return
  isConfirming.value = true
  try {
    await confirmConnection(selectedIntegration.value.key)
    await refetchDefinitions()
  } finally {
    isConfirming.value = false
  }
}

function confirmDelete(name: string) {
  defToDelete.value = name
  deleteDialog.value = true
}

async function doDelete() {
  if (!defToDelete.value || !selectedOrgId.value) return

  const defn = activeConnections.value.find(d => d.name === defToDelete.value)
  if (!defn) return

  const connectionId = defn.default_value
  const providerConfigKey = (defn.metadata as Record<string, unknown>)?.provider_config_key as string
  if (!connectionId || !providerConfigKey) return

  try {
    await deleteMutation.mutateAsync({ connectionId, providerConfigKey })
    defToDelete.value = ''
    deleteDialog.value = false
  } catch (error) {
    notify.error('Failed to revoke connection')
  }
}

const showDialog = computed(() => ['waiting_oauth', 'error'].includes(oauthState.value))
</script>

<template>
  <!-- Available Integrations -->
  <div class="mb-6">
    <h4 class="text-h6 mb-3">Available Integrations</h4>
    <VRow>
      <VCol v-for="integration in AVAILABLE_INTEGRATIONS" :key="integration.key" cols="12" sm="6" md="4">
        <VCard elevation="0" class="integration-card pa-4 h-100 d-flex flex-column">
          <div class="d-flex align-center gap-3 mb-3">
            <VAvatar size="40" rounded="lg" color="grey-100">
              <VIcon :icon="integration.icon" size="24" />
            </VAvatar>
            <span class="text-subtitle-1 font-weight-medium">{{ integration.name }}</span>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-4 flex-grow-1">
            {{ integration.description }}
          </p>
          <VBtn
            color="primary"
            variant="tonal"
            size="small"
            prepend-icon="tabler-plug"
            block
            :loading="oauthState === 'authorizing' && selectedIntegration?.key === integration.key"
            @click="openConnectDialog(integration)"
          >
            Connect
          </VBtn>
        </VCard>
      </VCol>
    </VRow>
  </div>

  <!-- Active OAuth Connections -->
  <div>
    <h4 class="text-h6 mb-3">Active Connections</h4>

    <VCard v-if="isLoading" class="pa-6 text-center">
      <VProgressCircular indeterminate color="primary" />
    </VCard>

    <EmptyState
      v-else-if="activeConnections.length === 0"
      icon="tabler-plug-off"
      title="No active connections"
      description="Connect an integration above to get started."
      size="sm"
    />

    <VDataTable
      v-else
      :headers="headers"
      :items="activeConnections"
      :items-per-page="-1"
      density="comfortable"
      class="elevation-0"
    >
      <template #item.provider="{ item }">
        <VChip size="small" variant="tonal" color="info">
          {{ getProvider(item) }}
        </VChip>
      </template>
      <template #item.actions="{ item }">
        <VBtn icon variant="text" size="small" color="error" @click="confirmDelete(item.name)">
          <VIcon icon="tabler-trash" size="18" />
        </VBtn>
      </template>
      <template #bottom />
    </VDataTable>
  </div>

  <!-- OAuth Dialog (waiting / error) -->
  <VDialog :model-value="showDialog" max-width="var(--dnr-dialog-sm)" persistent>
    <VCard>
      <template v-if="oauthState === 'waiting_oauth'">
        <VCardTitle class="text-h6 d-flex align-center gap-2">
          <VIcon v-if="selectedIntegration" :icon="selectedIntegration.icon" size="22" />
          Connect {{ selectedIntegration?.name }}
        </VCardTitle>

        <VCardText>
          <VAlert type="info" variant="tonal" density="compact" class="mb-4">
            Complete the authorization in the opened browser tab, then click "I've authorized, continue" below.
          </VAlert>

          <div class="text-center py-4">
            <VIcon icon="tabler-external-link" size="48" class="text-medium-emphasis mb-3" />
            <div class="text-body-2 text-medium-emphasis">Authorization window opened</div>
          </div>
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="text" @click="cancelFlow"> Cancel </VBtn>
          <VBtn color="primary" variant="elevated" :loading="isConfirming" @click="handleConfirm">
            I've authorized, continue
          </VBtn>
        </VCardActions>
      </template>

      <template v-else-if="oauthState === 'error'">
        <VCardTitle class="text-h6">Connection Failed</VCardTitle>

        <VCardText>
          <VAlert type="error" variant="tonal" density="compact">
            {{ errorMessage }}
          </VAlert>
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="text" @click="cancelFlow"> Close </VBtn>
        </VCardActions>
      </template>
    </VCard>
  </VDialog>

  <!-- Delete OAuth Connection Confirmation -->
  <GenericConfirmDialog
    :is-dialog-visible="deleteDialog"
    title="Delete Connection"
    :message="`Are you sure you want to delete the connection <strong>${defToDelete}</strong>? Workflows using this connection will no longer be able to authenticate.`"
    confirm-text="Delete"
    confirm-color="error"
    :loading="deleteMutation.isPending.value"
    @update:is-dialog-visible="deleteDialog = $event"
    @confirm="doDelete"
    @cancel="deleteDialog = false"
  />
</template>

<style lang="scss" scoped>
.integration-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition:
    background-color 0.2s ease-out,
    border-color 0.2s ease-out;

  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.02);
    border-color: rgba(var(--v-border-color), 0.12);
  }
}
</style>
