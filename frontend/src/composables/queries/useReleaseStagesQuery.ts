import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed, ref } from 'vue'
import { getReleaseStageRank } from '@/utils/releaseStages'
import { supabase } from '@/services/auth'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import { logger } from '@/utils/logger'

// Release stage constants matching the backend
export const RELEASE_STAGES = {
  INTERNAL: 'internal',
  EARLY_ACCESS: 'early_access',
  BETA: 'beta',
  PUBLIC: 'public',
} as const

export type ReleaseStage = (typeof RELEASE_STAGES)[keyof typeof RELEASE_STAGES]

export interface ReleaseStageData {
  id: string
  name: string
  description: string
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
  created_by?: string
}

export interface OrganizationReleaseStage {
  id: string
  org_id: string
  release_stage_id: string
  release_stage_name: string
  release_stage_description: string
  display_order: number
  assigned_at: string
  assigned_by?: string
  organizations?: {
    id: string
    name: string
  }
}

/**
 * Fetch all release stages
 */
async function fetchReleaseStages(): Promise<ReleaseStageData[]> {
  logNetworkCall(['release-stages'], 'release_stages')

  const { data, error: dbError } = await supabase
    .from('release_stages')
    .select('*')
    .order('display_order', { ascending: true })

  if (dbError) throw dbError
  return data || []
}

/**
 * Fetch organization release stage assignments
 */
async function fetchOrgReleaseStages(orgId?: string): Promise<OrganizationReleaseStage[]> {
  const endpoint = orgId ? `organization_release_stages_view?org_id=${orgId}` : 'organization_release_stages_view'

  logNetworkCall(['org-release-stages', orgId], endpoint)

  let query = supabase
    .from('organization_release_stages_view')
    .select(
      `
      *,
      organizations!inner(id, name)
    `
    )
    .order('display_order', { ascending: true })

  if (orgId) {
    query = query.eq('org_id', orgId)
  }

  const { data, error: dbError } = await query
  if (dbError) throw dbError
  return data || []
}

/**
 * Check if current user is super admin
 */
async function checkSuperAdminStatus(): Promise<boolean> {
  logNetworkCall(['super-admin-check'], 'check-super-admin')

  const { data, error } = await supabase.functions.invoke('check-super-admin')
  if (error) throw error
  return data?.is_super_admin || false
}

/**
 * Query: Fetch all release stages
 */
export function useReleaseStagesQuery() {
  const queryKey = ['release-stages']

  logQueryStart(queryKey, 'useReleaseStagesQuery')

  return useQuery({
    queryKey,
    queryFn: fetchReleaseStages,
    staleTime: 1000 * 60, // 1 minute
  })
}

/**
 * Query: Fetch organization release stages
 */
export function useOrgReleaseStagesQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['org-release-stages', orgId.value])

  return useQuery({
    queryKey,
    queryFn: () => fetchOrgReleaseStages(orgId.value),
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60, // 1 minute
  })
}

/**
 * Query: Check super admin status
 */
export function useSuperAdminQuery() {
  return useQuery({
    queryKey: ['super-admin-check'],
    queryFn: checkSuperAdminStatus,
    staleTime: 1000 * 60 * 60, // 1 hour - rarely changes
  })
}

/**
 * Mutation: Create a new release stage
 */
export function useCreateReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (stageData: Partial<ReleaseStageData>) => {
      const { data, error: dbError } = await supabase.from('release_stages').insert(stageData).select().single()

      if (dbError) throw dbError
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['release-stages'] })
    },
  })
}

/**
 * Mutation: Update an existing release stage
 */
export function useUpdateReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ stageId, stageData }: { stageId: string; stageData: Partial<ReleaseStageData> }) => {
      const { data, error: dbError } = await supabase
        .from('release_stages')
        .update(stageData)
        .eq('id', stageId)
        .select()
        .single()

      if (dbError) throw dbError
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['release-stages'] })
    },
  })
}

/**
 * Mutation: Delete a release stage (soft delete)
 */
export function useDeleteReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (stageId: string) => {
      const { error: dbError } = await supabase.from('release_stages').update({ is_active: false }).eq('id', stageId)

      if (dbError) throw dbError
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['release-stages'] })
    },
  })
}

/**
 * Mutation: Assign organization to release stage
 */
export function useAssignOrgToReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, releaseStageId }: { orgId: string; releaseStageId: string }) => {
      // First, remove any existing assignment for this org (one stage per org)
      await supabase.from('organization_release_stages').delete().eq('org_id', orgId)

      // Create new assignment
      const { data, error: dbError } = await supabase
        .from('organization_release_stages')
        .insert({
          org_id: orgId,
          release_stage_id: releaseStageId,
        })
        .select(
          `
          *,
          release_stages(name, description, display_order)
        `
        )
        .single()

      if (dbError) throw dbError
      return data
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['org-release-stages'] })
      queryClient.invalidateQueries({ queryKey: ['org-release-stages', variables.orgId] })
    },
  })
}

