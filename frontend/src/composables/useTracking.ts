import { type Ref, watch } from 'vue'
import { logger } from '@/utils/logger'

/**
 * Vue composable for Google Tag Manager tracking
 * Provides an easy interface to track various user interactions
 */
export function useTracking() {
  const isDev = import.meta.env.DEV

  // Core tracking function
  const trackEvent = (eventName: string, parameters: Record<string, any> = {}) => {
    if (typeof window !== 'undefined' && window.trackEvent) {
      window.trackEvent(eventName, parameters)
    } else if (isDev) {
      logger.info('[Tracking] Event would be tracked', eventName, parameters)
    }
  }

  // Track tab changes
  const trackTabChange = (tabName: string, pageContext?: string, additionalData?: Record<string, any>) => {
    if (typeof window !== 'undefined' && window.trackTabChange) {
      window.trackTabChange(tabName, pageContext, additionalData)
    } else if (isDev) {
      logger.info('[Tracking] Tab change would be tracked', { tabName, pageContext, additionalData })
    }
  }

  // Track modal interactions
  const trackModalOpen = (modalName: string, trigger?: string) => {
    if (typeof window !== 'undefined' && window.trackModalOpen) {
      window.trackModalOpen(modalName, trigger)
    } else if (isDev) {
      logger.info('[Tracking] Modal open would be tracked', { modalName, trigger })
    }
  }

  const trackModalClose = (modalName: string) => {
    if (typeof window !== 'undefined' && window.trackModalClose) {
      window.trackModalClose(modalName)
    } else if (isDev) {
      logger.info('[Tracking] Modal close would be tracked', { modalName })
    }
  }

  // Track button clicks
  const trackButtonClick = (buttonName: string, context?: string, additionalData?: Record<string, any>) => {
    if (typeof window !== 'undefined' && window.trackButtonClick) {
      window.trackButtonClick(buttonName, context, additionalData)
    } else if (isDev) {
      logger.info('[Tracking] Button click would be tracked', { buttonName, context, additionalData })
    }
  }

  // Track search interactions
  const trackSearch = (searchTerm: string, searchContext: string, resultsCount?: number) => {
    if (typeof window !== 'undefined' && window.trackSearch) {
      window.trackSearch(searchTerm, searchContext, resultsCount)
    } else if (isDev) {
      logger.info('[Tracking] Search would be tracked', { searchTerm, searchContext, resultsCount })
    }
  }

  // Track errors
  const trackError = (errorMessage: string, errorContext: string, errorCode?: string) => {
    if (typeof window !== 'undefined' && window.trackError) {
      window.trackError(errorMessage, errorContext, errorCode)
    } else if (isDev) {
      logger.info('[Tracking] Error would be tracked', { errorMessage, errorContext, errorCode })
    }
  }

  // Track sign up events
  const trackSignUp = (method: string, userId?: string, additionalData?: Record<string, any>) => {
    if (typeof window !== 'undefined' && window.trackSignUp) {
      window.trackSignUp(method, userId, additionalData)
    } else if (isDev) {
      logger.info('[Tracking] Sign up would be tracked', { method, userId, additionalData })
    }
  }

  // Track sign in events
  const trackSignIn = (method: string, userId?: string, additionalData?: Record<string, any>) => {
    if (typeof window !== 'undefined' && window.trackSignIn) {
      window.trackSignIn(method, userId, additionalData)
    } else if (isDev) {
      logger.info('[Tracking] Sign in would be tracked', { method, userId, additionalData })
    }
  }

  // Track session start
  const trackSessionStart = (userId?: string, sessionData?: Record<string, any>) => {
    if (typeof window !== 'undefined' && window.trackSessionStart) {
      window.trackSessionStart(userId, sessionData)
    } else if (isDev) {
      logger.info('[Tracking] Session start would be tracked', { userId, sessionData })
    }
  }

  // Track session end
  const trackSessionEnd = (userId?: string, sessionDuration?: number) => {
    if (typeof window !== 'undefined' && window.trackSessionEnd) {
      window.trackSessionEnd(userId, sessionDuration)
    } else if (isDev) {
      logger.info('[Tracking] Session end would be tracked', { userId, sessionDuration })
    }
  }

  // Auto-track reactive tab changes
  const useTabTracking = (activeTab: Ref<string>, pageContext: string, additionalData?: () => Record<string, any>) => {
    watch(activeTab, (newTab, oldTab) => {
      if (oldTab !== undefined && newTab !== oldTab) {
        trackTabChange(newTab, pageContext, additionalData?.())
      }
    })
  }

  // Auto-track reactive search
  const useSearchTracking = (
    searchTerm: Ref<string>,
    searchContext: string,
    resultsCount?: Ref<number>,
    debounceMs: number = 500
  ) => {
    let debounceTimer: number | null = null

    const sourcesToWatch = resultsCount ? [searchTerm, resultsCount] : [searchTerm]

    watch(sourcesToWatch, () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }

      debounceTimer = window.setTimeout(() => {
        const term = searchTerm.value
        const count = resultsCount?.value
        if (term && term.length > 2) {
          trackSearch(term, searchContext, count)
        }
      }, debounceMs)
    })
  }

  return {
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
    useTabTracking,
    useSearchTracking,
  }
}
