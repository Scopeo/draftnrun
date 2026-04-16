<script setup lang="ts">
defineProps<{ rows?: number; cols?: number }>()
</script>

<template>
  <div class="d-flex flex-column gap-2">
    <VSkeletonLoader type="table-heading" />
    <VSkeletonLoader v-for="i in rows ?? 5" :key="i" type="table-row" />
  </div>
</template>
