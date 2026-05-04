<script setup lang="ts">
import type { PromptResponse } from '@/api/prompts'
import type { TreeNode } from '@/types/prompts'
import { formatDate } from '@/utils/formatters'

defineProps<{
  node: TreeNode
  orgId: string
  expandedFolders: Set<string>
}>()

const emit = defineEmits<{
  toggleFolder: [path: string]
  delete: [prompt: PromptResponse]
}>()
</script>

<template>
  <div v-if="node.kind === 'folder'" class="tree-folder">
    <button
      class="tree-folder__header"
      :aria-expanded="expandedFolders.has(node.path)"
      @click="emit('toggleFolder', node.path)"
    >
      <VIcon
        :icon="expandedFolders.has(node.path) ? 'tabler-chevron-down' : 'tabler-chevron-right'"
        size="16"
      />
      <VIcon icon="tabler-folder" size="20" color="warning" />
      <span class="text-subtitle-2 font-weight-medium">{{ node.name }}</span>
      <span class="text-caption text-medium-emphasis ms-1">({{ node.children.length }})</span>
    </button>
    <div v-if="expandedFolders.has(node.path)" class="tree-folder__children">
      <PromptTreeNode
        v-for="child in node.children"
        :key="child.kind === 'folder' ? child.path : child.prompt.id"
        :node="child"
        :org-id="orgId"
        :expanded-folders="expandedFolders"
        @toggle-folder="emit('toggleFolder', $event)"
        @delete="emit('delete', $event)"
      />
    </div>
  </div>

  <div v-else class="tree-file">
    <RouterLink
      :to="{ name: 'org-org-id-prompts-id', params: { orgId, id: node.prompt.id } }"
      class="tree-file__link text-decoration-none"
    >
      <VIcon icon="tabler-file-text" size="20" color="primary" />
      <span class="text-subtitle-2 font-weight-medium text-truncate tree-file__name">{{ node.name }}</span>
      <VSpacer />
      <VChip v-if="node.prompt.latest_version" size="x-small" variant="tonal" color="info" label>
        v{{ node.prompt.latest_version.version_number }}
      </VChip>
      <span v-if="node.prompt.latest_version" class="text-caption text-medium-emphasis">
        {{ formatDate(node.prompt.latest_version.created_at) }}
      </span>
    </RouterLink>
    <VBtn
      icon
      variant="text"
      size="x-small"
      class="tree-file__delete"
      aria-label="Delete prompt"
      @click="emit('delete', node.prompt)"
    >
      <VIcon icon="tabler-trash" size="16" />
    </VBtn>
  </div>
</template>

<style lang="scss" scoped>
.tree-folder {
  &__header {
    display: flex;
    inline-size: 100%;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border: none;
    border-radius: 8px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
    transition: background-color 0.15s;

    &:hover {
      background: rgba(var(--v-theme-on-surface), 0.04);
    }
  }

  &__children {
    padding-inline-start: 28px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
}

.tree-file {
  display: flex;
  align-items: center;
  gap: 0;
  padding-inline-end: 4px;
  border-radius: 8px;
  transition: background-color 0.15s;
  color: rgb(var(--v-theme-on-surface));

  &:hover {
    background: rgba(var(--v-theme-on-surface), 0.04);
  }

  &__link {
    display: flex;
    flex: 1;
    align-items: center;
    gap: 8px;
    padding: 8px 0 8px 12px;
    min-inline-size: 0;
    color: inherit;
    cursor: pointer;
  }

  &__name {
    flex: 1;
    min-inline-size: 0;
  }

  &__delete {
    opacity: 0;
    transition: opacity 0.15s;
    flex-shrink: 0;
  }

  &:hover &__delete,
  &__delete:focus-visible {
    opacity: 1;
  }
}
</style>
