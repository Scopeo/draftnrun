import type { PromptResponse } from '@/api/prompts'

export interface TreeFolder {
  kind: 'folder'
  name: string
  path: string
  children: TreeNode[]
}

export interface TreeFile {
  kind: 'file'
  name: string
  prompt: PromptResponse
}

export type TreeNode = TreeFolder | TreeFile
