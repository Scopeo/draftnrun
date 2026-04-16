import { type Ref, computed } from 'vue'
import type { Condition } from '@/types/conditions'
import type {
  ComponentDefinition,
  ComponentSuggestion,
  ExpressionReference,
  ExpressionSuggestion,
  GraphEdge,
  GraphNodeData,
  HighlightedPart,
  JsonBuildNode,
  ParsedExpression,
  PortDefinition,
  PortSuggestion,
  RefNode,
  ValidationError,
  ValidationResult,
  ValidationWarning,
  VarNode,
} from '@/types/fieldExpressions'

/**
 * Composable for field expression autocomplete, validation, and parsing
 *
 * @param graphNodes - All nodes in the current graph
 * @param currentNodeId - The ID of the node being edited (to find upstream nodes)
 * @param componentDefinitions - Component definitions with port information
 * @param graphEdges - Graph edges to determine upstream components
 */
export function useFieldExpressions(
  graphNodes: Ref<GraphNodeData[]>,
  currentNodeId: Ref<string | undefined>,
  componentDefinitions?: Ref<ComponentDefinition[]>,
  graphEdges?: Ref<GraphEdge[]>
) {
  // ============================================================================
  // Constants (non-global regex to avoid stateful issues)
  // ============================================================================

  const EXPRESSION_PATTERN = /@\{\{([^}]+)\}\}/g
  const REF_PATTERN = /^([a-f0-9-]+)\.([a-zA-Z_]\w*)(?:::([a-zA-Z_]\w*))?$/

  // ============================================================================
  // Helper: Get Upstream Component IDs
  // ============================================================================

  function getUpstreamComponentIds(currentId: string, edges: GraphEdge[]): Set<string> {
    const upstreamIds = new Set<string>()
    const visited = new Set<string>()

    function traverse(nodeId: string) {
      if (visited.has(nodeId)) return
      visited.add(nodeId)

      // Find all edges pointing TO this node (only horizontal left/right connections, exclude vertical children)
      const incomingEdges = edges.filter(edge => {
        const isTargetNode = edge.target === nodeId || edge.destination === nodeId

        // Exclude vertical connections (bottom/top handles)
        const isVertical = edge.sourceHandle === 'bottom' || edge.targetHandle === 'top'

        return isTargetNode && !isVertical
      })

      incomingEdges.forEach(edge => {
        const sourceId = edge.source || edge.origin
        if (sourceId) {
          upstreamIds.add(sourceId)
          traverse(sourceId) // Recursively find upstream
        }
      })
    }

    traverse(currentId)

    return upstreamIds
  }

  // ============================================================================
  // Get Available Components (Upstream nodes only)
  // ============================================================================

  const availableComponents = computed((): ComponentSuggestion[] => {
    if (!graphNodes.value) return []

    // Get upstream component IDs if currentNodeId and edges are available
    let upstreamIds: Set<string> | null = null
    if (currentNodeId.value && graphEdges?.value)
      upstreamIds = getUpstreamComponentIds(currentNodeId.value, graphEdges.value)

    let componentsWithOutputs = graphNodes.value.filter(node => {
      // Get outputs from node data OR component definition
      let outputs: PortDefinition[] = node.outputs || []

      // If node outputs are empty, try to get from component definition
      if ((!outputs || outputs.length === 0) && componentDefinitions?.value) {
        const componentDef = componentDefinitions.value.find(
          def => def.component_version_id === node.component_version_id || def.id === node.component_version_id
        )

        if (componentDef) {
          outputs = componentDef.port_definitions?.filter(p => p.port_type === 'OUTPUT') || componentDef.outputs || []
        }
      }

      return outputs && outputs.length > 0
    })

    // Filter to only upstream components (exclude self and downstream)
    if (upstreamIds) {
      // If we have upstream info, use it to filter (upstreamIds already excludes self)
      componentsWithOutputs = componentsWithOutputs.filter(node => upstreamIds!.has(node.id))
    }

    // Always exclude self, even if we have upstream info (safety check)
    if (currentNodeId.value)
      componentsWithOutputs = componentsWithOutputs.filter(node => node.id !== currentNodeId.value)

    return componentsWithOutputs.map(node => ({
      id: node.id,
      name: node.name || node.ref || 'Unnamed',
      ref: node.ref || node.name || node.id.substring(0, 8),
      type: (node.type as 'component' | 'worker') || 'component',
    }))
  })

  // ============================================================================
  // Get Output Ports for a Component
  // ============================================================================

  function getComponentOutputPorts(componentId: string): PortSuggestion[] {
    // Never return outputs for the current component (self)
    if (currentNodeId.value && componentId === currentNodeId.value) return []

    const node = graphNodes.value?.find(n => n.id === componentId)
    if (!node) return []

    // Get outputs from node data OR component definition
    let outputs: PortDefinition[] = node.outputs || []

    // If node outputs are empty, try to get from component definition
    if ((!outputs || outputs.length === 0) && componentDefinitions?.value) {
      const componentDef = componentDefinitions.value.find(
        def => def.component_version_id === node.component_version_id || def.id === node.component_version_id
      )

      if (componentDef) {
        outputs = componentDef.port_definitions?.filter(p => p.port_type === 'OUTPUT') || componentDef.outputs || []
      }
    }

    if (!outputs || outputs.length === 0) return []

    return outputs.map(output => {
      const portType = output.type || 'any'
      const isDict = isDictType(portType)

      return {
        name: output.name,
        type: portType,
        description: output.description,
        isDict,
        availableKeys: isDict ? extractKeysFromSchema(output.schema) : undefined,
      }
    })
  }

  // ============================================================================
  // Get Dict Keys from Port Schema
  // ============================================================================

  function getOutputKeys(componentId: string, portName: string): string[] {
    const ports = getComponentOutputPorts(componentId)
    const port = ports.find(p => p.name === portName)

    return port?.availableKeys || []
  }

  // ============================================================================
  // Type Checking Helpers
  // ============================================================================

  function isDictType(type: string): boolean {
    if (!type) return false
    const normalized = type.toLowerCase().trim()

    return (
      normalized === 'dict' ||
      normalized === 'object' ||
      normalized.startsWith('dict<') ||
      normalized.startsWith('object<') ||
      normalized.includes('{')
    )
  }

  function extractKeysFromSchema(schema: Record<string, unknown> | undefined): string[] | undefined {
    if (!schema) return undefined

    // If schema is a JSON Schema object with properties
    if (schema.type === 'object' && schema.properties && typeof schema.properties === 'object')
      return Object.keys(schema.properties)

    // If schema has a custom keys field
    if (schema.keys && Array.isArray(schema.keys)) return schema.keys

    return undefined
  }

  // ============================================================================
  // Generate Autocomplete Suggestions
  // ============================================================================

  function getAutocompleteSuggestions(query: string, trigger: '@' | '@{{' | '::'): ExpressionSuggestion[] {
    if (trigger === '@' || trigger === '@{{') return getComponentPortSuggestions(query)
    else if (trigger === '::') return getKeySuggestions(query)

    return []
  }

  function getComponentPortSuggestions(query: string): ExpressionSuggestion[] {
    const suggestions: ExpressionSuggestion[] = []
    const lowerQuery = query.toLowerCase()

    for (const component of availableComponents.value) {
      const ports = getComponentOutputPorts(component.id)

      for (const port of ports) {
        const matchText = `${component.ref}.${port.name}`.toLowerCase()
        if (!lowerQuery || matchText.includes(lowerQuery)) {
          suggestions.push({
            component,
            port,
            displayText: `${component.ref}.${port.name}${port.description ? ` - ${port.description}` : ''}`,
            insertText: `@{{${component.id}.${port.name}}}`,
          })
        }
      }
    }

    return suggestions
  }

  function getKeySuggestions(query: string): ExpressionSuggestion[] {
    // Parse the current expression to find component.port
    const match = query.match(/([a-f0-9-]+)\.([a-zA-Z_]\w*)::(.*)/)
    if (!match) return []

    const [, componentId, portName, keyQuery] = match
    const keys = getOutputKeys(componentId, portName)

    const component = availableComponents.value.find(c => c.id === componentId)
    const ports = getComponentOutputPorts(componentId)
    const port = ports.find(p => p.name === portName)

    if (!component || !port || !keys) return []

    const lowerKeyQuery = keyQuery.toLowerCase()

    return keys
      .filter(key => !lowerKeyQuery || key.toLowerCase().includes(lowerKeyQuery))
      .map(key => ({
        component,
        port,
        key,
        displayText: `${component.ref}.${port.name}::${key}`,
        insertText: `@{{${component.id}.${port.name}::${key}}}`,
      }))
  }

  // ============================================================================
  // Parse and Validate Expression
  // ============================================================================

  function parseExpression(text: string): ParsedExpression {
    const parts: HighlightedPart[] = []
    const references: ExpressionReference[] = []
    const errors: ValidationError[] = []
    let lastIndex = 0

    // Create fresh regex to avoid stateful issues with global flag
    const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')
    const matches = text.matchAll(regex)

    for (const match of matches) {
      const fullMatch = match[0]
      const innerContent = match[1]
      const position = match.index!

      // Add text before this match
      if (position > lastIndex) {
        parts.push({
          type: 'text',
          content: text.substring(lastIndex, position),
        })
      }

      // Parse the reference
      const refMatch = innerContent.match(REF_PATTERN)

      if (refMatch) {
        const [, componentId, portName, keyName] = refMatch

        // Validate component exists
        const component = availableComponents.value.find(c => c.id === componentId)
        if (!component) {
          parts.push({
            type: 'invalid',
            content: fullMatch,
            tooltip: `Component not found: ${componentId}`,
          })
          errors.push({
            message: `Referenced component not found: ${componentId}`,
            position,
            componentId,
          })
        } else {
          // Validate port exists
          const ports = getComponentOutputPorts(componentId)
          const port = ports.find(p => p.name === portName)

          if (!port) {
            parts.push({
              type: 'invalid',
              content: fullMatch,
              componentId,
              tooltip: `Port '${portName}' not found on ${component.ref}`,
            })
            errors.push({
              message: `Output port '${portName}' not found for component ${component.ref}`,
              position,
              componentId,
              portName,
            })
          } else {
            // Validate key extraction if present
            if (keyName) {
              if (!port.isDict) {
                parts.push({
                  type: 'invalid',
                  content: fullMatch,
                  componentId,
                  portName,
                  keyName,
                  tooltip: `Cannot extract key from non-dict port '${portName}'`,
                })
                errors.push({
                  message: `Key extraction '::${keyName}' cannot be used on ${component.ref}.${portName}: port does not output a dict`,
                  position,
                  componentId,
                  portName,
                })
              } else if (port.availableKeys && !port.availableKeys.includes(keyName)) {
                parts.push({
                  type: 'invalid',
                  content: fullMatch,
                  componentId,
                  portName,
                  keyName,
                  tooltip: `Key '${keyName}' not found in schema. Available: ${port.availableKeys.join(', ')}`,
                })
                errors.push({
                  message: `Key '${keyName}' not found in schema for ${component.ref}.${portName}`,
                  position,
                  componentId,
                  portName,
                })
              } else {
                // Valid reference with key
                parts.push({
                  type: 'expression',
                  content: fullMatch,
                  componentId,
                  portName,
                  keyName,
                  tooltip: `${component.ref}.${portName}::${keyName}`,
                })
              }
            } else {
              // Valid reference without key
              parts.push({
                type: 'expression',
                content: fullMatch,
                componentId,
                portName,
                tooltip: `${component.ref}.${portName}`,
              })
            }

            // Add to references
            references.push({
              componentId,
              componentName: component.ref,
              portName,
              keyName,
              position,
            })
          }
        }
      } else {
        // Invalid reference syntax
        parts.push({
          type: 'invalid',
          content: fullMatch,
          tooltip:
            'Invalid expression syntax. Expected: @{{component_id.port_name}} or @{{component_id.port_name::key}}',
        })
        errors.push({
          message: `Invalid expression syntax: ${fullMatch}`,
          position,
        })
      }

      lastIndex = position + fullMatch.length
    }

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push({
        type: 'text',
        content: text.substring(lastIndex),
      })
    }

    return {
      raw: text,
      parts,
      isValid: errors.length === 0,
      references,
    }
  }

  function validateExpression(text: string): ValidationResult {
    const parsed = parseExpression(text)
    const warnings: ValidationWarning[] = []

    // Add warnings for dict ports used without key extraction
    for (const ref of parsed.references) {
      if (!ref.keyName) {
        const ports = getComponentOutputPorts(ref.componentId)
        const port = ports.find(p => p.name === ref.portName)

        if (port?.isDict && port.availableKeys && port.availableKeys.length > 0) {
          warnings.push({
            message: `Consider using key extraction for dict output: @{{${ref.componentId}.${ref.portName}::key}}`,
            suggestion: `Available keys: ${port.availableKeys.join(', ')}`,
          })
        }
      }
    }

    return {
      isValid: parsed.isValid,
      errors: parsed.parts
        .filter(p => p.type === 'invalid')
        .map(p => ({
          message: p.tooltip || 'Invalid expression',
        })),
      warnings,
    }
  }

  // ============================================================================
  // Helper: Check if text contains expressions
  // ============================================================================

  function hasExpressions(text: string): boolean {
    // Create fresh regex to avoid stateful issues with global flag
    const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')

    return regex.test(text)
  }

  // ============================================================================
  // Helper: Extract plain references from expression
  // ============================================================================

  function extractReferences(text: string): ExpressionReference[] {
    return parseExpression(text).references
  }

  // ============================================================================
  // Helper: Convert UUID expression to readable format
  // ============================================================================

  function expressionToReadable(text: string): string {
    if (!text) return text

    // Create fresh regex to avoid stateful issues with global flag
    const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')

    return text.replace(regex, (match, innerContent) => {
      const refMatch = innerContent.match(REF_PATTERN)
      if (!refMatch) return match

      const [, componentId, portName, keyName] = refMatch
      const component = availableComponents.value.find(c => c.id === componentId)

      if (!component) return match

      const displayName = component.ref || component.name
      const keyPart = keyName ? `::${keyName}` : ''

      return `@${displayName}: ${portName}${keyPart}`
    })
  }

  // ============================================================================
  // Helper: Convert readable format to UUID expression
  // ============================================================================

  function readableToExpression(text: string): string {
    if (!text) return text

    // Match pattern like @ComponentName: port or @ComponentName: port::key
    const readablePattern = /@([^:]+):\s*([^\s:]+)(?:::(\S+))?/g

    return text.replace(readablePattern, (match, componentName, portName, keyName) => {
      const trimmedName = componentName.trim()
      const trimmedPort = portName.trim()
      const trimmedKey = keyName?.trim()

      // Find component by ref or name
      const component = availableComponents.value.find(c => c.ref === trimmedName || c.name === trimmedName)

      if (!component) return match

      const keyPart = trimmedKey ? `::${trimmedKey}` : ''

      return `@{{${component.id}.${trimmedPort}${keyPart}}}`
    })
  }

  // ============================================================================
  // Return API
  // ============================================================================

  return {
    // Data
    availableComponents,

    // Functions
    getComponentOutputPorts,
    getOutputKeys,
    getAutocompleteSuggestions,
    parseExpression,
    validateExpression,
    hasExpressions,
    extractReferences,
    expressionToReadable,
    readableToExpression,
  }
}

