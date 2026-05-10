<template>
  <div class="chat-layout">
    <div class="sidebar">
      <div class="sidebar-header">
        <h3>会话</h3>
        <div style="display:flex;gap:4px;align-items:center">
          <el-button size="small" type="primary" @click="handleNewSession" :icon="Plus">新建</el-button>
          <el-button size="small" text :icon="Setting" @click="settingsVisible = true" title="设置" />
        </div>
      </div>
      <div class="session-list">
        <div v-for="s in sessionStore.sessions" :key="s.id"
          :class="['session-item', { active: s.id === sessionStore.currentSessionId }]"
          @click="selectSession(s.id)">
          <span class="session-title">{{ s.title }}</span>
          <el-popconfirm title="删除？" @confirm="sessionStore.deleteSession(s.id)">
            <template #reference>
              <el-button size="small" text type="danger" :icon="Delete" @click.stop />
            </template>
          </el-popconfirm>
        </div>
        <el-empty v-if="!sessionStore.sessions.length" description="暂无会话" />
      </div>
      <div class="sidebar-footer">
        <ModelSelector v-model="chatStore.currentModelId" />
        <UsageBar :usage="chatStore.usage" />
        <el-button text type="danger" @click="handleLogout" style="margin-top:8px;width:100%">退出登录</el-button>
      </div>
    </div>

    <div class="main-area">
      <template v-if="sessionStore.currentSessionId">
        <div class="message-list" ref="msgListRef">
          <div v-if="!sessionStore.visibleMessages.length && !chatStore.isStreaming" class="empty-chat">
            <div class="ink-seal">壹</div>
            <h3>AI Agent 系统 · 1号机</h3>
            <p>发送消息开始对话</p>
          </div>

          <template v-for="(msg, idx) in sessionStore.visibleMessages" :key="msg.id">
            <div :class="['message', msg.role]">
              <div class="msg-role">{{ roleLabel(msg.role) }}</div>

              <!-- 用户消息 -->
              <div v-if="msg.role === 'user'" class="msg-content user-msg">
                <div v-if="getImages(msg.content).length" class="msg-images">
                  <img v-for="(img, i) in getImages(msg.content)" :key="i"
                    :src="img" class="msg-thumb" @click="previewImage(img)" />
                </div>
                <div v-if="getText(msg.content)" class="msg-text">{{ getText(msg.content) }}</div>
                <div class="msg-actions">
                  <el-tooltip content="重新生成回复" placement="top">
                    <span class="action-btn" @click="handleRegenerate(msg)"><el-icon><Refresh /></el-icon></span>
                  </el-tooltip>
                  <el-tooltip content="编辑消息" placement="top">
                    <span class="action-btn" @click="editMessage(msg)"><el-icon><Edit /></el-icon></span>
                  </el-tooltip>
                  <el-tooltip content="复制" placement="top">
                    <span class="action-btn" @click="copyMessage(msg)"><el-icon><DocumentCopy /></el-icon></span>
                  </el-tooltip>
                </div>
                <!-- 分支导航 (树形) -->
                <div v-if="userBranchInfo(msg)" class="branch-nav">
                  <span v-for="(sib, si) in userBranchInfo(msg)!.siblings" :key="sib.id">
                    <span v-if="sib.id === msg.id" class="branch-active">{{ si + 1 }}</span>
                    <span v-else class="branch-link" @click="switchToSibling(sib.id)">{{ si + 1 }}</span>
                    <span v-if="si < userBranchInfo(msg)!.siblings.length - 1" class="branch-sep">/</span>
                  </span>
                  <span class="branch-label">&lt;{{ userBranchInfo(msg)!.idx + 1 }}/{{ userBranchInfo(msg)!.siblings.length }}&gt;</span>
                </div>
              </div>

              <!-- 助手消息 -->
              <div v-else class="msg-content assistant-msg">
                <div v-if="msg._reasoning" class="reasoning-block">
                  <el-collapse>
                    <el-collapse-item title="思考过程">
                      <div class="reasoning-content">{{ msg._reasoning }}</div>
                    </el-collapse-item>
                  </el-collapse>
                </div>
                <div v-html="renderAssistant(msg, idx)" />
                <div v-if="msg._placeholder && !msg._imageUrl" class="image-placeholder">
                  <div class="placeholder-card">
                    <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                    <p>正在生成图片...</p>
                    <span class="placeholder-prompt">{{ msg._placeholder }}</span>
                  </div>
                </div>
                <div v-if="msg._imageUrl" class="generated-image">
                  <img :src="msg._imageUrl" @click="previewImage(msg._imageUrl)" />
                </div>
              </div>

              <div v-if="msg.tool_calls?.length" class="thinking-chain">
                <el-collapse>
                  <el-collapse-item :title="`工具调用 (${msg.tool_calls.length})`">
                    <div v-for="tc in msg.tool_calls" :key="tc.id" class="tc-detail">
                      <el-tag size="small" type="info">{{ tc.function?.name }}</el-tag>
                      <pre>{{ formatArgs(tc.function?.arguments) }}</pre>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </template>

          <div v-if="chatStore.pendingTools.length" class="pending-indicator">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>执行: {{ chatStore.pendingTools.map(t => t.name).join(', ') }}</span>
          </div>

          <div v-if="chatStore.isStreaming && !chatStore.pendingTools.length" class="waiting-indicator">
            <span>思考中</span><span class="dot-pulse"></span>
          </div>

          <div v-if="chatError" class="error-banner">
            <el-alert :title="chatError" type="error" show-icon closable @close="chatError=''" />
          </div>
        </div>

        <el-dialog v-model="editVisible" title="编辑消息" width="500px">
          <el-input v-model="editText" type="textarea" :rows="4" />
          <template #footer>
            <el-button @click="editVisible = false">取消</el-button>
            <el-button type="primary" @click="submitEdit">重新发送</el-button>
          </template>
        </el-dialog>

        <div class="input-area">
          <div class="input-toolbar">
            <McpSelector />
          </div>
          <ChatInput
            :disabled="!sessionStore.currentSessionId"
            :loading="chatStore.isStreaming"
            @send="handleSend"
            @stop="chatStore.cancel()" />
        </div>
      </template>
      <el-empty v-else description="选择或创建一个会话开始聊天" style="margin-top:200px" />
    </div>

    <el-dialog v-model="imgPreviewVisible" title="图片预览" width="80%">
      <img :src="imgPreviewUrl" style="width:100%" />
    </el-dialog>

    <SettingsDialog v-model:visible="settingsVisible" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Delete, Loading, Refresh, Edit, DocumentCopy, Setting } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useMcpStore } from '@/stores/mcp'
