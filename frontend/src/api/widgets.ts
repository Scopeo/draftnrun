import { $api } from '@/utils/api'

export interface WidgetTheme {
  primary_color: string
  secondary_color: string
  background_color: string
  text_color: string
  border_radius: number
  font_family: string
  logo_url: string | null
}

export interface WidgetConfig {
  name?: string
  theme: WidgetTheme
  header_message: string | null
  first_messages: string[]
  suggestions: string[]
  placeholder_text: string
  powered_by_visible: boolean
  rate_limit_config: number
  rate_limit_chat: number
  allowed_origins: string[]
}

export interface Widget {
  id: string
  widget_key: string
  project_id: string
  organization_id: string
  name: string
  is_enabled: boolean
  config: WidgetConfig
  created_at: string
  updated_at: string
}

export interface CreateWidgetData {
  project_id: string
  name: string
  is_enabled?: boolean
  config?: Partial<WidgetConfig>
}

export interface UpdateWidgetData {
  name?: string
  is_enabled?: boolean
  config?: Partial<WidgetConfig>
}

export const widgetApi = {
  getByProject: (projectId: string): Promise<Widget | null> => $api(`/widgets/project/${projectId}`),

  getById: (widgetId: string): Promise<Widget> => $api(`/widgets/${widgetId}`),

  listByOrg: (organizationId: string): Promise<Widget[]> => $api(`/org/${organizationId}/widgets`),

  create: (organizationId: string, data: CreateWidgetData): Promise<Widget> =>
    $api(`/org/${organizationId}/widgets`, { method: 'POST', body: data }),

  update: (widgetId: string, data: UpdateWidgetData): Promise<Widget> =>
    $api(`/widgets/${widgetId}`, { method: 'PATCH', body: data }),

  regenerateKey: (widgetId: string): Promise<Widget> => $api(`/widgets/${widgetId}/regenerate-key`, { method: 'POST' }),

  delete: (widgetId: string): Promise<void> => $api(`/widgets/${widgetId}`, { method: 'DELETE' }),
}
