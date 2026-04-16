<script setup lang="ts">
import type { SubcomponentInfo } from '../data/component-definitions'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'

interface Props {
  optionalSubcomponents: SubcomponentInfo[]
  enabledOptionalTools: Record<string, boolean>
  componentDefinitions: any[]
  color: string
  isReadOnlyMode: boolean
}

defineProps<Props>()

const emit = defineEmits<{ toggle: [toolId: string, enabled: boolean] }>()
</script>

<template>
  <div v-if="optionalSubcomponents.length > 0" class="mt-6">
    <div class="text-h6 mb-4">Optional Tools</div>
    <VCard variant="outlined" class="pa-4">
      <div
        v-for="tool in optionalSubcomponents"
        :key="tool.component_version_id"
        class="d-flex align-center justify-space-between mb-4"
      >
        <div>
          <div class="text-subtitle-1">{{ tool.parameter_name }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ getComponentDefinitionFromCache(componentDefinitions, tool.component_version_id)?.description || '' }}
          </div>
        </div>
        <VSwitch
          :model-value="enabledOptionalTools[tool.component_version_id]"
          :color="color"
          :disabled="isReadOnlyMode"
          hide-details
          @update:model-value="emit('toggle', tool.component_version_id, $event || false)"
        />
      </div>
    </VCard>
  </div>
</template>
