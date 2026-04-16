import { $api } from '@/utils/api'

export const workflowsApi = {
  getAll: () => $api('/projects'),
  getById: (projectId: string) => $api(`/projects/${projectId}`),
  getByOrgId: (organizationId: string, type?: 'AGENT' | 'WORKFLOW', includeTemplates?: boolean) => {
    const params: Record<string, any> = {}
    if (type) {
      params.type = type.toLowerCase()
    }
    if (includeTemplates !== undefined) params.include_templates = includeTemplates

    return $api(`/projects/org/${organizationId}`, { query: params })
  },
  create: (organizationId: string, data: any) => $api(`/projects/${organizationId}`, { method: 'POST', body: data }),
  update: (projectId: string, data: any) => $api(`/projects/${projectId}`, { method: 'PUT', body: data }),
  updateProject: (
    projectId: string,
    data: {
      project_name?: string
      description?: string
      companion_image_url?: string
      icon?: string
      icon_color?: string
    }
  ) => $api(`/projects/${projectId}`, { method: 'PATCH', body: data }),
  delete: (projectId: string) => $api(`/projects/${projectId}`, { method: 'DELETE' }),
}

export const templatesApi = {
  getAll: (organizationId: string) => $api(`/templates/${organizationId}`),
}
