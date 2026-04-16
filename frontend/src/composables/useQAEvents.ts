import { onUnmounted } from 'vue'

export interface QAJudgesUpdatedEvent {
  projectId: string
}

export interface QAConversationSavedEvent {
  projectId: string
  datasetId: string
  traceId: string
}

export interface QADatasetCreatedEvent {
  projectId: string
  datasetId: string
}

type EventCallback<T> = (event: T) => void

// Simple event bus using Sets
const createEventBus = <T>() => {
  const listeners = new Set<EventCallback<T>>()
  return {
    emit: (event: T) => listeners.forEach(listener => listener(event)),
    on: (callback: EventCallback<T>) => {
      listeners.add(callback)
      return () => listeners.delete(callback)
    },
  }
}

const judgesBus = createEventBus<QAJudgesUpdatedEvent>()
const conversationBus = createEventBus<QAConversationSavedEvent>()
const datasetBus = createEventBus<QADatasetCreatedEvent>()

/**
 * Composable for QA-related events
 * Replaces window.dispatchEvent with Vue-compatible event system
 */
export function useQAEvents() {
  return {
    emitJudgesUpdated: judgesBus.emit,
    emitConversationSaved: conversationBus.emit,
    emitDatasetCreated: datasetBus.emit,
    onJudgesUpdated: judgesBus.on,
    onConversationSaved: conversationBus.on,
    onDatasetCreated: datasetBus.on,
  }
}

/**
 * Helper composable that automatically cleans up listeners on unmount
 */
export function useQAEventsListener() {
  const { onJudgesUpdated, onConversationSaved, onDatasetCreated } = useQAEvents()

  const setupListeners = (
    judgesUpdatedCallback?: EventCallback<QAJudgesUpdatedEvent>,
    conversationSavedCallback?: EventCallback<QAConversationSavedEvent>,
    datasetCreatedCallback?: EventCallback<QADatasetCreatedEvent>
  ) => {
    const cleanupFunctions: Array<() => void> = []

    if (judgesUpdatedCallback) cleanupFunctions.push(onJudgesUpdated(judgesUpdatedCallback))
    if (conversationSavedCallback) cleanupFunctions.push(onConversationSaved(conversationSavedCallback))
    if (datasetCreatedCallback) cleanupFunctions.push(onDatasetCreated(datasetCreatedCallback))

    onUnmounted(() => cleanupFunctions.forEach(cleanup => cleanup()))

    return () => cleanupFunctions.forEach(cleanup => cleanup())
  }

  return { setupListeners }
}
