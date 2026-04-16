import { nextTick, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { v4 as uuidv4 } from 'uuid'
import { omit } from 'lodash-es'

/**
 * Options for useCollectionWithIds composable
 */
export interface UseCollectionWithIdsOptions<T> {
  /** Reactive reference to the model value */
  modelValue: Ref<T[] | undefined>
  /** Function to create a default item */
  createDefault: () => T
  /** Callback when items change */
  onChange?: (items: T[]) => void
}

/**
 * Composable for managing collections with internal IDs for Vue keys
 *
 * This composable solves the problem of managing arrays where:
 * - Items need stable IDs for Vue's :key binding
 * - Parent component doesn't include IDs
 * - Need to emit changes without IDs
 *
 * Used by RouterConfigBuilder and ConditionBuilder to manage routes/conditions.
 *
 * @example
 * ```ts
 * const { items, add, remove, update } = useCollectionWithIds({
 *   modelValue: toRef(props, 'modelValue'),
 *   createDefault: () => ({ value_a: '', operator: 'equals', value_b: '' }),
 *   onChange: (items) => emit('update:modelValue', items)
 * })
 * ```
 */
export function useCollectionWithIds<T extends Record<string, any>>(options: UseCollectionWithIdsOptions<T>) {
  type ItemWithId = T & { _id: string }

  const localItems = ref<ItemWithId[]>([]) as Ref<ItemWithId[]>
  const isUpdatingFromParent = ref(false)

  /**
   * Watch for external changes from parent component
   */
  watch(
    () => options.modelValue.value,
    newValue => {
      // Skip update if we're currently emitting changes to parent
      if (isUpdatingFromParent.value) return

      if (!newValue || newValue.length === 0) {
        // Clear items if new value is empty
        if (localItems.value.length > 0) {
          localItems.value = []
        }
        return
      }

      // Map new items to items with IDs, trying to preserve existing IDs where possible
      const newItemsWithIds = newValue.map(item => {
        // Try to find matching existing item by comparing content (excluding _id)
        const existing = localItems.value.find(local => JSON.stringify(omit(local, '_id')) === JSON.stringify(item))

        // Use existing item's ID if found, otherwise create new ID
        return existing || ({ ...item, _id: uuidv4() } as ItemWithId)
      })

      localItems.value = newItemsWithIds
    },
    { immediate: true, deep: true }
  )

  /**
   * Add a new item to the collection
   *
   * @param item - Optional item to add (uses createDefault if not provided)
   */
  const add = (item?: T) => {
    localItems.value.push({
      ...(item || options.createDefault()),
      _id: uuidv4(),
    } as ItemWithId)
    emitChanges()
  }

  /**
   * Remove an item by its internal ID
   *
   * @param id - Internal _id of the item to remove
   */
  const remove = (id: string) => {
    localItems.value = localItems.value.filter(item => item._id !== id)
    emitChanges()
  }

  /**
   * Update a specific field of an item
   *
   * @param id - Internal _id of the item to update
   * @param field - Field name to update
   * @param value - New value for the field
   */
  const update = <K extends keyof T>(id: string, field: K, value: T[K]) => {
    const item = localItems.value.find(item => item._id === id)
    if (item) {
      ;(item as T)[field] = value
      emitChanges()
    }
  }

  /**
   * Emit changes to parent component (strips internal _id)
   */
  const emitChanges = () => {
    isUpdatingFromParent.value = true

    // Remove internal _id before emitting
    const itemsWithoutIds = localItems.value.map(item => omit(item, '_id') as unknown as T)

    options.onChange?.(itemsWithoutIds)

    // Reset flag after a tick to allow external updates
    nextTick(() => {
      isUpdatingFromParent.value = false
    })
  }

  return {
    /** Reactive array of items with internal IDs */
    items: localItems,
    /** Add a new item */
    add,
    /** Remove an item by ID */
    remove,
    /** Update an item field */
    update,
  }
}
