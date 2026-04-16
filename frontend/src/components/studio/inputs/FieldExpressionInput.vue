<script setup lang="ts">
import { Mention } from '@tiptap/extension-mention'
import { Placeholder } from '@tiptap/extension-placeholder'
import { StarterKit } from '@tiptap/starter-kit'
import type { SuggestionOptions } from '@tiptap/suggestion'
import type { Editor } from '@tiptap/vue-3'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VIcon } from 'vuetify/components/VIcon'
import { VLabel } from 'vuetify/components/VLabel'
import { VTooltip } from 'vuetify/components/VTooltip'
import { type FloatingPopup, createFloatingPopup } from '@/utils/floatingPopup'
import { useFieldExpressions } from '@/composables/useFieldExpressions'
import { useCurrentProject } from '@/composables/queries/useProjectsQuery'
import type {
  ComponentDefinition,
  FieldExpressionAutocompleteSuggestion,
  GraphEdge,
  GraphNodeData,
  MentionItem,
  TipTapDocNode,
  TipTapMentionNode,
  TipTapParagraphNode,
  TipTapTextNode,
} from '@/types/fieldExpressions'
import { scopeoApi } from '@/api'

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  label: '',
  hint: '',
  persistentHint: false,
  isTextarea: false,
  showPreview: true,
  readonly: false,
  enableAutocomplete: false,
  disableMarkdown: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// ============================================================================
// Shared Constants (same as composable)
// ============================================================================

const EXPRESSION_PATTERN = /@\{\{([^}]+)\}\}/g
const REF_PATTERN = /^([a-f0-9-]+)\.([a-z_]\w*)(?:::([a-z_]\w*))?$/i
const REF_NAME_PATTERN = /^([a-z_]\w*)\.([a-z_]\w*)(?:::([a-z_]\w*))?$/i
const EXPRESSION_OPEN = '{{'

// ============================================================================
// Props & Emits
// ============================================================================

interface Props {
  modelValue: string
  label?: string
  alertMessage?: string
  hint?: string
  placeholder?: string
  persistentHint?: boolean
  graphNodes: GraphNodeData[]
  graphEdges?: GraphEdge[]
  currentNodeId?: string
  componentDefinitions?: ComponentDefinition[]
  isTextarea?: boolean
  showPreview?: boolean
  readonly?: boolean
  enableAutocomplete?: boolean // Whether to enable backend autocomplete
  targetInstanceId?: string // The instance being edited
  disableMarkdown?: boolean // Whether to disable markdown (bold/italic) interpretation
}

// ============================================================================
// Mention List Component Helper
// ============================================================================

interface ExtendedMentionItem extends MentionItem {
  kind?: 'module' | 'property' | 'variable'
  description?: string | null
  variableType?: string | null
  hasDefault?: boolean | null
}

interface ExtendedMentionListProps {
  items: ExtendedMentionItem[]
  command: (item: { id: string; label: string }) => void
  clientRect?: (() => DOMRect | null) | null
  editor: Editor | null
  fetchSuggestions: ((query: string) => Promise<ExtendedMentionItem[]>) | null
}

interface MentionListState {
  selectedIndex: number
  items: ExtendedMentionItem[]
  command: ExtendedMentionListProps['command']
  editor: Editor | null
  fetchSuggestions: ((query: string) => Promise<ExtendedMentionItem[]>) | null
  selectionMode: 'idle' | 'selecting-property'
  selectedModule: { label: string; id: string } | null
  isLoading: boolean
  fetchRequestId: number
}

interface MentionListInstance {
  element: HTMLDivElement
  onKeyDown: (params: { event: KeyboardEvent }) => boolean
  updateProps: (newProps: Partial<ExtendedMentionListProps>) => void
  destroy: () => void
  shouldPreventExit: () => boolean
}

