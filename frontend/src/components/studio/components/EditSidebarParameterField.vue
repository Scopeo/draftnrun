<script setup lang="ts">
import { computed } from 'vue'
import { VSelect } from 'vuetify/components/VSelect'
import type { ComponentConfig, SidebarParameter } from './edit-sidebar/types'
import { isInlineLabelComponent, normalizeUiComponent } from './edit-sidebar/types'
import ParameterLabel from '@/components/shared/ParameterLabel.vue'

interface Props {
  param: SidebarParameter
  componentConfig: ComponentConfig
  color: string
  jsonValidationState?: 'valid' | 'invalid' | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'file-update': [value: unknown]
  'json-blur': []
}>()

const model = defineModel<any>()

const isInlineLabel = computed(() => isInlineLabelComponent(props.param))
const normalizedUi = computed(() => normalizeUiComponent(props.param.ui_component))
const isFileUpload = computed(() => props.param.ui_component === 'FileUpload')

const isFileUploadWithBase64 = computed(
  () => isFileUpload.value && model.value && typeof model.value === 'string' && !model.value.startsWith('data:')
)

const isLlmModel = computed(() => props.param.type === 'llm_model')
const isOutputFormat = computed(() => props.param.name === 'output_format')
const isSlider = computed(() => normalizedUi.value === 'SLIDER')

const bindProps = computed(() => ({
  ...props.componentConfig.props,
  ...(isInlineLabel.value ? {} : { label: undefined }),
}))
</script>

<template>
  <div class="parameter-item mb-4">
    <ParameterLabel
      v-if="!isInlineLabel"
      :label="componentConfig.props?.label || param.name"
      :description="param.ui_component_properties?.description || param.ui_component_properties?.placeholder"
      :required="param.nullable === false"
    />
    <div class="d-flex align-center">
      <!-- FileUpload with saved base64 string -->
      <template v-if="isFileUploadWithBase64">
        <div class="flex-grow-1">
          <VChip color="success" variant="tonal" size="small" class="mb-2">
            <VIcon icon="tabler-check" size="small" class="me-1" />
            File uploaded
          </VChip>
          <component
            :is="componentConfig.component"
            :model-value="null"
            v-bind="bindProps"
            variant="outlined"
            :color="color"
            class="mb-2"
            hide-details="auto"
            @update:model-value="emit('file-update', $event)"
          />
        </div>
      </template>

      <!-- FileUpload -->
      <component
        :is="componentConfig.component"
        v-else-if="isFileUpload"
        :model-value="model"
        v-bind="bindProps"
        variant="outlined"
        :color="color"
        class="mb-2 flex-grow-1"
        hide-details="auto"
        @update:model-value="emit('file-update', $event)"
      />

      <!-- LLM model select with credit display -->
      <VSelect
        v-else-if="isLlmModel"
        v-model="model"
        v-bind="bindProps"
        variant="outlined"
        :color="color"
        class="mb-2 flex-grow-1"
        hide-details="auto"
      >
        <template #item="{ item, props: itemProps }">
          <VListItem v-bind="itemProps" :title="item.raw.title">
            <template #subtitle>
              <span class="text-medium-emphasis text-caption">{{ item.raw.subtitle }}</span>
            </template>
          </VListItem>
        </template>
      </VSelect>

      <!-- output_format with JSON validation -->
      <div v-else-if="isOutputFormat" class="output-format-wrapper flex-grow-1" style="position: relative">
        <component
          :is="componentConfig.component"
          :key="`${param.name}-${normalizedUi}`"
          v-model="model"
          v-bind="bindProps"
          variant="outlined"
          :color="color"
          class="mb-2"
          hide-details="auto"
          @blur="emit('json-blur')"
        />
        <div v-if="jsonValidationState === 'valid'" class="json-validation-icon json-validation-icon--valid">
          <VIcon icon="tabler-check" color="white" size="13" />
        </div>
        <VTooltip v-else-if="jsonValidationState === 'invalid'" location="left">
          <template #activator="{ props: tooltipProps }">
            <div v-bind="tooltipProps" class="json-validation-icon json-validation-icon--invalid">
              <VIcon icon="tabler-x" color="white" size="13" />
            </div>
          </template>
          <span>Invalid JSON format</span>
        </VTooltip>
      </div>

      <!-- Generic component -->
      <component
        :is="componentConfig.component"
        v-else
        :key="`${param.name}-${normalizedUi}`"
        v-model="model"
        v-bind="bindProps"
        variant="outlined"
        :color="color"
        class="mb-2 flex-grow-1"
        hide-details="auto"
      />

      <!-- Slider value display -->
      <span v-if="isSlider" class="slider-value ms-3">{{ model }}</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.parameter-item {
  position: relative;
}

.slider-value {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.875rem;
  font-weight: 500;
  min-inline-size: 40px;
  text-align: end;
}

.output-format-wrapper {
  position: relative;

  > .v-tooltip,
  > .json-validation-icon {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 1;
    pointer-events: auto;
  }
}

.json-validation-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  cursor: help;
  transition: opacity 0.2s ease-in-out;
}

.json-validation-icon--valid {
  background-color: rgb(var(--v-theme-success));
}

.json-validation-icon--invalid {
  background-color: rgb(var(--v-theme-error));
}

:deep(.v-overlay.v-tooltip .v-overlay__content) {
  background: rgba(var(--v-theme-surface-variant), 0.95) !important;
  color: rgb(var(--v-theme-on-surface-variant)) !important;
  font-size: 0.75rem;
  padding: 4px 8px;
}
</style>
