import { $api } from '@/utils/api'

export interface GitHubAppInfo {
  configured: boolean
  install_url: string | null
}

export interface GitHubRepo {
  full_name: string
  name: string
  owner: string
  default_branch: string
  private: boolean
}

export interface GitSyncImportResult {
  graph_folder: string
  project_id: string
  project_name: string
  config_id: string
  status: string
}

export interface GitSyncImportResponse {
  imported: GitSyncImportResult[]
  skipped: string[]
}

export interface GitSyncConfig {
  id: string
  organization_id: string
  project_id: string
  github_owner: string
  github_repo_name: string
  graph_folder: string
  branch: string
  github_installation_id: number
  last_sync_at: string | null
  last_sync_status: string | null
  last_sync_commit_sha: string | null
  last_sync_error: string | null
  created_at: string
  updated_at: string
}

export const gitSyncApi = {
  getGitHubAppInfo: (orgId: string) =>
    $api<GitHubAppInfo>(`/organizations/${orgId}/git-sync/github-app`),

  listConfigs: (orgId: string) =>
    $api<GitSyncConfig[]>(`/organizations/${orgId}/git-sync`),

  listInstallationRepos: (orgId: string, installationId: number, state?: string | null) => {
    const params = state ? `?${new URLSearchParams({ state })}` : ''
    return $api<GitHubRepo[]>(`/organizations/${orgId}/git-sync/installations/${installationId}/repos${params}`)
  },

  importFromGitHub: (
    orgId: string,
    data: {
      github_owner: string
      github_repo_name: string
      branch: string
      github_installation_id: number
    }
  ) =>
    $api<GitSyncImportResponse>(`/organizations/${orgId}/git-sync`, {
      method: 'POST',
      body: data,
    }),

  deleteConfig: (orgId: string, configId: string) =>
    $api(`/organizations/${orgId}/git-sync/${configId}`, { method: 'DELETE' }),
}
