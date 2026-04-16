import type { ExtractSubjectType, InferSubjects } from '@casl/ability'
import { useAbility } from '@casl/vue'
import type { UserData } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import { logger } from '@/utils/logger'

// Define your subjects
type Subjects = InferSubjects<string | 'all'>

// Define your actions
type Actions = string | string[]

// Define your AppAbility type
export interface AppAbilityRawRule {
  action: Actions
  subject: ExtractSubjectType<Subjects>
  fields?: string[]
  conditions?: any
  inverted?: boolean
  reason?: string
}

/**
 * Generate ability rules based on role and user data
 */
export function generateAbilityRules(role: string, userData: UserData | null = null): AppAbilityRawRule[] {
  const lowerRole = role.toLowerCase()
  const userId = userData?.id
  const isSuperAdmin = userData?.super_admin || false

  const rules: AppAbilityRawRule[] = [
    { action: 'read', subject: 'all' },
    { action: 'read', subject: 'Auth' },
    { action: 'read', subject: 'dashboards-crm' },
    { action: 'read', subject: 'Project' },
    { action: 'read', subject: 'data-sources' },
    { action: 'read', subject: 'Knowledge' },
    { action: 'manage', subject: 'customer' },
  ]

  // Super admin gets all permissions
  if (isSuperAdmin) {
    rules.push(
      { action: ['create', 'read', 'update', 'delete'], subject: 'Project' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'Organization' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'User' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'DataSource' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'Knowledge' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'Role' },
      { action: 'read', subject: 'dashboards-crm' },
      { action: 'read', subject: 'access-control' },
      { action: 'read', subject: 'Acl' },
      { action: 'manage', subject: 'customer' },
      { action: 'manage', subject: 'SuperAdmin' }
    )
    return rules
  }

  switch (lowerRole) {
    case 'admin':
      rules.push(
        { action: ['create', 'read', 'update', 'delete'], subject: 'Project' },
        { action: ['read', 'update'], subject: 'Organization' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'User' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'DataSource' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'Knowledge' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'Agent' },
        { action: 'read', subject: 'Role' },
        { action: 'read', subject: 'dashboards-crm' }
      )
      break
    case 'developer':
      rules.push(
        { action: ['create', 'read', 'update'], subject: 'Project' },
        { action: 'read', subject: 'Organization' },
        { action: 'read', subject: 'User' },
        { action: ['create', 'read', 'update'], subject: 'DataSource' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'Knowledge' },
        { action: ['create', 'read', 'update', 'delete'], subject: 'Agent' },
        { action: 'read', subject: 'dashboards-crm' }
      )
      break
    case 'member':
      rules.push(
        { action: 'read', subject: 'Project' },
        { action: 'read', subject: 'User' },
        { action: 'read', subject: 'data-sources' },
        { action: ['read', 'create', 'update'], subject: 'Agent' }
      )
      if (userId) rules.push({ action: 'update', subject: 'User', conditions: { id: userId } })
      break
    case 'user':
      rules.push(
        { action: 'read', subject: 'Project' },
        { action: 'read', subject: 'Organization' },
        { action: 'read', subject: 'User' },
        { action: ['read', 'create', 'update'], subject: 'Agent' }
      )
      if (userId) rules.push({ action: 'update', subject: 'User', conditions: { id: userId } })
      break
    default:
      logger.warn('[abilityRules] Unknown role', { error: lowerRole })
      break
  }
  return rules
}

/**
 * Update the CASL ability system with new rules
 */
export function updateAbilitySystem(rules: AppAbilityRawRule[]): void {
  // Update CASL ability instance
  try {
    const ability = useAbility()

    ability.update(rules as any)
  } catch (error) {
    logger.warn('[abilityRules] Failed to update ability instance', { error })
  }

  // Persist via auth store
  try {
    const authStore = useAuthStore()

    authStore.updateAbilities(rules)
  } catch (error: unknown) {
    logger.warn('Auth store not available for abilities, falling back to localStorage', { error })
    if (typeof window !== 'undefined') {
      localStorage.setItem('userAbilityRules', JSON.stringify(rules))
    }
  }
}
