<script lang="ts" setup>
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import AppNotifications from '@/components/shared/AppNotifications.vue'

const route = useRoute()
const isFallbackStateActive = ref(false)
const refLoadingIndicator = ref<any>(null)
const loadError = ref(false)

watch(
  [isFallbackStateActive, refLoadingIndicator],
  () => {
    if (isFallbackStateActive.value && refLoadingIndicator.value) refLoadingIndicator.value.fallbackHandle()
    if (!isFallbackStateActive.value && refLoadingIndicator.value) refLoadingIndicator.value.resolveHandle()
  },
  { immediate: true }
)

watch(
  () => route.path,
  () => {
    loadError.value = false
  }
)

onErrorCaptured((err: Error) => {
  if (
    err.message?.includes('Failed to fetch dynamically imported module') ||
    /Loading chunk .* failed/.test(err.message ?? '')
  ) {
    loadError.value = true
    return false
  }
})
</script>

<template>
  <VLayout class="default-layout-shell">
    <AppSidebar />

    <VMain>
      <AppLoadingIndicator ref="refLoadingIndicator" />

      <div class="layout-page-content">
        <div v-if="loadError" class="d-flex flex-column align-center justify-center" style="min-block-size: 400px">
          <VIcon icon="tabler-alert-triangle" size="48" color="warning" class="mb-4" />
          <p class="text-body-1 text-medium-emphasis mb-4">
            Failed to load this page. This usually happens after a new version is deployed.
          </p>
          <VBtn color="primary" variant="tonal" @click="$router.go(0)">Reload page</VBtn>
        </div>
        <RouterView v-else v-slot="{ Component }">
          <Transition name="page-fade" mode="out-in">
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
          </Transition>
        </RouterView>
      </div>
    </VMain>
  </VLayout>

  <AppNotifications />
</template>

<style lang="scss">
.default-layout-shell {
  min-block-size: 100vh;
}

.layout-page-content {
  padding: var(--dnr-page-padding);
}

@media (max-width: 959px) {
  .layout-page-content {
    padding: var(--dnr-page-padding-mobile);
    padding-block-start: 4.5rem;
  }
}

.page-fade-enter-active {
  transition:
    opacity 0.25s ease-out,
    transform 0.25s ease-out;
}

.page-fade-leave-active {
  transition: opacity 0.15s ease-out;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.page-fade-leave-to {
  opacity: 0;
}
</style>
