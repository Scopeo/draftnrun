<script setup lang="ts">
import { computed } from 'vue'
import { getProjectColor, getProjectIcon } from '@/composables/useProjectDefaults'

type AvatarSize = 'small' | 'medium' | 'default' | 'large'

interface Props {
  icon?: string
  iconColor?: string
  size?: AvatarSize
}

const props = withDefaults(defineProps<Props>(), {
  size: 'default',
})

const sizeMap = {
  small: { avatar: 36, icon: 20 },
  medium: { avatar: 40, icon: 26 },
  default: { avatar: 50, icon: 32 },
  large: { avatar: 60, icon: 36 },
}

const avatarSize = computed(() => sizeMap[props.size].avatar)
const iconSize = computed(() => sizeMap[props.size].icon)

const displayIcon = computed(() => getProjectIcon(props.icon))
const displayColor = computed(() => getProjectColor(props.iconColor))

// Detect if color is a hex value (e.g., #FF6B6B) or a theme color name (e.g., grey-500)
const isHexColor = computed(() => displayColor.value.startsWith('#'))

const borderColorStyle = computed(() =>
  isHexColor.value ? displayColor.value : `rgb(var(--v-theme-${displayColor.value}))`
)
</script>

<template>
  <div
    class="project-avatar"
    :style="{
      backgroundColor: 'rgb(var(--v-theme-surface))',
      inlineSize: `${avatarSize}px`,
      blockSize: `${avatarSize}px`,
    }"
  >
    <VIcon :icon="displayIcon" :size="iconSize" :color="displayColor" />
  </div>
</template>

<style lang="scss" scoped>
.project-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  flex-shrink: 0;
  overflow: visible;
  isolation: isolate;
  background-color: rgba(var(--v-theme-primary), 0.06);
}
</style>
