<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-red-400 to-rose-500 flex items-center justify-center text-white">
          <el-icon :size="20"><CircleClose /></el-icon>
        </div>
        <div>
          <h3 class="text-lg font-bold text-slate-800">错题本</h3>
          <p class="text-xs text-slate-500">共 {{ wrongAnswers.length }} 道错题</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button v-if="wrongAnswers.length > 0"
          class="px-4 py-2 text-sm font-medium text-white rounded-lg transition-all"
          style="background: linear-gradient(135deg, #6366f1, #8b5cf6);"
          @click="retryAll">
          <el-icon class="mr-1"><RefreshRight /></el-icon> 全部重做
        </button>
      </div>
    </div>

    <!-- List -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4">
      <div v-if="wrongAnswers.length === 0" class="flex flex-col items-center justify-center py-16 text-emerald-500">
        <el-icon :size="40" class="mb-3"><CircleCheckFilled /></el-icon>
        <p class="text-sm font-medium">暂无错题，继续保持</p>
      </div>

      <div v-for="(item, idx) in wrongAnswers" :key="idx"
        class="bg-white rounded-xl border border-slate-100 hover:border-slate-200 hover:shadow-sm transition-all overflow-hidden">
        <!-- Question -->
        <div class="px-5 pt-4 pb-2">
          <div class="flex items-start gap-3">
            <span class="flex-shrink-0 w-7 h-7 rounded-lg bg-red-50 text-red-500 flex items-center justify-center text-sm font-bold">{{ idx + 1 }}</span>
            <div class="text-sm text-slate-800 font-medium leading-relaxed flex-1">{{ item.question }}</div>
          </div>
        </div>
        <!-- Options -->
        <div class="px-5 pb-2 space-y-1.5 ml-10">
          <div v-for="(opt, oIdx) in item.options" :key="oIdx"
            class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
            :class="{
              'bg-red-50 text-red-700 border border-red-200': oIdx === item.userIndex && oIdx !== item.correctIndex,
              'bg-emerald-50 text-emerald-700 border border-emerald-200': oIdx === item.correctIndex,
              'text-slate-500': oIdx !== item.userIndex && oIdx !== item.correctIndex
            }">
            <span class="w-5 h-5 rounded text-xs font-bold flex items-center justify-center flex-shrink-0"
              :class="{
                'bg-red-500 text-white': oIdx === item.userIndex && oIdx !== item.correctIndex,
                'bg-emerald-500 text-white': oIdx === item.correctIndex,
                'bg-slate-200 text-slate-500': oIdx !== item.userIndex && oIdx !== item.correctIndex
              }">
              {{ String.fromCharCode(65 + oIdx) }}
            </span>
            <span>{{ opt }}</span>
            <span v-if="oIdx === item.userIndex && oIdx !== item.correctIndex" class="ml-auto text-xs text-red-400">你的选择</span>
            <span v-if="oIdx === item.correctIndex" class="ml-auto text-xs text-emerald-400">正确答案</span>
          </div>
        </div>

        <!-- Explanation -->
        <div v-if="item.explanation" class="mx-5 mb-3 ml-10 p-3 bg-slate-50 rounded-lg">
          <div class="text-xs font-bold text-slate-500 mb-1">解析</div>
          <div class="text-sm text-slate-600 leading-relaxed">{{ item.explanation }}</div>
        </div>

        <!-- Reflection -->
        <div v-if="getReflection(item)" class="mx-5 mb-3 ml-10 p-3 bg-amber-50 rounded-lg border border-amber-100">
          <div class="text-xs font-bold text-amber-600 mb-1">💡 我的反思</div>
          <div class="text-sm text-amber-800 leading-relaxed whitespace-pre-wrap">{{ getReflection(item) }}</div>
        </div>

        <!-- Footer -->
        <div class="px-5 pb-3 flex items-center justify-between ml-10">
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <span>{{ item.nodeName }}</span>
            <span v-if="item.reviewCount > 0">· 已复习 {{ item.reviewCount }} 次</span>
            <span>· {{ formatTime(item.timestamp) }}</span>
          </div>
          <div class="flex items-center gap-1">
            <button class="px-2.5 py-1 text-xs font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors" @click="retry(item)">
              <el-icon class="mr-0.5"><RefreshRight /></el-icon> 重做
            </button>
            <button class="px-2.5 py-1 text-xs font-medium text-emerald-600 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors" @click="markDone(item)">
              <el-icon class="mr-0.5"><CircleCheckFilled /></el-icon> 已掌握
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleClose, CircleCheckFilled, RefreshRight } from '@element-plus/icons-vue'
import { useCourseStore } from '../stores/course'
import { useReviewStore } from '../stores/review'
import { useNoteStore } from '../stores/notes'
import { ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const reviewStore = useReviewStore()
const noteStore = useNoteStore()

const wrongAnswers = computed(() =>
  [...reviewStore.wrongAnswers].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
)

// Get reflection text: first from wrongAnswers item, then fallback to notes with sourceType 'wrong'
function getReflection(item: any): string {
  if (item.reflection) return item.reflection
  // Fallback: find matching note with sourceType 'wrong'
  const matchingNote = noteStore.notes.find(
    n => n.sourceType === 'wrong' && n.quote === item.question && n.nodeId === item.nodeId
  )
  if (matchingNote?.content) {
    // Extract reflection from the formatted note content
    const reflectionMatch = matchingNote.content.match(/\*\*💡 我的反思\*\*：\n([\s\S]*)$/)
    return reflectionMatch ? reflectionMatch[1]!.trim() : ''
  }
  return ''
}

function formatTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function retry(item: any) {
  // Send the wrong question to AI assistant for re-practice
  const prompt = `请帮我重新出一道关于以下知识点的类似题目：\n题目：${item.question}\n正确答案：${item.options[item.correctIndex]}\n章节：${item.nodeName}`
  courseStore.setPendingChatInput(prompt)
}

function retryAll() {
  reviewStore.generateSmartQuizFromMistakes()
  courseStore.showFloatingAI = true
  ElMessage.success('已生成错题复习，请查看 AI 助手')
}

function markDone(item: any) {
  reviewStore.markWrongAnswerReviewed(item.question, item.nodeId, true)
  ElMessage.success('已移除，继续加油')
}
</script>
