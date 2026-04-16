import { emailValidator } from '@/utils/validators'
import { supabase } from '@/services/auth'
import { logger } from '@/utils/logger'

// Cache for organization members (orgId -> { data, timestamp })
const orgMembersCache = new Map<string, { data: { id: string; email: string }[]; timestamp: number }>()
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

/**
 * Get organization members with caching
 */
async function getOrganizationMembers(orgId: string): Promise<{ id: string; email: string }[] | null> {
  const cached = orgMembersCache.get(orgId)
  const now = Date.now()

  if (cached && now - cached.timestamp < CACHE_TTL_MS) {
    return cached.data
  }

  const { data: functionData, error: functionError } = await supabase.functions.invoke(
    'get-organization-members-details',
    { body: { orgId } }
  )

  if (functionError || !functionData || !Array.isArray(functionData)) {
    logger.warn('[getOrganizationMembers] Could not fetch organization members', { error: functionError })
    return null
  }

  orgMembersCache.set(orgId, { data: functionData, timestamp: now })
  return functionData
}

/**
 * Resolve user email from user ID using organization members
 */
export async function resolveUserEmail(userId: string, orgId: string): Promise<string | null> {
  if (!userId || !orgId) {
    return null
  }

  try {
    const members = await getOrganizationMembers(orgId)

    if (!members) {
      return null
    }

    const member = members.find(m => m.id === userId)

    if (!member) {
      return null
    }

    return emailValidator(member.email) === true ? member.email : null
  } catch (error) {
    logger.warn('[resolveUserEmail] Error resolving user email', { error })
    return null
  }
}

/**
 * Resolve user emails for a list of user IDs in a single API call
 * Returns a Map of userId -> email
 */
export async function resolveUserEmailsBatch(userIds: string[], orgId: string): Promise<Map<string, string>> {
  const emailMap = new Map<string, string>()

  if (!userIds.length || !orgId) {
    return emailMap
  }

  try {
    const members = await getOrganizationMembers(orgId)

    if (!members) {
      return emailMap
    }

    // Build map for quick lookup
    const membersMap = new Map<string, string>()
    for (const member of members) {
      if (emailValidator(member.email) === true) {
        membersMap.set(member.id, member.email)
      }
    }

    // Map only the requested user IDs
    for (const userId of userIds) {
      const email = membersMap.get(userId)
      if (email) {
        emailMap.set(userId, email)
      }
    }

    return emailMap
  } catch (error) {
    logger.warn('[resolveUserEmailsBatch] Error resolving user emails', { error })
    return emailMap
  }
}
