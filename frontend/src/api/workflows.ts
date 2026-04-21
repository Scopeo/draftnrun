import { $api } from '@/utils/api'

export const workflowsApi = {
  getAll: () => $api('/projects'),
  getById: (projectId: string) => $api(`/projects/${projectId}`),
  getByOrgId: (
    organizationId: string,
    type?: 'AGENT' | 'WORKFLOW',
    includeTemplates?: boolean,
    tags?: string[]
  ) => {
    const params: Record<string, any> = {}
    if (type) {
      params.type = type.toLowerCase()
    }
    if (includeTemplates !== undefined) params.include_templates = includeTemplates
    if (tags && tags.length > 0) params.tags = tags

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
      tags?: string[]
    }
  ) => $api(`/projects/${projectId}`, { method: 'PATCH', body: data }),
  delete: (projectId: string) => $api(`/projects/${projectId}`, { method: 'DELETE' }),
  getOrgTags: (organizationId: string): Promise<string[]> =>
    $api(`/projects/org/${organizationId}/tags`),
  addTags: (projectId: string, tags: string[]): Promise<string[]> =>
    $api(`/projects/${projectId}/tags`, { method: 'POST', body: { tags } }),
  removeTag: (projectId: string, tag: string): Promise<string[]> =>
    $api(`/projects/${projectId}/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' }),
}

export const templatesApi = {
  getAll: (organizationId: string) => $api(`/templates/${organizationId}`),
}
