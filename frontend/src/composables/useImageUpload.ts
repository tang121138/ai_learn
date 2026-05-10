import { ref } from 'vue'

export function useImageUpload() {
  const images = ref<string[]>([])

  function addFromFile(file: File): Promise<string> {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = () => {
        const dataUri = reader.result as string
        images.value.push(dataUri)
        resolve(dataUri)
      }
      reader.readAsDataURL(file)
    })
  }

  function addFromClipboard(item: DataTransferItem): Promise<string | null> {
    if (!item.type.startsWith('image/')) return Promise.resolve(null)
    const file = item.getAsFile()
    if (!file) return Promise.resolve(null)
    return addFromFile(file)
  }

  function remove(index: number) {
    images.value.splice(index, 1)
  }

  function clear() {
    images.value = []
  }

  return { images, addFromFile, addFromClipboard, remove, clear }
}
