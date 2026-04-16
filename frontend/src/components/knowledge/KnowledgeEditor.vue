<script setup lang="ts">
import type { Editor } from '@tiptap/core'
import { Placeholder } from '@tiptap/extension-placeholder'
import { Table } from '@tiptap/extension-table'
import { TableCell } from '@tiptap/extension-table-cell'
import { TableHeader } from '@tiptap/extension-table-header'
import { TableRow } from '@tiptap/extension-table-row'
import { Markdown } from '@tiptap/markdown'
import { StarterKit } from '@tiptap/starter-kit'
import type { SuggestionProps } from '@tiptap/suggestion'
import { EditorContent, VueRenderer, useEditor } from '@tiptap/vue-3'
import { onBeforeUnmount, ref, watch } from 'vue'

import {
  type MenuItem,
  type SlashCommandItem,
  SlashCommands,
  createMenuItems,
  createSlashCommands,
} from './extensions/SlashCommands'
import SlashCommandMenu from './SlashCommandMenu.vue'
import TableBubbleMenu from './TableBubbleMenu.vue'
import { type FloatingPopup, createFloatingPopup } from '@/utils/floatingPopup'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'backspace-at-start'): void
  (e: 'arrow-up-at-start'): void
  (e: 'arrow-down-at-end'): void
  (e: 'split-at-cursor', payload: { before: string; after: string }): void
  (e: 'add-chunk-below'): void
  (e: 'delete-chunk'): void
}>()

// Create menu items with callbacks (shared between slash menu and context menu)
const menuCallbacks = { onAddChunk: () => emit('add-chunk-below') }
const menuItems = createMenuItems(menuCallbacks)
const slashCommands = createSlashCommands(menuCallbacks)

// Context menu state
const showContextMenu = ref(false)
const contextMenuPosition = ref({ x: 0, y: 0 })
const savedCursorPosition = ref(0)

// Slash command menu state
const isSlashMenuOpen = ref(false)

function handleContextMenuAction(item: MenuItem) {
  showContextMenu.value = false
  if (editor.value) {
    item.action(editor.value)
  }
}

function handleSplitFromContextMenu() {
  showContextMenu.value = false

  if (!editor.value) return

  const view = editor.value.view
  const from = savedCursorPosition.value
  const textBefore = view.state.doc.textBetween(0, from, '\n')
  const textAfter = view.state.doc.textBetween(from, view.state.doc.content.size, '\n')

  emit('split-at-cursor', {
    before: textBefore.trim(),
    after: textAfter.trim(),
  })
}

