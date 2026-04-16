export interface FloatingPopup {
  show(): void
  hide(): void
  destroy(): void
  updatePosition(getReferenceClientRect: () => DOMRect | null): void
}

/**
 * Lightweight replacement for tippy.js when used as a floating popup positioner
 * (e.g. TipTap suggestion dropdowns). Appends content to document.body and
 * positions it below the reference rect (bottom-start placement).
 */
export function createFloatingPopup(
  content: HTMLElement,
  getReferenceClientRect?: (() => DOMRect | null) | null
): FloatingPopup {
  const wrapper = document.createElement('div')

  wrapper.style.cssText = 'position:fixed;z-index:9999;'
  wrapper.appendChild(content)
  document.body.appendChild(wrapper)

  function updatePosition(getRect: () => DOMRect | null) {
    const rect = getRect()
    if (!rect) return
    wrapper.style.left = `${rect.left}px`
    wrapper.style.top = `${rect.bottom}px`
  }

  if (getReferenceClientRect) {
    updatePosition(getReferenceClientRect)
  }

  return {
    show() {
      wrapper.style.display = ''
    },
    hide() {
      wrapper.style.display = 'none'
    },
    destroy() {
      wrapper.remove()
    },
    updatePosition,
  }
}
