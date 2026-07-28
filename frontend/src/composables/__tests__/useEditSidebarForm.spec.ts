import { computed, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useEditSidebarForm } from '../useEditSidebarForm'
import { scopeoApi } from '@/api'

vi.mock('@/composables/useNotifications', () => ({
  useNotifications: () => ({
    notify: {
      success: vi.fn(),
      info: vi.fn(),
      error: vi.fn(),
    },
  }),
}))

vi.mock('@/composables/useSelectedOrg', () => ({
  useSelectedOrg: () => ({ selectedOrgId: ref(null) }),
}))

vi.mock('@/api', () => ({
  scopeoApi: {
    sources: {
      getAll: vi.fn(),
    },
    studio: {
      testApiCallOutputPorts: vi.fn(),
    },
  },
}))

describe('useEditSidebarForm API Call output-port test values', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('detects per-expression runtime inputs and sends parsed test values', async () => {
    vi.mocked(scopeoApi.studio.testApiCallOutputPorts).mockResolvedValue({ output_port_names: ['name'] })

    const componentData = computed(() => ({
      id: 'component-instance-id',
      name: 'API Call',
      component_name: 'API Call',
      parameters: [
        { name: 'method', value: 'GET', kind: 'parameter', type: 'string', ui_component: 'SELECT' },
        {
          name: 'endpoint',
          value: 'https://api.example.com/users/@{{start.user_id}}',
          kind: 'parameter',
          type: 'string',
          ui_component: 'TEXTFIELD',
        },
        {
          name: 'headers',
          value: { Authorization: 'Bearer @{{api_token}}' },
          kind: 'parameter',
          type: 'json',
          ui_component: 'JSON_TEXTAREA',
        },
        {
          name: 'fixed_parameters',
          value: { filters: '@{{filters}}' },
          kind: 'parameter',
          type: 'json',
          ui_component: 'JSON_TEXTAREA',
        },
      ],
    }))

    const componentDefinition = computed(() => ({
      name: 'API Call',
      parameters: componentData.value.parameters,
    }))

    const form = useEditSidebarForm(
      componentData,
      componentDefinition,
      computed(() => []),
      computed(() => 'api-call-component-version-id'),
      computed(() => false),
      computed(() => true),
      computed(() => null),
      computed(() => ({ projectId: 'project-id', graphRunnerId: 'graph-runner-id' }))
    )

    await nextTick()

    expect(form.apiCallDetectedTestValues.value).toEqual([
      { key: 'api_token', label: 'api_token' },
      { key: 'filters', label: 'filters' },
      { key: 'start.user_id', label: 'start.user_id' },
    ])

    form.apiCallTestValueInputs.value['api_token'] = 'secret-token'
    form.apiCallTestValueInputs.value['filters'] = '{"active":true}'
    form.apiCallTestValueInputs.value['start.user_id'] = '123'

    await form.testApiCallOutputPorts('component-instance-id', form.buildParametersForApiCallOutputPortTest())

    expect(scopeoApi.studio.testApiCallOutputPorts).toHaveBeenCalledWith(
      'project-id',
      'graph-runner-id',
      'component-instance-id',
      expect.any(Array),
      {
        api_token: 'secret-token',
        filters: { active: true },
        'start.user_id': 123,
      },
      []
    )
  })
})
