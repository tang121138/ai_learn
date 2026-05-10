import { ref, onUnmounted } from 'vue'

export function useTypewriter(speed = 30) {
  const displayedText = ref('')
  const charBuffer: string[] = []
  let timer: number | null = null

  function start() {
    if (timer) return
    timer = window.setInterval(() => {
      if (charBuffer.length > 0) {
        displayedText.value += charBuffer.shift()!
      }
    }, speed)
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function push(text: string) {
    for (const ch of text) {
      charBuffer.push(ch)
    }
    if (!timer) start()
  }

  function flush() {
    if (charBuffer.length > 0) {
      displayedText.value += charBuffer.join('')
      charBuffer.length = 0
    }
  }

  function reset() {
    stop()
    displayedText.value = ''
    charBuffer.length = 0
  }

  onUnmounted(stop)

  return { displayedText, push, start, stop, flush, reset }
}
