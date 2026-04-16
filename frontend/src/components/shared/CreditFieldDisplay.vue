<script setup lang="ts">
interface Props {
  value: number | Record<string, number> | null | undefined
}

const props = defineProps<Props>()

const displayValue = computed(() => {
  if (props.value === null || props.value === undefined) {
    return null
  }

  if (typeof props.value === 'number') {
    return formatNumberWithSpaces(props.value)
  }

  if (typeof props.value === 'object') {
    // Handle dict/object
    const entries = Object.entries(props.value)
    if (entries.length === 0) {
      return null
    }
    return entries.map(([key, val]) => `${key}: ${formatNumberWithSpaces(val)}`).join(', ')
  }

  return null
})
</script>

<template>
  <span v-if="displayValue !== null">
    {{ displayValue }}
  </span>
  <span v-else class="text-grey">—</span>
</template>
