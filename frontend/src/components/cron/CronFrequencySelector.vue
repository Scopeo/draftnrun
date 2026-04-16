<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { type FrequencyConfig, FrequencyType } from '@/types/cron'

const props = defineProps<{
  modelValue?: FrequencyConfig
}>()

const emit = defineEmits<{
  'update:modelValue': [value: FrequencyConfig]
  cronExpression: [expr: string, description: string]
}>()

// Frequency type selection
const frequencyType = ref<FrequencyType>(props.modelValue?.type || FrequencyType.DAILY)

// Minutely settings
const minutelyInterval = ref(props.modelValue?.interval || 10)

const minutelyIntervalOptions = [
  { title: 'Every 10 minutes', value: 10 },
  { title: 'Every 15 minutes', value: 15 },
  { title: 'Every 30 minutes', value: 30 },
]

// Hourly settings
const hourlyInterval = ref(props.modelValue?.interval || 1)

const hourlyIntervalOptions = [
  { title: 'Every hour', value: 1 },
  { title: 'Every 2 hours', value: 2 },
  { title: 'Every 3 hours', value: 3 },
  { title: 'Every 6 hours', value: 6 },
  { title: 'Every 12 hours', value: 12 },
]

// Daily/Weekly/Monthly settings
const time = ref(props.modelValue?.time || '09:00')

// Weekly settings
const daysOfWeek = ref<number[]>(props.modelValue?.daysOfWeek || [1]) // Default to Monday

const weekDayOptions = [
  { label: 'Sun', value: 0 },
  { label: 'Mon', value: 1 },
  { label: 'Tue', value: 2 },
  { label: 'Wed', value: 3 },
  { label: 'Thu', value: 4 },
  { label: 'Fri', value: 5 },
  { label: 'Sat', value: 6 },
]

const toggleDay = (dayValue: number) => {
  if (daysOfWeek.value.includes(dayValue)) {
    daysOfWeek.value = daysOfWeek.value.filter(d => d !== dayValue)
  } else {
    daysOfWeek.value = [...daysOfWeek.value, dayValue]
  }
}

// Monthly settings
const dayOfMonth = ref(props.modelValue?.dayOfMonth || 1)
const daysInMonth = Array.from({ length: 31 }, (_, i) => i + 1)

// Current config
const currentConfig = computed<FrequencyConfig>(() => ({
  type: frequencyType.value,
  interval:
    frequencyType.value === FrequencyType.MINUTELY || frequencyType.value === FrequencyType.HOURLY
      ? frequencyType.value === FrequencyType.MINUTELY
        ? minutelyInterval.value
        : hourlyInterval.value
      : undefined,
  time:
    frequencyType.value !== FrequencyType.HOURLY && frequencyType.value !== FrequencyType.MINUTELY
      ? time.value
      : undefined,
  daysOfWeek: frequencyType.value === FrequencyType.WEEKLY ? daysOfWeek.value : undefined,
  dayOfMonth: frequencyType.value === FrequencyType.MONTHLY ? dayOfMonth.value : undefined,
}))

/**
 * Generate cron expression from frequency config
 * Cron format: minute hour day-of-month month day-of-week
 */
const generateCronExpression = (config: FrequencyConfig): string => {
  const [hour, minute] = (config.time || '09:00').split(':').map(Number)

  logger.info('[CronFrequencySelector] generateCronExpression called with', {
    config,
    time: config.time,
    type: config.type,
    parsedHour: hour,
    parsedMinute: minute,
  })

  let expression: string
  switch (config.type) {
    case FrequencyType.MINUTELY: {
      const interval = config.interval || 1

      // Run every N minutes
      expression = `*/${interval} * * * *`
      break
    }

    case FrequencyType.HOURLY: {
      const interval = config.interval || 1

      // Run at minute 0 of every Nth hour
      expression = `0 */${interval} * * *`
      break
    }

    case FrequencyType.DAILY:
      // Run once per day at specified time
      expression = `${minute} ${hour} * * *`
      break

    case FrequencyType.WEEKLY: {
      // Run on specified days of week at specified time
      const days = (config.daysOfWeek || [1]).sort((a, b) => a - b).join(',')

      expression = `${minute} ${hour} * * ${days}`
      break
    }

    case FrequencyType.MONTHLY:
      // Run on specified day of month at specified time
      expression = `${minute} ${hour} ${config.dayOfMonth || 1} * *`
      break

    default:
      expression = `${minute} ${hour} * * *`
  }

  logger.info('[CronFrequencySelector] Generated cron expression', {
    expression,
    length: expression.length,
    fields: expression.split(' '),
    fieldCount: expression.split(' ').length,
  })
  return expression
}

/**
 * Generate human-readable description
 */
