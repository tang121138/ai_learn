<template>
  <div class="model-selector">
    <el-select :model-value="modelValue" @update:model-value="handleChange" placeholder="选择模型" size="small" style="width:100%">
      <el-option-group label="文本模型">
        <el-option
          v-for="m in textModels" :key="m.id"
          :label="m.name" :value="m.id"
        >
          <span>{{ m.name }}</span>
          <span style="float:right;color:#909399;font-size:12px;">{{ m.context_window / 1000 }}K</span>
        </el-option>
      </el-option-group>
      <el-option-group label="多模态模型">
        <el-option
          v-for="m in multimodalModels" :key="m.id"
          :label="m.name" :value="m.id"
        />
      </el-option-group>
    </el-select>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { ModelInfo } from '@/types'
import { getModels } from '@/api/sessions'

const props = defineProps<{ modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [val: string] }>()

const models = ref<ModelInfo[]>([])

const textModels = computed(() => models.value.filter((m) => m.type === 'text'))
const multimodalModels = computed(() => models.value.filter((m) => m.type === 'multimodal'))

function handleChange(val: string) { emit('update:modelValue', val) }

onMounted(async () => {
  try {
    const { data } = await getModels()
    models.value = data.models
    if (!props.modelValue && data.default_model) {
      emit('update:modelValue', data.default_model)
    }
  } catch { /* ignore */ }
})
</script>
