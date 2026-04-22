<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import {
  useDeleteGitSyncConfigMutation,
  useGitHubAppInfoQuery,
  useGitSyncConfigsQuery,
  useGitSyncInstallationReposQuery,
  useImportFromGitHubMutation,
} from '@/composables/queries/useGitSyncQueries'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { GitHubRepo, GitSyncConfig } from '@/api/gitSync'

const { selectedOrgId } = useSelectedOrg()
const { notify } = useNotifications()

const { data: githubAppInfo, isLoading: githubAppLoading } = useGitHubAppInfoQuery(selectedOrgId)
const { data: gitSyncConfigs, isLoading: gitSyncLoading } = useGitSyncConfigsQuery(selectedOrgId)

const githubConnecting = ref(false)
let pollCloseHandle: ReturnType<typeof setInterval> | null = null
let popupRef: Window | null = null

function clearPopupPoll() {
  if (pollCloseHandle !== null) {
    clearInterval(pollCloseHandle)
    pollCloseHandle = null
  }
  popupRef = null
  githubConnecting.value = false
}

const pendingInstallationId = ref<number | null>(null)
const pendingInstallState = ref<string | null>(null)
const importDialogVisible = ref(false)
const selectedRepo = ref<GitHubRepo | null>(null)
const importBranch = ref('main')

const { data: importRepos, isLoading: importReposLoading } = useGitSyncInstallationReposQuery(
  selectedOrgId,
  pendingInstallationId,
  pendingInstallState,
)

const disconnectDialog = ref(false)
const configToDisconnect = ref<GitSyncConfig | null>(null)

const importMutation = useImportFromGitHubMutation()
const deleteMutation = useDeleteGitSyncConfigMutation()

const gitSyncHeaders = [
  { title: 'Repository', key: 'repo', sortable: true },
  { title: 'Branch', key: 'branch', sortable: true },
  { title: 'Folder', key: 'graph_folder', sortable: false },
  { title: 'Last Sync', key: 'last_sync_status', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' as const },
]

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
  pendingInstallState.value = (event.data.state as string) ?? null
  openImportDialog(installationId)
}

function connectGitHub() {
  if (!githubAppInfo.value?.install_url) return

  clearPopupPoll()
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
    return
  }

  popupRef = popup
  pollCloseHandle = setInterval(() => {
    if (popup.closed) {
      clearPopupPoll()
    }
  }, 500)
}

function openImportDialog(installationId: number) {
  importDialogVisible.value = true
  selectedRepo.value = null
  importBranch.value = 'main'
  pendingInstallationId.value = installationId
}

function onRepoSelected(repo: GitHubRepo | null) {
  selectedRepo.value = repo
  if (repo) {
    importBranch.value = repo.default_branch
  }
}

async function doImport() {
  if (!selectedRepo.value || !pendingInstallationId.value || !selectedOrgId.value) return

  try {
    const result = await importMutation.mutateAsync({
      orgId: selectedOrgId.value,
      data: {
        github_owner: selectedRepo.value.owner,
        github_repo_name: selectedRepo.value.name,
        branch: importBranch.value,
        github_installation_id: pendingInstallationId.value,
      },
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
    pendingInstallState.value = null
  } catch (error) {
    logger.error('GitHub import failed', { error })
    notify.error(error instanceof Error ? error.message : 'Failed to import from GitHub.')
  }
}

function cancelImport() {
  importDialogVisible.value = false
  pendingInstallationId.value = null
  pendingInstallState.value = null
}

function confirmDisconnect(config: GitSyncConfig) {
  configToDisconnect.value = config
  disconnectDialog.value = true
}

async function doDisconnect() {
  if (!configToDisconnect.value || !selectedOrgId.value) return

  try {
    await deleteMutation.mutateAsync({
      orgId: selectedOrgId.value,
      configId: configToDisconnect.value.id,
    })
    disconnectDialog.value = false
    configToDisconnect.value = null
    notify.success('Git sync disconnected.')
  } catch (error) {
    logger.error('Failed to disconnect git sync', { error })
    notify.error('Failed to disconnect git sync.')
  }
}

function syncStatusColor(status: string | null): string {
  if (status === 'success') return 'success'
  if (status === 'fetch_failed') return 'warning'
  if (status) return 'error'
  return 'default'
}

function syncStatusLabel(status: string | null): string {
  if (!status) return 'Pending'
  if (status === 'success') return 'Success'
  return status.replace(/_/g, ' ')
}

onMounted(() => {
  window.addEventListener('message', handleGitHubMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handleGitHubMessage)
  clearPopupPoll()
})
</script>

<template>
  <!-- Version Control -->
  <div v-if="!githubAppLoading && githubAppInfo?.configured" class="mb-6">
    <h4 class="text-h6 mb-3">Version Control</h4>
    <VRow>
      <VCol cols="12" sm="6" md="4">
        <VCard elevation="0" class="integration-card pa-4 h-100 d-flex flex-column">
          <div class="d-flex align-center gap-3 mb-3">
            <VAvatar size="40" rounded="lg" color="grey-100">
              <VIcon icon="logos-github-icon" size="24" />
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

  <!-- Git Sync Connections -->
  <div v-if="(gitSyncConfigs?.length ?? 0) > 0 || gitSyncLoading" class="mb-6">
    <h4 class="text-h6 mb-3">Auto-deploy settings</h4>

    <VCard v-if="gitSyncLoading" class="pa-6 text-center" elevation="0">
      <VProgressCircular indeterminate color="primary" />
    </VCard>

    <VDataTable
      v-else
      :headers="gitSyncHeaders"
      :items="gitSyncConfigs ?? []"
      :items-per-page="-1"
      density="comfortable"
      class="elevation-0"
    >
      <template #item.repo="{ item }">
        <div class="d-flex align-center">
          <VIcon icon="logos-github-icon" size="18" class="me-3" />
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

  <!-- GitHub Import Dialog -->
  <VDialog v-model="importDialogVisible" max-width="560" persistent>
    <VCard>
      <VCardTitle class="text-h6 d-flex align-center">
        <VIcon icon="logos-github-icon" size="22" class="me-3" />
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
            :items="importRepos ?? []"
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
          :loading="importMutation.isPending.value"
          :disabled="!selectedRepo || !importBranch"
          @click="doImport"
        >
          Import
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Disconnect Git Sync Confirmation -->
  <GenericConfirmDialog
    :is-dialog-visible="disconnectDialog"
    title="Disconnect Git Sync"
    :message="configToDisconnect
      ? `Are you sure you want to disconnect sync for <strong>${configToDisconnect.github_owner}/${configToDisconnect.github_repo_name}</strong>? The project will remain but will no longer auto-deploy on push.`
      : ''"
    confirm-text="Disconnect"
    confirm-color="error"
    :loading="deleteMutation.isPending.value"
    @update:is-dialog-visible="disconnectDialog = $event"
    @confirm="doDisconnect"
    @cancel="disconnectDialog = false"
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
