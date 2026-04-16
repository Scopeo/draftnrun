import { type Ref, onMounted, onUnmounted, ref, watch } from 'vue'

/**
 * Detects whether a text element is truncated (e.g. via line-clamp / text-overflow).
 * Returns a reactive boolean so the caller can conditionally show a tooltip.
 */
export function useTextTruncated(elRef: Ref<HTMLElement | null>) {
  const isTruncated = ref(false)

  const check = () => {
    const el = elRef.value
    if (!el) {
      isTruncated.value = false
      return
    }
    isTruncated.value = el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth
  }

  let observer: ResizeObserver | null = null

  const setup = () => {
    if (!elRef.value) return
    check()
    observer = new ResizeObserver(check)
    observer.observe(elRef.value)
  }

  onMounted(setup)
  watch(elRef, () => {
    observer?.disconnect()
    setup()
  })
  onUnmounted(() => observer?.disconnect())

  return { isTruncated }
}