function createMentionList(listProps: ExtendedMentionListProps): MentionListInstance {
  const element = document.createElement('div')

  element.className = 'mention-dropdown'

  // Consolidated mutable state
  const state: MentionListState = {
    selectedIndex: 0,
    items: listProps.items,
    command: listProps.command,
    editor: listProps.editor,
    fetchSuggestions: listProps.fetchSuggestions,
    selectionMode: 'idle',
    selectedModule: null,
    isLoading: true,
    fetchRequestId: 0,
  }

  const render = () => {
    if (!state.items || state.items.length === 0) {
      const message = state.isLoading ? 'Searching...' : 'No results'

      element.innerHTML = `<div class="mention-item empty">${message}</div>`

      return
    }

    element.innerHTML = state.items
      .map((item: ExtendedMentionItem, index: number) => {
        // Escape label for safe HTML insertion
        const escapedLabel = item.label.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

        const iconClass =
          item.kind === 'variable' ? 'mdi-at' : item.kind === 'property' ? 'mdi-code-braces' : 'mdi-cube-outline'

        // Build meta section for variables (type badge + optional default badge)
        let metaHtml = ''
        if (item.kind === 'variable') {
          const typeBadge = item.variableType ? `<span class="mention-item__type">${item.variableType}</span>` : ''
          const defaultBadge = item.hasDefault ? '<span class="mention-item__default">default</span>' : ''

          metaHtml = `<span class="mention-item__meta">${typeBadge}${defaultBadge}</span>`
        } else if (item.kind) {
          metaHtml = `<span class="mention-item__kind">${item.kind}</span>`
        }

        return `
          <div class="mention-item ${index === state.selectedIndex ? 'selected' : ''}" data-index="${index}">
            <span class="mdi ${iconClass} mention-item__icon"></span>
            <span class="mention-item__label">${escapedLabel}</span>
            ${metaHtml}
          </div>
        `
      })
      .join('')

    // Add click handlers
    const itemElements = element.querySelectorAll('.mention-item')

    itemElements.forEach((el, index) => {
      el.addEventListener('click', () => {
        selectItem(index)
      })
    })
  }

  const selectItem = async (index: number) => {
    const item = state.items[index]
    if (!item) return

    if (item.kind === 'variable') {
      // Variable suggestions insert directly as {{var_name}} — no second-level
      // Use item.id as label so the chip shows just the variable name (e.g., "user_email")
      state.command({ id: `@{{${item.id}}}`, label: item.id })
      return
    }

    if (item.kind === 'module' && state.editor) {
      state.selectionMode = 'selecting-property'
      // Extract UUID from insertText (e.g., "{{uuid." -> "uuid")
      state.selectedModule = {
        label: item.label,
        id: item.insertText.replace(EXPRESSION_OPEN, '').replace('.', ''),
      }

      // DON'T modify the editor content - keep the @ symbol in place
      // Just fetch and show property suggestions
      if (state.fetchSuggestions) {
        const currentRequestId = ++state.fetchRequestId

        try {
          // Query with the module prefix (will be cleaned by fetchAutocompleteSuggestions)
          const suggestions = await state.fetchSuggestions(item.insertText)

          // Ignore if a newer request was started (race condition protection)
          if (currentRequestId !== state.fetchRequestId) return

          // Filter to only show properties
          const propertySuggestions = suggestions.filter(s => s.kind === 'property')

          state.items = propertySuggestions
          state.selectedIndex = 0
          render()
        } finally {
          // Only reset selection mode if this was the current request
          if (currentRequestId === state.fetchRequestId) {
            state.selectionMode = 'idle'
          }
        }
      }
    } else {
      // For properties: Build full expression and create mention node
      if (state.editor) {
        const { from } = state.editor.state.selection
        const textBefore = state.editor.state.doc.textBetween(0, from)
        const atTextIndex = textBefore.lastIndexOf('@')

        // Convert text index to document position
        const atDocPosition = from - textBefore.length + atTextIndex

        // Build full expression using stored module ID
        // item.insertText is "propertyname}}" for properties
        const propertyName = item.insertText.replace('}}', '')
        const moduleId = state.selectedModule?.id || ''
        const fullId = `@{{${moduleId}.${propertyName}}}`

        // Build full label: "module_label.property_label" (e.g., "AI Agent.full_message")
        const fullLabel = state.selectedModule ? `${state.selectedModule.label}.${item.label}` : item.label

        // Manually delete and insert mention node
        // because command's range tracking is broken after module selection
        state.editor
          .chain()
          .focus()
          .deleteRange({ from: atDocPosition, to: from })
          .insertContent({
            type: 'mention',
            attrs: {
              id: fullId,
              label: fullLabel,
            },
          })
          .run()

        // Reset stored module data after successful selection
        state.selectedModule = null
      } else {
        state.command({ id: `@${item.insertText}`, label: item.label })
      }
    }
  }

  const onKeyDown = ({ event }: { event: KeyboardEvent }) => {
    if (event.key === 'ArrowUp') {
      state.selectedIndex = Math.max(0, state.selectedIndex - 1)
      render()

      return true
    }

    if (event.key === 'ArrowDown') {
      state.selectedIndex = Math.min(state.items.length - 1, state.selectedIndex + 1)
      render()

      return true
    }

    if (event.key === 'Enter') {
      selectItem(state.selectedIndex)

      return true
    }

    return false
  }

  const updateProps = (newProps: Partial<ExtendedMentionListProps>) => {
    if (newProps.items !== undefined) {
      state.items = newProps.items
      state.isLoading = false // Items received, no longer loading
    }
    if (newProps.command) state.command = newProps.command
    if (newProps.editor !== undefined) state.editor = newProps.editor
    if (newProps.fetchSuggestions) state.fetchSuggestions = newProps.fetchSuggestions
    state.selectedIndex = 0
    render()
  }

  const destroy = () => {
    element.remove()
  }

  render()

  return {
    element,
    onKeyDown,
    updateProps,
    destroy,
    shouldPreventExit: () => state.selectionMode === 'selecting-property',
  }
}

