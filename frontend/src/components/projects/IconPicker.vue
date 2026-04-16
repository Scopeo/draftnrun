<script setup lang="ts">
import { computed } from 'vue'
import { AVATAR_COLORS, OBJECT_ICONS } from '@/utils/randomNameGenerator'

interface IconSelection {
  icon: string
  iconColor: string
}

interface Props {
  modelValue: IconSelection
}

interface Emits {
  (e: 'update:modelValue', value: IconSelection): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Get unique icons from the object mapping
const availableIcons = computed(() => {
  const iconSet = new Set(Object.values(OBJECT_ICONS))
  return Array.from(iconSet)
})

const selectedIcon = computed({
  get: () => props.modelValue.icon,
  set: (value: string) => {
    emit('update:modelValue', { ...props.modelValue, icon: value })
  },
})

const selectedColor = computed({
  get: () => props.modelValue.iconColor,
  set: (value: string) => {
    emit('update:modelValue', { ...props.modelValue, iconColor: value })
  },
})

function selectIcon(icon: string) {
  selectedIcon.value = icon
}

function selectColor(color: string) {
  selectedColor.value = color
}
</script>

<template>
  <div class="icon-picker">
    <!-- Preview Section -->
    <VCard class="mb-4">
      <VCardText class="d-flex align-center gap-4">
        <div class="preview-avatar" :style="{ backgroundColor: 'rgb(var(--v-theme-surface))' }">
          <VIcon :icon="selectedIcon" size="40" :color="selectedColor" />
        </div>
        <div>
          <div class="text-subtitle-2 text-medium-emphasis mb-1">Preview</div>
          <div class="text-caption text-disabled">{{ selectedIcon }}</div>
        </div>
      </VCardText>
    </VCard>

    <!-- Icon Selection -->
    <div class="mb-4">
      <div class="text-subtitle-2 mb-2">Select Icon</div>
      <div class="icon-grid">
        <VBtn
          v-for="icon in availableIcons"
          :key="icon"
          :variant="selectedIcon === icon ? 'elevated' : 'flat'"
          :class="{ 'selected-icon': selectedIcon === icon }"
          size="large"
          class="icon-option"
          @click="selectIcon(icon)"
        >
          <VIcon :icon="icon" size="26" :color="selectedColor || AVATAR_COLORS[0]" />
        </VBtn>
      </div>
    </div>

    <!-- Color Selection -->
    <div>
      <div class="text-subtitle-2 mb-2">Select Color</div>
      <div class="color-grid">
        <VBtn
          v-for="color in AVATAR_COLORS"
          :key="color"
          :variant="selectedColor === color ? 'elevated' : 'flat'"
          size="large"
          class="color-option"
          :class="{ selected: selectedColor === color }"
          :style="{ '--swatch-color': color }"
          @click="selectColor(color)"
        >
          <VIcon v-if="selectedColor === color" icon="tabler-check" color="white" size="20" />
        </VBtn>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.icon-picker {
  inline-size: 100%;
}

.preview-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: 72px;
  block-size: 72px;
  border-radius: 50%;
  flex-shrink: 0;
  margin: 2px;
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.12),
    0 1px 2px rgba(0, 0, 0, 0.08);
}

.icon-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
}

.icon-option {
  aspect-ratio: 1;
  min-inline-size: 56px;
  padding: 0 !important;
  background-color: rgb(var(--v-theme-surface)) !important;
  border: 1px solid rgba(0, 0, 0, 0.12);

  &.selected-icon {
    border: 2px solid rgb(var(--v-theme-primary));
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
}

.color-grid {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fill, minmax(48px, 1fr));
}

.color-option {
  aspect-ratio: 1;
  min-inline-size: 48px;
  padding: 0 !important;
  border: 2px solid transparent;
  transition: all 0.2s ease;
  background-color: var(--swatch-color) !important;

  &.selected {
    border-color: rgba(255, 255, 255, 0.5);
  }

  &:hover {
    transform: scale(1.1);
  }
}
</style>
