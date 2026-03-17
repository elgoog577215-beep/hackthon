<template>
  <div class="border-t border-slate-200/50 mt-2">
    <!-- 折叠标题栏 -->
    <button
      class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-50/80 transition-colors"
      @click="collapsed = !collapsed"
    >
      <div class="flex items-center gap-2">
        <div class="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white flex-shrink-0">
          <el-icon :size="14"><User /></el-icon>
        </div>
        <span class="text-sm font-medium text-slate-700">学习者画像</span>
        <span v-if="profileStore.isGenerating" class="text-xs text-violet-500 animate-pulse">生成中...</span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="profileStore.lastUpdated" class="text-xs text-slate-400">
          {{ formatTime(profileStore.lastUpdated) }}
        </span>
        <el-icon :size="14" class="text-slate-400 transition-transform" :class="{ 'rotate-180': !collapsed }">
          <ArrowDown />
        </el-icon>
      </div>
    </button>

    <!-- 展开内容 -->
    <div v-show="!collapsed" class="px-4 pb-3 space-y-3 max-h-[50vh] overflow-y-auto custom-scrollbar">
      <!-- 空状态 -->
      <div v-if="!profileStore.hasProfile && !profileStore.isGenerating" class="text-center py-6">
        <div class="w-10 h-10 mx-auto rounded-xl bg-violet-50 flex items-center justify-center mb-2">
          <el-icon :size="20" class="text-violet-400"><User /></el-icon>
        </div>
        <p class="text-xs text-slate-400 mb-3">开始学习后将自动生成画像</p>
        <el-button size="small" type="primary" plain @click="confirmGenerate" :loading="profileStore.isGenerating">
          立即生成
        </el-button>
      </div>

      <!-- 画像内容 -->
      <template v-if="profileStore.hasProfile">
        <!-- 重新生成遮罩 -->
        <div v-if="profileStore.isGenerating" class="rounded-lg border border-violet-200 bg-violet-50/60 p-4 flex flex-col items-center justify-center gap-2 profile-regenerating">
          <div class="flex items-center gap-2">
            <el-icon class="animate-spin text-violet-500" :size="18"><Loading /></el-icon>
            <span class="text-sm text-violet-600 font-medium">正在重新生成画像...</span>
          </div>
          <div class="w-full h-1 rounded-full bg-violet-100 overflow-hidden mt-1">
            <div class="h-full bg-violet-400 rounded-full animate-progress-bar"></div>
          </div>
        </div>

        <!-- AI 画像区块 -->
        <div v-else class="space-y-3 profile-content-enter">
          <div class="rounded-lg bg-slate-50/80 border border-slate-100 p-3">
            <div class="flex items-center gap-1.5 mb-2 text-xs font-semibold text-violet-600">
              <el-icon :size="12"><MagicStick /></el-icon>
              <span>AI 画像</span>
            </div>
            <div class="prose prose-sm prose-slate text-xs leading-relaxed max-h-60 overflow-y-auto custom-scrollbar">
              <MarkdownRenderer :content="profileStore.aiProfile" />
            </div>
          </div>

          <!-- Agent 评论区块 -->
          <div v-if="profileStore.agentCommentary" class="rounded-lg bg-violet-50/50 border border-violet-100 p-3">
            <div class="flex items-center gap-1.5 mb-2 text-xs font-semibold text-purple-600">
              <el-icon :size="12"><ChatDotRound /></el-icon>
              <span>学习伙伴的话</span>
            </div>
            <div class="prose prose-sm prose-slate text-xs leading-relaxed max-h-60 overflow-y-auto custom-scrollbar">
              <MarkdownRenderer :content="profileStore.agentCommentary" />
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="flex gap-2">
          <el-button size="small" plain @click="confirmRegenerate" :loading="profileStore.isGenerating" :disabled="profileStore.isGenerating">
            重新生成
          </el-button>
        </div>
      </template>

      <!-- 加载状态 -->
      <div v-if="profileStore.isGenerating && !profileStore.hasProfile" class="flex items-center justify-center py-6 gap-2">
        <el-icon class="animate-spin text-violet-500" :size="16"><Loading /></el-icon>
        <span class="text-xs text-slate-500">正在分析学习数据...</span>
      </div>

      <!-- 自评输入区 -->
      <div class="space-y-1.5">
        <div class="text-xs font-medium text-slate-500">自我评价</div>
        <el-input
          v-model="selfEvalText"
          type="textarea"
          :rows="2"
          placeholder="写下你对自己学习情况的看法..."
          resize="none"
          size="small"
        />
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="!selfEvalText.trim() || profileStore.isGenerating"
          :loading="profileStore.isGenerating"
          @click="handleSubmitSelfEval"
        >
          提交自评
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useProfileStore } from '../stores/profile'
import { useReviewStore } from '../stores/review'
import { useNoteStore } from '../stores/notes'
import { useCourseStore } from '../stores/course'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { User, ArrowDown, MagicStick, ChatDotRound, Loading } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

