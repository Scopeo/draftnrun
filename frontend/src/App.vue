<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { useOnline } from '@vueuse/core'
import { hexToRgb } from '@/utils/colorConverter'
import { useConfigStore } from '@/stores/config'
import { logger } from '@/utils/logger'

const { global } = useTheme()
const configStore = useConfigStore()
const router = useRouter()
const isOnline = useOnline()
const showAccessDenied = ref(false)
const accessDeniedMessage = ref('You do not have access to this organization')

function consumeAccessDeniedFlag() {
  try {
    const deniedData = sessionStorage.getItem('org_access_denied')
    if (!deniedData) return

    const parsed = JSON.parse(deniedData)

    accessDeniedMessage.value = parsed?.message || 'You do not have access to this organization'
    showAccessDenied.value = true
    sessionStorage.removeItem('org_access_denied')
  } catch (error) {
    logger.warn('Failed to parse org_access_denied flag', { error: String(error) })
    sessionStorage.removeItem('org_access_denied')
  }
}

let removeAfterEachHook: (() => void) | undefined

onMounted(() => {
  consumeAccessDeniedFlag()
  removeAfterEachHook = router.afterEach(() => {
    consumeAccessDeniedFlag()
  })
})

onUnmounted(() => {
  removeAfterEachHook?.()
})

watch(
  () => configStore.resolvedTheme,
  themeName => {
    global.name.value = themeName
  },
  { immediate: true }
)
</script>

<template>
  <VApp :style="`--v-global-theme-primary: ${hexToRgb(global.current.value.colors.primary)}`">
    <VBanner v-if="!isOnline" color="warning" sticky style="z-index: 9999">
      <template #prepend>
        <VIcon icon="tabler-wifi-off" />
      </template>
      You are offline. Some features may not be available.
    </VBanner>
    <RouterView />

    <VSnackbar v-model="showAccessDenied" location="top" color="warning" :timeout="5000">
      <div class="d-flex align-center gap-2">
        <VIcon icon="tabler-alert-circle" />
        <span>{{ accessDeniedMessage }}</span>
      </div>
      <template #actions>
        <VBtn variant="text" @click="showAccessDenied = false"> Close </VBtn>
      </template>
    </VSnackbar>
  </VApp>
</template>
