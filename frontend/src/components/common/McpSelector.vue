<template>
  <div v-if="mcpStore.sdkAvailable && mcpStore.activeServers.length > 0" class="mcp-selector">
    <el-popover placement="top" :width="320" trigger="click">
      <template #reference>
        <el-badge :value="mcpStore.selectedServers.length" :hidden="!mcpStore.mcpEnabled || mcpStore.selectedServers.length === 0">
          <el-button
            size="small"
            :type="mcpStore.mcpEnabled ? 'primary' : 'default'"
            :icon="Connection"
            text
            @click="toggleMcpPopover"
          >
            MCP
          </el-button>
        </el-badge>
      </template>

      <div class="mcp-popover">
        <div class="mcp-pop-header">
          <el-switch
            v-model="mcpStore.mcpEnabled"
            size="small"
            @change="mcpStore.toggleMcp"
          />
          <span>MCP 工具</span>
          <el-button
            v-if="mcpStore.mcpEnabled"
            size="small"
            text
            @click="mcpStore.selectAllServers()"
          >
            全选
          </el-button>
          <el-button
            v-if="mcpStore.mcpEnabled"
            size="small"
            text
            @click="mcpStore.deselectAllServers()"
          >
            取消全选
          </el-button>
        </div>

        <div v-if="mcpStore.mcpEnabled" class="mcp-pop-servers">
          <el-checkbox-group v-model="mcpStore.selectedServers">
            <div v-for="srv in mcpStore.activeServers" :key="srv.name" class="mcp-pop-server">
              <el-checkbox :label="srv.name" :value="srv.name">
                {{ srv.name }}
              </el-checkbox>
              <span class="mcp-tool-count">{{ srv.tools.length }} 个工具</span>
            </div>
          </el-checkbox-group>
        </div>

        <div v-if="mcpStore.mcpEnabled && mcpStore.selectedServers.length > 0" class="mcp-pop-tools">
          <el-tag
            v-for="t in mcpStore.activeTools"
            :key="t.toolName"
            size="small"
            effect="light"
          >
            {{ t.toolName }}
          </el-tag>
        </div>

        <div v-if="!mcpStore.mcpEnabled" class="mcp-pop-disabled">
          启用后可选择 MCP 工具参与对话
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import { useMcpStore } from '../../stores/mcp'

const mcpStore = useMcpStore()
const visible = ref(false)

function toggleMcpPopover() {
  visible.value = !visible.value
}
</script>

<style scoped>
.mcp-selector {
  display: inline-flex;
  align-items: center;
}
.mcp-popover {
  min-height: 60px;
}
.mcp-pop-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
}
.mcp-pop-servers {
  margin-bottom: 10px;
}
.mcp-pop-server {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}
.mcp-tool-count {
  font-size: 11px;
  color: var(--ink-gray);
}
.mcp-pop-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--ink-border);
}
.mcp-pop-disabled {
  color: var(--ink-gray);
  font-size: 13px;
  text-align: center;
  padding: 12px;
}
</style>
