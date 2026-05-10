import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SSEEvent, UsageInfo } from '@/types'
import { sendMessage } from '@/api/chat'
import { useSessionStore } from './session'
import { useMcpStore } from './mcp'
import { getUsage } from '@/api/sessions'

export const useChatStore = defineStore('chat', () => {
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const reasoningContent = ref('')
  const pendingTools = ref<{ name: string; args: string }[]>([])
  const currentModelId = ref('')
  const usage = ref<UsageInfo | null>(null)
  let abortController: AbortController | null = null

  // 树形分支: 当前消息的父节点 ID
  let currentParentId: string | null = null

  // 打字机效果
  const charBuffer: string[] = []
  let typewriterTimer: number | null = null

  function startTypewriter() {
    if (typewriterTimer) return
    const sessionStore = useSessionStore()
    typewriterTimer = window.setInterval(() => {
      if (charBuffer.length > 0) {
        const ch = charBuffer.shift()!
        streamingContent.value += ch
        sessionStore.updateLastAssistant(ch)
      } else if (!isStreaming.value) {
        stopTypewriter()
      }
    }, 30)
  }

  function stopTypewriter() {
    if (typewriterTimer !== null) {
      clearInterval(typewriterTimer)
      typewriterTimer = null
    }
  }

  function flushTypewriter() {
    if (charBuffer.length > 0) {
      const rest = charBuffer.join('')
      charBuffer.length = 0
      streamingContent.value += rest
      useSessionStore().updateLastAssistant(rest)
    }
  }

  function pushToBuffer(text: string) {
    for (const ch of text) {
      charBuffer.push(ch)
    }
    if (!typewriterTimer) startTypewriter()
  }

  // 生成临时 ID (前端使用，后端会替换为 UUID)
  let _idCounter = 0
  function _tmpId(): string { return '_tmp_' + (++_idCounter) }

  async function send(sessionId: string, content: string | any[], modelId: string) {
    const sessionStore = useSessionStore()
    isStreaming.value = true
    streamingContent.value = ''
    pendingTools.value = []

    // parent_id = 当前活跃叶节点
    currentParentId = sessionStore.activeLeafId

    const userMsgId = _tmpId()
    const asstMsgId = _tmpId()

    sessionStore.addMessage({ id: userMsgId, role: 'user', content, _parentId: currentParentId })
    sessionStore.addMessage({ id: asstMsgId, role: 'assistant', content: '', _parentId: userMsgId })

    const mcpStore = useMcpStore()
    const enabledMcp = mcpStore.mcpEnabled ? [...mcpStore.selectedServers] : []

    abortController = sendMessage(
      sessionId, content, modelId,
      (event: SSEEvent) => {
        switch (event.type) {
          case 'text': pushToBuffer(event.content || ''); break
          case 'reasoning':
            reasoningContent.value += event.content || ''
            sessionStore.updateLastAssistantReasoning(event.content || '')
            break
          case 'tool_call': {
            const name = event.function?.name || 'unknown'
            const args = event.function?.arguments || ''
            pendingTools.value.push({ name, args })
            if (name === 'generate_image') {
              try { sessionStore.addImagePlaceholder(JSON.parse(args).prompt || '生成中...') }
              catch { sessionStore.addImagePlaceholder('生成中...') }
            }
            break
          }
          case 'tool_result':
            if (event.content?.startsWith('生图成功')) {
              const urlMatch = event.content.match(/https?:\/\/\S+/)
              if (urlMatch) sessionStore.replaceLastPlaceholder(urlMatch[0])
            }
            pendingTools.value = pendingTools.value.slice(1)
            break
          case 'error':
            stopTypewriter()
            sessionStore.updateLastAssistant('\n\n[错误: ' + (event.content || '') + ']')
            break
        }
      },
      (err: string) => {
        isStreaming.value = false; stopTypewriter()
        sessionStore.updateLastAssistant('\n\n[连接错误: ' + err + ']')
      },
      () => {
        stopTypewriter(); flushTypewriter()
        isStreaming.value = false; streamingContent.value = ''; reasoningContent.value = ''; pendingTools.value = []
      },
      currentParentId,
      enabledMcp,
    )
  }

  async function regenerate(msgId: string) {
    const sessionStore = useSessionStore()
    isStreaming.value = true
    streamingContent.value = ''
    reasoningContent.value = ''
    pendingTools.value = []

    // regenerate: 新回复和原回复共享同一用户消息为 parent (兄弟关系)
    const userMsg = sessionStore.messages.find(m => m.id === msgId)
    if (!userMsg) { isStreaming.value = false; return }
    const content = userMsg.content
    if (!content) { isStreaming.value = false; return }

    // 新回复的 parent = 用户消息本身 (新 asst 是原 asst 的兄弟)
    currentParentId = msgId

    const asstMsgId = _tmpId()
    sessionStore.addMessage({ id: asstMsgId, role: 'assistant', content: '', _parentId: msgId })

    abortController = sendMessage(
      sessionStore.currentSessionId!, content, currentModelId.value || 'Qwen/Qwen3-30B-A3B',
      (event: SSEEvent) => {
        switch (event.type) {
          case 'text': pushToBuffer(event.content || ''); break
          case 'reasoning':
            reasoningContent.value += event.content || ''
            sessionStore.updateLastAssistantReasoning(event.content || '')
            break
          case 'tool_call': {
            const name = event.function?.name || 'unknown'
            pendingTools.value.push({ name, args: event.function?.arguments || '' })
            if (name === 'generate_image') {
              try { sessionStore.addImagePlaceholder(JSON.parse(event.function?.arguments || '{}').prompt || '') }
              catch { sessionStore.addImagePlaceholder('生成中...') }
            }
            break
          }
          case 'tool_result':
            if (event.content?.startsWith('生图成功')) {
              const urlMatch = event.content.match(/https?:\/\/\S+/)
              if (urlMatch) sessionStore.replaceLastPlaceholder(urlMatch[0])
            }
            pendingTools.value = pendingTools.value.slice(1)
            break
          case 'error':
            stopTypewriter()
            sessionStore.updateLastAssistant('\n\n[错误: ' + (event.content || '') + ']')
            break
        }
      },
      (err: string) => {
        isStreaming.value = false; stopTypewriter()
        sessionStore.updateLastAssistant('\n\n[连接错误: ' + err + ']')
      },
      () => {
        stopTypewriter(); flushTypewriter()
        isStreaming.value = false; streamingContent.value = ''; reasoningContent.value = ''; pendingTools.value = []
      },
      currentParentId,
    )
  }

  async function reedit(msgId: string, newContent: string) {
    const sessionStore = useSessionStore()
    isStreaming.value = true
    streamingContent.value = ''
    reasoningContent.value = ''
    pendingTools.value = []

    // reedit: 新用户消息和原用户消息共享同一 parent (兄弟关系)
    const origMsg = sessionStore.messages.find(m => m.id === msgId)
    if (!origMsg) { isStreaming.value = false; return }

    // 新用户消息的 parent = 原用户消息的 parent
    currentParentId = origMsg._parentId ?? null

    const userMsgId = _tmpId()
    const asstMsgId = _tmpId()

    sessionStore.addMessage({ id: userMsgId, role: 'user', content: newContent, _parentId: currentParentId })
    sessionStore.addMessage({ id: asstMsgId, role: 'assistant', content: '', _parentId: userMsgId })

    abortController = sendMessage(
      sessionStore.currentSessionId!, newContent, currentModelId.value || 'Qwen/Qwen3-30B-A3B',
      (event: SSEEvent) => {
        switch (event.type) {
          case 'text': pushToBuffer(event.content || ''); break
          case 'reasoning':
            reasoningContent.value += event.content || ''
            sessionStore.updateLastAssistantReasoning(event.content || '')
            break
          case 'tool_call': {
            const name = event.function?.name || 'unknown'
            pendingTools.value.push({ name, args: event.function?.arguments || '' })
            if (name === 'generate_image') {
              try { sessionStore.addImagePlaceholder(JSON.parse(event.function?.arguments || '{}').prompt || '') }
              catch { sessionStore.addImagePlaceholder('生成中...') }
            }
            break
          }
          case 'tool_result':
            if (event.content?.startsWith('生图成功')) {
              const urlMatch = event.content.match(/https?:\/\/\S+/)
              if (urlMatch) sessionStore.replaceLastPlaceholder(urlMatch[0])
            }
            pendingTools.value = pendingTools.value.slice(1)
            break
          case 'error':
            stopTypewriter()
            sessionStore.updateLastAssistant('\n\n[错误: ' + (event.content || '') + ']')
            break
        }
      },
      (err: string) => {
        isStreaming.value = false; stopTypewriter()
        sessionStore.updateLastAssistant('\n\n[连接错误: ' + err + ']')
      },
      () => {
        stopTypewriter(); flushTypewriter()
        isStreaming.value = false; streamingContent.value = ''; reasoningContent.value = ''; pendingTools.value = []
      },
      currentParentId,
    )
  }

  function cancel() { abortController?.abort(); stopTypewriter(); isStreaming.value = false }

  async function fetchUsage() {
    try { const { data } = await getUsage(); usage.value = data } catch { /* */ }
  }

  return { isStreaming, streamingContent, reasoningContent, pendingTools, currentModelId, usage, send, cancel, regenerate, reedit, fetchUsage }
})
