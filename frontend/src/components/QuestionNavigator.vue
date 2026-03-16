<template>
  <div class="flex items-center justify-between py-2 px-1">
    <button
      class="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1"
      :class="currentIndex <= 0 ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100'"
      :disabled="currentIndex <= 0"
      @click="$emit('prev')"
    >
      <el-icon :size="14"><ArrowLeft /></el-icon> 上一题
    </button>
    <span class="text-sm text-slate-500 font-medium">
      第 <span class="text-slate-800 font-bold">{{ currentIndex + 1 }}</span> 题 / 共 {{ totalCount }} 题
    </span>
    <button
      class="px-3 py-1.5 text-sm font-medium rounded-lg transition-all flex items-center gap-1"
      :class="currentIndex >= totalCount - 1 ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100'"
      :disabled="currentIndex >= totalCount - 1"
      @click="$emit('next')"
    >
      下一题 <el-icon :size="14"><ArrowRight /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

defineProps<{
  currentIndex: number
  totalCount: number
}>()

defineEmits<{
  (e: 'prev'): void
  (e: 'next'): void
}>()
</script>
