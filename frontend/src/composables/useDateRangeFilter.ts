import { parseISO } from 'date-fns'
import { computed, ref } from 'vue'

export const CUSTOM_RANGE_VALUE = -1

export const DATE_RANGES = [
  { title: 'Last 24 hours', value: 1 },
  { title: 'Last 7 days', value: 7 },
  { title: 'Last 30 days', value: 30 },
  { title: 'Last 90 days', value: 90 },
  { title: 'Custom range', value: CUSTOM_RANGE_VALUE },
] as const

export function toISOWithTimezone(localDatetime: string): string {
  return parseISO(localDatetime).toISOString()
}

export function formatDuration(start: string, end: string): string {
  const startTime = parseISO(start).getTime()
  const endTime = parseISO(end).getTime()
  return ((endTime - startTime) / 1000).toFixed(2)
}

export function useDateRangeFilter(defaultRange = 90) {
  const selectedRange = ref(defaultRange)
  const customStartDate = ref('')
  const customEndDate = ref('')

  const isCustomRange = computed(() => selectedRange.value === CUSTOM_RANGE_VALUE)

  const dateRangeParams = computed(() => {
    if (isCustomRange.value && (customStartDate.value || customEndDate.value)) {
      return {
        start_time: customStartDate.value ? toISOWithTimezone(customStartDate.value) : undefined,
        end_time: customEndDate.value ? toISOWithTimezone(customEndDate.value) : undefined,
      }
    }

    return {
      duration: selectedRange.value === CUSTOM_RANGE_VALUE ? 90 : selectedRange.value,
    }
  })

  return {
    selectedRange,
    customStartDate,
    customEndDate,
    isCustomRange,
    dateRangeParams,
  }
}
