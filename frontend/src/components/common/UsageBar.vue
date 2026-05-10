<template>
  <div class="usage-bar">
    <div v-for="item in items" :key="item.key" class="usage-item">
      <span class="usage-label">{{ item.label }}</span>
      <el-progress
        :percentage="item.percentage"
        :status="item.percentage > 80 ? 'exception' : item.percentage > 50 ? '' : 'success'"
        :stroke-width="6"
        :show-text="false"
      />
      <span class="usage-count">{{ item.remaining }}/{{ item.limit }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface UsageInfo {
  text: number
  multimodal: number
  image_gen: number
  limits: { text: number; multimodal: number; image_gen: number }
}

const props = defineProps<{
  usage: UsageInfo | null
}>()

const items = computed(() => {
  if (!props.usage) return []
  const pct = (used: number, limit: number) => Math.round((1 - used / limit) * 100)
  return [
    { key: 'text', label: '文本', remaining: props.usage.text, limit: props.usage.limits.text, percentage: pct(props.usage.text, props.usage.limits.text) },
    { key: 'multimodal', label: '多模态', remaining: props.usage.multimodal, limit: props.usage.limits.multimodal, percentage: pct(props.usage.multimodal, props.usage.limits.multimodal) },
    { key: 'image_gen', label: '生图', remaining: props.usage.image_gen, limit: props.usage.limits.image_gen, percentage: pct(props.usage.image_gen, props.usage.limits.image_gen) },
  ]
})
</script>

<style scoped>
.usage-bar { padding: 8px 0; }
.usage-item { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.usage-item :deep(.el-progress) { flex: 1; }
.usage-label { font-size: 11px; color: var(--ink-gray); width: 36px; flex-shrink: 0; }
.usage-count { font-size: 11px; color: var(--ink-gray); width: 60px; text-align: right; flex-shrink: 0; }
</style>
