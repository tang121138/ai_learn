import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMcpServers } from '../api/sessions'
import type { McpServer } from '../types'

export const useMcpStore = defineStore('mcp', () => {
  const servers = ref<McpServer[]>([])
  const sdkAvailable = ref(false)
  const loading = ref(false)
  const mcpEnabled = ref(false)           // 全局 MCP 开关
  const selectedServers = ref<string[]>([]) // 选中的 MCP 服务名

  const activeServers = computed(() =>
    servers.value.filter(s => s.connected)
  )

  const activeTools = computed(() => {
    const tools: { serverName: string; toolName: string; description: string }[] = []
    for (const s of activeServers.value) {
      if (selectedServers.value.includes(s.name)) {
        for (const t of s.tools) {
          tools.push({ serverName: s.name, toolName: t.name, description: t.description })
        }
      }
    }
    return tools
  })

  async function fetchServers() {
    loading.value = true
    try {
      const res = await getMcpServers()
      sdkAvailable.value = res.data.sdk_available
      servers.value = res.data.servers || []
    } catch (e) {
      console.warn('获取 MCP 服务器列表失败:', e)
    } finally {
      loading.value = false
    }
  }

  function toggleMcp(val: boolean) {
    mcpEnabled.value = val
    if (!val) {
      selectedServers.value = []
    }
  }

  function toggleServer(name: string) {
    const idx = selectedServers.value.indexOf(name)
    if (idx >= 0) {
      selectedServers.value.splice(idx, 1)
    } else {
      selectedServers.value.push(name)
    }
  }

  function selectAllServers() {
    selectedServers.value = activeServers.value.map(s => s.name)
  }

  function deselectAllServers() {
    selectedServers.value = []
  }

  return {
    servers, sdkAvailable, loading, mcpEnabled, selectedServers,
    activeServers, activeTools,
    fetchServers, toggleMcp, toggleServer, selectAllServers, deselectAllServers,
  }
})
