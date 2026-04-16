import { ref } from 'vue'

const environment = ref<'draft' | 'production'>('production')

export function useApiEnvironment() {
  return {
    environment,
  }
}
