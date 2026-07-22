"""Shared role tuples for MCP-level RBAC gates.

These gates are advisory UX — the backend independently enforces membership
and role on every route via the check-org-access edge function. Keeping the
tuples here avoids drift between modules.

The data layer stores roles from organization_members.role. Both underscore
and hyphen spellings of super admin are accepted because the backend hierarchy
uses "super-admin" while older MCP code matched "super_admin".
"""

SUPER_ADMIN_ROLES = ("super_admin", "super-admin")
ADMIN_ROLES = ("admin", *SUPER_ADMIN_ROLES)
DEVELOPER_ROLES = ("developer", *ADMIN_ROLES)
MEMBER_ROLES = ("member", "user", *DEVELOPER_ROLES)
