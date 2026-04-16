import { describe, expect, it, vi } from 'vitest'

import {
  agentsApi,
  apiKeysApi,
  chatApi,
  cronApi,
  filesApi,
  integrationApi,
  knowledgeApi,
  llmModelsApi,
  oauthConnectionsApi,
  observabilityApi,
  qaApi,
  scopeoApi,
  sourcesApi,
  studioApi,
  widgetApi,
  workflowsApi,
} from '../index'

vi.mock('@/utils/api', () => ({
  $api: vi.fn(),
  SESSION_EXPIRED_KEY: 'sessionExpired',
}))

describe('api barrel (src/api/index.ts)', () => {
  it('scopeoApi.projects is the same reference as workflowsApi (backward compat)', () => {
    expect(scopeoApi.projects).toBe(workflowsApi)
  })

  it('all expected API modules are accessible on scopeoApi', () => {
    expect(scopeoApi.agents).toBe(agentsApi)
    expect(scopeoApi.studio).toBe(studioApi)
    expect(scopeoApi.observability).toBe(observabilityApi)
    expect(scopeoApi.qa).toBe(qaApi)
    expect(scopeoApi.knowledge).toBe(knowledgeApi)
    expect(scopeoApi.cron).toBe(cronApi)
    expect(scopeoApi.widget).toBe(widgetApi)
    expect(scopeoApi.integration).toBe(integrationApi)
    expect(scopeoApi.apiKeys).toBe(apiKeysApi)
    expect(scopeoApi.files).toBe(filesApi)
    expect(scopeoApi.llmModels).toBe(llmModelsApi)
    expect(scopeoApi.chat).toBe(chatApi)
    expect(scopeoApi.oauthConnections).toBe(oauthConnectionsApi)
    expect(scopeoApi.sources).toBe(sourcesApi)
  })

  it('individual named exports are defined', () => {
    expect(workflowsApi).toBeDefined()
    expect(agentsApi).toBeDefined()
    expect(studioApi).toBeDefined()
    expect(observabilityApi).toBeDefined()
    expect(qaApi).toBeDefined()
    expect(knowledgeApi).toBeDefined()
    expect(cronApi).toBeDefined()
    expect(widgetApi).toBeDefined()
    expect(integrationApi).toBeDefined()
    expect(apiKeysApi).toBeDefined()
    expect(filesApi).toBeDefined()
    expect(llmModelsApi).toBeDefined()
    expect(chatApi).toBeDefined()
    expect(oauthConnectionsApi).toBeDefined()
    expect(sourcesApi).toBeDefined()
  })
})
