/**
 * Represents a graph runner version.
 *
 * Version Management Concept:
 * - ENVIRONMENTS (draft, production, staging...): Pointers to specific graph runners
 * - VERSION TAGS (v0.1.1, v0.2.0...): Immutable identifiers for graph runners
 *
 * Rules:
 * - Draft environment ALWAYS points to a graph runner with tag_name=null
 * - Production/other environments point to graph runners with version tags
 */
export interface GraphRunner {
  graph_runner_id: string
  env: string | null
  tag_name: string | null
}
