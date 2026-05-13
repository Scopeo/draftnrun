import { ref } from 'vue'

/**
 * Composable for managing context menu state and positioning.
 */
export function useContextMenu() {
  const menuVisible = ref(false)
  const menuTargetId = ref<string | null>(null)
  const menuActivatorElement = ref<HTMLElement | null>(null)

  const openMenu = (event: MouseEvent, targetId: string) => {
    event.preventDefault()
    event.stopPropagation()
    menuActivatorElement.value = event.currentTarget as HTMLElement
    menuTargetId.value = targetId
    menuVisible.value = true
  }

  const closeMenu = () => {
    menuVisible.value = false
    menuActivatorElement.value = null
    menuTargetId.value = null
  }

  return {
    menuVisible,
    menuTargetId,
    menuActivatorElement,
    openMenu,
    closeMenu,
  }
}
