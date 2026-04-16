<script setup lang="ts">
import AppPageHeader from './AppPageHeader.vue'

defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <AppPageHeader :title="title" :description="description">
    <template v-if="$slots.title" #title><slot name="title" /></template>
    <template v-if="$slots.badge" #badge><slot name="badge" /></template>
    <template v-if="$slots.actions" #actions><slot name="actions" /></template>
    <template v-if="$slots.description" #description><slot name="description" /></template>
  </AppPageHeader>
</template>
