import { Ability, AbilityBuilder } from '@casl/ability'
import type { UserData } from '@/services/auth'

export type Actions = 'manage' | 'create' | 'read' | 'update' | 'delete'
export type Subjects =
  | 'all'
  | 'Project'
  | 'Organization'
  | 'User'
  | 'Role'
  | 'access-control'
  | 'Auth'
  | 'dashboards-crm'
  | 'customer'
  | 'projects'
  | 'organizations'
  | 'data-sources'
  | 'ThemeDemo'
  | 'SuperAdmin'
  | 'Agent'
  | 'Knowledge'
  | 'Acl'

export default function defineAbilityFor(user: UserData) {
  const { can, cannot, build } = new AbilityBuilder(Ability)

  // Basic permissions for all authenticated users
  can('read', 'all')
  can('read', 'Auth')
  can('read', 'dashboards-crm')
  can('read', 'Project')
  can('read', 'data-sources')
  can('read', 'Agent')

  // Super Admin permissions
  if (user.super_admin) {
    can('manage', 'all')
    can('manage', 'customer')
    can('read', 'Organization')
    can('read', 'Acl')
  }

  cannot(['read', 'update', 'delete'], 'all', { deleted: true })

  return build()
}

export type AppAbility = Ability<[Actions, Subjects]>