// ============================================================================
// Composables
// ============================================================================

const graphNodesRef = computed(() => props.graphNodes || [])
const graphEdgesRef = computed(() => props.graphEdges || [])
const currentNodeIdRef = computed(() => props.currentNodeId)
const componentDefinitionsRef = computed(() => props.componentDefinitions || [])

const { parseExpression, validateExpression } = useFieldExpressions(
  graphNodesRef,
  currentNodeIdRef,
  componentDefinitionsRef,
  graphEdgesRef
)

// Backend autocomplete support
const { currentProject, currentGraphRunner } = useCurrentProject()
const projectId = computed(() => currentProject.value?.project_id)
const graphRunnerId = computed(() => currentGraphRunner.value?.graph_runner_id)

// Debounce configuration for backend autocomplete
const debounceTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const DEBOUNCE_MS = 200

/**
 * Fetch autocomplete suggestions from backend API
 * Returns empty array when backend is unavailable or errors
 */
async function fetchAutocompleteSuggestions(query: string): Promise<ExtendedMentionItem[]> {
  if (!props.enableAutocomplete) return []
  if (!projectId.value || !graphRunnerId.value || !props.targetInstanceId) {
    return []
  }

  try {
    const cleanQuery = query.startsWith(EXPRESSION_OPEN) ? query.slice(2) : query

    const suggestions = await scopeoApi.studio.autocompleteFieldExpression(
      projectId.value,
      graphRunnerId.value,
      cleanQuery,
      props.targetInstanceId
    )

    return suggestions.map((s: FieldExpressionAutocompleteSuggestion) => ({
      id: s.id,
      label: s.label,
      insertText: s.kind === 'module' ? `${EXPRESSION_OPEN}${s.insert_text}` : s.insert_text,
      kind: s.kind,
      description: s.description,
      variableType: s.variable_type,
      hasDefault: s.has_default,
    }))
  } catch (error: unknown) {
    return []
  }
}

// ============================================================================
// Helper Functions (must be defined before editor setup)
// ============================================================================

/**
 * Serialize editor content to backend format
 * Converts mention nodes to @{{id}} format using TipTap's renderText configuration
 * Always ensures @{{}} format is preserved - never strips it
 * Preserves paragraph breaks (newlines)
 */
