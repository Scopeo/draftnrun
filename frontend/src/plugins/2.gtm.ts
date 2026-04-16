import { createGtm } from '@gtm-support/vue-gtm'
import type { App } from 'vue'
import { router } from './1.router'
import { logger } from '@/utils/logger'

// Extend Window interface for gtag
declare global {
  interface Window {
    gtag?: (...args: any[]) => void
    trackEvent?: (eventName: string, parameters?: Record<string, any>) => void
    trackTabChange?: (tabName: string, pageContext?: string, additionalData?: Record<string, any>) => void
    trackModalOpen?: (modalName: string, trigger?: string) => void
    trackModalClose?: (modalName: string) => void
    trackButtonClick?: (buttonName: string, context?: string, additionalData?: Record<string, any>) => void
    trackSearch?: (searchTerm: string, searchContext: string, resultsCount?: number) => void
    trackError?: (errorMessage: string, errorContext: string, errorCode?: string) => void
    trackSignUp?: (method: string, userId?: string, additionalData?: Record<string, any>) => void
    trackSignIn?: (method: string, userId?: string, additionalData?: Record<string, any>) => void
    trackSessionStart?: (userId?: string, sessionData?: Record<string, any>) => void
    trackSessionEnd?: (userId?: string, sessionDuration?: number) => void
  }
}

export default function (app: App) {
  // Only initialize GTM if we have a GTM ID
  const gtmId = import.meta.env.VITE_GTM_ID
  const isDev = import.meta.env.DEV

  if (!gtmId) {
    if (!isDev) {
      logger.warn('GTM_ID not found in environment variables')
    }
    return
  }

  app.use(
    createGtm({
      id: gtmId,
      defer: false, // Script can be loaded immediately
      compatibility: false, // No need for compatibility mode in Vue 3
      nonce: undefined, // Add nonce if you have CSP
      enabled: !isDev, // Disable in development mode
      debug: isDev, // Enable debug mode in development
      loadScript: true, // Load the GTM script
      vueRouter: router, // Enable router integration for automatic page tracking
      ignoredViews: [], // Views to ignore for tracking
      trackOnNextTick: false, // Track immediately, not on next tick
    })
  )

  // Enhanced tracking utilities
  if (typeof window !== 'undefined') {
    // Initialize dataLayer if it doesn't exist
    window.dataLayer = window.dataLayer || []

    // Enhanced GTM tracking functions available globally
    window.gtag =
      window.gtag ||
      function () {
        window.dataLayer?.push(arguments)
      }

    // Custom tracking functions for common app interactions
    const trackEvent = (eventName: string, parameters: Record<string, any> = {}) => {
      if (window.gtag) {
        if (!isDev) {
          window.gtag('event', eventName, {
            event_category: 'UI_Interaction',
            ...parameters,
          })
        } else {
          logger.info('GTM event tracked', { eventName, ...parameters })
        }
      }
    }

    const trackTabChange = (tabName: string, pageContext?: string, additionalData?: Record<string, any>) => {
      trackEvent('tab_change', {
        tab_name: tabName,
        page_context: pageContext || window.location.pathname,
        page_title: document.title,
        ...additionalData,
      })
    }

    const trackModalOpen = (modalName: string, trigger?: string) => {
      trackEvent('modal_open', {
        modal_name: modalName,
        trigger,
        page_location: window.location.pathname,
      })
    }

    const trackModalClose = (modalName: string) => {
      trackEvent('modal_close', {
        modal_name: modalName,
        page_location: window.location.pathname,
      })
    }

    const trackButtonClick = (buttonName: string, context?: string, additionalData?: Record<string, any>) => {
      trackEvent('button_click', {
        button_name: buttonName,
        button_context: context,
        page_location: window.location.pathname,
        ...additionalData,
      })
    }

    const trackSearch = (searchTerm: string, searchContext: string, resultsCount?: number) => {
      trackEvent('search', {
        search_term: searchTerm,
        search_context: searchContext,
        results_count: resultsCount,
        page_location: window.location.pathname,
      })
    }

    const trackError = (errorMessage: string, errorContext: string, errorCode?: string) => {
      trackEvent('error_occurred', {
        error_message: errorMessage,
        error_context: errorContext,
        error_code: errorCode,
        page_location: window.location.pathname,
      })
    }

    // Authentication tracking functions
    const trackSignUp = (method: string, userId?: string, additionalData?: Record<string, any>) => {
      // Remove personal identifiers for privacy compliance (keep user_id)
      const { email, username, full_name, ...safeData } = additionalData || {}

      trackEvent('sign_up', {
        method,
        user_id: userId, // Keep full user ID for tracking
        page_location: window.location.pathname,
        timestamp: new Date().toISOString(),
        // Track email domain only (not full email)
        email_domain: email ? email.split('@')[1] : undefined,
        // Track username length only (not actual username)
        username_length: username ? username.length : undefined,
        ...safeData,
      })
    }

    const trackSignIn = (method: string, userId?: string, additionalData?: Record<string, any>) => {
      // Remove personal identifiers for privacy compliance (keep user_id)
      const { email, username, full_name, ...safeData } = additionalData || {}

      trackEvent('sign_in', {
        method,
        user_id: userId, // Keep full user ID for tracking
        page_location: window.location.pathname,
        timestamp: new Date().toISOString(),
        // Track email domain only (not full email)
        email_domain: email ? email.split('@')[1] : undefined,
        // Track username length only (not actual username)
        username_length: username ? username.length : undefined,
        ...safeData,
      })
    }

    const trackSessionStart = (userId?: string, sessionData?: Record<string, any>) => {
      // Store session start time for duration calculation
      if (userId) {
        sessionStorage.setItem('session_start_time', Date.now().toString())
        sessionStorage.setItem('session_user_id', userId)
      }

      // Remove personal identifiers for privacy compliance (keep user_id)
      const { user_email, ...safeData } = sessionData || {}

      trackEvent('session_start', {
        user_id: userId, // Keep full user ID for tracking
        page_location: window.location.pathname,
        timestamp: new Date().toISOString(),
        // Track email domain only (not full email)
        email_domain: user_email ? user_email.split('@')[1] : undefined,
        ...safeData,
      })
    }

    const trackSessionEnd = (userId?: string, sessionDuration?: number) => {
      // Calculate session duration if not provided
      if (!sessionDuration && userId) {
        const startTime = sessionStorage.getItem('session_start_time')
        if (startTime) {
          sessionDuration = Date.now() - Number.parseInt(startTime)
        }
      }

      trackEvent('session_end', {
        user_id: userId, // Keep full user ID for tracking
        session_duration_ms: sessionDuration,
        page_location: window.location.pathname,
        timestamp: new Date().toISOString(),
      })

      // Clear session storage
      sessionStorage.removeItem('session_start_time')
      sessionStorage.removeItem('session_user_id')
    }

    // Make tracking functions available globally
    Object.assign(window, {
      trackEvent,
      trackTabChange,
      trackModalOpen,
      trackModalClose,
      trackButtonClick,
      trackSearch,
      trackError,
      trackSignUp,
      trackSignIn,
      trackSessionStart,
      trackSessionEnd,
    })

    // Track initial page view with enhanced data
    if (!isDev) {
      window.gtag('event', 'page_view', {
        page_title: document.title,
        page_location: window.location.href,
        page_path: window.location.pathname,
        user_agent: navigator.userAgent,
        timestamp: new Date().toISOString(),
      })
    }
  }
}