import { getModels } from '@/api/sessions'
import ModelSelector from '@/components/common/ModelSelector.vue'
import UsageBar from '@/components/common/UsageBar.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import McpSelector from '@/components/common/McpSelector.vue'
import SettingsDialog from '@/components/common/SettingsDialog.vue'

const router = useRouter()
const sessionStore = useSessionStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const mcpStore = useMcpStore()
const msgListRef = ref<HTMLElement>()
const chatError = ref('')
const imgPreviewVisible = ref(false)
const imgPreviewUrl = ref('')
const settingsVisible = ref(false)
const editVisible = ref(false)
const editText = ref('')

function roleLabel(r: string) { return { user: '你', assistant: 'Agent', system: '系统', tool: '工具' }[r] || r }

function getText(content: any): string {
  if (!content) return ''
  if (typeof content === 'string') {
    if (content.startsWith('[用户发送了') || content.startsWith('{')) return ''
    return content
  }
  if (Array.isArray(content)) return content.filter((p: any) => p?.type === 'text').map((p: any) => p.text).join(' ')
  return ''
}

function getImages(content: any): string[] {
  if (!content || typeof content === 'string') return []
  if (Array.isArray(content)) return content.filter((p: any) => p?.type === 'image_url').map((p: any) => p.image_url?.url || '')
  return []
}

function previewImage(url: string) { imgPreviewUrl.value = url; imgPreviewVisible.value = true }

function renderAssistant(msg: any, idx: number): string {
  const content = typeof msg.content === 'string' ? msg.content : ''
  if (!content) {
    const isLast = idx === sessionStore.visibleMessages.length - 1 && chatStore.isStreaming
    return isLast ? '<span class="streaming-cursor">▌</span>' : ''
  }
  const html = marked.parse(content, { breaks: true }) as string
  const clean = DOMPurify.sanitize(html)
  const isLast = idx === sessionStore.visibleMessages.length - 1 && chatStore.isStreaming
  return isLast ? clean + '<span class="streaming-cursor">▌</span>' : clean
}

function formatArgs(args: string): string {
  try { return JSON.stringify(JSON.parse(args), null, 2) } catch { return args }
}

function scrollToBottom() { nextTick(() => { if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight }) }

