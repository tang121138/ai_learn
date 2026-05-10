import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Session } from '@/types'
import * as sessionsApi from '@/api/sessions'

export interface DisplayMessage {
  id: string
  role: string
  content: any
  tool_calls?: any[]
  _reasoning?: string         // DeepSeek 思考链
  _placeholder?: string
  _imageUrl?: string
  _parentId?: string | null   // 树形结构: 父节点 ID
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<DisplayMessage[]>([])

  // 树形分支: 当前活跃的叶节点 ID
  const activeLeafId = ref<string | null>(null)

  const currentSession = computed(() =>
    sessions.value.find((s) => s.id === currentSessionId.value) || null)

  // childrenMap: parentId → 子节点 ID 列表
  const childrenMap = computed(() => {
    const map = new Map<string, string[]>()
    for (const m of messages.value) {
      const pid = m._parentId
      if (pid) {
        const list = map.get(pid)
        if (list) list.push(m.id)
        else map.set(pid, [m.id])
      }
    }
    return map
  })

  // 可见消息: 从 activeLeaf 沿 _parentId 链上溯到根，反序
  const visibleMessages = computed(() => {
    if (!activeLeafId.value) return []
    const chain: DisplayMessage[] = []
    let id: string | null = activeLeafId.value
    while (id) {
      const msg = messages.value.find(m => m.id === id)
      if (!msg) break
      chain.unshift(msg)
      id = msg._parentId ?? null
    }
    return chain
  })

  // 获取同一 parent 下的所有兄弟节点
  function getSiblings(nodeId: string): DisplayMessage[] {
    const msg = messages.value.find(m => m.id === nodeId)
    if (!msg) return []
    const pid = msg._parentId
    if (!pid) return []
    const childIds = childrenMap.value.get(pid) || []
    return childIds.map(id => messages.value.find(m => m.id === id)!).filter(Boolean)
  }

  // 切换到某个兄弟节点
  function switchToSibling(siblingId: string) {
    activeLeafId.value = siblingId
  }

  async function fetchSessions() {
    const { data } = await sessionsApi.getSessions()
    sessions.value = data
  }

  async function createSession(title?: string, modelId?: string) {
    const { data } = await sessionsApi.createSession(title, modelId)
    sessions.value.unshift(data)
    return data
  }

  async function selectSession(id: string) {
    currentSessionId.value = id
    const { data } = await sessionsApi.getSession(id)
    messages.value = (data.messages || []).map((m: any) => ({
      ...m,
      id: m.id,
      _parentId: m.parent_id ?? m._parentId ?? null,
      _reasoning: m.reasoning_content ?? m._reasoning ?? undefined,
    }))
    // activeLeaf: 最后一条消息 (最深叶节点)
    const last = messages.value[messages.value.length - 1]
    activeLeafId.value = last?.id ?? null
  }

  async function deleteSession(id: string) {
    await sessionsApi.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      messages.value = []
      activeLeafId.value = null
    }
  }

  function addMessage(msg: DisplayMessage) {
    messages.value.push(msg)
    // 新增消息自动成为活跃叶节点
    activeLeafId.value = msg.id
  }

  function updateLastAssistant(content: string) {
    const idx = messages.value.length - 1
    if (idx >= 0 && messages.value[idx].role === 'assistant') {
      messages.value[idx] = {
        ...messages.value[idx],
        content: (messages.value[idx].content || '') + content,
      }
    }
  }

  function updateLastAssistantReasoning(reasoning: string) {
    const idx = messages.value.length - 1
    if (idx >= 0 && messages.value[idx].role === 'assistant') {
      messages.value[idx] = {
        ...messages.value[idx],
        _reasoning: (messages.value[idx]._reasoning || '') + reasoning,
      }
    }
  }

  function addImagePlaceholder(prompt: string) {
    const idx = messages.value.length - 1
    if (idx >= 0) {
      messages.value[idx] = { ...messages.value[idx], _placeholder: prompt }
    }
  }

  function replaceLastPlaceholder(imageUrl: string) {
    const idx = messages.value.length - 1
    if (idx >= 0) {
      messages.value[idx] = { ...messages.value[idx], _placeholder: undefined, _imageUrl: imageUrl }
    }
  }

  return {
    sessions, currentSessionId, messages, visibleMessages, currentSession,
    activeLeafId, childrenMap,
    fetchSessions, createSession, selectSession, deleteSession,
    addMessage, updateLastAssistant, updateLastAssistantReasoning, addImagePlaceholder, replaceLastPlaceholder,
    getSiblings, switchToSibling,
  }
})
