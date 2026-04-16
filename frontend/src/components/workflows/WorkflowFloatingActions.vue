<script setup lang="ts">
import WorkflowPlayground from './WorkflowPlayground.vue'
import RunHistoryFloatingPanel from '@/components/shared/RunHistoryFloatingPanel.vue'
import { PANEL_SIZES } from '@/config/panelSizes'

interface Props {
  projectId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  windowsChanged: [observabilityOpen: boolean, expandedMode: boolean, widthPx?: number]
  widthChanged: [widthPx: number]
}>()

const handleWindowsChanged = (open: boolean, expanded: boolean, width?: number) => {
  emit('windowsChanged', open, expanded, width)
}

const handleWidthChanged = (width: number) => {
  emit('widthChanged', width)
}
</script>

<template>
  <RunHistoryFloatingPanel
    :project-id="props.projectId"
    :playground-component="WorkflowPlayground"
    :playground-props="{ projectId: props.projectId }"
    :default-playground-width="PANEL_SIZES.DEFAULT_WIDTH"
    :default-observability-width="PANEL_SIZES.DEFAULT_WIDTH"
    @windows-changed="handleWindowsChanged"
    @width-changed="handleWidthChanged"
  />
</template>
