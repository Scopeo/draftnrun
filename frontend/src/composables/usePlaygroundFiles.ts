import { ref } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import { supabase } from '@/services/auth'
import {
  isCsvFile as isCsvFileType,
  isExcelFile as isExcelFileType,
  isImageFile as isImageFileType,
  isPdfFile as isPdfFileType,
  isWordFile as isWordFileType,
} from '@/utils/fileUtils'

export const MAX_FILE_SIZE = 10 * 1024 * 1024

export function readFileContent(file: File): Promise<{ filename: string; fileData: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    const isExcel = isExcelFileType(file)
    const isCsv = isCsvFileType(file)
    const isBinary = isWordFileType(file)

    reader.onload = e => {
      const result = e.target?.result as string
      let fileData: string
      if (isPdfFileType(file)) {
        const base64 = result.includes(',') ? result.split(',')[1] : result

        fileData = `data:application/pdf;base64,${base64}`
      } else if (isImageFileType(file) || isExcel || isCsv || isBinary) {
        fileData = result
      } else {
        fileData = result
      }
      resolve({ filename: file.name, fileData })
    }
    reader.onerror = () => reject(new Error(`Failed to read file: ${file.name}`))

    const readAsBinary =
      file.type === 'application/pdf' || file.type.startsWith('image/') || isExcel || isCsv || isBinary

    if (readAsBinary) reader.readAsDataURL(file)
    else reader.readAsText(file)
  })
}

export function formatContentWithFile(text: string, fileData: string, filename: string): any {
  const isPdf = filename.toLowerCase().endsWith('.pdf') || fileData.startsWith('data:application/pdf')
  const isImage = fileData.startsWith('data:image/')

  if (isPdf) {
    return [
      { type: 'text', text },
      { type: 'file', file: { filename, file_data: fileData } },
    ]
  }
  if (isImage) {
    return [
      { type: 'text', text },
      { type: 'image_url', image_url: { url: fileData } },
    ]
  }
  return `${text}\n\nFile content from ${filename}:\n${fileData}`
}

export function usePlaygroundFiles() {
  const { notify } = useNotifications()
  const uploadedFiles = ref<File[]>([])
  const isProcessingFile = ref(false)
  const isDragOver = ref(false)
  const downloadingFiles = ref<Record<string, boolean>>({})
  const downloadingResponseFiles = ref<Record<string, boolean>>({})

  const handleFileUpload = async (file: File) => {
    if (!file) return
    uploadedFiles.value.push(file)
    isProcessingFile.value = true
    try {
      await readFileContent(file)
    } catch (error) {
      logger.error('Error processing file', { error })
      uploadedFiles.value.pop()
    } finally {
      isProcessingFile.value = false
    }
  }

  const handleFileSelect = (e: Event) => {
    const target = e.target as HTMLInputElement
    const files = target.files
    if (files && files.length > 0) {
      const file = files[0]
      if (file.size > MAX_FILE_SIZE) {
        notify.error(`File too large (max 10 MB). Your file: ${(file.size / 1024 / 1024).toFixed(1)} MB`)
        target.value = ''
        return
      }
      handleFileUpload(file)
    }
    target.value = ''
  }

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    isDragOver.value = true
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    isDragOver.value = false
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    isDragOver.value = false

    const files = e.dataTransfer?.files
    if (files && files.length > 0) handleFileUpload(files[0])
  }

  const removeFile = (index: number) => {
    uploadedFiles.value.splice(index, 1)
  }

  const handleSourceClick = async (source: { url: string; document_name?: string; name?: string }) => {
    const url = source.url
    const fileName = source.document_name || source.name || 'file'
    if (url?.startsWith('http://') || url?.startsWith('https://')) {
      window.open(url, '_blank', 'noopener,noreferrer')
      return
    }
    if (!url) return

    const isPdf = url.toLowerCase().endsWith('.pdf')

    downloadingFiles.value[url] = true
    try {
      const cleanPath = url.replace(/-/g, '')
      const { data, error } = await supabase.storage.from('ada-bucket').download(cleanPath)
      if (error) throw error
      if (!data) throw new Error('No data returned from download')

      if (isPdf) {
        const blobUrl = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))

        window.open(blobUrl, '_blank')
        setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
      } else {
        const blobUrl = URL.createObjectURL(data)
        const a = document.createElement('a')

        a.href = blobUrl
        a.download = fileName
        document.body.appendChild(a)
        a.click()
        URL.revokeObjectURL(blobUrl)
        document.body.removeChild(a)
      }
    } catch (error) {
      logger.error('Error handling source file', { error })
      if (isPdf) {
        try {
          const cleanPath = url.replace(/-/g, '')
          const { data: urlData } = await supabase.storage.from('ada-bucket').createSignedUrl(cleanPath, 3600)
          if (urlData?.signedUrl) {
            const win = window.open('', '_blank')
            if (win) {
              win.document.write(
                `<iframe src="${urlData.signedUrl}" style="width:100%;height:100%;border:none" type="application/pdf"></iframe>`
              )
              win.document.title = fileName
            } else {
              window.open(urlData.signedUrl, '_blank')
            }
          }
        } catch (fallbackError) {
          logger.error('PDF fallback also failed', { error: fallbackError })
        }
      }
    } finally {
      downloadingFiles.value[url] = false
    }
  }

  const handleResponseFileClick = async (
    file: { filename?: string; s3_key?: string; content_type?: string },
    projectId: string,
    orgId?: string
  ) => {
    const fileName = file.filename || 'file'
    const fileKey = file.s3_key || fileName
    if (!file.s3_key) return

    downloadingResponseFiles.value[fileKey] = true
    try {
      const { data, error } = await supabase.functions.invoke('presign-temp-file', {
        body: { project_id: String(projectId), s3_key: file.s3_key, org_id: orgId },
      })

      if (error) throw new Error(error.message || error.detail || 'Unknown error')
      if (!data?.url) throw new Error('No download URL returned')

      const a = document.createElement('a')

      a.href = data.url
      a.target = '_blank'

      const isPdf = file.content_type === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf')
      if (!isPdf) a.download = fileName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } catch (error: unknown) {
      logger.error('Error downloading response file', { error })
      notify.error(`Failed to download file: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      downloadingResponseFiles.value[fileKey] = false
    }
  }

  return {
    uploadedFiles,
    isProcessingFile,
    isDragOver,
    downloadingFiles,
    downloadingResponseFiles,
    handleFileUpload,
    handleFileSelect,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeFile,
    handleSourceClick,
    handleResponseFileClick,
  }
}
