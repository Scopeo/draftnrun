import type { Edge } from '../types/edge.types'
import type { Node } from '../types/node.types'

export function getRelatedWorkers(
  componentId: string,
  nodes: Node[],
  edges: Edge[],
  visited = new Set<string>()
): string[] {
  if (visited.has(componentId)) return []
  visited.add(componentId)

  const directWorkers = edges
    .filter(edge => edge.source === componentId)
    .map(edge => {
      const targetNode = nodes.find(n => n.id === edge.target)
      return targetNode?.type === 'worker' ? edge.target : null
    })
    .filter(Boolean) as string[]

  const childWorkers = directWorkers.flatMap(workerId => getRelatedWorkers(workerId, nodes, edges, visited))

  return [...directWorkers, ...childWorkers]
}
