import { type Ref, ref } from 'vue'

export interface UseStudioBreadcrumbsOptions {
  activeComponentId: Ref<string | null>
  setActiveComponent: (id: string | null) => void
  getNodeName: (id: string) => string
  getNodeType: (id: string) => string
  getActiveName: () => string
}

export function useStudioBreadcrumbs(options: UseStudioBreadcrumbsOptions) {
  const { activeComponentId, setActiveComponent, getNodeName, getNodeType, getActiveName } = options

  const breadcrumbs = ref<string[]>([])
  const zoomHistory = ref<Array<{ id: string; name: string; type: string }>>([])

  function navigateToNode(nodeId: string) {
    setActiveComponent(nodeId)
    zoomHistory.value.push({
      id: nodeId,
      name: getNodeName(nodeId),
      type: getNodeType(nodeId),
    })
    breadcrumbs.value.push(getActiveName())
  }

  function handleBreadcrumbClick(index: number) {
    if (index < 0 || index >= zoomHistory.value.length) return

    const targetHistoryItem = zoomHistory.value[index]

    zoomHistory.value = zoomHistory.value.slice(0, index + 1)
    breadcrumbs.value = breadcrumbs.value.slice(0, index + 1)
    setActiveComponent(targetHistoryItem.id)
  }

  function goToOverviewAndClearHistory() {
    zoomHistory.value = []
    breadcrumbs.value = []
    setActiveComponent(null)
  }

  function resetView() {
    if (zoomHistory.value.length === 0) return

    zoomHistory.value.pop()
    breadcrumbs.value.pop()

    if (zoomHistory.value.length === 0) {
      setActiveComponent(null)
    } else {
      const previousZoom = zoomHistory.value[zoomHistory.value.length - 1]

      setActiveComponent(previousZoom.id)
    }
  }

  function resetState() {
    zoomHistory.value = []
    breadcrumbs.value = []
  }

  return {
    breadcrumbs,
    zoomHistory,
    navigateToNode,
    handleBreadcrumbClick,
    goToOverviewAndClearHistory,
    resetView,
    resetState,
  }
}
