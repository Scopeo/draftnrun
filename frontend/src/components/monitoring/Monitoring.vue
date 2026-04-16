<script setup lang="ts">
import { useMonitoringOrgChartsQuery, useMonitoringOrgKPIsQuery } from '@/composables/queries/useObservabilityQuery'
import { CALL_TYPE_OPTIONS, type CallType } from '@/types/observability'
import { getLineChartConfig } from '@/utils/chartConfig'
import { format, fromUnixTime } from 'date-fns'
import { computed, defineAsyncComponent, ref, toRef } from 'vue'
import { useTheme } from 'vuetify'

interface Props {
  organizationId: string
  projectIds: string[]
  isAllSelected?: boolean
}

const props = defineProps<Props>()

// Use defineAsyncComponent for chart components to break potential circular dependencies
const BarChart = defineAsyncComponent(() => import('@/components/charts/BarChart'))
const BubbleChart = defineAsyncComponent(() => import('@/components/charts/BubbleChart'))
const DoughnutChart = defineAsyncComponent(() => import('@/components/charts/DoughnutChart'))
const LineChart = defineAsyncComponent(() => import('@/components/charts/LineChart'))
const PolarAreaChart = defineAsyncComponent(() => import('@/components/charts/PolarAreaChart'))
const RadarChart = defineAsyncComponent(() => import('@/components/charts/RadarChart'))

const vuetifyTheme = useTheme()
const selectedRange = ref(7)
const callTypeFilter = ref<CallType>('all')
const callTypeOptions = CALL_TYPE_OPTIONS

const organizationIdRef = computed(() => props.organizationId)
const projectIdsRef = computed(() => props.projectIds || [])

const orgChartsQuery = useMonitoringOrgChartsQuery(
  organizationIdRef,
  projectIdsRef,
  toRef(selectedRange),
  toRef(callTypeFilter)
)

const orgKpisQuery = useMonitoringOrgKPIsQuery(
  organizationIdRef,
  projectIdsRef,
  toRef(selectedRange),
  toRef(callTypeFilter)
)

interface Chart {
  id: string
  type: ChartType
  title: string
  subtitle?: string | null
  data: ChartData
  progress_percentage?: number | null
  x_axis_type?: string | null
  y_axis_type?: string | null
  x_axis_label?: string | null
  y_axis_label?: string | null
  category?: string | null
  details?: string | null
}

interface RawChart extends Omit<Chart, 'type'> {
  type: ChartType | 'table'
}

interface DatasetConfig {
  backgroundColor: string | string[]
  borderColor?: string | string[]
  [key: string]: any
}

type ChartType = 'line' | 'bar' | 'doughnut' | 'radar' | 'polarArea' | 'bubble'

interface ChartDataset {
  data?: unknown[]
  [key: string]: unknown
}

interface ChartData {
  labels?: string[]
  datasets: ChartDataset[]
}

interface KPI {
  title: string
  stats: string | number
  change?: string
  color: string
  icon: string
}

interface ApiKPI {
  title: string
  stats: string | number
  change?: string
  color?: string
  icon?: string
}

const dateRanges = [
  { title: 'Last 24 hours', value: 1 },
  { title: 'Last 7 days', value: 7 },
  { title: 'Last 30 days', value: 30 },
  { title: 'Last 90 days', value: 90 },
]

const chartComponents: Record<ChartType, ReturnType<typeof defineAsyncComponent>> = {
  line: LineChart,
  bar: BarChart,
  doughnut: DoughnutChart,
  radar: RadarChart,
  polarArea: PolarAreaChart,
  bubble: BubbleChart,
}

