import { serve } from 'https://deno.land/std@0.224.0/http/server.ts'

import { GetObjectCommand, S3Client } from 'npm:@aws-sdk/client-s3@3'
import { getSignedUrl } from 'npm:@aws-sdk/s3-request-presigner@3'
import { corsHeaders } from '../_shared/cors.ts'

interface PresignRequest {
  project_id: string | number
  s3_key: string
  org_id: string
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  })
}

function badRequest(detail: string) {
  console.error('[presign-temp-file] Bad request:', detail)
  return json({ error: { code: 'bad_request', detail } }, 400)
}

function unauthorized(detail: string) {
  console.error('[presign-temp-file] Unauthorized:', detail)
  return json({ error: { code: 'unauthorized', detail } }, 401)
}

function forbidden(detail: string) {
  console.error('[presign-temp-file] Forbidden:', detail)
  return json({ error: { code: 'forbidden', detail } }, 403)
}

serve(async req => {
  // Handle preflight OPTIONS request for CORS
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  if (req.method !== 'POST') {
    console.error('[presign-temp-file] Method not allowed:', req.method)
    return json({ error: { code: 'method_not_allowed', detail: 'Use POST' } }, 405)
  }

  // --- 1) JWT: read Authorization header (needed to pass to check-org-access) ---
  const authHeader = req.headers.get('authorization') ?? req.headers.get('Authorization')
  if (!authHeader?.startsWith('Bearer ')) {
    return unauthorized('Missing or invalid Authorization header (expected Bearer token)')
  }

  // --- 2) Get Supabase URL ---
  const supabaseUrl = Deno.env.get('SUPABASE_URL')
  if (!supabaseUrl) {
    console.error('[presign-temp-file] Server misconfigured: Missing env var SUPABASE_URL')
    return json(
      {
        error: {
          code: 'server_misconfigured',
          detail: 'Missing env var: SUPABASE_URL',
        },
      },
      500
    )
  }

  // --- 3) Parse body ---
  let payload: PresignRequest
  try {
    payload = (await req.json()) as PresignRequest
  } catch {
    return badRequest('Invalid JSON body')
  }

  const projectId = payload?.project_id
  const s3Key = payload?.s3_key
  const orgId = payload?.org_id

  if (projectId === undefined || projectId === null) {
    return badRequest("Missing 'project_id'")
  }
  if (!s3Key || typeof s3Key !== 'string') {
    return badRequest("Missing or invalid 's3_key'")
  }
  if (!orgId || typeof orgId !== 'string') {
    return badRequest("Missing or invalid 'org_id'")
  }

  // --- 4) Check access using check-org-access ---
  const checkOrgAccessUrl = `${supabaseUrl}/functions/v1/check-org-access`

  try {
    const checkAccessResponse = await fetch(checkOrgAccessUrl, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ org_id: orgId }),
    })

    if (!checkAccessResponse.ok) {
      if (checkAccessResponse.status === 401) {
        return unauthorized('Invalid or expired token')
      }
      const errorText = await checkAccessResponse.text()

      console.error(`[presign-temp-file] check-org-access failed:`, {
        status: checkAccessResponse.status,
        errorText,
      })
      return forbidden('Access check failed')
    }

    const accessData = await checkAccessResponse.json()
    if (!accessData?.access) {
      return forbidden("Access denied (user is not a member of this project's organization)")
    }
  } catch (fetchError) {
    console.error('[presign-temp-file] Failed to call check-org-access:', fetchError)
    return forbidden('Failed to verify project access')
  }

  console.log(`[presign-temp-file] Access granted for project_id: ${projectId}`)

  // --- 5) Verify s3_key format and check that project_id and org_id match the ones in the key ---
  // Expected format: temp-files/{org_id}/{project_id}/{conversation_id}/{filename}
  if (!s3Key.startsWith('temp-files/')) {
    return badRequest("Invalid S3 key format. Must start with 'temp-files/'")
  }

  const parts = s3Key.split('/')
  if (parts.length < 5) {
    return badRequest('Invalid S3 key format.')
  }

  const keyOrgId = parts[1]
  const keyProjectId = parts[2]

  if (keyOrgId !== orgId) {
    return forbidden(`S3 key org_id (${keyOrgId}) does not match endpoint org_id (${orgId})`)
  }

  if (keyProjectId !== String(projectId)) {
    return forbidden(`S3 key project_id (${keyProjectId}) does not match endpoint project_id (${projectId})`)
  }

  // --- 6) Generate presigned S3 URL ---
  const bucket = Deno.env.get('S3_BUCKET')
  const region = Deno.env.get('AWS_REGION')
  const accessKeyId = Deno.env.get('AWS_ACCESS_KEY_ID')
  const secretAccessKey = Deno.env.get('AWS_SECRET_ACCESS_KEY')

  if (!bucket || !region || !accessKeyId || !secretAccessKey) {
    console.error('[presign-temp-file] Server misconfigured: Missing S3 env vars', {
      hasBucket: !!bucket,
      hasRegion: !!region,
      hasAccessKeyId: !!accessKeyId,
      hasSecretAccessKey: !!secretAccessKey,
    })
    return json(
      {
        error: {
          code: 'server_misconfigured',
          detail: 'Missing env vars: S3_BUCKET, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY',
        },
      },
      500
    )
  }

  try {
    const s3 = new S3Client({
      region,
      credentials: { accessKeyId, secretAccessKey },
    })

    const command = new GetObjectCommand({
      Bucket: bucket,
      Key: s3Key,
    })

    const presignedUrl = await getSignedUrl(s3, command, { expiresIn: 300 })
    return json({ url: presignedUrl })
  } catch (error) {
    console.error('[presign-temp-file] Failed to generate presigned URL:', error)
    return json(
      {
        error: { code: 'presign_failed', detail: 'Failed to generate presigned URL' },
      },
      500
    )
  }
})
