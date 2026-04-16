import { $api } from '@/utils/api'

export interface OAuthConnectionListItem {
  id: string
  name: string
  provider_config_key: string
  created_at: string
  created_by_user_id: string | null
}

export const oauthConnectionsApi = {
  authorize: (
    orgId: string,
    data: {
      provider_config_key: string
      end_user_email?: string
    }
  ) =>
    $api<{ oauth_url: string; pending_connection_id: string }>(`/organizations/${orgId}/oauth-connections/authorize`, {
      method: 'POST',
      body: data,
    }),

  confirm: (
    orgId: string,
    data: {
      provider_config_key: string
      name?: string
      pending_connection_id: string
    }
  ) =>
    $api<{ connection_id: string; provider_config_key: string; name: string; definition_id?: string }>(
      `/organizations/${orgId}/oauth-connections`,
      { method: 'POST', body: data }
    ),

  list: (orgId: string, providerConfigKey?: string) =>
    $api<OAuthConnectionListItem[]>(`/organizations/${orgId}/oauth-connections`, {
      query: providerConfigKey ? { provider_config_key: providerConfigKey } : undefined,
    }),

  update: (orgId: string, connectionId: string, data: { name: string }) =>
    $api<{ connection_id: string; provider_config_key: string; name: string }>(
      `/organizations/${orgId}/oauth-connections/${connectionId}`,
      { method: 'PATCH', body: data }
    ),

  delete: (orgId: string, connectionId: string, providerConfigKey: string) =>
    $api(`/organizations/${orgId}/oauth-connections/${connectionId}`, {
      method: 'DELETE',
      query: { provider_config_key: providerConfigKey },
    }),

  checkStatus: (orgId: string, connectionId: string, providerConfigKey: string) =>
    $api<{ connected: boolean; provider_config_key: string; connection_id: string | null; name?: string }>(
      `/organizations/${orgId}/oauth-connections/status`,
      {
        query: {
          connection_id: connectionId,
          provider_config_key: providerConfigKey,
        },
      }
    ),
}