// ============================================================================
// Standalone Utilities (outside composable)
// ============================================================================

function refToExpression(refNode: VarNode | RefNode): string {
  if (refNode.type === 'var') {
    return `@{{${refNode.name}}}`
  }
  const keyPart = refNode.key ? `::${refNode.key}` : ''
  return `@{{${refNode.instance}.${refNode.port}${keyPart}}}`
}

/**
 * Transform JsonBuildNode format back to Condition[] array
 * Replaces placeholders with actual field expressions
 *
 * @param jsonBuildNode - JsonBuildNode structure from backend
 * @returns Array of conditions for ConditionBuilder
 */
export function transformJsonBuildToConditions(jsonBuildNode: JsonBuildNode): Condition[] {
  if (!jsonBuildNode || !jsonBuildNode.template || !Array.isArray(jsonBuildNode.template)) {
    return []
  }

  const refs = jsonBuildNode.refs || {}

  /**
   * Replace placeholders with actual field expressions
   */
  function restoreFieldValue(value: string): string {
    if (!value || typeof value !== 'string') return value

    // Replace all placeholders with their corresponding field expressions
    let restoredValue = value
    for (const [placeholder, refNode] of Object.entries(refs)) {
      if (restoredValue.includes(placeholder)) {
        restoredValue = restoredValue.replaceAll(placeholder, refToExpression(refNode))
      }
    }

    return restoredValue
  }

  // Process all conditions and restore field expressions
  return jsonBuildNode.template.map(condition => {
    // Start with ALL fields from the condition (preserves routeOrder and other custom fields)
    const result: any = {
      ...condition, // Preserve ALL original fields
    }

    // Override with restored field expression values
    result.value_a = restoreFieldValue(condition.value_a) || ''
    result.operator = condition.operator || ''
    result.value_b = condition.value_b ? restoreFieldValue(condition.value_b) : ''

    // Add logical_operator if present (for Condition type)
    if ('logical_operator' in condition && !result.logical_operator) {
      result.logical_operator = condition.logical_operator || 'AND'
    }

    return result
  })
}