function serializeMentions(): string {
  if (!editor.value) return ''

  // Manually serialize to ensure mention nodes always use @{{}} format
  const { state } = editor.value
  const { doc } = state
  const parts: string[] = []
  let isFirstParagraph = true

  // Traverse the document in order
  doc.descendants((node, pos, parent) => {
    // Handle paragraph nodes - add newline between paragraphs
    if (node.type.name === 'paragraph') {
      if (!isFirstParagraph) parts.push('\n')

      isFirstParagraph = false

      // Continue to process paragraph children
      return true
    }

    if (node.type.name === 'mention') {
      // Always use the id attribute which contains @{{uuid.port}} format
      // This ensures we never strip the @{{}} wrapper
      const id = node.attrs.id
      if (id && typeof id === 'string') parts.push(id)
    } else if (node.type.name === 'hardBreak') {
      // Handle Shift+Enter hard breaks as newlines
      parts.push('\n')
    } else if (node.isText && node.text) {
      parts.push(node.text)
    }

    return true
  })

  return parts.join('')
}

/**
 * Parse a single line of text with @{{...}} patterns and convert to TipTap paragraph content
 */
function parseLineToContent(lineText: string): Array<TipTapTextNode | TipTapMentionNode> {
  if (!lineText) return []

  // Create fresh regex to avoid stateful issues
  const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')
  const parts: Array<TipTapTextNode | TipTapMentionNode> = []
  let lastIndex = 0

  // Find all @{{...}} patterns
  const matches = [...lineText.matchAll(regex)]

  // If no expressions found, return plain text node
  if (matches.length === 0) return [{ type: 'text', text: lineText }]

  for (const match of matches) {
    const fullMatch = match[0]
    const innerContent = match[1]
    const position = match.index!

    // Add text before this match
    if (position > lastIndex) {
      const textBefore = lineText.substring(lastIndex, position)
      if (textBefore) {
        parts.push({
          type: 'text',
          text: textBefore,
        })
      }
    }

    // Parse the reference to get readable label
    // Try UUID format first: @{{uuid.port}}
    const refMatch = innerContent.match(REF_PATTERN)

    if (refMatch) {
      const [, componentId, portName, keyName] = refMatch

      // Find component to get ref name for label
      const component = graphNodesRef.value?.find(n => n.id === componentId)
      const componentRef = component?.ref || component?.name || componentId.substring(0, 8)
      const label = `${componentRef}.${portName}${keyName ? `::${keyName}` : ''}`

      // Create mention node
      parts.push({
        type: 'mention',
        attrs: {
          id: fullMatch, // Store full @{{uuid.port}} format
          label, // Display name for rendering
        },
      })
    } else {
      // Try component ref format: @{{componentRef.port}}
      const refNameMatch = innerContent.match(REF_NAME_PATTERN)

      if (refNameMatch) {
        const [, componentRef, portName, keyName] = refNameMatch

        // Find component by ref name
        const component = graphNodesRef.value?.find(n => n.ref === componentRef || n.name === componentRef)

        if (component) {
          // Reconstruct with UUID format for id
          const uuidFormat = `@{{${component.id}.${portName}${keyName ? `::${keyName}` : ''}}}`
          const label = `${componentRef}.${portName}${keyName ? `::${keyName}` : ''}`

          // Create mention node
          parts.push({
            type: 'mention',
            attrs: {
              id: uuidFormat, // Store @{{uuid.port}} format
              label, // Display name for rendering
            },
          })
        } else {
          // Component not found - add as text
          parts.push({
            type: 'text',
            text: fullMatch,
          })
        }
      } else {
        // Try variable reference format: @{{variable_name}} (no dot, simple identifier)
        const varMatch = innerContent.match(/^[a-z_]\w*$/i)
        if (varMatch) {
          parts.push({
            type: 'mention',
            attrs: {
              id: fullMatch, // @{{variable_name}}
              label: innerContent, // variable_name
            },
          })
        } else {
          // Invalid format - just add as text
          parts.push({
            type: 'text',
            text: fullMatch,
          })
        }
      }
    }

    lastIndex = position + fullMatch.length
  }

  // Add remaining text
  if (lastIndex < lineText.length) {
    const remainingText = lineText.substring(lastIndex)
    if (remainingText) {
      parts.push({
        type: 'text',
        text: remainingText,
      })
    }
  }

  return parts
}

/**
 * Parse text with @{{...}} patterns and convert to TipTap content with mention nodes
 * Preserves newlines by creating separate paragraph nodes for each line
 */
