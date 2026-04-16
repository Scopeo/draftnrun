/**
 * Format file size in bytes to human-readable string
 * @param bytes - File size in bytes
 * @returns Formatted string (e.g., "1.5 MB")
 */
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Math.round((bytes / k ** i) * 100) / 100} ${sizes[i]}`
}

/**
 * File extension to icon mapping
 */
const extMap: Record<string, string> = {
  pdf: 'tabler-file-type-pdf',
  txt: 'tabler-file-text',
  doc: 'tabler-file-type-doc',
  docx: 'tabler-file-type-doc',
  xls: 'tabler-file-type-xls',
  xlsx: 'tabler-file-type-xls',
  xlsm: 'tabler-file-type-xls',
  csv: 'tabler-file-spreadsheet',
  json: 'tabler-json',
  xml: 'tabler-file-code',
  md: 'tabler-markdown',
}

/**
 * Check if a file is an Excel file
 * @param file - File object to check
 * @returns True if the file is an Excel file
 */
export const isExcelFile = (file: File): boolean => {
  return (
    file.type === 'application/vnd.ms-excel' ||
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    file.type === 'application/vnd.ms-excel.sheet.macroEnabled.12' ||
    file.name.endsWith('.xls') ||
    file.name.endsWith('.xlsx') ||
    file.name.endsWith('.xlsm')
  )
}

/**
 * Check if a file is a CSV file
 * @param file - File object to check
 * @returns True if the file is a CSV file
 */
export const isCsvFile = (file: File): boolean => {
  return file.type === 'text/csv' || file.name.endsWith('.csv')
}

/**
 * Check if a file is a PDF file
 * @param file - File object to check
 * @returns True if the file is a PDF file
 */
export const isPdfFile = (file: File): boolean => {
  return file.type === 'application/pdf'
}

/**
 * Check if a file is an image file
 * @param file - File object to check
 * @returns True if the file is an image
 */
export const isImageFile = (file: File): boolean => {
  return file.type.startsWith('image/')
}

/**
 * Check if a file is a Word document
 * @param file - File object to check
 * @returns True if the file is a Word document
 */
export const isWordFile = (file: File): boolean => {
  return (
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    file.name.endsWith('.docx') ||
    file.type === 'application/msword' ||
    file.name.endsWith('.doc')
  )
}

/**
 * Get file icon based on content type and filename
 * @param contentType - MIME type of the file
 * @param filename - Name of the file
 * @returns Icon name for the file type
 */
export const getFileIcon = (contentType: string, filename: string): string => {
  // Check for images first
  if (contentType && contentType.startsWith('image/')) return 'tabler-photo'

  // Check content type mappings
  if (contentType === 'application/pdf') return 'tabler-file-type-pdf'
  if (contentType === 'text/csv') return 'tabler-file-spreadsheet'
  if (contentType.includes('spreadsheet') || contentType.includes('excel')) return 'tabler-file-type-xls'
  if (contentType.includes('text')) return 'tabler-file-text'
  if (contentType.includes('word')) return 'tabler-file-type-doc'
  if (contentType.includes('json')) return 'tabler-json'
  if (contentType.includes('xml')) return 'tabler-file-code'

  // Check file extension
  const ext = filename.split('.').pop()?.toLowerCase()
  if (ext && extMap[ext]) return extMap[ext]

  return 'tabler-file'
}
