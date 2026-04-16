<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ text?: string }>()

// Unique ID for this popover instance
const instanceId = Math.random().toString(36).slice(2)

const isOpen = ref(false)
const root = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)
const popoverStyle = ref<Record<string, string>>({})
const openingClick = ref<MouseEvent | null>(null)

const close = () => {
  isOpen.value = false
}

// Listen for other popovers opening
const handleOtherPopoverOpen = (event: Event) => {
  const customEvent = event as CustomEvent<string>
  if (customEvent.detail !== instanceId && isOpen.value) {
    close()
  }
}

const POPOVER_WIDTH = 320
const POPOVER_HEIGHT = 150
const OFFSET = 8

const updatePosition = () => {
  if (!root.value || !isOpen.value) return

  const triggerRect = root.value.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  const spaceOnRight = viewportWidth - triggerRect.right
  const spaceOnLeft = triggerRect.left

  // Calculate vertical position (prefer below, fallback to above)
  let top = triggerRect.bottom + OFFSET
  if (top + POPOVER_HEIGHT > viewportHeight) {
    top = triggerRect.top - POPOVER_HEIGHT - OFFSET
  }
  if (top < OFFSET) top = OFFSET

  // Calculate horizontal position (prefer right, fallback to left, then center)
  let left

  // Try positioning to the right of trigger first
  if (spaceOnRight >= POPOVER_WIDTH + OFFSET) {
    left = triggerRect.left
  }
  // If not enough space on right, position to left of trigger
  else if (spaceOnLeft >= POPOVER_WIDTH + OFFSET) {
    left = triggerRect.right - POPOVER_WIDTH
  }
  // If neither side has space, center it
  else {
    left = Math.max(OFFSET, (viewportWidth - POPOVER_WIDTH) / 2)
  }

  popoverStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    userSelect: 'text',
    WebkitUserSelect: 'text',
  }
}

const toggle = (event: MouseEvent) => {
  if (!isOpen.value) {
    // Notify other popovers to close
    document.dispatchEvent(new CustomEvent('infopopover:open', { detail: instanceId }))
    openingClick.value = event
  }
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    nextTick(() => {
      updatePosition()
    })
  }
}

const handleDocumentClick = (event: MouseEvent) => {
  if (!isOpen.value) return
  // Ignore the same click event that opened the popover
  if (event === openingClick.value) {
    openingClick.value = null
    return
  }
  const target = event.target as Node
  if (root.value?.contains(target) || content.value?.contains(target)) return
  close()
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && isOpen.value) {
    close()
    root.value?.querySelector('button')?.focus()
  }
}

const handleScroll = () => {
  if (isOpen.value) close()
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('infopopover:open', handleOtherPopoverOpen)
  window.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleScroll)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('infopopover:open', handleOtherPopoverOpen)
  window.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleScroll)
})

watch(isOpen, value => {
  if (value) {
    nextTick(() => {
      updatePosition()
    })
  }
})
</script>

<template>
  <div ref="root" class="info-popover">
    <button
      class="info-popover__trigger"
      type="button"
      aria-label="Show information"
      :aria-expanded="isOpen"
      @click.stop="toggle($event)"
    >
      ?
    </button>

    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="isOpen"
          ref="content"
          class="info-popover__content"
          :style="popoverStyle"
          role="dialog"
          @mousedown.stop
          @selectstart.stop
        >
          <button class="info-popover__close" type="button" aria-label="Close information" @click.stop="close">
            &times;
          </button>
          <div class="info-popover__body" style="-webkit-user-select: text; user-select: text; cursor: text">
            <slot>{{ props.text }}</slot>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
.info-popover {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.info-popover__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.35);
  border-radius: 50%;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition:
    border-color 0.2s,
    color 0.2s,
    background-color 0.2s;

  &:hover,
  &:focus-visible {
    border-color: rgb(var(--v-theme-primary));
    color: rgb(var(--v-theme-primary));
    outline: none;
  }

  &:focus-visible {
    box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.2);
  }
}

.info-popover__content {
  position: fixed;
  inline-size: clamp(260px, 40vw, 420px);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  padding: 18px 24px 18px 18px;
  z-index: 9999;
  cursor: auto;
  line-height: 1.5;
  pointer-events: auto;
  -webkit-user-select: text !important;
  user-select: text !important;
}

.info-popover__body {
  font-size: 0.875rem;
  -webkit-user-select: text !important;
  user-select: text !important;
  cursor: text;
  white-space: pre-wrap;
  word-break: break-word;
}

.info-popover__close {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition:
    background-color 0.15s,
    color 0.15s;

  &:hover,
  &:focus-visible {
    background: rgba(var(--v-theme-on-surface), 0.08);
    color: rgba(var(--v-theme-on-surface), 0.8);
    outline: none;
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
}
</style>