function parseMentionsToContent(text: string): string | TipTapDocNode {
  // Handle empty/null/undefined
  if (!text || typeof text !== 'string') return ''

  // Split text by newlines to create separate paragraphs
  const lines = text.split('\n')

  // Check if there are any expressions in the entire text
  // Create fresh regex to avoid stateful issues
  const regex = new RegExp(EXPRESSION_PATTERN.source, 'g')
  const hasExpressions = regex.test(text)

  // If no expressions and single line, return plain text
  if (!hasExpressions && lines.length === 1) return text

  // Create paragraph nodes for each line
  const paragraphs: TipTapParagraphNode[] = lines.map(line => {
    const content = parseLineToContent(line)

    return {
      type: 'paragraph',

      // TipTap paragraphs need content array, empty array for empty lines
      content: content.length > 0 ? content : undefined,
    }
  })

  return {
    type: 'doc',
    content: paragraphs,
  }
}

// ============================================================================
// Extended Mention Extension with Label Attribute
// ============================================================================

const CustomMention = Mention.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      label: {
        default: null,
      },
    }
  },
})

// ============================================================================
// TipTap Editor Setup
// ============================================================================

const editor = useEditor({
  content: parseMentionsToContent(props.modelValue),
  editable: !props.readonly,
  extensions: [
    StarterKit.configure({
      heading: false,
      blockquote: false,
      codeBlock: false,
      horizontalRule: false,
      listItem: false,
      bulletList: false,
      orderedList: false,
      bold: props.disableMarkdown ? false : undefined,
      italic: props.disableMarkdown ? false : undefined,
    }),
    Placeholder.configure({
      placeholder: (() => {
        const originalPlaceholder = props.placeholder || props.hint

        if (originalPlaceholder) return `${originalPlaceholder} (Type @ to mention variables...)`

        return 'Type @ to mention variables...'
      })(),
    }),
    CustomMention.configure({
      HTMLAttributes: {
        class: 'mention',
      },
      renderLabel({ node }) {
        // Display the label attribute (human-readable) instead of id (UUID format)
        return node.attrs.label || node.attrs.id
      },
      renderText({ node }) {
        // Serialize mention nodes to @{{uuid.port}} format for backend
        return node.attrs.id
      },
      suggestion: {
        char: '@',
        items: async ({ query }: { query: string }): Promise<ExtendedMentionItem[]> => {
          // Clear pending debounce
          if (debounceTimer.value) {
            clearTimeout(debounceTimer.value)
            debounceTimer.value = null
          }

          // Return immediately for empty query (no debounce needed)
          if (!query) return fetchAutocompleteSuggestions(query)

          // Debounce for non-empty queries
          return new Promise(resolve => {
            debounceTimer.value = setTimeout(async () => {
              resolve(await fetchAutocompleteSuggestions(query))
            }, DEBOUNCE_MS)
          })
        },
        render: () => {
          let component: MentionListInstance | null = null
          let popup: FloatingPopup | null = null

          return {
            onStart: (suggestionProps: {
              items: ExtendedMentionItem[]
              command: ExtendedMentionListProps['command']
              clientRect?: (() => DOMRect | null) | null
            }) => {
              popup?.destroy()
              component?.destroy()

              component = createMentionList({
                items: suggestionProps.items || [],
                command: suggestionProps.command,
                clientRect: suggestionProps.clientRect,
                editor: editor.value ?? null,
                fetchSuggestions: fetchAutocompleteSuggestions,
              })

              if (!suggestionProps.clientRect) return

              popup = createFloatingPopup(component.element, suggestionProps.clientRect as () => DOMRect)
            },
            onUpdate(suggestionProps: {
              items: ExtendedMentionItem[]
              command: ExtendedMentionListProps['command']
              clientRect?: (() => DOMRect | null) | null
            }) {
              component?.updateProps({ ...suggestionProps, items: suggestionProps.items || [] })

              if (!suggestionProps.clientRect) return

              popup?.updatePosition(suggestionProps.clientRect as () => DOMRect)
            },
            onKeyDown(keyProps: { event: KeyboardEvent }) {
              if (keyProps.event.key === 'Escape') {
                popup?.hide()

                return true
              }

              return component?.onKeyDown(keyProps) ?? false
            },
            onExit() {
              if (component?.shouldPreventExit()) return

              popup?.destroy()
              component?.destroy()
            },
          }
        },
      } as Partial<SuggestionOptions>,
    }),
  ],
  editorProps: {
    attributes: {
      class: 'prose prose-sm focus:outline-none',
    },
  },
  onUpdate: () => {
    // Use custom serializer to preserve @{{}} format
    emit('update:modelValue', serializeMentions())
  },
})

