import { ref } from 'vue'
import { logger } from '@/utils/logger'

// Image modal state
const imageModal = ref({
  show: false,
  image: '',
  index: 0,
})

export function useImageUtils() {
  // Function to open image in modal
  const openImageModal = (image: string, index: number) => {
    imageModal.value = {
      show: true,
      image,
      index,
    }
  }

  // Function to close image modal
  const closeImageModal = () => {
    imageModal.value.show = false
  }

  // Function to download image
  const downloadImage = (image: string, index: number, filename?: string) => {
    try {
      // Convert base64 to blob
      const byteCharacters = atob(image)
      const byteNumbers = Array.from({ length: byteCharacters.length }, () => 0)
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i)
      }
      const byteArray = new Uint8Array(byteNumbers)
      const blob = new Blob([byteArray], { type: 'image/png' })

      // Create download link
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')

      a.href = url
      a.download = filename || `generated-image-${index + 1}.png`
      document.body.appendChild(a)
      a.click()
      URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      logger.error('Error downloading image', { error })
    }
  }

  return {
    imageModal,
    openImageModal,
    closeImageModal,
    downloadImage,
  }
}
