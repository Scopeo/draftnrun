import { describe, expect, it } from 'vitest'

import { ensureProviderModelFormat, transformModelParametersToConfig } from '../agentUtils'

describe('agentUtils', () => {
  it('defaults empty models to GPT-5 Mini with OpenAI provider', () => {
    expect(ensureProviderModelFormat('')).toBe('openai:gpt-5-mini')
  })

  it('defaults missing completion model parameters to GPT-5 Mini', () => {
    const config = transformModelParametersToConfig([
      {
        id: 'completion-model',
        name: 'completion_model',
        type: 'llm_model',
        value: null,
        default: null,
        nullable: false,
        is_advanced: false,
        display_order: null,
        ui_component: null,
        ui_component_properties: null,
      },
    ])

    expect(config.model).toBe('openai:gpt-5-mini')
  })
})
