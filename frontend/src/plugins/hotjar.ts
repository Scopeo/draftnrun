import type { App } from 'vue'
import { logger } from '@/utils/logger'

export default function (app: App) {
  const hostname = typeof window !== 'undefined' ? window.location.hostname : ''
  const isProduction = hostname.includes('app.draftnrun.com')

  if (!isProduction) {
    logger.info('Hotjar skipping — not production')
    return
  }

  try {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('userData')
      if (stored) {
        const data = JSON.parse(stored)
        const email = (data.email || '').toLowerCase()
        if (email.endsWith('@draftnrun.com') || email.endsWith('@scopeo.ai')) {
          logger.info('Hotjar skipping — internal user')
          return
        }
      }
    }
  } catch (e) {
    logger.error('Hotjar error reading localStorage', { error: String(e) })
  }

  logger.info('Hotjar initializing')

  const hotjarId = 6584482

  const hotjarVersion = 6

  ;(function (h: any, o: any, t: any, j: any) {
    h.hj =
      h.hj ||
      function () {
        ;(h.hj.q = h.hj.q || []).push(arguments)
      }
    h._hjSettings = { hjid: hotjarId, hjsv: hotjarVersion }

    const a = o.getElementsByTagName('head')[0]
    const r = o.createElement('script')

    r.async = 1
    r.src = t + h._hjSettings.hjid + j + h._hjSettings.hjsv
    a.appendChild(r)
  })(window, document, 'https://static.hotjar.com/c/hotjar-', '.js?sv=')
}