// Get base chart configuration based on current theme
const baseChartConfig = computed(() => {
  const currentTheme = vuetifyTheme.current.value.colors
  const baseConfig = getLineChartConfig(vuetifyTheme.current.value) as Record<string, any>

  // Define color palettes for different chart types
  const colorPalette = [
    currentTheme.primary,
    currentTheme.secondary,
    currentTheme.success,
    currentTheme.warning,
    currentTheme.error,
    currentTheme.info,
  ]

  const datasets: Record<ChartType, DatasetConfig> = {
    line: {
      backgroundColor: colorPalette,
      borderColor: colorPalette,
      tension: 0.4,
    },
    bar: {
      backgroundColor: colorPalette,
      borderRadius: 5,
    },
    doughnut: {
      backgroundColor: colorPalette,
      borderWidth: 0,
    },
    radar: {
      backgroundColor: colorPalette.map(color => `${color}80`),
      borderColor: colorPalette,
    },
    polarArea: {
      backgroundColor: colorPalette,
    },
    bubble: { backgroundColor: colorPalette },
  }

  return {
    ...baseConfig,
    scales: {
      ...baseConfig.scales,
      y: {
        ...baseConfig.scales?.y,
        min: undefined,
        max: undefined,
        beginAtZero: true,
        grace: '10%',
        ticks: {
          ...baseConfig.scales?.y?.ticks,
          precision: 0,
          stepSize: undefined,
        },
      },
    },
    plugins: {
      ...baseConfig.plugins,
      colors: {
        forceOverride: true,
      },
    },
    datasets,
  }
})

// Get chart configuration with axis labels for a specific chart
const getChartConfig = (chart: Chart) => {
  const baseConfig = baseChartConfig.value

  // Only add axis labels for chart types that support scales (not doughnut, radar, polarArea)
  if (['line', 'bar', 'bubble'].includes(chart.type)) {
    return {
      ...baseConfig,
      scales: {
        ...baseConfig.scales,
        x: {
          ...baseConfig.scales?.x,
          title: {
            display: !!chart.x_axis_label,
            text: chart.x_axis_label || '',
          },
        },
        y: {
          ...baseConfig.scales?.y,
          title: {
            display: !!chart.y_axis_label,
            text: chart.y_axis_label || '',
          },
        },
      },
    }
  }

  return baseConfig
}

const allCharts = computed<Chart[]>(() => {
  const data = orgChartsQuery.data.value
  if (!data?.charts || !Array.isArray(data.charts)) {
    return []
  }

  return (data.charts as RawChart[])
    .filter((chart: RawChart): chart is Chart => chart.type !== 'table')
    .map((chart: Chart) => {
      if (chart.x_axis_type === 'datetime' && chart.data.labels) {
        return {
          ...chart,
          data: {
            ...chart.data,
            labels: chart.data.labels.map((label: string) => {
              const timestamp = Number.parseInt(label, 10)
              if (!isNaN(timestamp) && timestamp > 1000000000) {
                const date = fromUnixTime(timestamp)
                return format(date, 'dd/MM/yy HH:mm:ss')
              } else {
                try {
                  const date = new Date(label)
                  return format(date, 'dd/MM/yy HH:mm:ss')
                } catch (e) {
                  return label
                }
              }
            }),
          },
        }
      }
      return chart
    })
})

const generalCharts = computed(() => allCharts.value.filter(chart => chart.category !== 'retrieval'))
const retrievalCharts = computed(() => allCharts.value.filter(chart => chart.category === 'retrieval'))

const formatStats = (stats: string | number, title: string): string | number => {
  if (typeof stats === 'number' && title.toLowerCase().includes('credit')) {
    return Math.round(stats)
  }
  if (typeof stats === 'string' && title.toLowerCase().includes('credit')) {
    const num = Number.parseFloat(stats)
    if (!isNaN(num)) return Math.round(num)
  }
  return stats
}

const statisticsData = computed<KPI[]>(() => {
  const data = orgKpisQuery.data.value
  if (!data?.kpis || !Array.isArray(data.kpis)) {
    return []
  }

  return (data.kpis as ApiKPI[]).map((kpi: ApiKPI) => ({
    title: kpi.title,
    stats: formatStats(kpi.stats, kpi.title),
    change: kpi.change,
    color: kpi.color || 'primary',
    icon: kpi.icon || 'tabler-chart-bar',
  }))
})

const getChartData = (chart: Chart): ChartData => {
  const config = baseChartConfig.value.datasets[chart.type] || {}

  const backgroundValues = Array.isArray(config.backgroundColor)
    ? config.backgroundColor
    : [config.backgroundColor].filter((value): value is string => typeof value === 'string')

  const borderValues = Array.isArray(config.borderColor)
    ? config.borderColor
    : typeof config.borderColor === 'string'
      ? [config.borderColor]
      : []

  return {
    ...chart.data,
    datasets: chart.data.datasets.map((dataset: ChartDataset, index: number) => ({
      ...dataset,
      ...config,
      backgroundColor:
        chart.type === 'doughnut' || chart.type === 'polarArea'
          ? backgroundValues.slice(0, dataset.data?.length ?? 0)
          : backgroundValues[index % backgroundValues.length],
      borderColor: borderValues.length > 0 ? borderValues[index % borderValues.length] : config.borderColor,
    })),
  }
}

