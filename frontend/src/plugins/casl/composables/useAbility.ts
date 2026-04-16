import { useAbility as useCaslAbility } from '@casl/vue'
import type { AppAbility } from '../ability'

export const useAbility = () => useCaslAbility<AppAbility>()