const editor = useEditor({
  content: props.modelValue,
  contentType: 'markdown',
  editable: props.editable ?? false,
  extensions: [
    StarterKit,
    Markdown,
    Table.configure({
      resizable: false,
    }),
    TableRow,
    TableHeader,
    TableCell,
    Placeholder.configure({
      placeholder: ({ node, pos }) => {
        if (props.placeholder) return props.placeholder
        if (node.type.name !== 'paragraph') return ''
        // Show delete hint only on first line of chunk
        if (pos === 0) return '/ commands · ⌘Enter new chunk · ⌘⌫ delete'
        return '/ commands · ⌘Enter new chunk'
      },
      showOnlyWhenEditable: true,
      showOnlyCurrent: true,
    }),
    SlashCommands.configure({
      suggestion: {
        decorationClass: 'slash-command-decoration',
        items: ({ query }: { query: string }) => {
          if (!query) return slashCommands

          const lowerQuery = query.toLowerCase()

          return slashCommands.filter(item => item.title.toLowerCase().includes(lowerQuery))
        },
        render: () => {
          let component: VueRenderer | null = null
          let popup: FloatingPopup | null = null

          return {
            onStart: (suggestionProps: SuggestionProps<SlashCommandItem>) => {
              isSlashMenuOpen.value = true

              component = new VueRenderer(SlashCommandMenu, {
                props: {
                  items: suggestionProps.items,
                  command: suggestionProps.command,
                },
                editor: suggestionProps.editor as Editor,
              })

              if (!suggestionProps.clientRect) return

              popup = createFloatingPopup(component.element as HTMLElement, suggestionProps.clientRect as () => DOMRect)
            },

            onUpdate(suggestionProps: SuggestionProps<SlashCommandItem>) {
              component?.updateProps({
                items: suggestionProps.items,
                command: suggestionProps.command,
              })

              if (!suggestionProps.clientRect) return

              popup?.updatePosition(suggestionProps.clientRect as () => DOMRect)
            },

            onKeyDown(suggestionProps: { event: KeyboardEvent }) {
              if (suggestionProps.event.key === 'Escape') {
                popup?.hide()

                return true
              }

              return component?.ref?.onKeyDown(suggestionProps.event) ?? false
            },

            onExit() {
              isSlashMenuOpen.value = false
              popup?.destroy()
              component?.destroy()
            },
          }
        },
      },
    }),
  ],
  editorProps: {
    handleKeyDown(view, event) {
      if (!props.editable) return false

      // Cmd/Ctrl+Backspace at start - delete entire chunk
      if ((event.metaKey || event.ctrlKey) && event.key === 'Backspace') {
        const { from, empty } = view.state.selection
        if (empty && from <= 1) {
          emit('delete-chunk')

          return true
        }
      }

      // Backspace at start (without modifiers) - merge with previous chunk
      if (event.key === 'Backspace' && !event.metaKey && !event.ctrlKey) {
        const { from, empty } = view.state.selection
        // Only emit if NO text is selected AND cursor is at start
        // ProseMirror positions start at 1, so position 1 means start of content
        if (empty && from <= 1) {
          emit('backspace-at-start')

          return true // Prevent default backspace behavior
        }
        // Otherwise let TipTap handle deletion naturally (including selected text)
      }

      // Delete/Backspace in empty table cell - delete the row
      if (event.key === 'Backspace' || event.key === 'Delete') {
        const { $from, empty } = view.state.selection
        if (empty) {
          // Check if we're in a table cell
          for (let d = $from.depth; d > 0; d--) {
            const node = $from.node(d)
            if (node.type.name === 'tableCell' || node.type.name === 'tableHeader') {
              // If cell is empty, delete the row
              if (node.textContent.length === 0) {
                editor.value?.chain().focus().deleteRow().run()

                return true
              }
              break
            }
          }
        }
      }

      // Cmd/Ctrl+Enter - split at cursor
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
        const { from } = view.state.selection
        const textBefore = view.state.doc.textBetween(0, from, '\n')
        const textAfter = view.state.doc.textBetween(from, view.state.doc.content.size, '\n')

        emit('split-at-cursor', {
          before: textBefore.trim(),
          after: textAfter.trim(),
        })

        return true
      }

      // Arrow down at end - move to next chunk (skip if slash menu is open)
      if (event.key === 'ArrowDown' && !isSlashMenuOpen.value) {
        const { to } = view.state.selection
        const docEnd = view.state.doc.content.size - 1

        if (to >= docEnd) {
          emit('arrow-down-at-end')

          return true
        }
      }

      // Arrow up at start - move to previous chunk (skip if slash menu is open)
      if (event.key === 'ArrowUp' && !isSlashMenuOpen.value) {
        const { from } = view.state.selection
        // ProseMirror positions start at 1, so position 1 means start of content
        if (from <= 1) {
          emit('arrow-up-at-start')

          return true
        }
      }

      return false
    },
    handleDOMEvents: {
      contextmenu(view, event) {
        if (!props.editable) return false

        event.preventDefault()
        savedCursorPosition.value = view.state.selection.from
        contextMenuPosition.value = { x: event.clientX, y: event.clientY }
        showContextMenu.value = true

        return true
      },
    },
  },
  onUpdate() {
    if (!editor.value || !props.editable) return

    const markdown = editor.value.getMarkdown?.() ?? editor.value.getHTML()

    emit('update:modelValue', markdown)
  },
})

watch(
  () => props.modelValue,
  value => {
    const currentMarkdown = editor.value?.getMarkdown?.() ?? ''
    const isSame = currentMarkdown === value

    if (isSame) return

    editor.value?.commands.setContent(value ?? '', { contentType: 'markdown' })
  }
)

function focusEditor() {
  if (props.editable && editor.value) {
    editor.value.commands.focus()
  }
}

function focusAtStart() {
  if (props.editable && editor.value) {
    editor.value.commands.focus('start')
  }
}

