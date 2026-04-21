<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import {
  type VariableDefinition,
  useOrgVariableDefinitionsQuery,
} from '@/composables/queries/useVariableDefinitionsQuery'
import { useOAuthFlow } from '@/composables/useOAuthFlow'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { scopeoApi } from '@/api'
import type { GitHubRepo, GitSyncConfig } from '@/api/gitSync'

const { selectedOrgId } = useSelectedOrg()
const { notify } = useNotifications()

// ─── OAuth integrations ───────────────────────────────────────

const {
  data: orgDefinitions,
  isLoading,
  refetch: refetchDefinitions,
} = useOrgVariableDefinitionsQuery(selectedOrgId, { type: 'oauth' })

const isRevoking = ref(false)

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
  {
    key: 'google-mail',
    name: 'Gmail',
    icon: 'logos-google-gmail',
    description: 'Gmail email integration',
  },
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
  const provider = (defn.metadata as Record<string, unknown>)?.provider_config_key as string
  if (!connectionId || !provider) return

  isRevoking.value = true
  try {
    await scopeoApi.oauthConnections.delete(selectedOrgId.value, connectionId, provider)
    await refetchDefinitions()
    defToDelete.value = ''
    deleteDialog.value = false
  } catch (error) {
    logger.error('Failed to revoke connection', { error })
  } finally {
    isRevoking.value = false
  }
}

const showDialog = computed(() => ['waiting_oauth', 'error'].includes(oauthState.value))

// ─── GitHub / Git Sync ────────────────────────────────────────

const githubAppInfo = ref<{ configured: boolean; install_url: string | null }>({ configured: false, install_url: null })
const githubAppLoading = ref(true)
const gitSyncConfigs = ref<GitSyncConfig[]>([])
const gitSyncLoading = ref(false)
const githubConnecting = ref(false)

const pendingInstallationId = ref<number | null>(null)
const importDialogVisible = ref(false)
const importRepos = ref<GitHubRepo[]>([])
const importReposLoading = ref(false)
const selectedRepo = ref<GitHubRepo | null>(null)
const importBranch = ref('main')
const isImporting = ref(false)

const disconnectDialog = ref(false)
const configToDisconnect = ref<GitSyncConfig | null>(null)
const isDisconnecting = ref(false)

const gitSyncHeaders = [
  { title: 'Repository', key: 'repo', sortable: true },
  { title: 'Branch', key: 'branch', sortable: true },
  { title: 'Folder', key: 'graph_folder', sortable: false },
  { title: 'Last Sync', key: 'last_sync_status', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

async function loadGitHubAppInfo() {
  if (!selectedOrgId.value) return
  githubAppLoading.value = true
  try {
    githubAppInfo.value = await scopeoApi.gitSync.getGitHubAppInfo(selectedOrgId.value)
  } catch (error) {
    logger.error('Failed to load GitHub App info', { error })
  } finally {
    githubAppLoading.value = false
  }
}

async function loadGitSyncConfigs() {
  if (!selectedOrgId.value) return
  gitSyncLoading.value = true
  try {
    gitSyncConfigs.value = await scopeoApi.gitSync.listConfigs(selectedOrgId.value)
  } catch (error) {
    logger.error('Failed to load git sync configs', { error })
  } finally {
    gitSyncLoading.value = false
  }
}

function handleGitHubMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin) return
  if (event.data?.type !== 'github-app-installed') return

  githubConnecting.value = false
  const installationId = event.data.installation_id as number | undefined
  if (!installationId) {
    notify.error('GitHub App installation failed — no installation ID received.')
    return
  }

  pendingInstallationId.value = installationId
  openImportDialog(installationId)
}

function connectGitHub() {
  if (!githubAppInfo.value.install_url) return

  githubConnecting.value = true
  const width = 1000
  const height = 700
  const left = window.screenX + (window.outerWidth - width) / 2
  const top = window.screenY + (window.outerHeight - height) / 2

  const popup = window.open(
    githubAppInfo.value.install_url,
    '_blank',
    `width=${width},height=${height},left=${left},top=${top},popup=yes`,
  )

  if (!popup) {
    githubConnecting.value = false
    notify.error('Failed to open GitHub. Please allow popups for this site.')
  }
}

async function openImportDialog(installationId: number) {
  importDialogVisible.value = true
  importReposLoading.value = true
  selectedRepo.value = null
  importBranch.value = 'main'

  try {
    importRepos.value = await scopeoApi.gitSync.listInstallationRepos(selectedOrgId.value!, installationId)
  } catch (error) {
    logger.error('Failed to list repos for installation', { error })
    notify.error('Failed to list repositories from GitHub.')
    importRepos.value = []
  } finally {
    importReposLoading.value = false
  }
}

