<script setup lang="ts">
import { computed, ref } from 'vue'
import ProjectAvatar from './ProjectAvatar.vue'
import { useTextTruncated } from '@/composables/useTextTruncated'
import { tagColor } from '@/utils/tagColor'

interface GraphRunner {
  graph_runner_id: string
  env: string | null
  tag_name: string | null
}

interface Project {
  project_id: string
  project_name: string
  description: string | null
  icon?: string
  icon_color?: string
  created_at?: string
  updated_at?: string
  graph_runners?: GraphRunner[]
  project_type?: 'AGENT' | 'WORKFLOW'
  is_template?: boolean
  tags?: string[]
}

interface Props {
  project: Project
  icon?: string
  canEdit?: boolean
  canDelete?: boolean
  isLoading?: boolean
  projectType?: 'AGENT' | 'WORKFLOW'
}

const props = withDefaults(defineProps<Props>(), {
  icon: 'tabler-file',
  canEdit: true,
  canDelete: true,
  isLoading: false,
})

const emit = defineEmits<{
  click: [project: Project]
  edit: [project: Project]
  delete: [project: Project]
  duplicate: [project: Project]
}>()

const menuOpen = ref(false)

const handleClick = () => {
  emit('click', props.project)
}

const handleEdit = (event: Event) => {
  event.stopPropagation()
  menuOpen.value = false
  emit('edit', props.project)
}

const handleDelete = (event: Event) => {
  event.stopPropagation()
  menuOpen.value = false
  emit('delete', props.project)
}

const handleDuplicate = (event: Event) => {
  event.stopPropagation()
  menuOpen.value = false
  emit('duplicate', props.project)
}

const descriptionRef = ref<HTMLElement | null>(null)
const { isTruncated } = useTextTruncated(descriptionRef)

const hasDescription = computed(() => !!props.project.description?.trim())

const versionCount = computed(() => {
  return props.project.graph_runners?.length || 0
})

const canDuplicate = computed(() => {
  const type = props.projectType || props.project.project_type
  return props.canEdit && type === 'WORKFLOW'
})

const visibleTags = computed(() => {
  const tags = props.project.tags
  if (!tags || tags.length === 0) return []
  return tags.slice(0, 3)
})

const hiddenTagCount = computed(() => {
  const tags = props.project.tags
  if (!tags) return 0
  return Math.max(0, tags.length - 3)
})
</script>

<template>
  <VCard
    class="project-card"
    :ripple="false"
    :loading="isLoading"
    :disabled="isLoading"
    elevation="0"
    @click="handleClick"
  >
    <VOverlay v-if="isLoading" :model-value="true" contained persistent class="align-center justify-center">
      <VProgressCircular indeterminate size="40" color="primary" />
    </VOverlay>

    <VCardText class="card-content pa-2">
      <div class="d-flex align-start gap-3 mb-2">
        <ProjectAvatar :icon="project.icon" :icon-color="project.icon_color" size="medium" />
        <div class="flex-grow-1 min-width-0">
          <div class="d-flex align-start justify-space-between">
            <span class="text-subtitle-1 font-weight-semibold line-clamp-2 text-start" style="word-break: break-word">
              {{ project.project_name }}
            </span>

            <VMenu v-if="canEdit || canDelete" v-model="menuOpen">
              <template #activator="{ props: menuProps }">
                <VBtn
                  v-bind="menuProps"
                  icon
                  variant="text"
                  size="x-small"
                  color="default"
                  class="menu-button flex-shrink-0"
                  @click.stop
                >
                  <VIcon icon="tabler-dots" size="16" />
                </VBtn>
              </template>
              <VList density="compact">
                <VListItem v-if="canEdit" @click="handleEdit">
                  <template #prepend>
                    <VIcon icon="tabler-edit" size="16" />
                  </template>
                  <VListItemTitle>Edit</VListItemTitle>
                </VListItem>
                <VListItem v-if="canDuplicate" @click="handleDuplicate">
                  <template #prepend>
                    <VIcon icon="tabler-copy" size="16" />
                  </template>
                  <VListItemTitle>Duplicate</VListItemTitle>
                </VListItem>
                <VListItem v-if="canDelete" @click="handleDelete">
                  <template #prepend>
                    <VIcon icon="tabler-trash" size="16" color="error" />
                  </template>
                  <VListItemTitle class="text-error">Delete</VListItemTitle>
                </VListItem>
              </VList>
            </VMenu>
          </div>
          <VTooltip v-if="hasDescription" :disabled="!isTruncated" location="bottom" max-width="320">
            <template #activator="{ props: tooltipProps }">
              <div
                ref="descriptionRef"
                v-bind="tooltipProps"
                class="text-caption text-medium-emphasis line-clamp-2 mt-1"
              >
                {{ project.description }}
              </div>
            </template>
            {{ project.description }}
          </VTooltip>
        </div>
      </div>

      <div class="d-flex align-center justify-space-between gap-2">
        <div v-if="visibleTags.length > 0" class="d-flex align-center gap-1 min-width-0 tags-row">
          <VChip
            v-for="tag in visibleTags"
            :key="tag"
            size="x-small"
            variant="tonal"
            :color="tagColor(tag)"
            label
            class="tag-chip"
          >
            {{ tag }}
          </VChip>
          <VChip v-if="hiddenTagCount > 0" size="x-small" variant="text" color="secondary" class="tag-chip">
            +{{ hiddenTagCount }}
          </VChip>
        </div>
        <VSpacer v-else />
        <VChip size="x-small" variant="tonal" color="primary" class="flex-shrink-0">
          <VIcon icon="tabler-versions" size="12" class="me-1" />
          {{ versionCount }} {{ versionCount === 1 ? 'version' : 'versions' }}
        </VChip>
      </div>
    </VCardText>
  </VCard>
</template>

<style lang="scss" scoped>
.project-card {
  cursor: pointer;
  transition:
    background-color 0.2s ease-out,
    border-color 0.2s ease-out;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: var(--dnr-radius-lg);
  block-size: 100%;
  position: relative;
  min-width: 0;
  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.02);
    border-color: rgba(var(--v-border-color), 0.12);
  }
}

.card-content {
  position: relative;
}

.menu-button {
  opacity: 0;
  transition: opacity 0.2s ease-out;

  .project-card:hover & {
    opacity: 1;
  }
}

.min-width-0 {
  min-inline-size: 0;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tags-row {
  overflow: hidden;
}

.tag-chip {
  max-inline-size: 80px;
  :deep(.v-chip__content) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
