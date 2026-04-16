<script lang="ts" setup>
import { useRoute } from 'vue-router'

const route = useRoute()
const isFallbackStateActive = ref(false)
const refLoadingIndicator = ref<any>(null)

watch(
  [isFallbackStateActive, refLoadingIndicator],
  () => {
    if (isFallbackStateActive.value && refLoadingIndicator.value) refLoadingIndicator.value.fallbackHandle()
    if (!isFallbackStateActive.value && refLoadingIndicator.value) refLoadingIndicator.value.resolveHandle()
  },
  { immediate: true }
)
</script>

<template>
  <AppLoadingIndicator ref="refLoadingIndicator" />

  <div class="layout-wrapper layout-blank" data-allow-mismatch>
    <RouterView #="{ Component }">
      <div :key="route.path">
        <Suspense :timeout="0" @fallback="isFallbackStateActive = true" @resolve="isFallbackStateActive = false">
          <Component :is="Component" />
          <template #fallback>
            <div class="d-flex justify-center align-center" style="min-block-size: 200px">
              <VProgressCircular indeterminate color="primary" />
            </div>
          </template>
        </Suspense>
      </div>
    </RouterView>
  </div>
</template>

<style>
.layout-wrapper.layout-blank {
  flex-direction: column;
}
</style>
