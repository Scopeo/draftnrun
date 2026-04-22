import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { gitSyncApi } from '@/api/gitSync'
import type { GitHubAppInfo, GitHubRepo, GitSyncConfig, GitSyncImportResponse } from '@/api/gitSync'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

export function useGitHubAppInfoQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['github-app-info', orgId.value])

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      logQueryStart(queryKey.value, 'useGitHubAppInfoQuery')
      logNetworkCall(queryKey.value, `/organizations/${orgId.value}/git-sync/github-app`)
      return gitSyncApi.getGitHubAppInfo(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 10,
    gcTime: 1000 * 60 * 30,
  })
}

export function useGitSyncConfigsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['git-sync-configs', orgId.value])

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      logQueryStart(queryKey.value, 'useGitSyncConfigsQuery')
      logNetworkCall(queryKey.value, `/organizations/${orgId.value}/git-sync`)
      return gitSyncApi.listConfigs(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

export function useGitSyncInstallationReposQuery(
  orgId: Ref<string | undefined>,
  installationId: Ref<number | null>,
  installState: Ref<string | null>,
) {
  const queryKey = computed(() => ['git-sync-repos', orgId.value, installationId.value])

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      if (!installationId.value) throw new Error('No installation ID provided')
      logQueryStart(queryKey.value, 'useGitSyncInstallationReposQuery')
      logNetworkCall(queryKey.value, `/organizations/${orgId.value}/git-sync/installations/${installationId.value}/repos`)
      return gitSyncApi.listInstallationRepos(orgId.value, installationId.value, installState.value)
    },
    enabled: computed(() => !!orgId.value && !!installationId.value),
    staleTime: 1000 * 60 * 2,
  })
}

export function useImportFromGitHubMutation() {
  const queryClient = useQueryClient()

  return useMutation<
    GitSyncImportResponse,
    Error,
    {
      orgId: string
      data: {
        github_owner: string
        github_repo_name: string
        branch: string
        github_installation_id: number
      }
    }
  >({
    mutationFn: async ({ orgId, data }) => {
      logNetworkCall(['import-github', orgId], `/organizations/${orgId}/git-sync`)
      return gitSyncApi.importFromGitHub(orgId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['git-sync-configs', variables.orgId] })
      queryClient.invalidateQueries({ queryKey: ['projects', variables.orgId] })
    },
  })
}

export function useDeleteGitSyncConfigMutation() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, { orgId: string; configId: string }>({
    mutationFn: async ({ orgId, configId }) => {
      logNetworkCall(['delete-git-sync-config', configId], `/organizations/${orgId}/git-sync/${configId}`)
      await gitSyncApi.deleteConfig(orgId, configId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['git-sync-configs', variables.orgId] })
    },
  })
}