/**
 * Transform Condition[] array to JsonBuildNode format
 * Extracts field expressions from value_a and value_b into separate refs
 *
 * @param conditions - Array of conditions from ConditionBuilder
 * @returns JsonBuildNode structure with template and refs
 */
export function transformConditionsToJsonBuild(conditions: Condition[]): JsonBuildNode {
  const EXPRESSION_PATTERN = /@\{\{([^}]+)\}\}/g
  const REF_PATTERN = /^([a-f0-9-]+)\.([a-zA-Z_]\w*)(?:::([a-zA-Z_]\w*))?$/

  const refs: Record<string, RefNode> = {}
  const refCounter: Record<string, number> = {}

  /**
   * Generate a unique placeholder name for a reference
   */
  function generatePlaceholder(componentId: string, portName: string, keyName?: string): string {
    // Create a base name from the port name (uppercase, with underscores)
    const baseName = portName.toUpperCase().replace(/[^A-Z0-9_]/g, '_')
    const keyPart = keyName ? `_${keyName.toUpperCase().replace(/[^A-Z0-9_]/g, '_')}` : ''
    const fullBase = `__REF_${baseName}${keyPart}`

    // If this is the first occurrence, use the base name
    if (!refCounter[fullBase]) {
      refCounter[fullBase] = 1
      return `${fullBase}__`
    }

    // Otherwise, append a counter
    refCounter[fullBase]++
    return `${fullBase}_${refCounter[fullBase]}__`
  }

  /**
   * Extract field expressions from a string and replace with placeholders
   */
  function processFieldValue(value: string): string {
    if (!value || typeof value !== 'string') return value

    const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')
    return value.replace(regex, (match, innerContent) => {
      const refMatch = innerContent.match(REF_PATTERN)

      if (refMatch) {
        const [, componentId, portName, keyName] = refMatch

        // Generate placeholder
        const placeholder = generatePlaceholder(componentId, portName, keyName)

        // Create RefNode
        const refNode: RefNode = {
          type: 'ref',
          instance: componentId,
          port: portName,
        }

        // Add key if present
        if (keyName) {
          refNode.key = keyName
        }

        // Store in refs object
        refs[placeholder] = refNode

        return placeholder
      }

      // If not a valid reference, return original match
      return match
    })
  }

  // Process all conditions and replace field expressions with placeholders
  const template = conditions.map(condition => {
    const result: any = {
      value_a: processFieldValue(condition.value_a),
      operator: condition.operator,
      value_b: condition.value_b ? processFieldValue(condition.value_b) : condition.value_b,
    }

    // Add logical_operator if present (for Condition type)
    if ('logical_operator' in condition && condition.logical_operator) {
      result.logical_operator = condition.logical_operator
    }

    return result
  })

  return {
    type: 'json_build',
    template,
    refs,
  }
}

