import { type Editor, Extension, type Range } from '@tiptap/core'
import Suggestion, { type SuggestionOptions } from '@tiptap/suggestion'

// Base menu item - reusable for both slash menu and context menu
export interface MenuItem {
  title: string
  icon: string
  action: (editor: Editor) => void
}

export interface MenuItemCallbacks {
  onAddChunk?: () => void
}

// Base menu items - shared between slash commands and context menu
export const createMenuItems = (callbacks?: MenuItemCallbacks): MenuItem[] => [
  {
    title: 'Heading 1',
    icon: 'tabler-h-1',
    action: editor => editor.chain().focus().setNode('heading', { level: 1 }).run(),
  },
  {
    title: 'Heading 2',
    icon: 'tabler-h-2',
    action: editor => editor.chain().focus().setNode('heading', { level: 2 }).run(),
  },
  {
    title: 'Heading 3',
    icon: 'tabler-h-3',
    action: editor => editor.chain().focus().setNode('heading', { level: 3 }).run(),
  },
  {
    title: 'Bullet List',
    icon: 'tabler-list',
    action: editor => editor.chain().focus().toggleBulletList().run(),
  },
  {
    title: 'Numbered List',
    icon: 'tabler-list-numbers',
    action: editor => editor.chain().focus().toggleOrderedList().run(),
  },
  {
    title: 'Table',
    icon: 'tabler-table',
    action: editor => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
  },
  {
    title: 'Code Block',
    icon: 'tabler-code',
    action: editor => editor.chain().focus().toggleCodeBlock().run(),
  },
  {
    title: 'Quote',
    icon: 'tabler-quote',
    action: editor => editor.chain().focus().toggleBlockquote().run(),
  },
  {
    title: 'Divider',
    icon: 'tabler-minus',
    action: editor => editor.chain().focus().setHorizontalRule().run(),
  },
  {
    title: 'New Chunk',
    icon: 'tabler-plus',
    action: () => callbacks?.onAddChunk?.(),
  },
]

// Slash command item - wraps MenuItem with range deletion
export interface SlashCommandItem {
  title: string
  icon: string
  command: (params: { editor: Editor; range: Range }) => void
}

// Slash commands - wraps menu items with deleteRange for "/" trigger removal
export const createSlashCommands = (callbacks?: MenuItemCallbacks): SlashCommandItem[] =>
  createMenuItems(callbacks).map(item => ({
    title: item.title,
    icon: item.icon,
    command: ({ editor, range }) => {
      editor.chain().focus().deleteRange(range).run()
      item.action(editor)
    },
  }))

export interface SlashCommandsOptions {
  suggestion: Omit<SuggestionOptions<SlashCommandItem>, 'editor'>
}

export const SlashCommands = Extension.create<SlashCommandsOptions>({
  name: 'slashCommands',

  addOptions() {
    return {
      suggestion: {
        char: '/',
        command: ({ editor, range, props }) => {
          props.command({ editor, range })
        },
      },
    }
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        editor: this.editor,
        ...this.options.suggestion,
      }),
    ]
  },
})