function onRepoSelected(repo: GitHubRepo | null) {
  selectedRepo.value = repo
  if (repo) {
    importBranch.value = repo.default_branch
  }
}

async function doImport() {
  if (!selectedRepo.value || !pendingInstallationId.value || !selectedOrgId.value) return

  isImporting.value = true
  try {
    const result = await scopeoApi.gitSync.importFromGitHub(selectedOrgId.value, {
      github_owner: selectedRepo.value.owner,
      github_repo_name: selectedRepo.value.name,
      branch: importBranch.value,
      github_installation_id: pendingInstallationId.value,
    })

    const count = result.imported.length
    const skippedCount = result.skipped.length
    let msg = `Imported ${count} project${count !== 1 ? 's' : ''} from GitHub.`
    if (skippedCount > 0) {
      msg += ` ${skippedCount} already linked.`
    }
    notify.success(msg)

    importDialogVisible.value = false
    pendingInstallationId.value = null
    await loadGitSyncConfigs()
  } catch (error) {
    logger.error('GitHub import failed', { error })
    notify.error(error instanceof Error ? error.message : 'Failed to import from GitHub.')
  } finally {
    isImporting.value = false
  }
}

function cancelImport() {
  importDialogVisible.value = false
  pendingInstallationId.value = null
}

function confirmDisconnect(config: GitSyncConfig) {
  configToDisconnect.value = config
  disconnectDialog.value = true
}

async function doDisconnect() {
  if (!configToDisconnect.value || !selectedOrgId.value) return
  isDisconnecting.value = true
  try {
    await scopeoApi.gitSync.deleteConfig(selectedOrgId.value, configToDisconnect.value.id)
    await loadGitSyncConfigs()
    disconnectDialog.value = false
    configToDisconnect.value = null
    notify.success('Git sync disconnected.')
  } catch (error) {
    logger.error('Failed to disconnect git sync', { error })
    notify.error('Failed to disconnect git sync.')
  } finally {
    isDisconnecting.value = false
  }
}

function syncStatusColor(status: string | null): string {
  if (status === 'success') return 'success'
  if (status === 'fetch_failed') return 'warning'
  if (status && status !== 'success') return 'error'
  return 'default'
}

function syncStatusLabel(status: string | null): string {
  if (!status) return 'Pending'
  if (status === 'success') return 'Success'
  return status.replace(/_/g, ' ')
}

onMounted(() => {
  window.addEventListener('message', handleGitHubMessage)
  loadGitHubAppInfo()
  loadGitSyncConfigs()
})

