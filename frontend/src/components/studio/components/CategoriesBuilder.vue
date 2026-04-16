<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

interface Category {
  id: string
  name: string
  description: string
}

interface Props {
  modelValue: Record<string, string>
  readonly?: boolean
  color?: string
  label?: string
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
  color: 'primary',
  label: 'Categories',
  description: 'Define the categories you want to classify content into.',
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, string>]
}>()

const categories = ref<Category[]>([])

const isInternalUpdate = ref(false)

let _nextId = 0
const generateId = () => `cat_${_nextId++}`

const categoriesDict = computed<Record<string, string>>(() => {
  const dict: Record<string, string> = {}

  categories.value.forEach(cat => {
    if (cat.name.trim() !== '') {
      dict[cat.name] = cat.description
    }
  })
  return dict
})

const initializeFromModelValue = (value: Record<string, string> | null | undefined) => {
  if (value && typeof value === 'object' && Object.keys(value).length > 0) {
    categories.value = Object.entries(value).map(([name, description]) => ({
      id: generateId(),
      name,
      description: description || '',
    }))
  } else {
    categories.value = [{ id: generateId(), name: '', description: '' }]
  }
}

const addCategory = () => {
  categories.value.push({ id: generateId(), name: '', description: '' })
}

const removeCategory = (id: string) => {
  if (categories.value.length > 1) {
    const index = categories.value.findIndex(c => c.id === id)
    if (index !== -1) {
      categories.value.splice(index, 1)
    }
  }
}

watch(
  categoriesDict,
  newValue => {
    if (!isInternalUpdate.value) {
      isInternalUpdate.value = true
      emit('update:modelValue', newValue)
      nextTick(() => {
        isInternalUpdate.value = false
      })
    }
  },
  { deep: true }
)

watch(
  () => props.modelValue,
  (newVal, oldVal) => {
    if (isInternalUpdate.value) {
      return
    }
    initializeFromModelValue(newVal)
  },
  { immediate: true }
)
</script>

<template>
  <div>
    <VCard v-for="category in categories" :key="category.id" class="mb-3" variant="outlined">
      <VCardText>
        <div class="d-flex gap-2 align-start">
          <VTextField
            v-model="category.name"
            label="Category Name"
            variant="outlined"
            density="compact"
            hide-details
            :readonly="readonly"
            :color="color"
            placeholder="e.g., Positive"
            style="max-width: 200px"
          />
          <VTextField
            v-model="category.description"
            label="Description"
            variant="outlined"
            density="compact"
            hide-details
            :readonly="readonly"
            :color="color"
            placeholder="e.g., Content expressing positive sentiment"
            class="flex-grow-1"
          />
          <VBtn
            v-if="!readonly && categories.length > 1"
            icon="tabler-trash"
            size="small"
            variant="text"
            color="error"
            @click="removeCategory(category.id)"
          />
        </div>
      </VCardText>
    </VCard>

    <VBtn
      v-if="!readonly"
      variant="outlined"
      prepend-icon="tabler-plus"
      size="small"
      :color="color"
      @click="addCategory"
    >
      Add Category
    </VBtn>
  </div>
</template>
