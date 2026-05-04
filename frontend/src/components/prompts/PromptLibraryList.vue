<script setup lang="ts">
import { computed, ref, reactive } from 'vue'
import type { PromptResponse } from '@/api/prompts'
import type { TreeFolder, TreeNode } from '@/types/prompts'
import { usePromptsQuery, useDeletePromptMutation } from '@/composables/queries/usePromptsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'
import PromptTreeNode from './PromptTreeNode.vue'

const props = defineProps<{ orgId: string }>()

const orgIdRef = computed(() => props.orgId)
const { data: prompts, isLoading, error } = usePromptsQuery(orgIdRef)
const deletePromptMutation = useDeletePromptMutation(orgIdRef)
const { notify } = useNotifications()

const promptToDelete = ref<PromptResponse | null>(null)
const showDeleteConfirm = ref(false)
const expandedFolders = reactive(new Set<string>())

function getPromptName(p: PromptResponse): string {
  return p.latest_version?.name || 'Untitled'
}

function buildTree(items: PromptResponse[]): TreeNode[] {
  const root: TreeNode[] = []
  const folderMap = new Map<string, TreeFolder>()

  function ensureFolder(pathParts: string[]): TreeFolder {
    const fullPath = pathParts.join('/')
    if (folderMap.has(fullPath)) return folderMap.get(fullPath)!

    const folder: TreeFolder = { kind: 'folder', name: pathParts[pathParts.length - 1], path: fullPath, children: [] }
    folderMap.set(fullPath, folder)

    if (pathParts.length === 1) {
      root.push(folder)
    } else {
      const parent = ensureFolder(pathParts.slice(0, -1))
      parent.children.push(folder)
    }
    return folder
  }

  for (const prompt of items) {
    const name = getPromptName(prompt)
    const parts = name.split('/')
    if (parts.length === 1) {
      root.push({ kind: 'file', name, prompt })
    } else {
      const folderParts = parts.slice(0, -1)
      const fileName = parts[parts.length - 1]
      const parent = ensureFolder(folderParts)
      parent.children.push({ kind: 'file', name: fileName, prompt })
    }
  }

  function sortNodes(nodes: TreeNode[]): TreeNode[] {
    return nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  }

  function sortTree(nodes: TreeNode[]): TreeNode[] {
    for (const node of nodes) {
      if (node.kind === 'folder') node.children = sortTree(node.children)
    }
    return sortNodes(nodes)
  }

  return sortTree(root)
}

const promptList = computed(() => prompts.value || [])

const tree = computed(() => buildTree(promptList.value))

function toggleFolder(path: string) {
  if (expandedFolders.has(path)) expandedFolders.delete(path)
  else expandedFolders.add(path)
}

function confirmDelete(prompt: PromptResponse) {
  promptToDelete.value = prompt
  showDeleteConfirm.value = true
}

async function handleDelete() {
  if (!promptToDelete.value) return
  try {
    await deletePromptMutation.mutateAsync(promptToDelete.value.id)
    showDeleteConfirm.value = false
    promptToDelete.value = null
  } catch (err) {
    logger.error('deletePrompt failed', { error: err })
    notify.error('Failed to delete prompt. Please try again.')
  }
}
</script>

<template>
  <div>
    <div class="d-flex align-center gap-4 mb-6">
      <VSpacer />
      <VBtn
        color="primary"
        prepend-icon="tabler-plus"
        :to="{ name: 'org-org-id-prompts-new', params: { orgId: props.orgId } }"
      >
        New Prompt
      </VBtn>
    </div>

    <LoadingState v-if="isLoading" message="Loading prompts..." />

    <ErrorState v-else-if="error" title="Failed to load prompts" :description="(error as Error).message" />

    <EmptyState
      v-else-if="!promptList.length"
      icon="tabler-file-text"
      title="No prompts yet"
      description="Create your first prompt to build a reusable prompt library for your organization."
      action-text="Create Prompt"
      @action="$router.push({ name: 'org-org-id-prompts-new', params: { orgId: props.orgId } })"
    />

    <div v-else class="prompt-tree">
      <template v-for="node in tree" :key="node.kind === 'folder' ? node.path : node.prompt.id">
        <PromptTreeNode
          :node="node"
          :org-id="props.orgId"
          :expanded-folders="expandedFolders"
          @toggle-folder="toggleFolder"
          @delete="confirmDelete"
        />
      </template>
    </div>

    <VDialog v-model="showDeleteConfirm" max-width="440">
      <VCard>
        <VCardTitle class="text-h6 pa-4">Delete Prompt</VCardTitle>
        <VCardText>
          Are you sure you want to delete
          <strong>{{ promptToDelete?.latest_version?.name }}</strong>? This action cannot be undone.
        </VCardText>
        <VCardActions class="justify-end pa-4">
          <VBtn variant="text" @click="showDeleteConfirm = false">Cancel</VBtn>
          <VBtn color="error" :loading="deletePromptMutation.isPending.value" @click="handleDelete">Delete</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.prompt-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
