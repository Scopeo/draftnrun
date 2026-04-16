<script setup lang="ts">
import PortConfigurationEditor from './PortConfigurationEditor.vue'

interface Props {
  toolDescriptionName: string
  toolDescriptionDescription: string
  color: string
  isReadOnlyMode: boolean
  componentDefinition: any
  componentDataId: string | null
  portConfigurations: any[]
  upstreamNodes: any[]
}

defineProps<Props>()

const emit = defineEmits<{ 'update:portConfigurations': [configs: any[]] }>()
const nameModel = defineModel<string>('toolDescriptionName')
const descModel = defineModel<string>('toolDescriptionDescription')
</script>

<template>
  <div class="text-h6 mb-4">Instructions for AI Agent</div>
  <VAlert type="info" variant="tonal" density="comfortable" class="mb-4">
    A tool description explains what a tool does, how it should be used, and in which situations an AI agent should call
    it. It helps the agent choose the right tool and interact with it correctly, reducing errors and improving
    efficiency.
  </VAlert>
  <VCard variant="outlined" class="pa-4">
    <div class="text-subtitle-1 mb-3">Tool Description</div>
    <VTextField
      v-model="nameModel"
      label="Tool Name"
      variant="outlined"
      :color="color"
      :readonly="isReadOnlyMode"
      class="mb-3"
    />
    <VTextarea
      v-model="descModel"
      label="Tool Description"
      variant="outlined"
      :color="color"
      :readonly="isReadOnlyMode"
      rows="3"
      class="mb-3"
      placeholder="Describe what this tool does"
    />
    <VDivider class="my-4" />
    <PortConfigurationEditor
      v-if="componentDefinition?.parameters && componentDataId"
      :parameters="componentDefinition.parameters"
      :port-configurations="portConfigurations"
      :component-instance-id="componentDataId"
      :readonly="isReadOnlyMode"
      :upstream-nodes="upstreamNodes"
      @update:port-configurations="emit('update:portConfigurations', $event)"
    />
  </VCard>
</template>
