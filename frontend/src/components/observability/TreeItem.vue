<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Span } from '../../types/observability'

defineOptions({
  name: 'TreeItem',
})

const props = defineProps<{
  item: Span
  level?: number
  isLastChild?: boolean
  selectedSpanId?: string
  rootDuration?: number
  iconMap?: Record<string, string>
  parentIcon?: string
}>()

const emit = defineEmits<{
  (e: 'click', span: Span): void
}>()

const level = computed(() => props.level || 0)
const hasChildren = computed(() => (props.item.children?.length ?? 0) > 0)
const isExpanded = ref(true)
const isSelected = computed(() => props.selectedSpanId === props.item.span_id)
const isError = computed(() => props.item.status_code !== 'OK')

const durationSeconds = computed(() => {
  const startTime = new Date(props.item.start_time).getTime()
  const endTime = new Date(props.item.end_time).getTime()
  return (endTime - startTime) / 1000
})

const formattedDuration = computed(() => durationSeconds.value.toFixed(2))

const durationSeverity = computed<'normal' | 'slow' | 'very-slow'>(() => {
  if (durationSeconds.value > 10) return 'very-slow'
  if (durationSeconds.value > 5) return 'slow'
  return 'normal'
})

const FALLBACK_ICON = 'tabler-code'

const spanIcon = computed(() => {
  if (props.iconMap?.[props.item.name]) return props.iconMap[props.item.name]
  return props.parentIcon ?? FALLBACK_ICON
})

const effectiveRootDuration = computed(() => {
  if (props.rootDuration && props.rootDuration > 0) return props.rootDuration
  return durationSeconds.value
})

const durationBarPercent = computed(() => {
  if (effectiveRootDuration.value <= 0) return 0
  return Math.max(4, Math.min(100, (durationSeconds.value / effectiveRootDuration.value) * 100))
})

const toggleExpand = (e: Event) => {
  e.stopPropagation()
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <div class="tree-item-wrapper">
    <div
      class="trace-node"
      :class="{
        selected: isSelected,
        'is-root': level === 0,
        'is-error': isError,
      }"
      :style="{ paddingInlineStart: `${level * 20 + 8}px` }"
      @click="emit('click', item)"
    >
      <!-- Expand/collapse toggle -->
      <button v-if="hasChildren" class="expand-toggle" @click="toggleExpand">
        <VIcon size="14" :icon="isExpanded ? 'tabler-chevron-down' : 'tabler-chevron-right'" />
      </button>
      <div v-else class="expand-spacer" />

      <!-- Icon circle with status dot -->
      <div class="icon-circle">
        <VIcon size="16" :icon="spanIcon" />
        <span v-if="isError" class="status-dot status-error" />
      </div>

      <!-- Name -->
      <span class="node-name text-truncate">{{ item.name }}</span>

      <!-- Duration bar + text -->
      <div class="duration-area">
        <div class="duration-bar-track">
          <div class="duration-bar-fill" :class="durationSeverity" :style="{ width: `${durationBarPercent}%` }" />
        </div>
        <span class="duration-text" :class="durationSeverity">{{ formattedDuration }}s</span>
      </div>
    </div>

    <div v-if="hasChildren && isExpanded" class="children-wrapper">
      <TreeItem
        v-for="(child, index) in item.children"
        :key="child.span_id"
        :item="child"
        :level="level + 1"
        :is-last-child="index === item.children!.length - 1"
        :selected-span-id="selectedSpanId"
        :root-duration="effectiveRootDuration"
        :icon-map="iconMap"
        :parent-icon="spanIcon"
        @click="emit('click', $event)"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.trace-node {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding-block: 3px;
  padding-inline-end: 8px;
  cursor: pointer;
  border-radius: 6px;
  border-inline-start: 3px solid transparent;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.04);
  }

  &.selected {
    border-inline-start-color: rgb(var(--v-theme-primary));
    background-color: rgba(var(--v-theme-primary), 0.06);
  }

  &.is-error {
    .icon-circle {
      background-color: rgba(var(--v-theme-error), 0.1);
      color: rgb(var(--v-theme-error));
    }
  }
}

.expand-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: pointer;
  padding: 0;

  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.08);
    color: rgba(var(--v-theme-on-surface), 0.8);
  }
}

.expand-spacer {
  flex-shrink: 0;
  width: 20px;
}

.icon-circle {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background-color: rgba(var(--v-theme-primary), 0.08);
  color: rgb(var(--v-theme-primary));
  transition: background-color 0.15s ease;
}

.status-dot {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid rgb(var(--v-theme-surface));
}

.status-error {
  background-color: rgb(var(--v-theme-error));
}

.node-name {
  flex: 1;
  min-width: 0;
  font-size: 0.8rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.85);
  line-height: 1.3;
}

.duration-area {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  min-width: 80px;
}

.duration-bar-track {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  overflow: hidden;
  min-width: 30px;
}

.duration-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;

  &.normal {
    background-color: rgb(var(--v-theme-primary));
    opacity: 0.5;
  }

  &.slow {
    background-color: rgb(var(--v-theme-warning));
    opacity: 0.7;
  }

  &.very-slow {
    background-color: rgb(var(--v-theme-error));
    opacity: 0.7;
  }
}

.duration-text {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.65rem;
  font-weight: 500;
  white-space: nowrap;

  &.normal {
    color: rgba(var(--v-theme-on-surface), 0.5);
  }

  &.slow {
    color: rgb(var(--v-theme-warning));
  }

  &.very-slow {
    color: rgb(var(--v-theme-error));
  }
}

.children-wrapper {
  position: relative;
}
</style>
