<template>
  <div class="d-flex flex-column gap-4 pa-4">
    <VSkeletonLoader type="heading" />
    <div class="d-flex gap-4 flex-wrap">
      <VSkeletonLoader v-for="i in 6" :key="i" type="card" width="300" height="200" />
    </div>
  </div>
</template>
