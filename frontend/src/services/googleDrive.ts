import { logger } from '@/utils/logger'

export interface GoogleAuthConfig {
  client_id: string
  client_secret: string
  redirect_uri: string
  auth_uri: string
  token_uri: string
  scopes: string[]
}

class GoogleDriveService {
  private credentials: GoogleAuthConfig = {
    client_id: import.meta.env.VITE_GOOGLE_DRIVE_CLIENT_ID,
    client_secret: import.meta.env.VITE_GOOGLE_DRIVE_CLIENT_SECRET,
    redirect_uri: import.meta.env.VITE_GOOGLE_REDIRECT_URI,
    auth_uri: 'https://accounts.google.com/o/oauth2/auth',
    token_uri: 'https://oauth2.googleapis.com/token',
    scopes: ['https://www.googleapis.com/auth/drive.file'],
  }

  private tokenClient: any = null
  private isApiLoaded = false

  private async loadGoogleAPI(): Promise<void> {
    if (this.isApiLoaded) return

    return new Promise((resolve, reject) => {
      const gsiScript = document.createElement('script')

      gsiScript.src = 'https://accounts.google.com/gsi/client'
      gsiScript.async = true
      gsiScript.defer = true
      gsiScript.onload = () => {
        const apiScript = document.createElement('script')

        apiScript.src = 'https://apis.google.com/js/api.js'
        apiScript.async = true
        apiScript.defer = true
        apiScript.onload = () => {
          gapi.load('client:picker', async () => {
            try {
              await gapi.client.init({
                discoveryDocs: ['https://www.googleapis.com/discovery/v1/apis/drive/v3/rest'],
              })
              this.isApiLoaded = true
              resolve()
            } catch (error) {
              reject(new Error('Failed to initialize Google API client'))
            }
          })
        }
        apiScript.onerror = () => reject(new Error('Failed to load Google API'))
        document.head.appendChild(apiScript)
      }
      gsiScript.onerror = () => reject(new Error('Failed to load Google Sign-In'))
      document.head.appendChild(gsiScript)
    })
  }

  async initialize() {
    try {
      await this.loadGoogleAPI()

      // Initialize the token client
      this.tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: this.credentials.client_id,
        scope: this.credentials.scopes.join(' '),
        callback: () => {}, // We'll handle the callback manually
        redirect_uri: this.credentials.redirect_uri,
      })
    } catch (error) {
      logger.error('Failed to initialize Google Drive service', { error })
      throw error
    }
  }

  async authenticate(): Promise<any> {
    if (!this.tokenClient) {
      throw new Error('Google Drive service not initialized')
    }

    return new Promise((resolve, reject) => {
      try {
        this.tokenClient.callback = (response: any) => {
          if (response.error) {
            reject(response)
          }
          resolve(response)
        }
        this.tokenClient.requestAccessToken()
      } catch (error) {
        reject(error)
      }
    })
  }

  async openFolderPicker(accessToken: string): Promise<{ id: string; name: string } | null> {
    if (!this.isApiLoaded) {
      throw new Error('Google API client not loaded')
    }

    logger.info('Opening Google Drive picker...')

    return new Promise((resolve, reject) => {
      try {
        const foldersView = new google.picker.DocsView(google.picker.ViewId.FOLDERS)
          .setSelectFolderEnabled(true)
          .setIncludeFolders(true)
          .setMode(google.picker.DocsViewMode.LIST)

        const picker = new google.picker.PickerBuilder()
          .addView(foldersView)
          .setOAuthToken(accessToken)
          .setCallback((data: any) => {
            logger.info('Picker callback', { data })
            if (data.action === google.picker.Action.PICKED) {
              const folder = data.docs[0]

              logger.info('Folder selected', { data: folder })
              resolve({
                id: folder.id,
                name: folder.name,
              })
            } else if (data.action === google.picker.Action.CANCEL) {
              logger.info('Picker cancelled')
              resolve(null)
            }
          })
          .setTitle('Select a Google Drive folder')
          .setSize(800, 650)
          .build()

        logger.info('Making picker visible...')
        picker.setVisible(true)

        // Position the picker to the right after it's created
        setTimeout(() => {
          // Try multiple selectors to find the picker
          const pickerSelectors = [
            'div[role="dialog"]',
            '.picker-dialog',
            'iframe[src*="picker"]',
            'div[aria-label*="picker"]',
          ]

          let pickerDialog: HTMLElement | null = null
          for (const selector of pickerSelectors) {
            pickerDialog = document.querySelector(selector) as HTMLElement
            if (pickerDialog) break
          }

          if (pickerDialog) {
            const screenWidth = window.innerWidth
            const pickerWidth = 1051
            const sidebarWidth = 280 // Assume typical sidebar width

            // Position well to the right of sidebar
            const rightPosition = Math.max(
              sidebarWidth + 50, // At least 50px right of sidebar
              screenWidth - pickerWidth - 20 // Or 20px from right edge
            )

            pickerDialog.style.position = 'fixed'
            pickerDialog.style.left = `${rightPosition}px`
            pickerDialog.style.top = '50px'
            pickerDialog.style.zIndex = '99999' // Much higher z-index
            pickerDialog.style.transform = 'none' // Override any transforms

            logger.info(`Positioned picker at left: ${rightPosition}px with z-index: 99999`)
          } else {
            logger.info('Could not find picker dialog to position')
          }
        }, 100)

        // Try positioning again after a longer delay in case the picker takes time to render
        setTimeout(() => {
          const allDialogs = document.querySelectorAll('div, iframe')
          for (const element of allDialogs) {
            const el = element as HTMLElement
            if (el.style.zIndex && Number.parseInt(el.style.zIndex) > 1000) {
              el.style.zIndex = '99999'
              el.style.position = 'fixed'
              if (el.style.left && Number.parseInt(el.style.left) < 300) {
                el.style.left = '350px' // Force to right of sidebar
              }
            }
          }
        }, 500)
      } catch (error) {
        logger.error('Error creating picker', { error })
        reject(error)
      }
    })
  }

  async listFolders(accessToken: string, parentId: string = 'root'): Promise<any[]> {
    if (!this.isApiLoaded) {
      throw new Error('Google API client not loaded')
    }

    gapi.client.setToken({ access_token: accessToken })

    try {
      await gapi.client.load('drive', 'v3')

      const response = await gapi.client.drive.files.list({
        q: `mimeType='application/vnd.google-apps.folder' and trashed=false`,
        fields: 'files(id, name)',
        pageSize: 100,
      })

      logger.info('Drive API response', { data: response.result })
      return response.result.files || []
    } catch (error) {
      logger.error('Error listing Google Drive folders', { error })
      throw error
    } finally {
      gapi.client.setToken(null)
    }
  }
}

export const googleDriveService = new GoogleDriveService()

// Declare google and gapi types globally to avoid TS errors
declare global {
  const google: any
  const gapi: any
}
