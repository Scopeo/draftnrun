import dagre from 'dagre'

export interface Node {
  id: string
  type: string
  data: any
  position?: { x: number; y: number }
  hidden?: boolean
}

export interface Edge {
  id: string
  source: string
  target: string
  data: any
  sourceHandle?: string | null
  targetHandle?: string | null
  hidden?: boolean
}

const COMPONENT_WIDTH = 220
const COMPONENT_HEIGHT = 50
const WORKER_WIDTH = 200
const WORKER_HEIGHT = 50

export function calculateLayout(nodes: Node[], edges: Edge[], activeComponentId?: string) {
  const g = new dagre.graphlib.Graph()

  g.setGraph({
    rankdir: 'LR',
    nodesep: 200,
    ranksep: 200,
    edgesep: 100,
  })

  g.setDefaultEdgeLabel(() => ({}))

  const components = nodes.filter(node => node.type === 'component' || node.type === 'router')
  const workers = nodes.filter(node => node.type === 'worker')

  const pipelineEdges = edges.filter(edge => {
    const sourceNode = nodes.find(n => n.id === edge.source)
    const targetNode = nodes.find(n => n.id === edge.target)
    const sourceIsComponent = sourceNode?.type === 'component' || sourceNode?.type === 'router'
    const targetIsComponent = targetNode?.type === 'component' || targetNode?.type === 'router'
    return sourceIsComponent && targetIsComponent
  })

  components.forEach(node => {
    g.setNode(node.id, { width: COMPONENT_WIDTH, height: COMPONENT_HEIGHT })
  })

  pipelineEdges.forEach(edge => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  const getRelatedWorkers = (componentId: string, visited = new Set<string>()): string[] => {
    if (visited.has(componentId)) return []
    visited.add(componentId)

    const relatedWorkers: string[] = []

    const directChildren = edges
      .filter(edge => edge.source === componentId && edge.sourceHandle === 'bottom' && edge.targetHandle === 'top')
      .map(edge => edge.target)

    directChildren.forEach(childId => {
      const childNode = nodes.find(n => n.id === childId)
      if (childNode?.type === 'worker') {
        relatedWorkers.push(childId)
        relatedWorkers.push(...getRelatedWorkers(childId, visited))
      }
    })

    return relatedWorkers
  }

  // Dagre returns center coordinates; VueFlow expects top-left, so subtract half dims
  const positionedNodes = components.map(node => {
    const dagreNode = g.node(node.id)
    return {
      ...node,
      position: {
        x: dagreNode.x - COMPONENT_WIDTH / 2,
        y: dagreNode.y - COMPONENT_HEIGHT / 2,
      },
      hidden: false,
    }
  })

  // Create a separate dagre graph for workers when there's an active component
  let workerPositions = workers.map(worker => ({
    ...worker,
    position: worker.position || { x: 0, y: 0 }, // Ensure position is always defined
    hidden: true,
  }))

  if (activeComponentId) {
    const relatedWorkers = getRelatedWorkers(activeComponentId)
    const activeComponent = positionedNodes.find(n => n.id === activeComponentId)
    const activeWorker = workers.find(w => w.id === activeComponentId)

    const isZoomingIntoWorker = !!activeWorker
    const activeNode = activeComponent || activeWorker

    if (activeNode && (relatedWorkers.length > 0 || isZoomingIntoWorker)) {
      const workerGraph = new dagre.graphlib.Graph()

      workerGraph.setGraph({
        rankdir: 'TB',
        nodesep: 150,
        ranksep: 180,
      })
      workerGraph.setDefaultEdgeLabel(() => ({}))

      let workersToLayout = relatedWorkers
      if (isZoomingIntoWorker) {
        workersToLayout = [activeComponentId, ...relatedWorkers]
      }

      workersToLayout.forEach(workerId => {
        workerGraph.setNode(workerId, { width: WORKER_WIDTH, height: WORKER_HEIGHT })
      })

      edges
        .filter(
          edge =>
            workersToLayout.includes(edge.source) &&
            workersToLayout.includes(edge.target) &&
            edge.sourceHandle === 'bottom' &&
            edge.targetHandle === 'top'
        )
        .forEach(edge => {
          workerGraph.setEdge(edge.source, edge.target)
        })

      dagre.layout(workerGraph)

      // Use the visual center of the parent as the anchor point
      let centerX, baseY

      if (isZoomingIntoWorker) {
        centerX = 400
        baseY = 250
      } else {
        centerX = activeComponent!.position.x + COMPONENT_WIDTH / 2
        baseY = activeComponent!.position.y + COMPONENT_HEIGHT + 200
      }

      let minWorkerX = Number.POSITIVE_INFINITY
      let maxWorkerX = Number.NEGATIVE_INFINITY
      let minWorkerY = Number.POSITIVE_INFINITY

      workersToLayout.forEach(workerId => {
        const workerNode = workerGraph.node(workerId)
        if (workerNode) {
          minWorkerX = Math.min(minWorkerX, workerNode.x)
          maxWorkerX = Math.max(maxWorkerX, workerNode.x)
          minWorkerY = Math.min(minWorkerY, workerNode.y)
        }
      })

      const workerTreeWidth = maxWorkerX - minWorkerX
      const offsetX = centerX - (minWorkerX + workerTreeWidth / 2)
      const offsetY = baseY - minWorkerY

      workerPositions = workers.map(worker => {
        const isInLayout = workersToLayout.includes(worker.id)
        if (!isInLayout) {
          return {
            ...worker,
            position: worker.position || { x: 0, y: 0 },
            hidden: true,
          }
        }

        const workerNode = workerGraph.node(worker.id)

        if (!workerNode) {
          return {
            ...worker,
            position: worker.position || { x: centerX - WORKER_WIDTH / 2, y: baseY },
            hidden: false,
          }
        }

        return {
          ...worker,
          position: {
            x: workerNode.x + offsetX - WORKER_WIDTH / 2,
            y: workerNode.y + offsetY - WORKER_HEIGHT / 2,
          },
          hidden: false,
        }
      })
    }
  }

  // Update edge visibility
  const visibleEdges = edges.map(edge => {
    const isPipelineEdge = pipelineEdges.some(pe => pe.id === edge.id)

    if (!activeComponentId) {
      return { ...edge, hidden: !isPipelineEdge }
    }

    // Show all edges between workers, or edges connecting the active component
    const sourceNode = nodes.find(n => n.id === edge.source)
    const targetNode = nodes.find(n => n.id === edge.target)

    const sourceIsComponent = sourceNode?.type === 'component' || sourceNode?.type === 'router'
    const targetIsComponent = targetNode?.type === 'component' || targetNode?.type === 'router'

    const isComponentWorkerEdge =
      (sourceIsComponent && sourceNode.id === activeComponentId) ||
      (targetIsComponent && targetNode.id === activeComponentId)

    const isWorkerWorkerEdge = sourceNode?.type === 'worker' && targetNode?.type === 'worker'

    return {
      ...edge,
      hidden: !(isComponentWorkerEdge || isWorkerWorkerEdge),
    }
  })

  return {
    nodes: [...positionedNodes, ...workerPositions],
    edges: visibleEdges,
  }
}

// Add this new function to position a single new node
export function positionNewNode(nodes: Node[], newNode: Node) {
  // Find visible nodes to avoid overlap
  const visibleNodes = nodes.filter(node => !node.hidden && node.position)

  if (visibleNodes.length === 0) {
    // If no visible nodes, place in the center
    return {
      ...newNode,
      position: { x: 300, y: 300 },
    }
  }

  // Find the rightmost node to place new node after it
  let rightmostX = 0
  let avgY = 0

  visibleNodes.forEach(node => {
    if (node.position && node.position.x > rightmostX) {
      rightmostX = node.position.x
    }
    if (node.position) {
      avgY += node.position.y
    }
  })

  // Get average Y position
  avgY = Math.round(avgY / visibleNodes.length)

  // Position the new node to the right of existing nodes with some spacing
  return {
    ...newNode,
    position: {
      x: rightmostX + 300, // Place it to the right with spacing
      y: avgY,
    },
  }
}
