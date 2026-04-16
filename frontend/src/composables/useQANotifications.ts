import { ref } from 'vue'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

interface Notification {
  type: NotificationType
  message: string
  timeout?: number
}

/**
 * Composable for managing QA-related snackbar notifications
 * Provides a centralized way to show success, error, warning, and info messages
 */
export function useQANotifications() {
  const showSnackbar = ref(false)
  const snackbarType = ref<NotificationType>('info')
  const snackbarMessage = ref('')
  const snackbarTimeout = ref(3000)

  const showNotification = (notification: Notification) => {
    snackbarType.value = notification.type
    snackbarMessage.value = notification.message
    snackbarTimeout.value = notification.timeout ?? (notification.type === 'error' ? 5000 : 3000)
    showSnackbar.value = true
  }

  const showSuccess = (message: string, timeout?: number) => {
    showNotification({ type: 'success', message, timeout })
  }

  const showError = (message: string, timeout?: number) => {
    showNotification({ type: 'error', message, timeout })
  }

  const showWarning = (message: string, timeout?: number) => {
    showNotification({ type: 'warning', message, timeout })
  }

  const showInfo = (message: string, timeout?: number) => {
    showNotification({ type: 'info', message, timeout })
  }

  const closeSnackbar = () => {
    showSnackbar.value = false
  }

  return {
    showSnackbar,
    snackbarType,
    snackbarMessage,
    snackbarTimeout,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    closeSnackbar,
  }
}
