export interface ApiKey {
  key_id: string
  key_name: string
}

export interface ApiKeysResponse {
  project_id: string
  api_keys: ApiKey[]
}

export interface CreateApiKeyRequest {
  key_name: string
  project_id: string
}

export interface CreateApiKeyResponse {
  private_key: string
  key_id: string
}

export interface RevokeKeyResponse {
  key_id: string
  message: string
}
