<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

interface Props {
  status: 'valid' | 'invalid' | 'saving' | 'just_saved'
  errorMessage?: string | null
}

const props = defineProps<Props>()

// Track pop animation state separately to avoid re-triggering on re-renders
const showPop = ref(false)
let popAnimationTimeout: ReturnType<typeof setTimeout> | null = null

// Clean up timeout on unmount
onUnmounted(() => {
  if (popAnimationTimeout) clearTimeout(popAnimationTimeout)
})

// Watch for status changes to handle animation
watch(
  () => props.status,
  (newStatus, oldStatus) => {
    // Clear existing timeout
    if (popAnimationTimeout) clearTimeout(popAnimationTimeout)

    if (newStatus === 'just_saved' && oldStatus !== 'just_saved') {
      // Trigger pop animation once
      showPop.value = true
      popAnimationTimeout = setTimeout(() => {
        showPop.value = false
      }, 350) // Match animation duration
    }
  }
)

const statusColor = computed(() => {
  switch (props.status) {
    case 'valid':
    case 'just_saved':
      return 'success'
    case 'invalid':
      return 'error'
    case 'saving':
      return 'warning'
    default:
      return 'success'
  }
})

const statusIcon = computed(() => {
  switch (props.status) {
    case 'valid':
    case 'just_saved':
      return 'tabler-circle-check-filled'
    case 'invalid':
      return 'tabler-circle-filled'
    case 'saving':
      return 'tabler-loader'
    default:
      return 'tabler-circle-check-filled'
  }
})

const tooltipText = computed(() => {
  switch (props.status) {
    case 'valid':
      return 'Configuration is valid'
    case 'just_saved':
      return 'Changes saved'
    case 'invalid':
      return props.errorMessage || 'Configuration has errors'
    case 'saving':
      return 'Saving changes...'
    default:
      return 'Configuration is valid'
  }
})

const isExpanded = computed(() => props.status === 'just_saved')
</script>

<template>
  <VTooltip location="bottom">
    <template #activator="{ props: tooltipProps }">
      <div class="validation-status-indicator" :class="{ expanded: isExpanded }" v-bind="tooltipProps">
        <VIcon
          :icon="statusIcon"
          :color="statusColor"
          :class="{ rotating: status === 'saving', pop: showPop }"
          size="20"
        />
        <span class="status-text" :class="{ visible: isExpanded }">Saved</span>
      </div>
    </template>
    <span>{{ tooltipText }}</span>
  </VTooltip>
</template>

<style lang="scss" scoped>
.validation-status-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-inline-start: 16px;
  align-self: center;
  border-radius: 16px;
  cursor: pointer;
  overflow: hidden;

  &.expanded {
    padding-inline-end: 10px;
  }
}

.status-text {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-success));
  white-space: nowrap;
  opacity: 0;
  max-width: 0;
  overflow: hidden;
  transition:
    opacity 0.25s ease,
    max-width 0.4s cubic-bezier(0.34, 1.56, 0.64, 1),
    margin 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  &.visible {
    opacity: 1;
    max-width: 50px;
    margin-inline-start: 4px;
  }
}

.rotating {
  animation: rotate 1s linear infinite;
}

.pop {
  animation: pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes pop {
  0% {
    transform: scale(0.6);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.2);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
