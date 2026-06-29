import { $api } from '@/utils/api'

export const filesApi = {
  upload: (organizationId: string, files: File[]) => {
    if (!files || files.length === 0) throw new Error('No files provided for upload')

    const formData = new FormData()

    files.forEach(file => {
      formData.append('files', file)
    })

    return $api(`/files/${organizationId}/upload`, {
      method: 'POST',
      body: formData,
    })
  },
  getPresignedUploadUrls: (organizationId: string, files: File[]) => {
    if (!files || files.length === 0) throw new Error('No files provided for presigned URL generation')

    const requests = files.map(file => ({
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
    }))

    return $api(`/organizations/${organizationId}/files/upload-urls`, {
      method: 'POST',
      body: requests,
    })
  },
  getPresignedDownloadUrl: (organizationId: string, key: string) => {
    if (!organizationId) throw new Error('No organization ID provided for download URL generation')
    if (!key) throw new Error('No S3 key provided for download URL generation')

    return $api<{ key: string; url: string }>(`/organizations/${organizationId}/files/download-url`, {
      method: 'POST',
      body: { key },
    })
  },
}
