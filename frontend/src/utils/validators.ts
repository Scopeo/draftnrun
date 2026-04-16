import { isEmpty, isEmptyArray, isNullOrUndefined } from './helpers'

export const requiredValidator = (value: unknown) => {
  if (isNullOrUndefined(value) || isEmptyArray(value) || value === false) return 'This field is required'

  return !!String(value).trim().length || 'This field is required'
}

export const emailValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  const re =
    /^(?:[^<>()[\]\\.,;:\s@"]+(?:\.[^<>()[\]\\.,;:\s@"]+)*|".+")@(?:\[\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\]|(?:[a-z\-\d]+\.)+[a-z]{2,})$/i

  if (Array.isArray(value)) return value.every(val => re.test(String(val))) || 'The Email field must be a valid email'

  return re.test(String(value)) || 'The Email field must be a valid email'
}

export const passwordValidator = (password: string) => {
  const regExp = /(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*[!@#$%&*()]).{8,}/

  const validPassword = regExp.test(password)

  return (
    validPassword ||
    'Field must contain at least one uppercase, lowercase, special character and digit with min 8 chars'
  )
}

export const confirmedValidator = (value: string, target: string) =>
  value === target || 'The Confirm Password field confirmation does not match'

export const betweenValidator = (value: unknown, min: number, max: number) => {
  const valueAsNumber = Number(value)

  return (Number(min) <= valueAsNumber && Number(max) >= valueAsNumber) || `Enter number between ${min} and ${max}`
}

export const integerValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  if (Array.isArray(value)) return value.every(val => /^-?\d+$/.test(String(val))) || 'This field must be an integer'

  return /^-?\d+$/.test(String(value)) || 'This field must be an integer'
}

export const regexValidator = (value: unknown, regex: RegExp | string): string | boolean => {
  if (isEmpty(value)) return true

  let regeX = regex
  if (typeof regeX === 'string') regeX = new RegExp(regeX)

  if (Array.isArray(value)) return value.every(val => regexValidator(val, regeX))

  return regeX.test(String(value)) || 'The Regex field format is invalid'
}

export const alphaValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  return /^[A-Z]*$/i.test(String(value)) || 'The Alpha field may only contain alphabetic characters'
}

export const urlValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  const re = /^https?:\/\/[^\s$.?#].\S*$/

  return re.test(String(value)) || 'URL is invalid'
}

export const lengthValidator = (value: unknown, length: number) => {
  if (isEmpty(value)) return true

  return String(value).length === length || `"The length of the Characters field must be ${length} characters."`
}

export const alphaDashValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  const valueAsString = String(value)

  return /^[\w-]*$/.test(valueAsString) || 'All Character are not valid'
}

export const jsonValidator = (value: unknown) => {
  if (isEmpty(value)) return true

  try {
    JSON.parse(String(value))
    return true
  } catch (e) {
    return 'Invalid JSON format'
  }
}
