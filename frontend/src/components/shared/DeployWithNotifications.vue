<script setup lang="ts">
import { ref } from 'vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { useNotifications } from '@/composables/useNotifications'

interface Props {
  successMessage?: string
  onDeploy?: () => Promise<void>
}

const props = withDefaults(defineProps<Props>(), {
  successMessage: 'Deployment successful! The production environment has been updated.',
})

const { notify } = useNotifications()
const isDeployDialogVisible = ref(false)

const triggerDeploy = () => {
  isDeployDialogVisible.value = true
}

const handleDeployConfirm = async () => {
  isDeployDialogVisible.value = false

  try {
    if (props.onDeploy) {
      await props.onDeploy()
    }
    notify.success(props.successMessage)
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to deploy. Please try again.'

    notify.error(message)
  }
}

const handleDeployCancel = () => {
  isDeployDialogVisible.value = false
}

const showError = (message: string) => {
  notify.error(message)
}

defineExpose({
  triggerDeploy,
  showError,
})
</script>

<template>
  <GenericConfirmDialog
    :is-dialog-visible="isDeployDialogVisible"
    title="Deploy to Production"
    message="Are you sure you want to deploy this draft version to production?"
    confirm-text="Deploy"
    confirm-color="error"
    @update:is-dialog-visible="isDeployDialogVisible = $event"
    @confirm="handleDeployConfirm"
    @cancel="handleDeployCancel"
  />
</template>