const generateDescription = (config: FrequencyConfig): string => {
  switch (config.type) {
    case FrequencyType.MINUTELY: {
      const interval = config.interval || 1
      return interval === 1 ? 'Every minute' : `Every ${interval} minutes`
    }

    case FrequencyType.HOURLY: {
      const interval = config.interval || 1
      return interval === 1 ? 'Every hour' : `Every ${interval} hours`
    }

    case FrequencyType.DAILY:
      return `Every day at ${config.time}`

    case FrequencyType.WEEKLY: {
      const days = config.daysOfWeek || [1]
      const dayNames = days.map(d => weekDayOptions.find(opt => opt.value === d)?.label || '').join(', ')
      return `Every ${dayNames} at ${config.time}`
    }

    case FrequencyType.MONTHLY:
      return `On day ${config.dayOfMonth} of every month at ${config.time}`

    default:
      return 'Custom schedule'
  }
}

/**
 * Validate that the cron interval meets minimum requirements
 * Backend requires minimum 10 minutes between executions
 */
const validateInterval = (config: FrequencyConfig): { valid: boolean; error?: string } => {
  // For minutely intervals, check if interval is less than 10 minutes
  if (config.type === FrequencyType.MINUTELY) {
    const interval = config.interval || 1
    if (interval < 10) {
      return {
        valid: false,
        error: 'Minimum interval is 10 minutes. Please select 10 or 15 minutes for minutely schedules.',
      }
    }
  }
  return { valid: true }
}

// Computed cron expression and description
const cronExpression = computed(() => generateCronExpression(currentConfig.value))
const cronDescription = computed(() => generateDescription(currentConfig.value))
const validation = computed(() => validateInterval(currentConfig.value))

// Watch for changes and emit
watch([currentConfig, cronExpression, cronDescription], () => {
  emit('update:modelValue', currentConfig.value)
  emit('cronExpression', cronExpression.value, cronDescription.value)
})

// Emit initial values
emit('update:modelValue', currentConfig.value)
emit('cronExpression', cronExpression.value, cronDescription.value)
</script>

<template>
  <VCard flat>
    <VCardText>
      <!-- Frequency Type Selection -->
      <div class="mb-4">
        <label class="text-sm font-weight-medium mb-2 d-block">Frequency</label>
        <VRadioGroup v-model="frequencyType" inline hide-details>
          <VRadio :value="FrequencyType.MINUTELY" label="Minutely" />
          <VRadio :value="FrequencyType.HOURLY" label="Hourly" />
          <VRadio :value="FrequencyType.DAILY" label="Daily" />
          <VRadio :value="FrequencyType.WEEKLY" label="Weekly" />
          <VRadio :value="FrequencyType.MONTHLY" label="Monthly" />
        </VRadioGroup>
      </div>

      <!-- Minutely Configuration -->
      <div v-if="frequencyType === FrequencyType.MINUTELY">
        <VSelect
          v-model="minutelyInterval"
          :items="minutelyIntervalOptions"
          item-title="title"
          item-value="value"
          label="Interval"
          variant="outlined"
          density="compact"
        />
      </div>

      <!-- Hourly Configuration -->
      <div v-if="frequencyType === FrequencyType.HOURLY">
        <VSelect
          v-model="hourlyInterval"
          :items="hourlyIntervalOptions"
          item-title="title"
          item-value="value"
          label="Interval"
          variant="outlined"
          density="compact"
        />
      </div>

      <!-- Daily Configuration -->
      <div v-if="frequencyType === FrequencyType.DAILY">
        <VTextField v-model="time" type="time" label="Time" variant="outlined" density="compact" hide-details />
      </div>

      <!-- Weekly Configuration -->
      <div v-if="frequencyType === FrequencyType.WEEKLY">
        <label class="text-sm font-weight-medium mb-2 d-block">Days of Week</label>
        <div class="d-flex gap-2 mb-4">
          <VChip
            v-for="day in weekDayOptions"
            :key="day.value"
            :color="daysOfWeek.includes(day.value) ? 'primary' : 'default'"
            :variant="daysOfWeek.includes(day.value) ? 'flat' : 'outlined'"
            @click="toggleDay(day.value)"
          >
            {{ day.label }}
          </VChip>
        </div>
        <VTextField v-model="time" type="time" label="Time" variant="outlined" density="compact" hide-details />
      </div>

      <!-- Monthly Configuration -->
      <div v-if="frequencyType === FrequencyType.MONTHLY">
        <VSelect
          v-model="dayOfMonth"
          :items="daysInMonth"
          label="Day of Month"
          variant="outlined"
          density="compact"
          class="mb-4"
        />
        <VTextField v-model="time" type="time" label="Time" variant="outlined" density="compact" hide-details />
      </div>

      <!-- Preview -->
      <VDivider class="my-4" />
      <div>
        <div class="text-sm text-medium-emphasis mb-1">Schedule</div>
        <div class="text-body-1 font-weight-medium">
          {{ cronDescription }}
        </div>
        <div class="text-caption text-medium-emphasis mt-1">Cron: {{ cronExpression }}</div>
      </div>

      <!-- Validation Error -->
      <VAlert v-if="!validation.valid" type="error" variant="tonal" class="mt-4">
        {{ validation.error }}
      </VAlert>
    </VCardText>
  </VCard>
</template>