function focusAtEnd() {
  if (props.editable && editor.value) {
    editor.value.commands.focus('end')
  }
}

onBeforeUnmount(() => {
  editor.value?.destroy()
})

defineExpose({ focusEditor, focusAtStart, focusAtEnd })
</script>

<template>
  <div class="knowledge-editor" @click="focusEditor">
    <EditorContent :editor="editor" />
    <TableBubbleMenu v-if="editor && props.editable" :editor="editor" />

    <!-- Context menu -->
    <VMenu
      v-model="showContextMenu"
      :target="[contextMenuPosition.x, contextMenuPosition.y]"
      location-strategy="connected"
      scroll-strategy="close"
    >
      <VList density="compact" class="py-1 context-menu-list">
        <VListItem v-for="item in menuItems" :key="item.title" @click="handleContextMenuAction(item)">
          <template #prepend>
            <VIcon :icon="item.icon" size="18" class="me-2" />
          </template>
          <VListItemTitle>{{ item.title }}</VListItemTitle>
        </VListItem>
        <VDivider class="my-1" />
        <VListItem @click="handleSplitFromContextMenu">
          <template #prepend>
            <VIcon icon="tabler-separator" size="18" class="me-2" />
          </template>
          <VListItemTitle>Split chunk here</VListItemTitle>
        </VListItem>
      </VList>
    </VMenu>
  </div>
</template>

<style scoped lang="scss">
.knowledge-editor {
  overflow: hidden;
  cursor: text;
  inline-size: 100%;
  min-block-size: 100px;
}

:deep(.ProseMirror) {
  padding: 1.25rem;
  margin: 0;
  font-family: var(--v-font-family, inherit);
  inline-size: 100%;
  line-height: 1.6;
  max-inline-size: 100%;
  min-block-size: 100px;
  outline: none;
  white-space: normal;
  word-break: break-word;

  p {
    margin-block-end: 0;
  }

  ul,
  ol {
    padding-inline-start: 1.5rem;
  }

  /* Show placeholder on current empty paragraph only (Notion-like behavior) */
  p.is-empty::before {
    block-size: 0;
    color: rgba(var(--v-theme-on-surface), 0.5);
    content: attr(data-placeholder);
    float: inline-start;
    pointer-events: none;
  }
}

:deep(.ProseMirror table) {
  border-collapse: collapse;
  inline-size: 100%;
  table-layout: fixed;
}

:deep(.ProseMirror th),
:deep(.ProseMirror td) {
  padding: 0.5rem;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  word-break: break-word;
}

:deep(.ProseMirror pre) {
  max-inline-size: 100%;
  overflow-x: auto;
  background: rgba(var(--v-theme-on-surface), 0.05);
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-block: 0.5rem;
}

:deep(.ProseMirror code) {
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.875em;
}

:deep(.ProseMirror pre code) {
  background: none;
  padding: 0;
}

:deep(.ProseMirror h1),
:deep(.ProseMirror h2),
:deep(.ProseMirror h3),
:deep(.ProseMirror h4),
:deep(.ProseMirror h5),
:deep(.ProseMirror h6) {
  font-weight: 600;
  line-height: 1.3;
  margin-block: 0.75rem 0.25rem;
}

:deep(.ProseMirror h1) {
  font-size: 1.75em;
}

:deep(.ProseMirror h2) {
  font-size: 1.5em;
}

:deep(.ProseMirror h3) {
  font-size: 1.25em;
}

:deep(.ProseMirror h4) {
  font-size: 1.125em;
}

:deep(.ProseMirror blockquote) {
  border-inline-start: 3px solid rgba(var(--v-theme-primary), 0.5);
  padding-inline-start: 1rem;
  margin-inline-start: 0;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

:deep(.ProseMirror strong) {
  font-weight: 600;
}

:deep(.ProseMirror em) {
  font-style: italic;
}

:deep(.ProseMirror hr) {
  border: none;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  margin-block: 1rem;
}

:deep(.ProseMirror a) {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}

/* Hide the slash command decoration (the "/" and query text) */
:deep(.slash-command-decoration) {
  color: transparent;
}

/* Context menu styling */
.context-menu-list {
  max-block-size: 300px;
  overflow-y: auto;
}
</style>
