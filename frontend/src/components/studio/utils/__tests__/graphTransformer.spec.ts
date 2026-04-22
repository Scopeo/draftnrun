import { describe, expect, it } from 'vitest'
import { graphTransformer } from '../graphTransformer'

describe('graphTransformer', () => {
  describe('extractComponentUpdateV2', () => {
    it('filters out input-kind parameters from the parameters list', () => {
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'model', value: 'gpt-4', kind: 'parameter', type: 'string', nullable: false },
            { name: 'messages', value: 'hello', kind: 'input', type: 'string', nullable: false },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      const paramNames = result.parameters.map(p => p.name)
      expect(paramNames).toContain('model')
      expect(paramNames).not.toContain('messages')
    })

    it('includes input-kind parameters as input_port_instances', () => {
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'model', value: 'gpt-4', kind: 'parameter', type: 'string', nullable: false },
            {
              name: 'messages',
              value: { type: 'json_build', template: [{ role: 'user', content: '__REF_0__' }], refs: { '__REF_0__': { type: 'ref', instance: 'abc', port: 'output' } } },
              kind: 'input',
              type: 'string',
              nullable: false,
            },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      expect(result.input_port_instances).toHaveLength(1)
      expect(result.input_port_instances[0].name).toBe('messages')
      expect(result.input_port_instances[0].field_expression.expression_json).toEqual(node.data.parameters[1].value)
    })

    it('skips input-kind parameters with null value', () => {
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'messages', value: null, kind: 'input', type: 'string', nullable: true },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      expect(result.input_port_instances).toHaveLength(0)
    })

    it('includes field_expressions with expression_json that are not input-kind params', () => {
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'prompt', value: '@{{abc.output}}', kind: 'parameter', type: 'string', nullable: false },
          ],
          field_expressions: [
            { field_name: 'prompt', expression_json: { type: 'ref', instance: 'abc', port: 'output' } },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      expect(result.input_port_instances).toHaveLength(1)
      expect(result.input_port_instances[0].name).toBe('prompt')
      expect(result.input_port_instances[0].field_expression.expression_json).toEqual({
        type: 'ref',
        instance: 'abc',
        port: 'output',
      })
    })

    it('uses expression_text as fallback when expression_json is missing', () => {
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'prompt', value: '@{{abc.output}}', kind: 'parameter', type: 'string', nullable: false },
          ],
          field_expressions: [
            { field_name: 'prompt', expression_text: '@{{abc.output}}' },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      expect(result.input_port_instances).toHaveLength(1)
      expect(result.input_port_instances[0].name).toBe('prompt')
      expect(result.input_port_instances[0].field_expression.expression_json).toBe('@{{abc.output}}')
    })

    it('does not duplicate when input-kind param already covers a field_expression', () => {
      const exprJson = { type: 'ref', instance: 'abc', port: 'output' }
      const node = {
        id: 'node-1',
        data: {
          parameters: [
            { name: 'messages', value: exprJson, kind: 'input', type: 'string', nullable: false },
          ],
          field_expressions: [
            { field_name: 'messages', expression_json: exprJson },
          ],
        },
      }

      const result = graphTransformer.extractComponentUpdateV2(node as any)

      expect(result.input_port_instances).toHaveLength(1)
      expect(result.input_port_instances[0].name).toBe('messages')
    })
  })

  describe('prepareTopologyForSaveV2', () => {
    const makeNode = (overrides: Record<string, any> = {}): any => ({
      id: 'n1',
      type: 'component',
      data: { name: 'Node 1', is_start_node: false },
      position: { x: 0, y: 0 },
      ...overrides,
    })

    const makeEdge = (overrides: Record<string, any> = {}): any => ({
      id: 'e1',
      source: 'n1',
      target: 'n2',
      sourceHandle: 'right',
      targetHandle: 'left',
      order: null,
      ...overrides,
    })

    it('converts nodes into topology format with instance_id and label', () => {
      const nodes = [makeNode({ id: 'a', data: { name: 'Alpha' } })]
      const result = graphTransformer.prepareTopologyForSaveV2(nodes, [])

      expect(result.nodes).toHaveLength(1)
      expect(result.nodes[0]).toEqual({
        instance_id: 'a',
        label: 'Alpha',
        is_start_node: true,
      })
    })

    it('marks component nodes without incoming left-handle edges as start nodes', () => {
      const nodes = [
        makeNode({ id: 'a', data: { name: 'A' } }),
        makeNode({ id: 'b', data: { name: 'B' } }),
      ]
      const edges = [makeEdge({ id: 'e1', source: 'a', target: 'b' })]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      const nodeA = result.nodes.find(n => n.instance_id === 'a')
      const nodeB = result.nodes.find(n => n.instance_id === 'b')
      expect(nodeA!.is_start_node).toBe(true)
      expect(nodeB!.is_start_node).toBe(false)
    })

    it('preserves is_start_node from data for non-component node types', () => {
      const workerNode = makeNode({
        id: 'w1',
        type: 'worker',
        data: { name: 'Worker', is_start_node: true },
      })
      const result = graphTransformer.prepareTopologyForSaveV2([workerNode], [])

      expect(result.nodes[0].is_start_node).toBe(true)
    })

    it('falls back to label when name is missing', () => {
      const node = makeNode({ id: 'x', data: { label: 'Fallback Label' } })
      const result = graphTransformer.prepareTopologyForSaveV2([node], [])

      expect(result.nodes[0].label).toBe('Fallback Label')
    })

    it('converts right→left edges to topology edges with from/to refs', () => {
      const nodes = [makeNode({ id: 'a' }), makeNode({ id: 'b' })]
      const edges = [makeEdge({ id: 'e1', source: 'a', target: 'b', order: 0 })]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.edges).toHaveLength(1)
      expect(result.edges[0]).toEqual({
        id: 'e1',
        from: { id: 'a' },
        to: { id: 'b' },
        order: 0,
      })
    })

    it('converts numeric sourceHandle (router edge) to topology edge with parsed order', () => {
      const nodes = [makeNode({ id: 'r1', type: 'router' }), makeNode({ id: 'n2' })]
      const edges = [
        makeEdge({ id: 'e-router', source: 'r1', target: 'n2', sourceHandle: '3', order: null }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.edges).toHaveLength(1)
      expect(result.edges[0].order).toBe(3)
    })

    it('excludes bottom→top edges from topology edges (they become relationships)', () => {
      const nodes = [makeNode({ id: 'parent' }), makeNode({ id: 'child', type: 'worker' })]
      const edges = [
        makeEdge({ id: 'rel', source: 'parent', target: 'child', sourceHandle: 'bottom', targetHandle: 'top' }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.edges).toHaveLength(0)
      expect(result.relationships).toHaveLength(1)
    })

    it('builds relationships from bottom→top edges with parameter_name', () => {
      const nodes = [
        makeNode({ id: 'agent', data: { name: 'Agent', subcomponents_info: [] } }),
        makeNode({ id: 'tool', type: 'worker', data: { name: 'Tool', component_version_id: 'cv-tool' } }),
      ]
      const edges = [
        makeEdge({
          id: 'rel1',
          source: 'agent',
          target: 'tool',
          sourceHandle: 'bottom',
          targetHandle: 'top',
          parameter_name: 'agent_tools',
        }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.relationships).toHaveLength(1)
      expect(result.relationships[0]).toEqual({
        parent: { id: 'agent' },
        child: { id: 'tool' },
        parameter_name: 'agent_tools',
        order: 0,
      })
    })

    it('assigns order to dynamic tool siblings sorted by y position', () => {
      const nodes = [
        makeNode({ id: 'agent', data: { name: 'Agent', subcomponents_info: [] } }),
        makeNode({ id: 't1', type: 'worker', data: { name: 'T1', component_version_id: 'cv1' }, position: { x: 0, y: 200 } }),
        makeNode({ id: 't2', type: 'worker', data: { name: 'T2', component_version_id: 'cv2' }, position: { x: 0, y: 100 } }),
      ]
      const edges = [
        makeEdge({ id: 'r1', source: 'agent', target: 't1', sourceHandle: 'bottom', targetHandle: 'top', parameter_name: 'agent_tools' }),
        makeEdge({ id: 'r2', source: 'agent', target: 't2', sourceHandle: 'bottom', targetHandle: 'top', parameter_name: 'agent_tools' }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      const t2Rel = result.relationships.find(r => r.child.id === 't2')
      const t1Rel = result.relationships.find(r => r.child.id === 't1')
      expect(t2Rel!.order).toBe(0)
      expect(t1Rel!.order).toBe(1)
    })

    it('assigns null order to static subcomponent relationships', () => {
      const nodes = [
        makeNode({
          id: 'parent',
          data: {
            name: 'Parent',
            subcomponents_info: [{ component_version_id: 'cv-static', is_optional: false, parameter_name: 'sub' }],
          },
        }),
        makeNode({ id: 'child', type: 'worker', data: { name: 'Child', component_version_id: 'cv-static' } }),
      ]
      const edges = [
        makeEdge({ id: 'r-static', source: 'parent', target: 'child', sourceHandle: 'bottom', targetHandle: 'top', parameter_name: 'sub' }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.relationships[0].order).toBeNull()
    })

    it('returns empty arrays for empty inputs', () => {
      const result = graphTransformer.prepareTopologyForSaveV2([], [])

      expect(result).toEqual({ nodes: [], edges: [], relationships: [] })
    })

    it('defaults parameter_name to agent_tools when edge has none', () => {
      const nodes = [
        makeNode({ id: 'p', data: { name: 'P', subcomponents_info: [] } }),
        makeNode({ id: 'c', type: 'worker', data: { name: 'C', component_version_id: 'cv-c' } }),
      ]
      const edges = [
        makeEdge({ id: 'r', source: 'p', target: 'c', sourceHandle: 'bottom', targetHandle: 'top' }),
      ]

      const result = graphTransformer.prepareTopologyForSaveV2(nodes, edges)

      expect(result.relationships[0].parameter_name).toBe('agent_tools')
    })

    it('sets label to null when node data has no name or label', () => {
      const node = makeNode({ id: 'bare', data: {} })
      const result = graphTransformer.prepareTopologyForSaveV2([node], [])

      expect(result.nodes[0].label).toBeNull()
    })
  })

  describe('mergeV2Topology', () => {
    const makeExistingNode = (overrides: Record<string, any> = {}): any => ({
      id: 'n1',
      type: 'component',
      data: {
        ref: 'ref-n1',
        name: 'Original Name',
        component_id: 'cid',
        component_version_id: 'cvid',
        is_agent: false,
        parameters: [{ name: 'model', value: 'gpt-4', kind: 'parameter', type: 'string', nullable: false }],
        tool_description: null,
        is_start_node: false,
      },
      position: { x: 100, y: 200 },
      ...overrides,
    })

    const makeV2Response = (overrides: Record<string, any> = {}): any => ({
      graph_map: {
        nodes: [],
        edges: [],
        relationships: [],
        ...overrides,
      },
    })

    it('preserves existing node data while updating label and is_start_node from v2 response', () => {
      const existing = [makeExistingNode({ id: 'n1' })]
      const v2 = makeV2Response({
        nodes: [{ instance_id: 'n1', label: 'Updated Name', is_start_node: true }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.nodes).toHaveLength(1)
      expect(result.nodes[0].data.name).toBe('Updated Name')
      expect(result.nodes[0].data.is_start_node).toBe(true)
      expect(result.nodes[0].data.parameters).toEqual(existing[0].data.parameters)
      expect(result.nodes[0].data.ref).toBe('ref-n1')
      expect(result.nodes[0].position).toEqual({ x: 100, y: 200 })
    })

    it('keeps original label when v2 response label is null/undefined', () => {
      const existing = [makeExistingNode({ id: 'n1' })]
      const v2 = makeV2Response({
        nodes: [{ instance_id: 'n1' }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.nodes[0].data.name).toBe('Original Name')
    })

    it('reports unknown node IDs that are not in existing nodes', () => {
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'known', label: 'K' },
          { instance_id: 'unknown-1', label: 'U1' },
          { instance_id: 'unknown-2', label: 'U2' },
        ],
      })
      const existing = [makeExistingNode({ id: 'known' })]

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.unknownNodeIds).toEqual(['unknown-1', 'unknown-2'])
      expect(result.nodes).toHaveLength(1)
      expect(result.nodes[0].id).toBe('known')
    })

    it('builds component edges from v2 response edges', () => {
      const existing = [
        makeExistingNode({ id: 'a' }),
        makeExistingNode({ id: 'b' }),
      ]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'a', label: 'A' },
          { instance_id: 'b', label: 'B' },
        ],
        edges: [{ id: 'e1', from: { id: 'a' }, to: { id: 'b' }, order: null }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.edges).toHaveLength(1)
      expect(result.edges[0].source).toBe('a')
      expect(result.edges[0].target).toBe('b')
      expect(result.edges[0].sourceHandle).toBe('right')
      expect(result.edges[0].targetHandle).toBe('left')
    })

    it('builds relationship edges from v2 response relationships', () => {
      const existing = [
        makeExistingNode({ id: 'parent' }),
        makeExistingNode({ id: 'child' }),
      ]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'parent', label: 'Parent' },
          { instance_id: 'child', label: 'Child' },
        ],
        relationships: [
          { parent: { id: 'parent' }, child: { id: 'child' }, parameter_name: 'agent_tools', order: 0 },
        ],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      const relEdge = result.edges.find(e => e.id === 'r-parent-child')
      expect(relEdge).toBeDefined()
      expect(relEdge!.sourceHandle).toBe('bottom')
      expect(relEdge!.targetHandle).toBe('top')
      expect(relEdge!.parameter_name).toBe('agent_tools')
    })

    it('updates child nodes to worker type and sets relationship metadata', () => {
      const existing = [
        makeExistingNode({ id: 'agent', type: 'component' }),
        makeExistingNode({ id: 'tool', type: 'component' }),
      ]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'agent', label: 'Agent' },
          { instance_id: 'tool', label: 'Tool' },
        ],
        relationships: [
          { parent: { id: 'agent' }, child: { id: 'tool' }, parameter_name: 'agent_tools', order: 0 },
        ],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      const toolNode = result.nodes.find(n => n.id === 'tool')!
      expect(toolNode.type).toBe('worker')
      expect(toolNode.data.parent_component_id).toBe('agent')
      expect(toolNode.data.parameter_name).toBe('agent_tools')
      expect(toolNode.data.is_optional).toBe(true)

      const agentNode = result.nodes.find(n => n.id === 'agent')!
      expect(agentNode.type).toBe('component')
      expect(agentNode.data.parent_component_id).toBeNull()
    })

    it('filters out nodes that are no longer in the v2 response (full-replace)', () => {
      const existing = [
        makeExistingNode({ id: 'keep' }),
        makeExistingNode({ id: 'remove' }),
      ]
      const v2 = makeV2Response({
        nodes: [{ instance_id: 'keep', label: 'Keep' }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.nodes).toHaveLength(1)
      expect(result.nodes[0].id).toBe('keep')
    })

    it('replaces all existing edges with edges from v2 response', () => {
      const existing = [makeExistingNode({ id: 'a' }), makeExistingNode({ id: 'b' })]
      const oldEdges: any[] = [
        { id: 'old-e', source: 'a', target: 'b', sourceHandle: 'right', targetHandle: 'left' },
      ]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'a', label: 'A' },
          { instance_id: 'b', label: 'B' },
        ],
        edges: [{ id: 'new-e', from: { id: 'b' }, to: { id: 'a' }, order: null }],
      })

      const result = graphTransformer.mergeV2Topology(existing, oldEdges, v2)

      expect(result.edges).toHaveLength(1)
      expect(result.edges[0].id).toBe('new-e')
      expect(result.edges[0].source).toBe('b')
    })

    it('returns empty arrays when v2 response has empty graph_map', () => {
      const result = graphTransformer.mergeV2Topology([], [], makeV2Response())

      expect(result.nodes).toEqual([])
      expect(result.edges).toEqual([])
      expect(result.unknownNodeIds).toEqual([])
    })

    it('generates edge id from source/target when v2 edge has no id', () => {
      const existing = [makeExistingNode({ id: 'a' }), makeExistingNode({ id: 'b' })]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'a', label: 'A' },
          { instance_id: 'b', label: 'B' },
        ],
        edges: [{ from: { id: 'a' }, to: { id: 'b' }, order: null }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.edges[0].id).toBe('e-a-b')
    })

    it('sets numeric sourceHandle for router edges by order', () => {
      const existing = [
        makeExistingNode({ id: 'r1', type: 'router', data: { name: 'Router', parameters: [{ name: 'routes', ui_component: 'RouteBuilder' }] } }),
        makeExistingNode({ id: 'n2' }),
      ]
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'r1', label: 'Router' },
          { instance_id: 'n2', label: 'N2' },
        ],
        edges: [{ id: 'e-r', from: { id: 'r1' }, to: { id: 'n2' }, order: 2 }],
      })

      const result = graphTransformer.mergeV2Topology(existing, [], v2)

      expect(result.edges[0].sourceHandle).toBe('2')
    })

    it('handles merge with all nodes unknown (full graph reload needed)', () => {
      const v2 = makeV2Response({
        nodes: [
          { instance_id: 'new-1', label: 'New 1' },
          { instance_id: 'new-2', label: 'New 2' },
        ],
      })

      const result = graphTransformer.mergeV2Topology([], [], v2)

      expect(result.nodes).toEqual([])
      expect(result.unknownNodeIds).toEqual(['new-1', 'new-2'])
    })
  })
})
