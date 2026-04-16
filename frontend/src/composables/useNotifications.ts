import { readonly, ref } from 'vue'

export interface NotificationAction {
  text: string
  onClick: () => void
}

export interface NotificationOptions {
  action?: NotificationAction
  persistent?: boolean
  timeout?: number
}

export interface Notification {
  id: number
  message: string
  color: string
  timeout: number
  persistent: boolean
  action?: NotificationAction
}

const notifications = ref<Notification[]>([])
let nextId = 0

export function useNotifications() {
  const add = (message: string, color: string, options?: NotificationOptions) => {
    const id = nextId++
    const defaultTimeout = color === 'error' ? 5000 : color === 'warning' ? 4000 : 3000
    const timeout = options?.persistent ? -1 : (options?.timeout ?? defaultTimeout)

    notifications.value.push({
      id,
      message,
      color,
      timeout,
      persistent: options?.persistent ?? false,
      action: options?.action,
    })
  }

  const remove = (id: number) => {
    notifications.value = notifications.value.filter(n => n.id !== id)
  }

  return {
    notifications: readonly(notifications),
    notify: {
      success: (msg: string, options?: NotificationOptions) => add(msg, 'success', options),
      error: (msg: string, options?: NotificationOptions) => add(msg, 'error', options),
      warning: (msg: string, options?: NotificationOptions) => add(msg, 'warning', options),
      info: (msg: string, options?: NotificationOptions) => add(msg, 'info', options),
    },
    remove,
  }
}
