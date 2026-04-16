<script setup lang="ts">
import { type Component, computed, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import UniversalObservabilityDrawer from '@/components/observability/UniversalObservabilityDrawer.vue'
import { PANEL_SIZES } from '@/config/panelSizes'
import { CALL_TYPE_OPTIONS, type CallType, type CallTypeOption, type TraceData } from '@/types/observability'

interface Props {
  projectId: string
  playgroundComponent: Component
  playgroundProps?: Record<string, any>
  toggleLabel?: string
  initialCallTypeFilter?: CallType
  callTypeFilterOptions?: CallTypeOption[]
  defaultPlaygroundWidth?: number
  minPlaygroundWidth?: number
  defaultObservabilityWidth?: number
  minObservabilityWidth?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'windowsChanged', observabilityOpen: boolean, expandedMode: boolean, widthPx?: number): void
  (e: 'widthChanged', widthPx: number): void
}>()

const DEFAULT_TOGGLE_LABEL = 'Inspect runs'
const DEFAULT_PLAYGROUND_WIDTH = props.defaultPlaygroundWidth ?? PANEL_SIZES.DEFAULT_WIDTH
const DEFAULT_OBSERVABILITY_WIDTH = props.defaultObservabilityWidth ?? PANEL_SIZES.DEFAULT_WIDTH
const MIN_PLAYGROUND_WIDTH = props.minPlaygroundWidth ?? PANEL_SIZES.MIN_PLAYGROUND_WIDTH
const MIN_OBSERVABILITY_WIDTH = props.minObservabilityWidth ?? PANEL_SIZES.MIN_OBSERVABILITY_WIDTH

const defaultCallTypeOptions = CALL_TYPE_OPTIONS

const callTypeOptions = computed<CallTypeOption[]>(() => {
  return props.callTypeFilterOptions && props.callTypeFilterOptions.length > 0
    ? props.callTypeFilterOptions
    : defaultCallTypeOptions
})

const toggleLabel = computed(() => props.toggleLabel ?? DEFAULT_TOGGLE_LABEL)

const showObservability = ref(false)
const callTypeFilter = ref<CallType>(props.initialCallTypeFilter ?? callTypeOptions.value[0]?.value ?? 'all')
const observabilityRef = ref<InstanceType<typeof UniversalObservabilityDrawer> | null>(null)
const playgroundRef = ref<any>(null)
const isTraceSelected = ref(false)

const typedCallTypeFilter = computed(() => callTypeFilter.value)

const windowWidth = ref(window.innerWidth)
const playgroundWidth = ref<number>(DEFAULT_PLAYGROUND_WIDTH)
const isResizing = ref(false)
let resizeStartX = 0
let resizeStartWidth = 0

const observabilityWidthPx = ref<number>(DEFAULT_OBSERVABILITY_WIDTH)
const isObsResizing = ref(false)
let obsResizeStartX = 0
let obsResizeStartWidth = 0

const PlaygroundComponent = computed(() => props.playgroundComponent)
const playgroundProps = computed(() => props.playgroundProps ?? {})

watch(callTypeOptions, options => {
  if (!options.some(option => option.value === callTypeFilter.value) && options[0]) {
    callTypeFilter.value = options[0].value
  }
})

watch(
  () => props.initialCallTypeFilter,
  value => {
    if (value && value !== callTypeFilter.value) {
      callTypeFilter.value = value
    }
  }
)

const maxPlaygroundWidth = computed(() => Math.round(window.innerWidth * 0.8 - 32))

const maxObservabilityWidth = computed(() => {
  const horizontalMargins = 32 // 16px left + 16px right
  const maxWidth = Math.round(window.innerWidth - horizontalMargins)
  return Math.max(MIN_OBSERVABILITY_WIDTH, maxWidth)
})

const observabilityWidth = computed(() => `${observabilityWidthPx.value}px`)

const playgroundShift = computed(() => '16px')

const expandedObservabilityWidth = computed(() => {
  const targetWidth = DEFAULT_OBSERVABILITY_WIDTH * PANEL_SIZES.EXPANDED_MULTIPLIER
  return Math.min(targetWidth, maxObservabilityWidth.value)
})

const clampObservabilityWidth = (rawWidth: number) => {
  return Math.min(Math.max(rawWidth, MIN_OBSERVABILITY_WIDTH), maxObservabilityWidth.value)
}

const handleWindowsChanged = () => {
  emit('windowsChanged', showObservability.value, isTraceSelected.value, observabilityWidthPx.value)
}

const updateObservabilityWidth = (target: number) => {
  const clamped = clampObservabilityWidth(target)
  if (observabilityWidthPx.value !== clamped) {
    observabilityWidthPx.value = clamped
  }
  handleWindowsChanged()
}

const adjustObservabilityWidth = (expanded: boolean) => {
  const targetWidth = expanded ? expandedObservabilityWidth.value : DEFAULT_OBSERVABILITY_WIDTH

  updateObservabilityWidth(targetWidth)
}

