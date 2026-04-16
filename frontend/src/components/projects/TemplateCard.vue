<!-- eslint-disable vue/prefer-true-attribute-shorthand -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import ProjectAvatar from './ProjectAvatar.vue'
import { useTextTruncated } from '@/composables/useTextTruncated'

interface Template {
  project_id: string
  project_name: string
  description: string | null
  icon?: string
  icon_color?: string
  project_type?: 'AGENT' | 'WORKFLOW'
  is_template?: boolean
}

interface Props {
  template: Template
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  click: [template: Template]
}>()

const handleClick = () => {
  emit('click', props.template)
}

const descriptionRef = ref<HTMLElement | null>(null)
const { isTruncated } = useTextTruncated(descriptionRef)

const hasDescription = computed(() => !!props.template.description?.trim())
</script>

<template>
  <VCard class="template-card" :class="{ 'is-disabled': disabled }" :ripple="false" elevation="0" @click="handleClick">
    <VCardText class="pa-3 d-flex flex-column template-card-content" style="height: 100%">
      <div class="d-flex align-center gap-2 mb-2">
        <ProjectAvatar :icon="template.icon" :icon-color="template.icon_color" size="small" />
        <VChip size="x-small" variant="tonal" color="secondary"> Template </VChip>
      </div>

      <div class="text-subtitle-2 font-weight-semibold line-clamp-1 text-start mb-1" style="word-break: break-word">
        {{ template.project_name }}
      </div>

      <VTooltip v-if="hasDescription" :disabled="!isTruncated" location="bottom" max-width="320">
        <template #activator="{ props: tooltipProps }">
          <div ref="descriptionRef" v-bind="tooltipProps" class="text-caption text-medium-emphasis line-clamp-2">
            {{ template.description }}
          </div>
        </template>
        {{ template.description }}
      </VTooltip>
    </VCardText>
  </VCard>
</template>

<style lang="scss" scoped>
.template-card {
  cursor: pointer;
  transition:
    background-color 0.2s ease-out,
    border-color 0.2s ease-out;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: var(--dnr-radius-lg);
  min-width: 0;
  height: 136px;

  &:hover:not(.is-disabled) {
    background-color: rgba(var(--v-theme-on-surface), 0.02);
    border-color: rgba(var(--v-border-color), 0.12);
  }
}

.template-card-content {
  position: relative;
}

.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
