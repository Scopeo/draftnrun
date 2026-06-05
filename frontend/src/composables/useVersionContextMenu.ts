import { ref } from 'vue'

/**
 * Composable for managing context menu state and positioning.
 *
 * The menu is positioned by viewport coordinates (VMenu `:target="[x, y]"`) captured from the
 * right-click event, NOT by anchoring to a DOM element. Anchoring to a list item that lives
 * inside the VSelect dropdown overlay made the menu get stuck open / unclickable once the
 * dropdown closed and that element unmounted (DRA-1310). This mirrors the working context-menu
 * pattern in KnowledgeEditor.vue.
 */
export function useContextMenu() {
  const menuVisible = ref(false)
  const menuTargetId = ref<string | null>(null)
  const menuPosition = ref<{ x: number; y: number }>({ x: 0, y: 0 })

  const openMenu = (event: MouseEvent, targetId: string) => {
    event.preventDefault()
    event.stopPropagation()
    menuPosition.value = { x: event.clientX, y: event.clientY }
    menuTargetId.value = targetId
    menuVisible.value = true
  }

  const closeMenu = () => {
    menuVisible.value = false
    menuTargetId.value = null
  }

  return {
    menuVisible,
    menuTargetId,
    menuPosition,
    openMenu,
    closeMenu,
  }
}