onUnmounted(() => {
  window.removeEventListener('message', handleGitHubMessage)
})

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader
      title="Integrations"
      description="Connect your organization to external services. Each connection creates an OAuth variable definition that can be used in workflows."
    >
      <template #badge>
        <VChip size="small" color="warning" variant="tonal">Beta</VChip>
      </template>
    </AppPageHeader>

    <!-- Version Control -->
    <div v-if="!githubAppLoading && githubAppInfo.configured" class="mb-6">
      <h4 class="text-h6 mb-3">Version Control</h4>
      <VRow>
        <VCol cols="12" sm="6" md="4">
          <VCard elevation="0" class="integration-card pa-4 h-100 d-flex flex-column">
            <div class="d-flex align-center gap-3 mb-3">
              <VAvatar size="40" rounded="lg" color="grey-100">
                <VIcon icon="mdi-github" size="24" />
              </VAvatar>
              <span class="text-subtitle-1 font-weight-medium">GitHub</span>
            </div>
            <p class="text-body-2 text-medium-emphasis mb-4 flex-grow-1">
              Sync workflows from a GitHub repository. Changes pushed to your branch are auto-deployed.
            </p>
            <VBtn
              color="primary"
              variant="tonal"
              size="small"
              prepend-icon="tabler-plug"
              block
              :loading="githubConnecting"
              @click="connectGitHub"
            >
              Connect
            </VBtn>
          </VCard>
        </VCol>
      </VRow>
    </div>

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

    <!-- Git Sync Connections -->
    <div v-if="gitSyncConfigs.length > 0 || gitSyncLoading" class="mb-6">
      <h4 class="text-h6 mb-3">Auto-deploy settings</h4>

      <VCard v-if="gitSyncLoading" class="pa-6 text-center" elevation="0">
        <VProgressCircular indeterminate color="primary" />
      </VCard>

      <VDataTable
        v-else
        :headers="gitSyncHeaders"
        :items="gitSyncConfigs"
        :items-per-page="-1"
        density="comfortable"
        class="elevation-0"
      >
        <template #item.repo="{ item }">
          <div class="d-flex align-center gap-2">
            <VIcon icon="mdi-github" size="18" />
            <a
              :href="`https://github.com/${item.github_owner}/${item.github_repo_name}`"
              target="_blank"
              rel="noopener"
              class="text-primary text-decoration-none"
            >
              {{ item.github_owner }}/{{ item.github_repo_name }}
            </a>
          </div>
        </template>
        <template #item.graph_folder="{ item }">
          <code class="text-body-2">{{ item.graph_folder || '/' }}</code>
        </template>
        <template #item.last_sync_status="{ item }">
          <VChip
            size="small"
            variant="tonal"
            :color="syncStatusColor(item.last_sync_status)"
          >
            {{ syncStatusLabel(item.last_sync_status) }}
          </VChip>
        </template>
        <template #item.actions="{ item }">
          <VBtn icon variant="text" size="small" color="error" @click="confirmDisconnect(item)">
            <VIcon icon="tabler-trash" size="18" />
            <VTooltip activator="parent" location="top">Disconnect sync</VTooltip>
          </VBtn>
        </template>
        <template #bottom />
      </VDataTable>
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

    <!-- GitHub Import Dialog -->
    <VDialog v-model="importDialogVisible" max-width="560" persistent>
      <VCard>
        <VCardTitle class="text-h6 d-flex align-center gap-2">
          <VIcon icon="mdi-github" size="22" />
          Import from GitHub
        </VCardTitle>

        <VCardText>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Select a repository to sync. Draft'n Run will scan it for workflow definitions and auto-deploy on every push.
          </p>

          <div v-if="importReposLoading" class="text-center py-6">
            <VProgressCircular indeterminate color="primary" />
            <div class="text-body-2 text-medium-emphasis mt-2">Loading repositories…</div>
          </div>

          <template v-else>
            <VAutocomplete
              v-model="selectedRepo"
              :items="importRepos"
              :item-title="(r: GitHubRepo) => r.full_name"
              label="Repository"
              placeholder="Search repositories…"
              return-object
              variant="outlined"
              density="compact"
              class="mb-3"
              @update:model-value="onRepoSelected"
            >
              <template #item="{ props: itemProps, item }">
                <VListItem v-bind="itemProps">
                  <template #prepend>
                    <VIcon :icon="item.raw.private ? 'tabler-lock' : 'tabler-world'" size="18" class="me-2" />
                  </template>
                </VListItem>
              </template>
            </VAutocomplete>

            <VTextField
              v-model="importBranch"
              label="Branch"
              variant="outlined"
              density="compact"
              placeholder="main"
            />
          </template>
        </VCardText>

        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="cancelImport">Cancel</VBtn>
          <VBtn
            color="primary"
            variant="elevated"
            :loading="isImporting"
            :disabled="!selectedRepo || !importBranch"
            @click="doImport"
          >
            Import
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Delete OAuth Connection Confirmation -->
    <GenericConfirmDialog
      :is-dialog-visible="deleteDialog"
      title="Delete Connection"
      :message="`Are you sure you want to delete the connection <strong>${defToDelete}</strong>? Workflows using this connection will no longer be able to authenticate.`"
      confirm-text="Delete"
      confirm-color="error"
      :loading="isRevoking"
      @update:is-dialog-visible="deleteDialog = $event"
      @confirm="doDelete"
      @cancel="deleteDialog = false"
    />

    <!-- Disconnect Git Sync Confirmation -->
    <GenericConfirmDialog
      :is-dialog-visible="disconnectDialog"
      title="Disconnect Git Sync"
      :message="configToDisconnect
        ? `Are you sure you want to disconnect sync for <strong>${configToDisconnect.github_owner}/${configToDisconnect.github_repo_name}</strong>? The project will remain but will no longer auto-deploy on push.`
        : ''"
      confirm-text="Disconnect"
      confirm-color="error"
      :loading="isDisconnecting"
      @update:is-dialog-visible="disconnectDialog = $event"
      @confirm="doDisconnect"
      @cancel="disconnectDialog = false"
    />
  </AppPage>
</template>

<style scoped>
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
