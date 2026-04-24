<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import {
  useGitHubAppInfoQuery,
  useGitSyncInstallationReposQuery,
  useImportFromGitHubMutation,
} from '@/composables/queries/useGitSyncQueries'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { GitHubRepo } from '@/api/gitSync'

const visible = defineModel<boolean>({ default: false })

const { selectedOrgId } = useSelectedOrg()
const { notify } = useNotifications()

const { data: githubAppInfo, isLoading: githubAppLoading } = useGitHubAppInfoQuery(selectedOrgId)

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
const selectedRepo = ref<GitHubRepo | null>(null)
const importBranch = ref('main')

const { data: importRepos, isLoading: importReposLoading } = useGitSyncInstallationReposQuery(
  selectedOrgId,
  pendingInstallationId,
  pendingInstallState,
)

const importMutation = useImportFromGitHubMutation()

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
    let msg = `Imported ${count} workflow${count !== 1 ? 's' : ''} from GitHub.`
    if (skippedCount > 0) {
      msg += ` ${skippedCount} already linked.`
    }
    notify.success(msg)
    closeDialog()
  } catch (error) {
    logger.error('GitHub import failed', { error })
    notify.error(error instanceof Error ? error.message : 'Failed to import from GitHub.')
  }
}

function resetState() {
  pendingInstallationId.value = null
  pendingInstallState.value = null
  selectedRepo.value = null
  importBranch.value = 'main'
  githubConnecting.value = false
  clearPopupPoll()
}

function closeDialog() {
  visible.value = false
  resetState()
}

watch(visible, (val) => {
  if (!val) resetState()
})

onMounted(() => {
  window.addEventListener('message', handleGitHubMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handleGitHubMessage)
  clearPopupPoll()
})
</script>

<template>
  <VDialog v-model="visible" max-width="560" persistent>
    <VCard>
      <VCardTitle class="d-flex justify-space-between align-center pa-4">
        <div class="d-flex align-center gap-3">
          <VIcon icon="logos-github-icon" size="22" />
          <span class="text-h6">Import from GitHub</span>
        </div>
        <VBtn icon variant="text" size="small" @click="closeDialog">
          <VIcon icon="tabler-x" size="18" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pt-4 px-4">
        <!-- Loading GitHub App info -->
        <div v-if="githubAppLoading" class="text-center py-6">
          <VProgressCircular indeterminate color="primary" />
          <div class="text-body-2 text-medium-emphasis mt-2">Checking GitHub connection…</div>
        </div>

        <!-- GitHub App not configured by admin -->
        <div v-else-if="!githubAppInfo?.configured" class="text-center py-6">
          <VIcon icon="tabler-brand-github" size="48" class="text-medium-emphasis mb-3" />
          <p class="text-body-1 mb-1">GitHub integration is not configured.</p>
          <p class="text-body-2 text-medium-emphasis">
            Ask your organization admin to set up the GitHub App in Settings.
          </p>
        </div>

        <!-- Step 1: Connect to GitHub -->
        <div v-else-if="!pendingInstallationId" class="text-center py-4">
          <VIcon icon="tabler-brand-github" size="48" class="text-medium-emphasis mb-3" />
          <p class="text-body-1 font-weight-medium mb-2">Connect your GitHub account</p>
          <p class="text-body-2 text-medium-emphasis mb-5">
            Install the Draft'n Run GitHub App to grant access to your repositories. Workflows will be imported and auto-deployed on every push.
          </p>
          <VBtn
            color="primary"
            prepend-icon="tabler-brand-github"
            :loading="githubConnecting"
            @click="connectGitHub"
          >
            Connect to GitHub
          </VBtn>
        </div>

        <!-- Step 2: Select repo & branch -->
        <template v-else>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Select a repository to import. Draft'n Run will scan it for workflow definitions and auto-deploy on every push.
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
        </template>
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-4">
        <VBtn variant="text" @click="closeDialog">Cancel</VBtn>
        <VBtn
          v-if="pendingInstallationId"
          color="primary"
          :loading="importMutation.isPending.value"
          :disabled="!selectedRepo || !importBranch"
          @click="doImport"
        >
          Import
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
