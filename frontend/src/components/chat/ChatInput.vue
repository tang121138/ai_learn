<template>
  <div class="chat-input-wrapper">
    <div v-if="images.length" class="image-previews">
      <div v-for="(img, i) in images" :key="i" class="img-preview">
        <img :src="img" />
        <el-button size="small" circle type="danger" @click="removeImage(i)" :icon="Close" />
      </div>
    </div>
    <el-input
      v-model="text"
      type="textarea"
      :rows="3"
      placeholder="输入消息，支持粘贴图片..."
      :disabled="disabled"
      @keydown.enter.exact.prevent="handleSend"
      @paste="handlePaste"
    />
    <div class="input-actions">
      <el-button @click="triggerUpload" :icon="Upload" :disabled="disabled">上传图片</el-button>
      <input ref="fileInput" type="file" accept="image/*" multiple hidden @change="handleFileChange" />
      <el-button v-if="!loading" type="primary" @click="handleSend" :disabled="disabled || !text.trim()">
        发送 (Enter)
      </el-button>
      <el-button v-else type="danger" @click="$emit('stop')">
        <el-icon class="is-loading"><Loading /></el-icon> 停止生成
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Close, Upload, Loading } from '@element-plus/icons-vue'

const props = defineProps<{ disabled: boolean; loading: boolean }>()
const emit = defineEmits<{ send: [content: string | any[]]; stop: [] }>()

const text = ref('')
const images = ref<string[]>([])
const fileInput = ref<HTMLInputElement>()

function triggerUpload() { fileInput.value?.click() }

function handleFileChange(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files) return
  for (const file of files) {
    const reader = new FileReader()
    reader.onload = () => { images.value.push(reader.result as string) }
    reader.readAsDataURL(file)
  }
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (!file) continue
      const reader = new FileReader()
      reader.onload = () => { images.value.push(reader.result as string) }
      reader.readAsDataURL(file)
    }
  }
}

function removeImage(i: number) { images.value.splice(i, 1) }

function handleSend() {
  if (!text.value.trim() && !images.value.length) return

  if (images.value.length) {
    const content: any[] = images.value.map((uri) => ({
      type: 'image_url',
      image_url: { url: uri },
    }))
    if (text.value.trim()) {
      content.push({ type: 'text', text: text.value.trim() })
    } else {
      content.push({ type: 'text', text: '请描述这张图片' })
    }
    emit('send', content)
  } else {
    emit('send', text.value.trim())
  }
  text.value = ''
  images.value = []
}
</script>

<style scoped>
.chat-input-wrapper { background: #fff; border-radius: 12px; padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.image-previews { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.img-preview { position: relative; width: 80px; height: 80px; }
.img-preview img { width: 100%; height: 100%; object-fit: cover; border-radius: 6px; }
.img-preview .el-button { position: absolute; top: -6px; right: -6px; }
.input-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
</style>