/**
 * Generic: Transform any JSON object into a JsonBuildNode by extracting
 * field expressions (@{{...}}) from all string values, recursively.
 * Returns the plain object unchanged if no expressions are found.
 */
export function transformJsonObjectToJsonBuild(obj: Record<string, any>): Record<string, any> | JsonBuildNode {
  const EXPRESSION_PATTERN = /@\{\{([^}]+)\}\}/g
  const REF_PATTERN = /^([a-f0-9-]+)\.([a-zA-Z_]\w*)(?:::([a-zA-Z_]\w*))?$/
  const VAR_PATTERN = /^[a-z_]\w*$/i

  const refs: Record<string, RefNode | VarNode> = {}
  let refIndex = 0

  function processString(value: string): string {
    const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')
    return value.replace(regex, (match, innerContent) => {
      const refMatch = innerContent.match(REF_PATTERN)
      if (refMatch) {
        const [, componentId, portName, keyName] = refMatch
        const placeholder = `__REF_${refIndex++}__`
        const refNode: RefNode = { type: 'ref', instance: componentId, port: portName }
        if (keyName) refNode.key = keyName
        refs[placeholder] = refNode
        return placeholder
      }

      if (VAR_PATTERN.test(innerContent)) {
        const placeholder = `__REF_${refIndex++}__`
        const varNode: VarNode = { type: 'var', name: innerContent }

        refs[placeholder] = varNode
        return placeholder
      }

      return match
    })
  }

  function processValue(value: any): any {
    if (typeof value === 'string') return processString(value)
    if (Array.isArray(value)) return value.map(processValue)
    if (value !== null && typeof value === 'object') {
      const result: Record<string, any> = {}
      for (const [k, v] of Object.entries(value)) {
        result[processString(k)] = processValue(v)
      }
      return result
    }
    return value
  }

  const template = processValue(obj)

  if (Object.keys(refs).length === 0) return obj

  return { type: 'json_build' as const, template, refs }
}

