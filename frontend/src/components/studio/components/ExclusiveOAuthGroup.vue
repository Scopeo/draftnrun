<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, ref, watch } from 'vue'
import { VDivider } from 'vuetify/components/VDivider'
import { VLabel } from 'vuetify/components/VLabel'
import OAuthConnectionInput from '@/components/studio/inputs/OAuthConnectionInput.vue'
import type { SidebarParameter } from './edit-sidebar/types'

interface Props {
  parameters: SidebarParameter[]
  formData: Record<string, any>
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
})

const initialSelected = (): string | null => {
  const connected = props.parameters.find(p => props.formData[p.name])
  return connected?.name ?? props.parameters[0]?.name ?? null
}

const selectedParamName = ref<string | null>(initialSelected())

watch(
  () => props.parameters.map(p => props.formData[p.name]),
  () => {
    const connected = props.parameters.find(p => props.formData[p.name])
    if (connected) selectedParamName.value = connected.name
  }
)

const selectedParam = computed(() => props.parameters.find(p => p.name === selectedParamName.value) ?? null)

const handleProviderChange = (paramName: string | null) => {
  if (!paramName) return
  if (selectedParamName.value && selectedParamName.value !== paramName) {
    props.formData[selectedParamName.value] = null
  }
  selectedParamName.value = paramName
}

const handleConnectionUpdate = (value: string | null) => {
  if (selectedParamName.value) {
    props.formData[selectedParamName.value] = value
  }
}
</script>

<template>
  <div class="exclusive-oauth-group">
    <VRadioGroup
      :model-value="selectedParamName"
      hide-details
      :disabled="readonly"
      @update:model-value="handleProviderChange"
    >
      <VLabel
        v-for="param in parameters"
        :key="param.name"
        class="provider-radio-option rounded mb-2 pa-3 d-flex align-center"
        :class="{ active: selectedParamName === param.name }"
      >
        <Icon
          :icon="param.ui_component_properties?.icon || 'mdi-connection'"
          width="24"
          height="24"
          class="me-3 flex-shrink-0"
        />
        <div class="flex-grow-1">
          <div class="text-subtitle-2">{{ param.ui_component_properties?.label }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ formData[param.name] ? 'Connection selected' : 'No connection selected' }}
          </div>
        </div>
        <VRadio :value="param.name" hide-details />
      </VLabel>
    </VRadioGroup>

    <VDivider class="my-3" />

    <div v-if="selectedParam">
      <div class="text-overline text-medium-emphasis mb-2">
        {{ selectedParam.ui_component_properties?.label }} — OAuth Connection
      </div>
      <OAuthConnectionInput
        :model-value="formData[selectedParam.name]"
        :provider="selectedParam.ui_component_properties?.provider || 'unknown'"
        :icon="selectedParam.ui_component_properties?.icon"
        :label="selectedParam.ui_component_properties?.label || selectedParam.name"
        :description="selectedParam.ui_component_properties?.description"
        :readonly="readonly"
        @update:model-value="handleConnectionUpdate"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.exclusive-oauth-group {
  width: 100%;
}

.provider-radio-option {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
  transition: border-color 0.15s ease;
  user-select: none;

  &.active {
    border-color: rgb(var(--v-theme-primary));
    background-color: rgba(var(--v-theme-primary), 0.04);
  }

  &:not(.active):hover {
    background-color: rgba(var(--v-theme-on-surface), 0.04);
  }
}
</style>
