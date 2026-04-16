import { $api } from '@/utils/api'

export const agentsApi = {
  getAll: (organizationId: string) => $api(`/org/${organizationId}/agents`),
  getById: (agentId: string, graphRunnerId: string) => $api(`/agents/${agentId}/versions/${graphRunnerId}`),
  create: (
    organizationId: string,
    data: {
      id: string
      name: string
      description?: string
      icon?: string
      icon_color?: string
      template?: { template_graph_runner_id: string; template_project_id: string }
    }
  ) => $api(`/org/${organizationId}/agents`, { method: 'POST', body: data }),
  update: (agentId: string, graphRunnerId: string, data: any) =>
    $api(`/agents/${agentId}/versions/${graphRunnerId}`, { method: 'PUT', body: data }),
  deploy: (agentId: string, graphRunnerId: string) =>
    $api(`/projects/${agentId}/graph/${graphRunnerId}/deploy`, { method: 'POST' }),
}
