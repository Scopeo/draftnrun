<script setup lang="ts">
import { useNotifications } from '@/composables/useNotifications'

interface Props {
  successMessage?: string
  onSaveVersion?: () => Promise<void> | void
}

const props = withDefaults(defineProps<Props>(), {
  successMessage: 'Version saved successfully! A new tagged version has been created.',
})

const { notify } = useNotifications()

const handleSaveVersion = async () => {
  try {
    if (props.onSaveVersion) {
      await props.onSaveVersion()
    }
    notify.success(props.successMessage)
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to save version. Please try again.'

    notify.error(message)
  }
}

defineExpose({
  triggerSaveVersion: handleSaveVersion,
})
</script>

<template>
  <span />
</template>