// === 分支相关 (树形) ===
function userBranchInfo(msg: any): { siblings: any[]; idx: number } | null {
  if (msg.role !== 'user') return null
  // 先查兄弟用户消息 (reedit 场景)
  const siblings = sessionStore.getSiblings(msg.id)
  if (siblings.length > 1) {
    const idx = siblings.findIndex((s: any) => s.id === msg.id)
    return { siblings, idx }
  }
  // 再查子助手消息 (regenerate 场景: 同一用户消息的多个回复)
  const childIds = sessionStore.childrenMap.get(msg.id)
  if (!childIds || childIds.length <= 1) return null
  const children = childIds
    .map(id => sessionStore.messages.find(m => m.id === id))
    .filter(m => m && m.role === 'assistant')
  if (children.length <= 1) return null
  // 找到当前活跃的子助手
  const activeLeaf = sessionStore.activeLeafId
  const idx = children.findIndex(c => c!.id === activeLeaf)
  return { siblings: children, idx: idx >= 0 ? idx : children.length - 1 }
}
function switchToSibling(siblingId: string) {
  sessionStore.switchToSibling(siblingId)
  scrollToBottom()
}

// === 发送 ===
async function handleSend(content: string | any[]) {
  if (!sessionStore.currentSessionId) return
  chatError.value = ''
  try { await chatStore.send(sessionStore.currentSessionId, content, chatStore.currentModelId || 'Qwen/Qwen3-30B-A3B') }
  catch (e: any) { chatError.value = e?.message || '发送失败' }
  scrollToBottom()
}

async function handleRegenerate(msg: any) {
  chatError.value = ''
  try { await chatStore.regenerate(msg.id) }
  catch (e: any) { chatError.value = e?.message || '重新生成失败' }
  scrollToBottom()
}

const editingMsgId = ref<string | null>(null)
function editMessage(msg: any) {
  editingMsgId.value = msg.id
  editText.value = typeof msg.content === 'string' ? msg.content : getText(msg.content)
  editVisible.value = true
}
async function submitEdit() {
  if (!editText.value.trim()) return
  editVisible.value = false
  const msgId = editingMsgId.value
  editingMsgId.value = null
  if (msgId) {
    chatError.value = ''
    try { await chatStore.reedit(msgId, editText.value.trim()) }
    catch (e: any) { chatError.value = e?.message || '编辑重发失败' }
    scrollToBottom()
    return
  }
  await handleSend(editText.value.trim())
}
function copyMessage(msg: any) {
  const text = getText(msg.content) || (typeof msg.content === 'string' ? msg.content : '')
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}

async function selectSession(id: string) { chatError.value = ''; await sessionStore.selectSession(id); scrollToBottom() }
async function handleNewSession() { const s = await sessionStore.createSession('新会话'); sessionStore.currentSessionId = s.id; sessionStore.messages = [] }
function handleLogout() { authStore.logout(); router.push('/login') }

watch(() => sessionStore.visibleMessages.length, scrollToBottom)
watch(() => chatStore.streamingContent, scrollToBottom)

onMounted(async () => {
  await sessionStore.fetchSessions()
  try { const { data } = await getModels(); if (data.default_model) chatStore.currentModelId = data.default_model }
  catch { /* */ }
  chatStore.fetchUsage()
  mcpStore.fetchServers()
})
</script>

