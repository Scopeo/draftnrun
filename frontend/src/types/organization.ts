export interface OrgApiKey {
  key_id: string
  key_name: string
}

export interface OrgApiKeysResponse {
  organization_id: string
  api_keys: OrgApiKey[]
}

export interface OrgApiKeyCreatedResponse {
  private_key: string
  key_id: string
}
