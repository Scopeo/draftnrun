import { $api } from '@/utils/api'

export interface MultipartInitResponse {
  upload_id: string
  key: string
}

export interface PresignedPartURL {
  part_number: number
  presigned_url: string
}

export interface CompletedPart {
  part_number: number
  etag: string
}

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
  initMultipartUpload: (
    organizationId: string,
    filename: string,
    contentType: string,
  ): Promise<MultipartInitResponse> => {
    return $api(`/organizations/${organizationId}/files/multipart/init`, {
      method: 'POST',
      body: { filename, content_type: contentType },
    })
  },
  getPartPresignedUrls: (
    organizationId: string,
    key: string,
    uploadId: string,
    partCount: number,
  ): Promise<PresignedPartURL[]> => {
    return $api(`/organizations/${organizationId}/files/multipart/presign-parts`, {
      method: 'POST',
      body: { key, upload_id: uploadId, part_count: partCount },
    })
  },
  completeMultipartUpload: (
    organizationId: string,
    key: string,
    uploadId: string,
    parts: CompletedPart[],
  ): Promise<void> => {
    return $api(`/organizations/${organizationId}/files/multipart/complete`, {
      method: 'POST',
      body: { key, upload_id: uploadId, parts },
    })
  },
  abortMultipartUpload: (organizationId: string, key: string, uploadId: string): Promise<void> => {
    return $api(`/organizations/${organizationId}/files/multipart/abort`, {
      method: 'POST',
      body: { key, upload_id: uploadId },
    })
  },
}

export default filesApi
