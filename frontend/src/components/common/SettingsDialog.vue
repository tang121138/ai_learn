<template>
  <el-dialog
    v-model="visible"
    title="设置"
    width="640px"
    :close-on-click-modal="false"
    class="settings-dialog"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="MCP 管理" name="mcp">
        <div class="mcp-section">
          <div class="mcp-global">
            <el-switch
              v-model="mcpStore.mcpEnabled"
              active-text="启用 MCP 外部工具"
              @change="mcpStore.toggleMcp"
            />
            <span class="mcp-hint">开启后可在对话中使用已连接的 MCP 工具</span>
          </div>

          <el-divider />

          <div class="mcp-header">
            <h4>MCP 服务器</h4>
            <el-button size="small" :icon="Refresh" :loading="mcpStore.loading" @click="mcpStore.fetchServers()">
              刷新
            </el-button>
          </div>

          <div v-if="!mcpStore.sdkAvailable" class="mcp-warning">
            <el-alert
              title="MCP SDK 未安装"
              description="运行 pip install mcp 后重启后端以启用 MCP 功能"
              type="warning"
              show-icon
              :closable="false"
            />
          </div>

          <div v-if="mcpStore.activeServers.length === 0" class="mcp-empty">
            <p>没有已连接的 MCP 服务器</p>
            <p class="mcp-tip">编辑 configs/mcp_servers.json 添加服务器，设置 "enabled": true 后重启后端</p>
          </div>

          <div v-for="srv in mcpStore.servers" :key="srv.name" class="mcp-server-card">
            <div class="mcp-server-info">
              <div class="mcp-server-header">
                <span class="mcp-server-name">{{ srv.name }}</span>
                <el-tag :type="srv.connected ? 'success' : 'info'" size="small">
                  {{ srv.connected ? '已连接' : srv.enabled ? '未连接' : '未启用' }}
                </el-tag>
              </div>
              <div class="mcp-server-meta">
                传输: {{ srv.transport }} | 工具: {{ srv.tools.length }} 个
              </div>

              <div v-if="srv.connected && srv.tools.length > 0" class="mcp-tools">
                <el-tag
                  v-for="t in srv.tools"
                  :key="t.name"
                  size="small"
                  effect="plain"
                >
                  {{ t.name }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="API Key" name="apikey">
        <div class="apikey-section">
          <el-alert
            title="每个用户可配置自己的 API Key，不同用户完全隔离。不填则使用服务端全局配置。"
            type="info" :closable="false" show-icon style="margin-bottom:16px"
          />

          <div v-for="p in providers" :key="p.key" class="apikey-card">
            <div class="apikey-header">
              <span class="apikey-name">{{ p.label }}</span>
              <el-tag :type="apiKeys[p.key]?.configured ? 'success' : 'warning'" size="small">
                {{ apiKeys[p.key]?.configured ? '已配置' : '未配置' }}
              </el-tag>
            </div>

            <div class="apikey-fields">
              <el-input
                v-model="form[p.key].api_key"
                type="password"
                show-password
                placeholder="API Key (留空使用全局配置)"
                size="small"
              />
              <el-input
                v-model="form[p.key].base_url"
                placeholder="Base URL (可留空用默认)"
                size="small"
              />
              <div class="apikey-actions">
                <el-button size="small" type="primary" @click="saveKey(p.key)" :loading="saving === p.key">
                  保存
                </el-button>
                <el-button v-if="apiKeys[p.key]?.configured" size="small" type="danger" @click="removeKey(p.key)">
                  删除
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="关于" name="about">
        <div class="about-section">
          <div class="ink-seal">壹</div>
          <p><strong>AI Agent 系统 (1号机)</strong></p>
          <p>版本: v1.4</p>
          <p>技术栈: FastAPI + Vue 3 + MySQL + 多模型</p>
          <p>工具: 22 个内置工具 + MCP 扩展</p>
          <p>模型: ModelScope Qwen3 + DeepSeek V4</p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useMcpStore } from '../../stores/mcp'
import { getUserKeys, saveUserKey, deleteUserKey } from '../../api/sessions'

const visible = defineModel<boolean>('visible', { default: false })
const mcpStore = useMcpStore()
const activeTab = ref('mcp')

// ─ API Key 管理 ─
const providers = [
  { key: 'modelscope', label: 'ModelScope (魔搭)' },
  { key: 'deepseek', label: 'DeepSeek' },
]
const apiKeys = ref<Record<string, { configured: boolean; masked_key: string; base_url: string }>>({})
const form = reactive<Record<string, { api_key: string; base_url: string }>>({
  modelscope: { api_key: '', base_url: '' },
  deepseek: { api_key: '', base_url: '' },
})
const saving = ref('')

async function fetchKeys() {
  try {
    const { data } = await getUserKeys()
    apiKeys.value = data.keys
  } catch { /* */ }
}

async function saveKey(provider: string) {
  saving.value = provider
  try {
    await saveUserKey(provider, form[provider].api_key, form[provider].base_url)
    ElMessage.success('API Key 已保存')
    form[provider].api_key = ''
    form[provider].base_url = ''
    await fetchKeys()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = ''
  }
}

async function removeKey(provider: string) {
  try {
    await deleteUserKey(provider)
    ElMessage.success('API Key 已删除')
    await fetchKeys()
  } catch (e: any) {
    ElMessage.error('删除失败')
  }
}

// 打开设置时自动加载
const _origVisible = visible
onMounted(() => { fetchKeys() })
</script>

<style scoped>
.mcp-section {
  padding: 8px 0;
}
.mcp-global {
  display: flex;
  align-items: center;
  gap: 12px;
}
.mcp-hint {
  color: var(--ink-gray);
  font-size: 13px;
}
.mcp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.mcp-header h4 {
  margin: 0;
  color: var(--ink-black);
}
.mcp-warning {
  margin-bottom: 12px;
}
.mcp-empty {
  text-align: center;
  padding: 24px;
  color: var(--ink-gray);
}
.mcp-tip {
  font-size: 12px;
  color: var(--ink-gray);
  margin-top: 8px;
}
.mcp-server-card {
  background: var(--ink-paper);
  border: 1px solid var(--ink-border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 10px;
}
.mcp-server-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.mcp-server-name {
  font-weight: 600;
  color: var(--ink-black);
}
.mcp-server-meta {
  font-size: 12px;
  color: var(--ink-gray);
  margin-bottom: 8px;
}
.mcp-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.about-section {
  text-align: center;
  padding: 24px;
}
.about-section .ink-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border: 2px solid #c44;
  color: #c44;
  border-radius: 50%;
  font-size: 20px;
  margin-bottom: 16px;
  font-family: 'STKaiti', 'KaiTi', serif;
}
.about-section p {
  margin: 6px 0;
  color: var(--ink-gray);
  font-size: 14px;
}
.about-section strong {
  color: var(--ink-black);
  font-size: 16px;
}
.apikey-section {
  padding: 8px 0;
}
.apikey-card {
  background: var(--ink-paper);
  border: 1px solid var(--ink-border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.apikey-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.apikey-name {
  font-weight: 600;
  color: var(--ink-black);
}
.apikey-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.apikey-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
