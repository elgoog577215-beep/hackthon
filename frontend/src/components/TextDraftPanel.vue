<template>
  <Transition name="slide-right">
    <div v-if="visible" class="fixed top-0 right-0 bottom-0 w-80 bg-white border-l border-slate-200 shadow-2xl flex flex-col" style="z-index: 2100;">
      <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50/80">
        <span class="text-sm font-bold text-slate-600 flex items-center gap-1.5">
          <el-icon :size="14"><EditPen /></el-icon> 文字草稿
        </span>
        <button class="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded hover:bg-slate-100" @click="$emit('update:visible', false)">
          <el-icon :size="16"><Close /></el-icon>
        </button>
      </div>
      <div class="px-4 py-2 text-xs text-slate-400 border-b border-slate-50">
        第 {{ questionIndex + 1 }} 题的草稿
      </div>
      <textarea
        ref="textareaRef"
        class="flex-1 w-full p-4 text-sm text-slate-700 leading-relaxed resize-none outline-none placeholder:text-slate-300"
        placeholder="在这里记录解题思路..."
        :value="draftStore.getTextDraft(questionIndex)"
        @input="onInput"
      />
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Close, EditPen } from '@element-plus/icons-vue'
import { useDraftStore } from '../stores/draft'

const props = defineProps<{
  visible: boolean
  questionIndex: number
}>()

defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const draftStore = useDraftStore()
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const onInput = (e: Event) => {
  const target = e.target as HTMLTextAreaElement
  draftStore.setTextDraft(props.questionIndex, target.value)
}

// 切换题目时聚焦
watch(() => props.questionIndex, () => {
  if (props.visible && textareaRef.value) {
    textareaRef.value.focus()
  }
})
</script>

<style scoped>
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