const handleViewModeChange = (expanded: boolean) => {
  isTraceSelected.value = expanded
  adjustObservabilityWidth(expanded)
}

const toggleObservability = () => {
  showObservability.value = !showObservability.value
  handleWindowsChanged()
}

const pendingTraceLoad = ref<TraceData | null>(null)

const isLoadingInPlayground = computed(() => {
  const loadingState = playgroundRef.value?.isLoadingTrace
  return loadingState ? loadingState.value : false
})

const handleLoadInPlayground = (traceData: TraceData) => {
  showObservability.value = false
  handleWindowsChanged()
  pendingTraceLoad.value = traceData
}

watchEffect(() => {
  if (pendingTraceLoad.value && !showObservability.value && playgroundRef.value?.loadTraceInPlayground) {
    const traceData = pendingTraceLoad.value

    pendingTraceLoad.value = null
    playgroundRef.value.loadTraceInPlayground(traceData)
  }
})

const handleOutsideClick = (event: MouseEvent) => {
  if (!observabilityRef.value || !isTraceSelected.value) return

  const target = event.target as Element
  const observabilityElement = document.querySelector('.observability-panel')

  if (observabilityElement && !observabilityElement.contains(target)) {
    ;(observabilityRef.value as any)?.clearTraceSelection?.()
  }
}

const handleResize = () => {
  windowWidth.value = window.innerWidth
  if (playgroundWidth.value > maxPlaygroundWidth.value) {
    playgroundWidth.value = maxPlaygroundWidth.value
    emit('widthChanged', playgroundWidth.value)
  }
  adjustObservabilityWidth(isTraceSelected.value)
}

const onResizeStart = (e: MouseEvent) => {
  isResizing.value = true
  resizeStartX = e.clientX
  resizeStartWidth = playgroundWidth.value
  window.addEventListener('mousemove', onResizing)
  window.addEventListener('mouseup', onResizeEnd)
}

const onResizing = (e: MouseEvent) => {
  const delta = resizeStartX - e.clientX
  const next = Math.min(Math.max(resizeStartWidth + delta, MIN_PLAYGROUND_WIDTH), maxPlaygroundWidth.value)

  playgroundWidth.value = next
  emit('widthChanged', next)
}

const onResizeEnd = () => {
  if (!isResizing.value) return
  isResizing.value = false
  window.removeEventListener('mousemove', onResizing)
  window.removeEventListener('mouseup', onResizeEnd)
  emit('widthChanged', playgroundWidth.value)
}

const onObsResizeStart = (e: MouseEvent) => {
  isObsResizing.value = true
  obsResizeStartX = e.clientX
  obsResizeStartWidth = observabilityWidthPx.value
  window.addEventListener('mousemove', onObsResizing)
  window.addEventListener('mouseup', onObsResizeEnd)
}

const onObsResizing = (e: MouseEvent) => {
  const delta = obsResizeStartX - e.clientX
  const next = Math.min(Math.max(obsResizeStartWidth + delta, MIN_OBSERVABILITY_WIDTH), maxObservabilityWidth.value)

  observabilityWidthPx.value = next
  handleWindowsChanged()
}

const onObsResizeEnd = () => {
  if (!isObsResizing.value) return
  isObsResizing.value = false
  window.removeEventListener('mousemove', onObsResizing)
  window.removeEventListener('mouseup', onObsResizeEnd)
  handleWindowsChanged()
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('resize', handleResize)
  adjustObservabilityWidth(false)
  handleWindowsChanged()
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('mousemove', onResizing)
  window.removeEventListener('mouseup', onResizeEnd)
  window.removeEventListener('mousemove', onObsResizing)
  window.removeEventListener('mouseup', onObsResizeEnd)
})
</script>