/**
 * Mutation: Update organization release stage assignment
 */
export function useUpdateOrgReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, releaseStageId }: { orgId: string; releaseStageId: string }) => {
      const { data, error: dbError } = await supabase
        .from('organization_release_stages')
        .update({
          release_stage_id: releaseStageId,
          assigned_at: new Date().toISOString(),
        })
        .eq('org_id', orgId)
        .select(
          `
          *,
          release_stages(name, description, display_order)
        `
        )
        .single()

      if (dbError) throw dbError
      return data
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['org-release-stages'] })
      queryClient.invalidateQueries({ queryKey: ['org-release-stages', variables.orgId] })
    },
  })
}

/**
 * Mutation: Remove organization from release stage
 */
export function useRemoveOrgFromReleaseStageMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (orgId: string) => {
      const { error: dbError } = await supabase.from('organization_release_stages').delete().eq('org_id', orgId)

      if (dbError) throw dbError
    },
    onSuccess: (_data, orgId) => {
      queryClient.invalidateQueries({ queryKey: ['org-release-stages'] })
      queryClient.invalidateQueries({ queryKey: ['org-release-stages', orgId] })
    },
  })
}

/**
 * Helper: Get current organization's release stage
 */
export function getCurrentOrgReleaseStage(
  organizationReleaseStages: OrganizationReleaseStage[],
  orgId: string
): OrganizationReleaseStage | null {
  return organizationReleaseStages.find(org => org.org_id === orgId) || null
}

/**
 * Helper: Check if organization has access to a specific release stage
 */
export function hasReleaseStageAccess(
  organizationReleaseStages: OrganizationReleaseStage[],
  orgId: string,
  requiredStage: ReleaseStage
): boolean {
  const orgStage = getCurrentOrgReleaseStage(organizationReleaseStages, orgId)
  if (!orgStage) return false

  const orgStageOrder = getReleaseStageRank(orgStage.release_stage_name)
  const requiredStageOrder = getReleaseStageRank(requiredStage)

  // Organization has access if their stage is equal or higher privilege (lower number)
  return orgStageOrder <= requiredStageOrder
}

/**
 * Computed: Active release stages
 */
export function getActiveReleaseStages(releaseStages: ReleaseStageData[]): ReleaseStageData[] {
  return releaseStages.filter(stage => stage.is_active)
}

/**
 * Computed: Sorted release stages
 */
export function getSortedReleaseStages(releaseStages: ReleaseStageData[]): ReleaseStageData[] {
  return [...releaseStages].sort((a, b) => a.display_order - b.display_order)
}

/**
 * User management functions
 */
export async function fetchUsers() {
  try {
    const { data: session } = await supabase.auth.getSession()
    if (!session?.session?.access_token) {
      throw new Error('No authentication token available')
    }

    logNetworkCall(['users'], 'list-users')

    const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/list-users`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${session.session.access_token}`,
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || 'Failed to fetch users')
    }

    const data = await response.json()
    return data.users
  } catch (err) {
    logger.error('Error fetching users', { error: err })
    throw err
  }
}

export async function findUserByEmail(email: string) {
  try {
    const { data: session } = await supabase.auth.getSession()
    if (!session?.session?.access_token) {
      throw new Error('No authentication token available')
    }

    logNetworkCall(['user-by-email', email], `list-users?email=${email}`)

    const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/list-users`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.session.access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || 'Failed to find user')
    }

    const data = await response.json()
    return data.user
  } catch (err) {
    logger.error('Error finding user by email', { error: err })
    throw err
  }
}

export async function fetchSuperAdmins() {
  try {
    const { data: session } = await supabase.auth.getSession()
    if (!session?.session?.access_token) {
      throw new Error('No authentication token available')
    }

    logNetworkCall(['super-admins'], 'manage-super-admins')

    const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/manage-super-admins`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${session.session.access_token}`,
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || 'Failed to fetch super admins')
    }

    const data = await response.json()
    return data.superAdmins
  } catch (err) {
    logger.error('Error fetching super admins', { error: err })
    throw err
  }
}

export async function addSuperAdmin(email: string, notes: string = '') {
  try {
    const { data: session } = await supabase.auth.getSession()
    if (!session?.session?.access_token) {
      throw new Error('No authentication token available')
    }

    logNetworkCall(['add-super-admin', email], 'manage-super-admins (POST)')

    const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/manage-super-admins`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.session.access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, notes }),
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || 'Failed to add super admin')
    }

    return true
  } catch (err) {
    logger.error('Error adding super admin', { error: err })
    throw err
  }
}

