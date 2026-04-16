export interface OrganizationLimit {
  limit?: number | null // Optional, defaults to 0.0 on backend
}

export interface OrganizationLimitResponse extends OrganizationLimit {
  id: string
  organization_id: string
  created_at: string
  updated_at: string
}

export interface OrganizationLimitAndUsageResponse {
  organization_id: string
  limit_id: string | null
  limit: number | null
  total_credits_used: number | null
}
