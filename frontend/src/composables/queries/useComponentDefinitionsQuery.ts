import { useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import type { Category } from './useCategoriesQuery'
import { getCurrentOrgReleaseStage, useOrgReleaseStagesQuery } from './useReleaseStagesQuery'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import { scopeoApi } from '@/api'
import type { ComponentDefinition } from '@/components/studio/data/component-definitions'
import { logger } from '@/utils/logger'

export interface ComponentsWithCategoriesResponse {
  components: ComponentDefinition[]
  categories: Category[]
}

/**
 * Fetch component definitions for an organization (returns full response with categories)
 */
async function fetchComponentDefinitionsWithCategories(
  organizationId: string,
  releaseStage: 'beta' | 'early_access' | 'public' | 'internal' = 'public'
): Promise<ComponentsWithCategoriesResponse> {
  logNetworkCall(
    ['component-definitions', organizationId, releaseStage],
    `/components/${organizationId}?release_stage=${releaseStage}`
  )

  const response = await scopeoApi.components.getAll(organizationId, releaseStage)

  logger.info('[useComponentDefinitionsQuery] API Response', { data: response })
  logger.info('[useComponentDefinitionsQuery] Response type', typeof response)
  logger.info('[useComponentDefinitionsQuery] Is Array', Array.isArray(response))
  logger.info('[useComponentDefinitionsQuery] Has components property', response && 'components' in response)

  // Handle both response formats: { components: [...], categories: [...] } or directly [...]
  if (Array.isArray(response)) {
    logger.info('[useComponentDefinitionsQuery] Response is array, returning with empty categories')
    return { components: response, categories: [] }
  } else if (response && response.components && Array.isArray(response.components)) {
    logger.info('[useComponentDefinitionsQuery] Response has components property, returning full response')
    return {
      components: response.components,
      categories: response.categories || [],
    }
  } else {
    logger.error('[useComponentDefinitionsQuery] Failed to fetch component definitions', { error: response })
    throw new Error('Failed to fetch component definitions - invalid response format')
  }
}

/**
 * Fetch global component definitions (super-admin) with categories
 */
async function fetchGlobalComponentDefinitionsWithCategories(): Promise<ComponentsWithCategoriesResponse> {
  logNetworkCall(['global-component-definitions'], '/components?global=true')

  const response = await scopeoApi.components.getAllGlobal()

  logger.info('[useComponentDefinitionsQuery] Global API Response', { data: response })

  // Handle both response formats: { components: [...], categories: [...] } or directly [...]
  if (Array.isArray(response)) {
    return { components: response, categories: [] }
  } else if (response && response.components && Array.isArray(response.components)) {
    return {
      components: response.components,
      categories: response.categories || [],
    }
  } else {
    logger.error('[useComponentDefinitionsQuery] Invalid global response', { error: response })
    throw new Error('Invalid response format from components API (global)')
  }
}

/**
 * Query: Fetch component definitions for an organization
 */
export function useComponentDefinitionsQuery(
  orgId: Ref<string | undefined>,
  additionalEnabled?: Ref<boolean> | boolean
) {
  // Fetch org release stages to determine which components to show (optional - won't block)
  const { data: orgReleaseStages } = useOrgReleaseStagesQuery(orgId)

  const queryKey = computed(() => {
    if (!orgId.value) return ['component-definitions', 'none']

    let releaseStage: 'beta' | 'early_access' | 'public' | 'internal' = 'public'

    if (orgReleaseStages.value && orgId.value) {
      const orgStage = getCurrentOrgReleaseStage(orgReleaseStages.value, orgId.value)

      if (orgStage?.release_stage_name) {
        const stageName = orgStage.release_stage_name.toLowerCase()
        if (['beta', 'early_access', 'internal'].includes(stageName)) {
          releaseStage = stageName as 'beta' | 'early_access' | 'internal'
        }
      }
    }

    return ['component-definitions', orgId.value, releaseStage]
  })

  const enabled = computed(() => {
    const hasOrgId = !!orgId.value

    if (additionalEnabled !== undefined) {
      const additionalCheck = typeof additionalEnabled === 'boolean' ? additionalEnabled : additionalEnabled.value

      return hasOrgId && additionalCheck
    }

    return hasOrgId
  })

  logQueryStart(queryKey.value, 'useComponentDefinitionsQuery')

  const query = useQuery({
    queryKey,
    queryFn: () => {
      const [, org, stage] = queryKey.value
      return fetchComponentDefinitionsWithCategories(
        org as string,
        stage as 'beta' | 'early_access' | 'public' | 'internal'
      )
    },
    enabled,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: q => q.state.dataUpdatedAt === 0 || q.isStale(),
  })

  return {
    ...query,
    components: computed(() => query.data.value?.components),
    categories: computed(() => query.data.value?.categories || []),
  }
}

/**
 * Query: Fetch global component definitions (super-admin)
 */
export function useGlobalComponentDefinitionsQuery() {
  const queryKey = ['global-component-definitions']

  logQueryStart(queryKey, 'useGlobalComponentDefinitionsQuery')

  const query = useQuery({
    queryKey,
    queryFn: fetchGlobalComponentDefinitionsWithCategories,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: q => q.state.dataUpdatedAt === 0 || q.isStale(),
  })

  return {
    ...query,
    components: computed(() => query.data.value?.components),
    categories: computed(() => query.data.value?.categories || []),
  }
}

/**
 * Computed Helper: Get function callable components
 */
export function useFunctionCallableComponents(orgId: Ref<string | undefined>) {
  const { components } = useComponentDefinitionsQuery(orgId)

  return computed(() => {
    return components.value?.filter(comp => comp.function_callable) || []
  })
}

/**
 * Computed Helper: Get function calling components
 */
export function useFunctionCallingComponents(orgId: Ref<string | undefined>) {
  const { components } = useComponentDefinitionsQuery(orgId)

  return computed(() => {
    return components.value?.filter(comp => comp.can_use_function_calling) || []
  })
}

/**
 * Helper: Get a specific component definition by ID
 */
export function useComponentDefinition(orgId: Ref<string | undefined>, componentVersionId: Ref<string | undefined>) {
  const { components } = useComponentDefinitionsQuery(orgId)

  return computed(() => {
    if (!components.value || !componentVersionId.value) {
      return undefined
    }

    return components.value.find(
      comp =>
        comp.component_version_id === componentVersionId.value ||
        comp.id === componentVersionId.value ||
        comp.component_id === componentVersionId.value
    )
  })
}

/**
 * Helper: Get component definition synchronously from cached data
 * Useful when you need to lookup a component definition outside of setup()
 */
export function getComponentDefinitionFromCache(
  componentDefinitions: ComponentDefinition[] | undefined,
  componentVersionId: string
): ComponentDefinition | undefined {
  if (!componentDefinitions) return undefined

  return componentDefinitions.find(
    comp =>
      comp.component_version_id === componentVersionId ||
      comp.id === componentVersionId ||
      comp.component_id === componentVersionId
  )
}