/**
 * Parse a raw JSON string that may contain @{{...}} field expressions
 * (both bare values and inside quoted strings) into a JsonBuildNode.
 * Handles context-aware replacement: bare expressions get quoted as standalone
 * string placeholders, while expressions inside JSON strings stay inline.
 * Returns the parsed plain object if no expressions are found, or null if parsing fails.
 */
export function parseJsonStringToJsonBuild(rawString: string): JsonBuildNode | Record<string, any> | null {
  const trimmed = rawString.trim()
  if (!trimmed) return null

  const REF_PATTERN = /^([a-f0-9-]+)\.([a-zA-Z_]\w*)(?:::([a-zA-Z_]\w*))?$/
  const VAR_PATTERN = /^[a-z_]\w*$/i

  const refs: Record<string, RefNode | VarNode> = {}
  let refIndex = 0

  function buildRef(innerContent: string): { placeholder: string; matched: boolean } {
    const refMatch = innerContent.match(REF_PATTERN)
    if (refMatch) {
      const [, componentId, portName, keyName] = refMatch
      const placeholder = `__REF_${refIndex++}__`
      const refNode: RefNode = { type: 'ref', instance: componentId, port: portName }
      if (keyName) refNode.key = keyName
      refs[placeholder] = refNode
      return { placeholder, matched: true }
    }

    if (VAR_PATTERN.test(innerContent)) {
      const placeholder = `__REF_${refIndex++}__`
      const varNode: VarNode = { type: 'var', name: innerContent }

      refs[placeholder] = varNode
      return { placeholder, matched: true }
    }

    return { placeholder: '', matched: false }
  }

  // Context-aware scan: track whether we're inside a JSON string to decide
  // how to replace expressions (bare values need quoting, inline ones don't).
  let result = ''
  let inString = false
  let i = 0

  while (i < trimmed.length) {
    if (trimmed[i] === '@' && trimmed.substring(i, i + 3) === '@{{') {
      const closeIdx = trimmed.indexOf('}}', i + 3)
      if (closeIdx !== -1) {
        const innerContent = trimmed.substring(i + 3, closeIdx)
        const { placeholder, matched } = buildRef(innerContent)
        if (matched) {
          if (inString) {
            result += placeholder
          } else {
            result += `"${placeholder}"`
          }
          i = closeIdx + 2
          continue
        }
      }
    }

    const char = trimmed[i]
    if (char === '"') {
      let backslashCount = 0
      let j = i - 1
      while (j >= 0 && trimmed[j] === '\\') {
        backslashCount++
        j--
      }
      if (backslashCount % 2 === 0) {
        inString = !inString
      }
    }
    result += char
    i++
  }

  try {
    const template = JSON.parse(result)
    if (Object.keys(refs).length === 0) return template
    return { type: 'json_build' as const, template, refs }
  } catch (error: unknown) {
    return null
  }
}

/**
 * Generic: Transform a JsonBuildNode back into a regular JSON object
 * by restoring placeholders to @{{...}} field expressions, recursively.
 */
export function transformJsonBuildToJsonObject(jsonBuildNode: JsonBuildNode): Record<string, any> {
  const refs = jsonBuildNode.refs || {}

  function restoreString(value: string): string {
    let restored = value
    for (const [placeholder, refNode] of Object.entries(refs)) {
      if (restored.includes(placeholder)) {
        restored = restored.replaceAll(placeholder, refToExpression(refNode))
      }
    }
    return restored
  }

  function restoreValue(value: any): any {
    if (typeof value === 'string') return restoreString(value)
    if (Array.isArray(value)) return value.map(restoreValue)
    if (value !== null && typeof value === 'object') {
      const result: Record<string, any> = {}
      for (const [k, v] of Object.entries(value)) {
        result[restoreString(k)] = restoreValue(v)
      }
      return result
    }
    return value
  }

  return restoreValue(jsonBuildNode.template)
}
