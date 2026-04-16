<script lang="ts" setup>
interface CustomInputContent {
  title: string
  desc?: string
  value: string
  subtitle?: string
  icon?: string | object
  images?: string
}

interface GridColumn {
  cols?: string
  sm?: string
  md?: string
  lg?: string
  xl?: string
  xxl?: string
}

interface Props {
  selectedRadio: string
  radioContent: CustomInputContent[]
  gridColumn?: GridColumn
}

interface Emit {
  (e: 'update:selectedRadio', value: string): void
}

const props = defineProps<Props>()

const emit = defineEmits<Emit>()

const updateSelectedOption = (value: string | null) => {
  if (value !== null) emit('update:selectedRadio', value)
}
</script>

<template>
  <VRadioGroup
    v-if="props.radioContent"
    :model-value="props.selectedRadio"
    class="custom-input-wrapper"
    @update:model-value="updateSelectedOption"
  >
    <VRow>
      <VCol v-for="item in props.radioContent" :key="item.title" v-bind="gridColumn">
        <VLabel
          class="custom-input custom-radio-icon rounded cursor-pointer"
          :class="props.selectedRadio === item.value ? 'active' : ''"
        >
          <slot :item="item">
            <div class="d-flex flex-column align-center text-center gap-2">
              <VIcon v-if="typeof item.icon === 'string'" :icon="item.icon" class="text-high-emphasis" />
              <VIcon
                v-else-if="item.icon && typeof item.icon === 'object'"
                v-bind="item.icon"
                class="text-high-emphasis"
              />
              <h6 class="text-h6">
                {{ item.title }}
              </h6>

              <p class="text-body-2 mb-0">
                {{ item.desc }}
              </p>
            </div>
          </slot>

          <div>
            <VRadio :value="item.value" />
          </div>
        </VLabel>
      </VCol>
    </VRow>
  </VRadioGroup>
</template>

<style lang="scss" scoped>
.custom-radio-icon {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  .v-radio {
    margin-block-end: -0.5rem;
  }
}
</style>

<style lang="scss">
.custom-radio-icon {
  .v-radio {
    margin-block-end: -0.25rem;

    .v-selection-control__wrapper {
      margin-inline-start: 0;
    }
  }
}
</style>
