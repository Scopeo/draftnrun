import { format, isAfter, isToday, isYesterday, subDays } from 'date-fns'

export function truncateString(value: string, maxLength = 20): string {
  if (value.length <= maxLength) return value
  return `${value.substring(0, maxLength)}...`
}

export const formatDate = (
  value: string,
  formatting: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }
) => {
  if (!value) return value

  return new Intl.DateTimeFormat('en-US', formatting).format(new Date(value))
}

/**
 * Uses fr-FR locale which formats with spaces instead of commas:
 * - new Intl.NumberFormat('fr-FR').format(100000000) // "100 000 000"
 * - new Intl.NumberFormat('en-US').format(100000000) // "100,000,000"
 * @param {number | null | undefined} value
 * @returns {string}
 */
export const formatNumberWithSpaces = (value: number | null | undefined): string => {
  if (value == null) return ''
  return new Intl.NumberFormat('fr-FR').format(value)
}

/**
 * Format date in calendar style:
 * - Today: time only (e.g., "14:30:00")
 * - Yesterday: "Yesterday 14:30:00"
 * - Within last week: day name + time (e.g., "Monday 14:30:00")
 * - Older: full date + time (e.g., "14/01/2026 14:30:00")
 * @param {string} value date to format
 */
export const formatDateCalendar = (value: string): string => {
  if (!value) return ''
  const date = new Date(value)
  if (isToday(date)) return format(date, 'HH:mm:ss')
  if (isYesterday(date)) return `Yesterday ${format(date, 'HH:mm:ss')}`
  const weekAgo = subDays(new Date(), 7)
  if (isAfter(date, weekAgo)) return format(date, 'EEEE HH:mm:ss')
  return format(date, 'dd/MM/yyyy HH:mm:ss')
}
