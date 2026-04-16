import hljs from 'highlight.js/lib/core'
import type { DirectiveBinding, ObjectDirective } from 'vue'
import { nextTick } from 'vue'

// Ensure languages are registered globally or passed via binding if needed
// For simplicity here, assume they are registered where the directive is used or globally.

const highlightDirective: ObjectDirective<HTMLElement> = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    highlightElement(el, binding)
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    // Only re-highlight if the code content actually changed
    if (binding.value !== binding.oldValue) {
      highlightElement(el, binding)
    }
  },
}

async function highlightElement(el: HTMLElement, binding: DirectiveBinding) {
  // Set the raw code content
  el.innerHTML = binding.value || ''

  // Wait for Vue to update the DOM with the new innerHTML
  await nextTick()

  // Now apply highlighting to the updated element
  hljs.highlightElement(el)

  // Modifiers can still be applied if needed
  Object.keys(binding.modifiers).forEach(modifier => {
    // Check if class already exists to avoid duplicates if updated hook runs multiple times rapidly
    if (!el.classList.contains(`language-${modifier}`)) {
      el.classList.add(`language-${modifier}`)
    }
  })
}

export default highlightDirective