<template>
  <div class="run-history-floating-actions">
    <div v-if="!showObservability" class="observability-edge-zone">
      <div class="observability-edge-toggle" role="button" aria-label="Open run history" @click="toggleObservability">
        <div class="edge-vertical-tab">
          <span class="tab-label">{{ toggleLabel }}</span>
        </div>
      </div>
      <div class="observability-preview" aria-hidden="true" @click="toggleObservability" />
    </div>

    <div class="playground-panel" :style="{ right: playgroundShift, width: `${playgroundWidth}px` }">
      <div class="resize-handle" @mousedown="onResizeStart" />
      <VCard class="playground-card" elevation="2">
        <VCardTitle class="d-flex align-center pa-4">
          <VIcon icon="tabler-play" color="primary" class="me-2" />
          <span class="text-h6">Playground</span>
        </VCardTitle>
        <VCardText class="pa-0 playground-content-area">
          <component :is="PlaygroundComponent" ref="playgroundRef" v-bind="playgroundProps" />
        </VCardText>
      </VCard>
    </div>

    <Transition name="slide-from-right">
      <div v-if="showObservability" class="observability-panel" :style="{ width: observabilityWidth }">
        <div class="observability-resize-handle" @mousedown="onObsResizeStart" />
        <VCard class="observability-card" elevation="3">
          <VCardTitle class="d-flex flex-column pa-4" :class="{ 'pb-2': isTraceSelected }">
            <div class="d-flex align-center justify-space-between w-100" :class="{ 'mb-3': !isTraceSelected }">
              <div class="d-flex align-center gap-2">
                <VIcon icon="tabler-eye" color="primary" size="20" />
                <span class="text-h6">Run history</span>
              </div>
              <div class="d-flex align-center gap-1">
                <VBtn
                  icon
                  variant="text"
                  size="small"
                  :loading="Boolean(observabilityRef?.isLoading)"
                  title="Refresh runs"
                  @click="observabilityRef?.refreshTraces?.()"
                >
                  <VIcon icon="tabler-refresh" />
                </VBtn>
                <VBtn icon variant="text" size="small" title="Close" @click="toggleObservability">
                  <VIcon icon="tabler-x" />
                </VBtn>
              </div>
            </div>
            <div v-if="!isTraceSelected && callTypeOptions.length > 1" class="d-flex justify-center w-100 px-2">
              <VSelect
                v-model="callTypeFilter"
                :items="callTypeOptions"
                item-title="label"
                item-value="value"
                density="compact"
                hide-details
                variant="outlined"
                class="w-100"
              >
                <template #selection="{ item }">
                  <div class="d-flex align-center gap-1">
                    <VIcon v-if="item.raw.icon" :icon="item.raw.icon" size="16" />
                    <span>{{ item.raw.label }}</span>
                  </div>
                </template>
                <template #item="{ item, props: itemProps }">
                  <VListItem v-bind="itemProps" :prepend-icon="item.raw.icon" :title="item.raw.label" />
                </template>
              </VSelect>
            </div>
          </VCardTitle>
          <VCardText class="pa-0" :style="{ height: isTraceSelected ? 'calc(100vh - 80px)' : 'calc(100vh - 140px)' }">
            <UniversalObservabilityDrawer
              ref="observabilityRef"
              :project-id="projectId"
              :call-type-filter="typedCallTypeFilter"
              :is-loading-playground="isLoadingInPlayground"
              @view-mode="handleViewModeChange"
              @load-in-playground="handleLoadInPlayground"
            />
          </VCardText>
        </VCard>
      </div>
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.run-history-floating-actions {
  position: relative;
}

.observability-edge-toggle {
  position: absolute;
  top: 40%;
  right: -52px;
  transform: translate(0, 0);
  z-index: 1002;
  transition: all 0.2s ease;

  &.hidden {
    opacity: 0;
    pointer-events: none;
  }

  &:hover {
    transform: translate(-36px, 0);
  }
}

.edge-vertical-tab {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  width: 140px;
  background: rgb(var(--v-theme-info));
  color: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  user-select: none;
  transition: filter 0.2s ease;
  transform: rotate(-90deg);
  transform-origin: center;

  &:hover {
    filter: brightness(1.05);
  }

  .tab-label {
    font-size: 14px;
    letter-spacing: 0.08em;
    font-weight: 700;
    text-transform: uppercase;
    white-space: nowrap;
  }
}

.playground-panel {
  position: fixed;
  top: 16px;
  right: 16px;
  bottom: 16px;
  z-index: 1000;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.playground-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.observability-panel {
  position: fixed;
  top: 16px;
  right: 16px;
  bottom: 16px;
  z-index: 1001;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.observability-card {
  height: 100%;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.observability-resize-handle {
  position: absolute;
  top: 0;
  left: -6px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 2;
}

.observability-edge-zone {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 48px;
  z-index: 1002;
}

.observability-edge-zone:hover .observability-preview {
  opacity: 1;
  transform: translateX(0);
}

.observability-edge-zone:hover .observability-edge-toggle {
  transform: translate(-36px, 0);
}

.observability-preview {
  position: absolute;
  top: 16px;
  right: 0;
  bottom: 16px;
  width: 36px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px 0 0 12px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
  opacity: 0;
  transform: translateX(100%);
  transition: all 0.2s ease;
  z-index: 1003;
  pointer-events: auto;
  cursor: pointer;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 1;
}

.slide-from-right-enter-active,
.slide-from-right-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-from-right-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-from-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.playground-content-area {
  flex: 1;
  min-height: 0;
}

.playground-card,
.observability-card {
  :deep(.v-card-text) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
}

@media (max-width: 768px) {
  .playground-panel {
    top: 8px;
    right: 8px;
    bottom: 8px;
    width: calc(100vw - 16px);
  }

  .observability-panel {
    top: 8px;
    right: 8px;
    bottom: 8px;
    width: calc(100vw - 16px);
  }

  .observability-edge-toggle {
    right: 8px;
  }
}
</style>
