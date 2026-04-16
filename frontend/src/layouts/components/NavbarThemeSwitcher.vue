<script setup lang="ts">
import { computed } from 'vue'
import { useConfigStore } from '@/stores/config'

const configStore = useConfigStore()

const themeIcon = computed(() => {
  const icons: Record<string, string> = {
    light: 'tabler-sun-high',
    dark: 'tabler-moon-stars',
    system: 'tabler-device-desktop-analytics',
  }

  return icons[configStore.theme]
})
</script>

<template>
  <IconBtn @click="configStore.toggleTheme()">
    <VIcon :icon="themeIcon" />
    <VTooltip activator="parent" location="bottom"> {{ configStore.theme }} mode </VTooltip>
  </IconBtn>
</template>
