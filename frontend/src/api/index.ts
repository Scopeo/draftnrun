import { templatesApi, workflowsApi } from './workflows'
import { agentsApi } from './agents'
import { studioApi } from './studio'
import { observabilityApi } from './observability'
import { qaApi, qaEvaluationApi } from './qa'
import { knowledgeApi } from './knowledge'
import { cronApi } from './cron'
import {
  orgVariableDefinitionsApi,
  organizationCreditUsageApi,
  organizationLimitsApi,
  organizationSecretsApi,
  variableSetsApi,
} from './organization'
import { widgetApi } from './widgets'
import { integrationApi } from './integration'
import { apiKeysApi, orgApiKeysApi } from './auth-keys'
import { filesApi } from './files'
import { llmModelsApi } from './llm-models'
import { adminToolsApi, categoriesApi, componentsApi, settingsSecretsApi } from './admin'
import { chatApi, runsApi } from './chat'
import { oauthConnectionsApi } from './oauth'
import { ingestionTaskApi, sourcesApi } from './sources'

export { workflowsApi, templatesApi } from './workflows'
export { agentsApi } from './agents'
export { studioApi } from './studio'
export { observabilityApi } from './observability'
export type { ObservabilityApi } from './observability'
export { qaApi, qaEvaluationApi } from './qa'
export { knowledgeApi } from './knowledge'
export { cronApi } from './cron'
export {
  organizationSecretsApi,
  organizationLimitsApi,
  organizationCreditUsageApi,
  orgVariableDefinitionsApi,
  variableSetsApi,
} from './organization'
export { widgetApi } from './widgets'
export type { WidgetTheme, WidgetConfig, Widget, CreateWidgetData, UpdateWidgetData } from './widgets'
export { integrationApi } from './integration'
export { apiKeysApi, orgApiKeysApi } from './auth-keys'
export { filesApi } from './files'
export { llmModelsApi } from './llm-models'
export { adminToolsApi, settingsSecretsApi, componentsApi, categoriesApi } from './admin'
export type { ComponentFieldsOptionsResponse, UpdateComponentFieldsRequest } from './admin'
export { chatApi, runsApi } from './chat'
export type { ChatAsyncAccepted, ChatAsyncResult } from './chat'
export { oauthConnectionsApi } from './oauth'
export type { OAuthConnectionListItem } from './oauth'
export { sourcesApi, ingestionTaskApi } from './sources'

export const scopeoApi = {
  projects: workflowsApi,
  templates: templatesApi,
  agents: agentsApi,
  apiKeys: apiKeysApi,
  orgApiKeys: orgApiKeysApi,
  knowledge: knowledgeApi,
  observability: observabilityApi,
  chat: chatApi,
  runs: runsApi,
  studio: studioApi,
  components: componentsApi,
  ingestionTask: ingestionTaskApi,
  sources: sourcesApi,
  files: filesApi,
  llmModels: llmModelsApi,
  organizationSecrets: organizationSecretsApi,
  organizationLimits: organizationLimitsApi,
  organizationCreditUsage: organizationCreditUsageApi,
  integration: integrationApi,
  adminTools: adminToolsApi,
  qa: qaApi,
  qaEvaluation: qaEvaluationApi,
  cron: cronApi,
  widget: widgetApi,
  categories: categoriesApi,
  oauthConnections: oauthConnectionsApi,
  orgVariableDefinitions: orgVariableDefinitionsApi,
  variableSets: variableSetsApi,
  settingsSecrets: settingsSecretsApi,
}