// ============================================================================
// Computed
// ============================================================================

const parsedExpression = computed(() => {
  if (!editor.value) return null
  const text = editor.value.getText()
  if (!text) return null

  return parseExpression(text)
})

const hasExpression = computed(() => {
  return (parsedExpression.value?.references.length ?? 0) > 0
})

const isValid = computed(() => {
  return parsedExpression.value?.isValid ?? true
})

const validationResult = computed(() => {
  if (!editor.value) return { isValid: true, errors: [], warnings: [] }
  const text = editor.value.getText()
  if (!text) return { isValid: true, errors: [], warnings: [] }

  return validateExpression(text)
})

const validationErrors = computed(() => validationResult.value.errors)

const errorMessages = computed(() => {
  if (isValid.value) return []

  return validationErrors.value.map(e => e.message)
})

// ============================================================================
// Watchers
// ============================================================================

watch(
  () => props.modelValue,
  newValue => {
    if (!editor.value) return

    const currentSerialized = serializeMentions()

    // Only update if values actually differ
    if (newValue !== currentSerialized) {
      // Don't clear the editor if newValue is empty but editor has content
      // This prevents clearing when component is being re-rendered with stale prop
      if (!newValue && currentSerialized) return

      // Parse @{{...}} patterns to mention nodes before setting content
      const content = parseMentionsToContent(newValue)

      // Pass emitUpdate: false to prevent triggering onUpdate during external sync
      editor.value.commands.setContent(content, { emitUpdate: false })
    }
  },
  { flush: 'post' }
)

watch(
  () => props.readonly,
  newVal => {
    editor.value?.setEditable(!newVal)
  }
)

// ============================================================================
// Lifecycle
// ============================================================================

onBeforeUnmount(() => {
  // Clean up debounce timer to prevent memory leak
  if (debounceTimer.value) {
    clearTimeout(debounceTimer.value)
    debounceTimer.value = null
  }
  editor.value?.destroy()
})

// ============================================================================
// Expose
// ============================================================================

defineExpose({
  focus: () => editor.value?.commands.focus(),
  validate: () => {
    const text = editor.value?.getText() || ''

    return validateExpression(text)
  },
})
</script>