const profileStore = useProfileStore()
const reviewStore = useReviewStore()
const noteStore = useNoteStore()
const courseStore = useCourseStore()

const collapsed = ref(true)
const selfEvalText = ref('')

onMounted(() => {
  profileStore.restore(courseStore.currentCourseId)
  selfEvalText.value = profileStore.selfEvaluation
  // 有画像时默认展开
  if (profileStore.hasProfile) collapsed.value = false
})

// 切换课程时恢复对应画像
watch(() => courseStore.currentCourseId, (newId) => {
  if (newId) {
    profileStore.restore(newId)
    selfEvalText.value = profileStore.selfEvaluation
    collapsed.value = !profileStore.hasProfile
  }
})

// 增量自动更新：监听错题/笔记/聊天变化
watch(() => reviewStore.wrongAnswers.length, (newLen, oldLen) => {
  if (newLen > oldLen && profileStore.hasProfile) {
    profileStore.scheduleUpdate('新增错题记录')
  }
})

watch(() => noteStore.notes.length, (newLen, oldLen) => {
  if (newLen > oldLen && profileStore.hasProfile) {
    profileStore.scheduleUpdate('新增笔记')
  }
})

watch(() => courseStore.chatHistory.length, (newLen, oldLen) => {
  if (newLen > oldLen + 1 && profileStore.hasProfile) {
    // 至少新增一对对话（user+ai）才触发
    profileStore.scheduleUpdate('新增问答对话')
  }
})

function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function buildChatSummary(): string {
  // 取最近20条对话，提取文本
  const recent = courseStore.chatHistory.slice(-20)
  return recent.map(msg => {
    const role = msg.type === 'user' ? '用户' : 'AI'
    const text = typeof msg.content === 'string'
      ? msg.content
      : ((msg.content as any).core_answer || (msg.content as any).answer || '')
    return `${role}: ${text.slice(0, 150)}`
  }).join('\n')
}

async function handleGenerate() {
  const wrongAnswers = reviewStore.wrongAnswers
  const notes = noteStore.notes.map(n => ({ content: n.content, nodeId: n.nodeId, sourceType: n.sourceType, quote: n.quote }))
  const chatSummary = buildChatSummary()
  await profileStore.generateFull(wrongAnswers, notes, chatSummary)
  if (profileStore.hasProfile) collapsed.value = false
}

async function confirmGenerate() {
  try {
    await ElMessageBox.confirm(
      '全量生成画像会将所有错题、笔记和对话数据发送给 AI 分析，数据量较大时可能需要较长时间。确认生成？',
      '确认生成画像',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'info' }
    )
    await handleGenerate()
  } catch {
    // 用户取消
  }
}

async function confirmRegenerate() {
  try {
    await ElMessageBox.confirm(
      '全量重新生成画像将重新分析所有学习数据，可能需要较长时间并消耗 API 额度。建议不要频繁操作。',
      '确认重新生成',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
    await handleGenerate()
  } catch {
    // 用户取消
  }
}

async function handleSubmitSelfEval() {
  await profileStore.submitSelfEvaluation(selfEvalText.value.trim())
}
</script>

<style scoped>
@keyframes progress-bar {
  0% { width: 0%; margin-left: 0; }
  50% { width: 60%; margin-left: 20%; }
  100% { width: 0%; margin-left: 100%; }
}
.animate-progress-bar {
  animation: progress-bar 1.8s ease-in-out infinite;
}
.profile-regenerating {
  animation: fade-in 0.3s ease;
}
.profile-content-enter {
  animation: content-appear 0.4s ease;
}
@keyframes fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes content-appear {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