export async function removeSuperAdmin(userId: string) {
  try {
    const { data: session } = await supabase.auth.getSession()
    if (!session?.session?.access_token) {
      throw new Error('No authentication token available')
    }

    logNetworkCall(['remove-super-admin', userId], 'manage-super-admins (DELETE)')

    const response = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/manage-super-admins`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${session.session.access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ userId }),
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || 'Failed to remove super admin')
    }

    return true
  } catch (err) {
    logger.error('Error removing super admin', { error: err })
    throw err
  }
}

/**
 * Backward-compatible wrapper that maintains the old API
 */
export function useReleaseStages() {
  const queryClient = useQueryClient()

  // Use the new query hooks
  const {
    data: releaseStagesData,
    isLoading: releaseStagesLoading,
    refetch: refetchReleaseStages,
  } = useReleaseStagesQuery()

  const { data: isSuperAdminData, isLoading: superAdminIsLoading } = useSuperAdminQuery()

  // Local refs for organization release stages
  const organizationReleaseStages = ref<OrganizationReleaseStage[]>([])
  const orgLoading = ref(false)

  const releaseStages = computed(() => releaseStagesData.value || [])
  const loading = computed(() => releaseStagesLoading.value || orgLoading.value)
  const isSuperAdmin = computed(() => isSuperAdminData.value || false)
  const superAdminLoading = computed(() => superAdminIsLoading.value)

  // Computed values
  const activeReleaseStages = computed(() => getActiveReleaseStages(releaseStages.value))

  // Fetch organization release stages
  const fetchOrgReleaseStages = async () => {
    orgLoading.value = true
    try {
      const { data, error } = await supabase
        .from('organization_release_stages')
        .select(
          `
          id,
          org_id,
          release_stage_id,
          assigned_at,
          assigned_by,
          release_stages!inner(
            name,
            description,
            display_order
          )
        `
        )
        .order('assigned_at', { ascending: false })

      if (error) throw error

      organizationReleaseStages.value = (data || []).map((item: any) => ({
        id: item.id,
        org_id: item.org_id,
        release_stage_id: item.release_stage_id,
        release_stage_name: item.release_stages.name,
        release_stage_description: item.release_stages.description,
        display_order: item.release_stages.display_order,
        assigned_at: item.assigned_at,
        assigned_by: item.assigned_by,
      }))
    } catch (err) {
      logger.error('Error fetching organization release stages', { error: err })
    } finally {
      orgLoading.value = false
    }
  }

  // Mutations
  const createReleaseStageMutation = useCreateReleaseStageMutation()
  const updateReleaseStageMutation = useUpdateReleaseStageMutation()
  const deleteReleaseStageMutation = useDeleteReleaseStageMutation()
  const assignOrgMutation = useAssignOrgToReleaseStageMutation()
  const updateOrgMutation = useUpdateOrgReleaseStageMutation()
  const removeOrgMutation = useRemoveOrgFromReleaseStageMutation()

  // Wrapper functions
  const createReleaseStage = async (stageData: Partial<ReleaseStageData>) => {
    await createReleaseStageMutation.mutateAsync(stageData)
  }

  const updateReleaseStage = async (id: string, stageData: Partial<ReleaseStageData>) => {
    await updateReleaseStageMutation.mutateAsync({ stageId: id, stageData })
  }

  const deleteReleaseStage = async (id: string) => {
    await deleteReleaseStageMutation.mutateAsync(id)
  }

  const fetchReleaseStages = async () => {
    await refetchReleaseStages()
  }

  const assignOrgToReleaseStage = async (orgId: string, releaseStageId: string) => {
    await assignOrgMutation.mutateAsync({ orgId, releaseStageId })
    await fetchOrgReleaseStages()
  }

  const updateOrgReleaseStage = async (orgId: string, newReleaseStageId: string) => {
    await updateOrgMutation.mutateAsync({ orgId, releaseStageId: newReleaseStageId })
    await fetchOrgReleaseStages()
  }

  const removeOrgFromReleaseStage = async (orgId: string) => {
    await removeOrgMutation.mutateAsync(orgId)
    await fetchOrgReleaseStages()
  }

  return {
    // State
    releaseStages,
    organizationReleaseStages,
    loading,
    error: ref<string | null>(null),
    isSuperAdmin,
    superAdminLoading,

    // Actions
    fetchReleaseStages,
    createReleaseStage,
    updateReleaseStage,
    deleteReleaseStage,
    fetchOrgReleaseStages,
    assignOrgToReleaseStage,
    updateOrgReleaseStage,
    removeOrgFromReleaseStage,
    getCurrentOrgReleaseStage,
    hasReleaseStageAccess,

    // User management
    fetchUsers,
    findUserByEmail,
    fetchSuperAdmins,
    addSuperAdmin,
    removeSuperAdmin,

    // Computed
    activeReleaseStages,

    // Constants
    RELEASE_STAGES,
  }
}
