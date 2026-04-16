import { createApp } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import * as Sentry from '@sentry/vue'

import '@fontsource/dm-sans/latin-400.css'
import '@fontsource/dm-sans/latin-500.css'
import '@fontsource/dm-sans/latin-600.css'
import '@fontsource/dm-sans/latin-700.css'
import '@styles/variables/_tokens.scss'

import App from '@/App.vue'
import { logQueryEnd } from '@/utils/queryLogger'
import { router } from '@/plugins/1.router'

import vuetifyPlugin from '@/plugins/vuetify'
import caslPlugin from '@/plugins/casl'
import piniaPlugin from '@/plugins/2.pinia'
import gtmPlugin from '@/plugins/2.gtm'
import hotjarPlugin from '@/plugins/hotjar'

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      gcTime: 1000 * 60 * 5,
      retry: 1,
      refetchOnWindowFocus: false,
      // @ts-expect-error queryKey type mismatch in onSettled
      onSettled: (data, error, queryKey) => {
        const cacheHit = data !== undefined && error === undefined

        logQueryEnd(queryKey as unknown[], cacheHit, error as Error | undefined)
      },
    },
    mutations: {
      retry: 0,
    },
  },
})

const app = createApp(App)

if (import.meta.env.VITE_SENTRY_DSN) {
  const tracePropagationTargets: (string | RegExp)[] = ['localhost']
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
  const scopeoApiUrl = import.meta.env.VITE_SCOPEO_API_URL?.replace(/\/$/, '')

  if (apiBaseUrl) {
    tracePropagationTargets.push(new RegExp(`^${escapeRegExp(apiBaseUrl)}`))
  }

  if (scopeoApiUrl && scopeoApiUrl !== apiBaseUrl) {
    tracePropagationTargets.push(new RegExp(`^${escapeRegExp(scopeoApiUrl)}`))
  }

  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || 'development',
    sendDefaultPii: true,
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 1.0,
    tracePropagationTargets,
    enableLogs: true,
    ignoreErrors: [
      'ResizeObserver loop',
      'ResizeObserver loop completed with undelivered notifications',
      'Non-Error promise rejection',
      'NetworkError when attempting to fetch resource',
      /Loading chunk \d+ failed/,
      /Failed to fetch dynamically imported module/,
    ],
  })
}

app.config.errorHandler = (err, instance, info) => {
  logger.error('[Vue] Unhandled error', { error: err, info })
}

window.addEventListener('unhandledrejection', event => {
  logger.error('[Global] Unhandled promise rejection', { error: event.reason })
})

app.use(VueQueryPlugin, { queryClient })

piniaPlugin(app)
vuetifyPlugin(app)
app.use(router)
caslPlugin(app)

app.mount('#app')

const deferInit = (fn: () => void) => ('requestIdleCallback' in window ? requestIdleCallback(fn) : setTimeout(fn, 0))

deferInit(() => gtmPlugin(app))
deferInit(() => hotjarPlugin(app))