<template>
  <div class="field-expression-input">
    <div v-if="label" class="d-flex align-center mb-2">
      <VLabel class="text-body-2 me-2">
        {{ label }}
      </VLabel>
      <div v-if="alertMessage" class="field-expression-alert d-flex align-center px-2 py-1 text-caption">
        <VIcon icon="tabler-info-circle" size="14" class="me-1" />
        <span>{{ alertMessage }}</span>
      </div>
    </div>

    <div class="editor-wrapper" :class="{ 'is-textarea': isTextarea }">
      <EditorContent :editor="editor" class="editor-content" />

      <!-- Icons overlay -->
      <div class="field-icons">
        <!-- Validation Status -->
        <VTooltip v-if="hasExpression" location="top">
          <template #activator="{ props }">
            <VIcon v-bind="props" :color="isValid ? 'success' : 'error'" size="small" class="me-1">
              {{ isValid ? 'mdi-check-circle' : 'mdi-alert-circle' }}
            </VIcon>
          </template>
          <span v-if="isValid">Valid expression</span>
          <div v-else>
            <div v-for="(error, idx) in validationErrors" :key="idx">
              {{ error.message }}
            </div>
          </div>
        </VTooltip>
      </div>
    </div>

    <!-- Validation/Hint Messages -->
    <div v-if="errorMessages.length > 0" class="v-messages text-error mt-1">
      <div v-for="(error, idx) in errorMessages" :key="idx" class="v-message text-caption">
        {{ error }}
      </div>
    </div>
    <div v-else-if="persistentHint && hint" class="v-messages mt-1">
      <div class="v-message text-caption text-medium-emphasis">
        {{ hint }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.field-expression-input {
  inline-size: 100%;
}

.field-expression-alert {
  border-radius: 4px;
  background-color: rgba(var(--v-theme-info), 0.08);
  color: rgb(var(--v-theme-info));
}

.editor-wrapper {
  position: relative;

  :deep(.editor-content) {
    .ProseMirror {
      border: 1px solid rgba(var(--v-border-color), 0.12);
      border-radius: 4px;
      font-family: inherit;
      font-size: 0.875rem;
      line-height: 1.4375;
      max-block-size: 40px;
      min-block-size: 40px;
      outline: none;
      overflow-y: auto;
      padding-block: 10px;
      padding-inline: 12px 64px;
      transition: border-color 0.2s;

      &:focus {
        border-color: rgb(var(--v-theme-primary));
      }

      &[contenteditable='false'] {
        background-color: rgba(var(--v-theme-on-surface), 0.04);
        color: rgba(var(--v-theme-on-surface), 0.38);
        cursor: default;
      }

      // Placeholder styles - show always when empty, not just when focused
      // Override TipTap's default behavior which only shows placeholder when focused
      p.is-editor-empty:first-child::before {
        display: block !important;
        block-size: 0;
        color: rgba(var(--v-theme-on-surface), 0.38);
        content: attr(data-placeholder);
        float: inline-start;
        pointer-events: none;
      }

      // Ensure placeholder shows even when not focused
      &:not(.ProseMirror-focused) p.is-editor-empty:first-child::before {
        display: block !important;
      }

      // Style mentions as chips
      .mention {
        display: inline-flex;
        align-items: center;
        border-radius: 12px;
        background: rgba(var(--v-theme-primary), 0.12);
        color: rgb(var(--v-theme-primary));
        font-size: 0.875rem;
        font-weight: 500;
        padding-block: 2px;
        padding-inline: 8px;
        text-decoration: none;
      }

      // Remove default paragraph margins
      p {
        margin: 0;
      }
    }
  }

  // Textarea variant (larger size)
  &.is-textarea :deep(.editor-content) {
    .ProseMirror {
      max-block-size: none;
      min-block-size: 120px;
    }
  }

  // Error state
  &:has(.field-icons .v-icon.text-error) :deep(.ProseMirror) {
    border-color: rgb(var(--v-theme-error));
  }
}

.field-icons {
  position: absolute;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 4px;
  inset-block-start: 50%;
  inset-inline-end: 12px;
  transform: translateY(-50%);
}
</style>

<style lang="scss">
// Global styles for mention dropdown
.mention-dropdown {
  padding: 4px;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 4px 6px rgba(0, 0, 0, 10%);
  max-block-size: 300px;
  overflow-y: auto;

  .mention-item {
    display: flex;
    align-items: center;
    border-radius: 4px;
    color: rgb(var(--v-theme-on-surface));
    cursor: pointer;
    padding-block: 8px;
    padding-inline: 12px;
    transition: background-color 0.2s;

    &:hover,
    &.selected {
      background: rgba(var(--v-theme-primary), 0.12);
    }

    &.empty {
      color: rgba(var(--v-theme-on-surface), 0.38);
      cursor: default;

      &:hover {
        background: transparent;
      }
    }

    &__icon {
      margin-inline-end: 8px;
      color: rgb(var(--v-theme-primary));
    }

    &__label {
      flex: 1;
    }

    &__kind {
      margin-inline-start: 8px;
      font-size: 0.75rem;
      text-transform: capitalize;
      color: rgba(var(--v-theme-on-surface), 0.6);
    }

    &__meta {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-inline-start: 8px;
    }

    &__type {
      border-radius: 4px;
      background: rgba(var(--v-theme-primary), 0.12);
      color: rgb(var(--v-theme-primary));
      font-size: 0.7rem;
      font-weight: 500;
      padding-block: 1px;
      padding-inline: 6px;
    }

    &__default {
      border-radius: 4px;
      background: rgba(var(--v-theme-success), 0.12);
      color: rgb(var(--v-theme-success));
      font-size: 0.7rem;
      font-weight: 500;
      padding-block: 1px;
      padding-inline: 6px;
    }
  }
}
</style>