const loading = computed(() => orgChartsQuery.isLoading.value)
const kpiLoading = computed(() => orgKpisQuery.isLoading.value)
const error = computed(() => (orgChartsQuery.error.value ? (orgChartsQuery.error.value as Error).message : null))
const kpiError = computed(() => (orgKpisQuery.error.value ? (orgKpisQuery.error.value as Error).message : null))
</script>

<template>
  <div>
    <!-- Date Range Selector and Filter -->
    <VCard class="mb-6">
      <VCardText class="d-flex align-center justify-space-between">
        <div class="d-flex align-center">
          <VIcon icon="tabler-calendar" class="me-2" size="20" />
          <VSelect
            v-model="selectedRange"
            :items="dateRanges"
            item-title="title"
            item-value="value"
            density="compact"
            hide-details
            variant="plain"
            class="date-range-select"
            style="max-inline-size: 200px"
          />
        </div>
        <VSelect
          v-model="callTypeFilter"
          :items="callTypeOptions"
          item-title="label"
          item-value="value"
          density="compact"
          hide-details
          variant="outlined"
          style="min-width: 160px"
        >
          <template #selection="{ item }">
            <div class="d-flex align-center gap-1">
              <VIcon v-if="item.raw.icon" :icon="item.raw.icon" size="16" />
              <span>{{ item.raw.label }}</span>
            </div>
          </template>
          <template #item="{ item, props: itemProps }">
            <VListItem v-bind="itemProps" :prepend-icon="item.raw.icon" :title="item.raw.label" />
          </template>
        </VSelect>
      </VCardText>
    </VCard>

    <!-- Statistics Cards -->
    <VRow>
      <VCol v-if="kpiLoading" cols="12">
        <VCard>
          <VCardText>
            <LoadingState size="sm" />
          </VCardText>
        </VCard>
      </VCol>

      <VCol v-else-if="kpiError" cols="12">
        <ErrorState :message="kpiError" />
      </VCol>

      <template v-else>
        <VCol v-for="(stat, index) in statisticsData" :key="index" cols="12" sm="6" lg="3">
          <VCard>
            <VCardText>
              <div class="d-flex justify-space-between align-center">
                <div>
                  <span class="text-caption">{{ stat.title }}</span>
                  <div class="d-flex align-center mt-1">
                    <h6 class="text-h6">
                      {{ stat.stats }}
                    </h6>
                    <span
                      v-if="stat.change"
                      :class="
                        stat.title === 'Average Latency'
                          ? stat.change.startsWith('-')
                            ? 'text-success'
                            : 'text-error'
                          : stat.change.startsWith('+')
                            ? 'text-success'
                            : 'text-error'
                      "
                      class="text-caption ms-2"
                    >
                      {{ stat.change }}
                    </span>
                  </div>
                </div>
                <VAvatar :color="stat.color" variant="tonal" rounded>
                  <VIcon :icon="stat.icon" size="24" />
                </VAvatar>
              </div>
            </VCardText>
          </VCard>
        </VCol>
      </template>
    </VRow>

    <!-- Charts Grid -->
    <VRow class="mt-6">
      <VCol v-if="loading" cols="12">
        <VCard>
          <VCardText>
            <LoadingState size="sm" />
          </VCardText>
        </VCard>
      </VCol>

      <VCol v-else-if="error" cols="12">
        <ErrorState :message="error" />
      </VCol>

      <template v-else>
        <VCol v-if="generalCharts.length === 0" cols="12">
          <EmptyState icon="tabler-chart-bar" title="No chart data available" size="sm" />
        </VCol>

        <VCol v-for="chart in generalCharts" :key="chart.id" cols="12" :md="chart.type === 'line' ? 12 : 6">
          <VCard>
            <VCardItem>
              <template #default>
                <div class="d-flex align-center">
                  <div>
                    <VCardTitle>{{ chart.title }}</VCardTitle>
                    <VCardSubtitle v-if="chart.subtitle">{{ chart.subtitle }}</VCardSubtitle>
                  </div>
                  <VSpacer />
                  <VMenu v-if="chart.details" open-on-hover location="top" :close-on-content-click="false">
                    <template #activator="{ props: menuProps }">
                      <VIcon
                        v-bind="menuProps"
                        icon="tabler-help-circle"
                        size="20"
                        class="text-medium-emphasis cursor-pointer"
                      />
                    </template>
                    <VCard max-width="400" variant="elevated">
                      <VCardText class="text-body-2 pa-4" style="white-space: pre-line">
                        {{ chart.details }}
                      </VCardText>
                    </VCard>
                  </VMenu>
                </div>
              </template>
            </VCardItem>

            <VCardText
              v-if="chart.progress_percentage !== null && chart.progress_percentage !== undefined"
              class="pb-2"
            >
              <div class="d-flex align-center justify-space-between mb-1">
                <span class="text-caption text-medium-emphasis"></span>
                <span class="text-caption font-weight-medium">{{ Math.round(chart.progress_percentage) }}%</span>
              </div>
              <VProgressLinear
                :model-value="chart.progress_percentage"
                :color="
                  chart.progress_percentage >= 90 ? 'error' : chart.progress_percentage >= 75 ? 'warning' : 'primary'
                "
                height="8"
                rounded
              />
            </VCardText>

            <VCardText>
              <component
                :is="chartComponents[chart.type]"
                :chart-options="getChartConfig(chart)"
                :height="400"
                :chart-data="getChartData(chart)"
              />
            </VCardText>
          </VCard>
        </VCol>
      </template>
    </VRow>

    <!-- Retrieval Augmented Generation Section -->
    <AppSection
      v-if="!loading && !error && props.projectIds.length === 1 && retrievalCharts.length > 0"
      title="Retrieval Augmented Generation"
      collapsible
      :default-open="false"
      class="mt-8"
    >
      <VRow>
        <VCol v-for="chart in retrievalCharts" :key="chart.id" cols="12" :md="chart.type === 'line' ? 12 : 6">
          <VCard>
            <VCardItem>
              <template #default>
                <div class="d-flex align-center">
                  <div>
                    <VCardTitle>{{ chart.title }}</VCardTitle>
                    <VCardSubtitle v-if="chart.subtitle">{{ chart.subtitle }}</VCardSubtitle>
                  </div>
                  <VSpacer />
                  <VMenu v-if="chart.details" open-on-hover location="top" :close-on-content-click="false">
                    <template #activator="{ props: menuProps }">
                      <VIcon
                        v-bind="menuProps"
                        icon="tabler-help-circle"
                        size="20"
                        class="text-medium-emphasis cursor-pointer"
                      />
                    </template>
                    <VCard max-width="400" variant="elevated">
                      <VCardText class="text-body-2 pa-4" style="white-space: pre-line">
                        {{ chart.details }}
                      </VCardText>
                    </VCard>
                  </VMenu>
                </div>
              </template>
            </VCardItem>

            <VCardText
              v-if="chart.progress_percentage !== null && chart.progress_percentage !== undefined"
              class="pb-2"
            >
              <div class="d-flex align-center justify-space-between mb-1">
                <span class="text-caption text-medium-emphasis"></span>
                <span class="text-caption font-weight-medium">{{ Math.round(chart.progress_percentage) }}%</span>
              </div>
              <VProgressLinear
                :model-value="chart.progress_percentage"
                :color="
                  chart.progress_percentage >= 90 ? 'error' : chart.progress_percentage >= 75 ? 'warning' : 'primary'
                "
                height="8"
                rounded
              />
            </VCardText>

            <VCardText>
              <component
                :is="chartComponents[chart.type]"
                :chart-options="getChartConfig(chart)"
                :height="400"
                :chart-data="getChartData(chart)"
              />
            </VCardText>
          </VCard>
        </VCol>
      </VRow>
    </AppSection>
  </div>
</template>

<style lang="scss" scoped>
.date-range-select {
  /* stylelint-disable-next-line selector-pseudo-class-no-unknown */
  :deep(.v-field__input) {
    min-block-size: 30px;
    padding-block: 0;
  }
}
</style>
