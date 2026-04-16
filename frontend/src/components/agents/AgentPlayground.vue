<script setup lang="ts">
import { ref } from 'vue'
import SharedPlayground from '@/components/shared/SharedPlayground.vue'
import type { TraceData } from '@/types/observability'

interface Props {
  agentId: string
  projectId: string
}

const props = defineProps<Props>()

const sharedPlaygroundRef = ref<InstanceType<typeof SharedPlayground> | null>(null)

defineExpose({
  loadTraceInPlayground: (traceData: TraceData) => {
    return sharedPlaygroundRef.value?.loadTraceInPlayground(traceData)
  },
})
</script>

<template>
  <!-- Agent Playground using SharedPlayground -->
  <SharedPlayground ref="sharedPlaygroundRef" :agent-id="props.agentId" :project-id="props.projectId" mode="agent" />
</template>
