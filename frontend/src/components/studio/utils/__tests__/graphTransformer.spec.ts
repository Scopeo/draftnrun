import { describe, expect, it } from 'vitest'

import type { Edge } from '../../types/edge.types'
import type { PortConfiguration } from '../../types/graph.types'
import type { Node } from '../../types/node.types'
import { graphTransformer } from '../graphTransformer'

interface TestNode extends Node {
  data: Node['data'] & {
    port_configurations?: PortConfiguration[]
  }
}

function createNode(portConfigurations?: PortConfiguration[]): TestNode {
  return {
    id: 'node-1',
    type: 'component',
    data: {
      ref: 'Test',
      name: 'Test',
      component_id: 'component-1',
      component_version_id: 'component-version-1',
      is_agent: false,
      parameters: [
        {
          name: 'messages',
          value: null,
          display_order: null,
          type: 'array',
          nullable: true,
          default: null,
          ui_component: null,
          ui_component_properties: null,
          is_advanced: false,
          parameter_group_id: null,
          parameter_order_within_group: null,
          parameter_group_name: null,
          kind: 'input',
          is_tool_input: true,
        },
      ],
      tool_description: null,
      inputs: [],
      outputs: [],
      can_use_function_calling: false,
      function_callable: false,
      tools: [],
      subcomponents_info: [],
      component_name: 'Test',
      component_description: '',
      is_start_node: true,
      port_configurations: portConfigurations,
    },
    position: { x: 0, y: 0 },
  }
}

describe('graphTransformer.fromFlow', () => {
  it('preserves empty port_configurations array in the API payload', () => {
    const result = graphTransformer.fromFlow({
      nodes: [createNode([])],
      edges: [] as Edge[],
    })

    expect(result.component_instances[0]).toHaveProperty('port_configurations')
    expect(result.component_instances[0].port_configurations).toEqual([])
  })

  it('keeps explicit deactivated port_configurations in the API payload', () => {
    const portConfigurations: PortConfiguration[] = [
      {
        component_instance_id: 'node-1',
        parameter_id: 'parameter-1',
        input_port_instance_id: null,
        setup_mode: 'deactivated',
        expression_json: null,
        ai_name_override: null,
        ai_description_override: null,
        is_required_override: null,
        custom_parameter_type: null,
        custom_ui_component_properties: null,
        json_schema_override: null,
      },
    ]

    const result = graphTransformer.fromFlow({
      nodes: [createNode(portConfigurations)],
      edges: [] as Edge[],
    })

    expect(result.component_instances[0]).toHaveProperty('port_configurations')
    expect(result.component_instances[0].port_configurations).toEqual(portConfigurations)
  })

  it('keeps non-empty user_set and ai_filled port_configurations arrays in the API payload', () => {
    const portConfigurations: PortConfiguration[] = [
      {
        component_instance_id: 'node-1',
        parameter_id: 'parameter-1',
        input_port_instance_id: null,
        setup_mode: 'user_set',
        expression_json: { type: 'literal', value: 'preset' },
        ai_name_override: null,
        ai_description_override: null,
        is_required_override: null,
        custom_parameter_type: null,
        custom_ui_component_properties: null,
        json_schema_override: null,
      },
      {
        component_instance_id: 'node-1',
        parameter_id: 'parameter-2',
        input_port_instance_id: null,
        setup_mode: 'ai_filled',
        expression_json: null,
        ai_name_override: null,
        ai_description_override: null,
        is_required_override: null,
        custom_parameter_type: null,
        custom_ui_component_properties: null,
        json_schema_override: null,
      },
    ]

    const result = graphTransformer.fromFlow({
      nodes: [createNode(portConfigurations)],
      edges: [] as Edge[],
    })

    expect(result.component_instances[0].port_configurations).toEqual(portConfigurations)
  })
})
