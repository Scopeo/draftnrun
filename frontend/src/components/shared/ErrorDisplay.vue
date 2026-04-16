<script setup lang="ts">
import { computed, ref } from 'vue'
import ErrorDetailModal from './ErrorDetailModal.vue'

interface Props {
  errors: string | string[] | null | undefined
}

const props = defineProps<Props>()

const showModal = ref(false)

// Parse errors into array format
const parsedErrors = computed<string[]>(() => {
  if (!props.errors) return []
  if (Array.isArray(props.errors)) return props.errors.filter(e => e.trim())
  // Split by newlines for potential nested errors in string format
  return props.errors.split('\n').filter(e => e.trim())
})

// Check if there are multiple errors
const hasMultipleErrors = computed(() => parsedErrors.value.length > 1)

const openModal = () => {
  showModal.value = true
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    openModal()
  }
}
</script>

<template>
  <div
    v-if="parsedErrors.length > 0"
    class="error-display"
    role="button"
    tabindex="0"
    aria-label="View error details"
    @click="openModal"
    @keydown="handleKeydown"
  >
    <VIcon icon="tabler-alert-triangle" color="warning" size="16" class="error-icon" />
    <span class="error-label">Issue detected</span>
    <VBadge v-if="hasMultipleErrors" :content="parsedErrors.length" color="warning" inline class="error-count" />
    <VIcon icon="tabler-chevron-right" size="14" class="expand-icon" />
    <VTooltip activator="parent" location="bottom">See details</VTooltip>
  </div>

  <ErrorDetailModal v-model="showModal" :errors="parsedErrors" title="Issue Details" />
</template>

<style lang="scss" scoped>
.error-display {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background-color: rgba(var(--v-theme-warning), 0.12);
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: rgba(var(--v-theme-warning), 0.2);
  }
}

.error-icon {
  flex-shrink: 0;
}

.error-label {
  font-size: 12px;
  color: rgb(var(--v-theme-warning));
  font-weight: 500;
}

.error-count {
  flex-shrink: 0;
}

.expand-icon {
  flex-shrink: 0;
  opacity: 0.6;
  color: rgb(var(--v-theme-warning));
}
</style>
