import { $api } from '@/utils/api'

export const integrationApi = {
  addOrUpdateIntegration: (
    projectId: string,
    integrationId: string,
    data: {
      integration_id: string
      access_token: string
      refresh_token: string
      expires_in: number
      token_last_updated: string
    }
  ) =>
    $api(`/project/${projectId}/integration/${integrationId}`, {
      method: 'PUT',
      body: data,
    }),
}
