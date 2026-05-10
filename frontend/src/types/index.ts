export interface User {
  id: string
  username: string
}

export interface Session {
  id: string
  title: string
  model_id?: string | null
  created_at?: string
  updated_at?: string
}

export interface ModelInfo {
  id: string
  name: string
  provider: string
  type: 'text' | 'multimodal' | 'image_gen'
  context_window: number
  multimodal: boolean
  description: string
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls?: any[] | null
}

export interface SSEEvent {
  type: 'text' | 'tool_call' | 'tool_result' | 'multimodal_analysis' | 'reasoning' | 'status' | 'error' | 'done'
  content?: string
  id?: string
  index?: number
  tool_call_id?: string
  function?: { name: string; arguments: string }
}

export interface UsageInfo {
  text: number
  multimodal: number
  image_gen: number
  limits: { text: number; multimodal: number; image_gen: number }
}

export interface McpServer {
  name: string
  transport: string
  enabled: boolean
  connected: boolean
  tools: { name: string; description: string }[]
}

export interface McpStatus {
  sdk_available: boolean
  servers: McpServer[]
}
