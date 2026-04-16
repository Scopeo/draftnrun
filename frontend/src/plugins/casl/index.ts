import type { App } from 'vue'

import { createMongoAbility } from '@casl/ability'
import { abilitiesPlugin } from '@casl/vue'
import { logger } from '@/utils/logger'

type Rule = any

export default function (app: App) {
  logger.info('CASL plugin initializing')

  let userAbilityRules: Rule[] = []

  let isSuperAdmin = false
  try {
    if (typeof window !== 'undefined') {
      const userData = localStorage.getItem('userData')
      if (userData) {
        const parsedUserData = JSON.parse(userData)

        isSuperAdmin = parsedUserData?.super_admin || false
        logger.info('Super admin status from localStorage', { isSuperAdmin })
      } else {
        logger.info('No userData found in localStorage')
      }
    }
  } catch (error) {
    logger.warn('Failed to check super admin status', { error: String(error) })
  }

  try {
    if (typeof window !== 'undefined') {
      const storedRules = localStorage.getItem('userAbilityRules')
      if (storedRules) {
        userAbilityRules = JSON.parse(storedRules)
        logger.info('Loaded ability rules from localStorage', { count: userAbilityRules.length })
      } else {
        logger.info('No ability rules found in localStorage')
      }
    }
  } catch (error) {
    logger.warn('Failed to load user ability rules from localStorage', { error: String(error) })
  }

  const defaultRules: Rule[] = [
    { action: 'read', subject: 'Auth' },
    { action: 'read', subject: 'dashboards-crm' },
    { action: 'read', subject: 'Project' },
    { action: 'read', subject: 'data-sources' },
    { action: 'read', subject: 'Agent' },
    { action: 'create', subject: 'Agent' },
    { action: 'update', subject: 'Agent' },
    { action: 'delete', subject: 'Agent' },
    { action: 'manage', subject: 'customer' },
  ]

  if (isSuperAdmin && userAbilityRules.length === 0) {
    const superAdminRules: Rule[] = [
      ...defaultRules,
      { action: 'manage', subject: 'all' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'Project' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'Organization' },
      { action: ['create', 'read', 'update', 'delete'], subject: 'User' },
      { action: 'read', subject: 'access-control' },
      { action: 'read', subject: 'Acl' },
    ]

    userAbilityRules = superAdminRules
    logger.info('Applied super admin rules', { count: superAdminRules.length })
  }

  const finalRules = userAbilityRules.length > 0 ? userAbilityRules : defaultRules

  logger.info('Creating ability', { ruleCount: finalRules.length })

  const initialAbility = createMongoAbility(finalRules)

  app.use(abilitiesPlugin, initialAbility, {
    useGlobalProperties: true,
  })

  logger.info('CASL plugin initialized successfully')
}
