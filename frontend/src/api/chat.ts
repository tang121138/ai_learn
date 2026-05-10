import type { SSEEvent } from '@/types'

export function sendMessage(
  sessionId: string,
  content: string | any[],
  modelId: string,
  onEvent: (event: SSEEvent) => void,
  onError: (err: string) => void,
  onDone: () => void,
  parentId: string | null = null,
  mcpServers: string[] = [],
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('token')

  const body: any = {
    session_id: sessionId,
    messages: [{ role: 'user', content }],
    model_id: modelId,
    stream: true,
    parent_id: parentId,
  }
  if (mcpServers.length > 0) {
    body.mcp_servers = mcpServers
  }

  fetch('/api/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (resp) => {
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
        onError(err.detail || `HTTP ${resp.status}`)
        return
      }
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') {
            onDone()
            return
          }
          try {
            const event = JSON.parse(payload) as SSEEvent
            onEvent(event)
          } catch {
            // skip malformed
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
      }
    })

  return controller
}