<style>
:root { --ink-black: #2c2c2c; --ink-gray: #8c8c8c; --ink-bg: #f7f4ed; --ink-paper: #faf7f0; --ink-accent: #8b6f4e; --ink-border: #d5cfc6; }
body { background: var(--ink-bg); font-family: 'Noto Serif SC', 'STSong', 'SimSun', serif; }
</style>
<style scoped>
.chat-layout { display: flex; height: 100vh; background: var(--ink-bg); }
.sidebar { width: 280px; display: flex; flex-direction: column; border-right: 1px solid var(--ink-border); background: linear-gradient(180deg, #faf7f0, #f2efe7); }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--ink-border); }
.sidebar-header h3 { margin: 0; font-size: 17px; font-weight: 400; letter-spacing: 2px; }
.session-list { flex: 1; overflow-y: auto; padding: 8px; }
.session-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
.session-item:hover { background: rgba(139,111,78,.08); }
.session-item.active { background: rgba(139,111,78,.15); border-left: 2px solid var(--ink-accent); }
.session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.sidebar-footer { padding: 12px; border-top: 1px solid var(--ink-border); }
.main-area { flex: 1; display: flex; flex-direction: column; background: var(--ink-bg); }
.empty-chat { text-align: center; padding-top: 160px; color: var(--ink-gray); }
.ink-seal { display: inline-block; width: 60px; height: 60px; line-height: 60px; font-size: 28px; color: #c44; border: 2px solid #c44; border-radius: 4px; margin-bottom: 16px; }
.message-list { flex: 1; overflow-y: auto; padding: 20px 40px; }
.message { margin-bottom: 20px; max-width: 80%; }
.message.user { margin-left: auto; }
.msg-role { font-size: 11px; color: var(--ink-gray); margin-bottom: 4px; letter-spacing: 1px; }
.user-msg { background: linear-gradient(135deg, #e8e3d8, #ded9cd); border-radius: 8px 8px 2px 8px; padding: 10px 14px; position: relative; }
.user-msg .msg-text { word-break: break-word; line-height: 1.6; }
.msg-images { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.msg-thumb { width: 80px; height: 80px; object-fit: cover; border-radius: 4px; cursor: pointer; border: 1px solid var(--ink-border); }
.msg-thumb:hover { transform: scale(1.05); }
.msg-actions { display: flex; gap: 6px; margin-top: 8px; opacity: 0; transition: opacity .2s; }
.user-msg:hover .msg-actions { opacity: 1; }
.action-btn { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; background: rgba(0,0,0,.06); color: var(--ink-gray); cursor: pointer; font-size: 11px; transition: all .2s; }
.action-btn:hover { background: rgba(0,0,0,.12); color: var(--ink-accent); }
/* 分支导航 */
.branch-nav { margin-top: 8px; display: flex; align-items: center; gap: 2px; font-size: 11px; opacity: 0; transition: opacity .2s; }
.user-msg:hover .branch-nav { opacity: 1; }
.branch-active, .branch-link, .branch-sep, .branch-label { color: var(--ink-gray); }
.branch-active { font-weight: 700; color: var(--ink-accent); }
.branch-link { cursor: pointer; text-decoration: underline; }
.branch-link:hover { color: var(--ink-accent); }
.branch-label { margin-left: 6px; color: #bbb; }
.assistant-msg { background: var(--ink-paper); border-radius: 8px 8px 8px 2px; padding: 10px 16px; box-shadow: 0 1px 4px rgba(0,0,0,.04); line-height: 1.8; word-break: break-word; }
.assistant-msg :deep(pre) { background: rgba(0,0,0,.03); padding: 12px; border-radius: 4px; overflow-x: auto; border: 1px solid var(--ink-border); }
.assistant-msg :deep(code) { font-size: 13px; }
.image-placeholder { margin-top: 12px; }
.placeholder-card { display: flex; flex-direction: column; align-items: center; padding: 32px; background: #e8e4db; border-radius: 8px; color: var(--ink-gray); gap: 8px; }
.placeholder-prompt { font-size: 12px; color: #999; max-width: 300px; text-align: center; }
.generated-image { margin-top: 12px; }
.generated-image img { max-width: 100%; max-height: 400px; border-radius: 8px; cursor: pointer; border: 1px solid var(--ink-border); }
.thinking-chain { margin-top: 6px; }
.thinking-chain :deep(.el-collapse-item__header) { font-size: 12px; color: var(--ink-gray); height: 30px; line-height: 30px; }
.reasoning-block { margin-bottom: 12px; }
.reasoning-block :deep(.el-collapse-item__header) { font-size: 12px; color: var(--ink-accent); height: 30px; line-height: 30px; }
.reasoning-content { font-size: 12px; color: var(--ink-gray); white-space: pre-wrap; line-height: 1.6; padding: 8px 0; border-left: 2px solid var(--ink-border); padding-left: 12px; }
.tc-detail pre { font-size: 11px; color: var(--ink-gray); white-space: pre-wrap; margin: 4px 0 0; }
.pending-indicator, .waiting-indicator { display: flex; align-items: center; gap: 8px; padding: 10px 0; color: var(--ink-gray); font-size: 13px; }
.dot-pulse { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: var(--ink-accent); margin-left: 4px; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%, to { opacity: .3; transform: scale(.8) } 50% { opacity: 1; transform: scale(1.2) } }
.streaming-cursor { animation: blink 1s infinite; color: var(--ink-accent); }
@keyframes blink { 0%, to { opacity: 1 } 50% { opacity: 0 } }
.error-banner { margin: 8px 0; }
.input-area { padding: 16px 40px 24px; }
.input-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
@media (max-width: 1024px) {
  .sidebar { width: 240px; }
  .message-list { padding: 16px 24px; }
  .message { max-width: 90%; }
}
@media (max-width: 768px) {
  .chat-layout { flex-direction: column; }
  .sidebar { width: 100%; height: auto; max-height: 200px; border-right: none; border-bottom: 1px solid var(--ink-border); overflow-y: auto; }
  .sidebar-header h3 { font-size: 14px; }
  .main-area { height: calc(100vh - 200px); }
  .message-list { padding: 12px; }
  .message { max-width: 95%; }
  .input-area { padding: 12px 12px 16px; }
}
</style>
