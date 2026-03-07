<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl flex items-center justify-center text-white"
             :class="activeTab === 'wrong' ? 'bg-gradient-to-br from-red-400 to-rose-500' : 'bg-gradient-to-br from-indigo-400 to-purple-500'">
          <el-icon :size="20"><Notebook /></el-icon>
        </div>
        <div>
          <h3 class="text-lg font-bold text-slate-800">{{ activeTab === 'wrong' ? '错题本' : '笔记本' }}</h3>
          <p class="text-xs text-slate-500">
            {{ activeTab === 'wrong' ? `共 ${wrongAnswers.length} 道错题` : `共 ${filteredNotes.length} 条笔记` }}
          </p>
        </div>
      </div>
      <div v-if="activeTab !== 'wrong'" class="flex items-center gap-2">
        <input v-model="search" type="text" placeholder="搜索笔记..." class="h-8 px-3 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary-300 focus:ring-2 focus:ring-primary-100 w-40" />
      </div>
    </div>

    <!-- Filter Tabs (hidden in wrong mode) -->
    <div v-if="activeTab !== 'wrong'" class="flex items-center gap-2 px-6 py-3 border-b border-slate-50 flex-shrink-0">
      <button v-for="tab in visibleTabs" :key="tab.key"
        class="px-3 py-1.5 text-xs font-medium rounded-lg transition-all"
        :class="activeTab === tab.key ? 'bg-primary-50 text-primary-600 border border-primary-200' : 'text-slate-500 hover:bg-slate-50'"
        @click="activeTab = tab.key">
        {{ tab.label }} ({{ tab.count }})
      </button>
    </div>

    <!-- ========== WRONG ANSWERS VIEW ========== -->
    <div v-if="activeTab === 'wrong'" class="flex-1 overflow-y-auto p-4 space-y-3">
      <div v-if="wrongAnswers.length === 0" class="flex flex-col items-center justify-center py-16 text-emerald-500">
        <el-icon :size="40" class="mb-3"><CircleCheckFilled /></el-icon>
        <p class="text-sm font-medium">暂无错题，继续保持</p>
      </div>

      <div v-for="item in wrongAnswers" :key="wrongItemKey(item)"
        class="bg-white rounded-xl border border-slate-100 hover:border-slate-200 transition-all overflow-hidden">
        
        <!-- Question Header (always visible, clickable) -->
        <div class="px-5 py-4 cursor-pointer flex items-start gap-3" @click="toggleExpand(wrongItemKey(item))">
          <span class="flex-shrink-0 w-7 h-7 rounded-lg bg-red-50 text-red-500 flex items-center justify-center text-sm font-bold">{{ wrongAnswers.indexOf(item) + 1 }}</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm text-slate-800 font-medium leading-relaxed">{{ item.question }}</div>
            <div class="flex items-center gap-2 mt-2 text-xs text-slate-400">
              <span>{{ item.nodeName }}</span>
              <span>·</span>
              <span>{{ formatTime(item.timestamp) }}</span>
              <span v-if="item.reviewCount > 0">· 已复习 {{ item.reviewCount }} 次</span>
            </div>
          </div>
          <el-icon :size="14" class="text-slate-400 mt-1 transition-transform duration-200" :class="{ 'rotate-180': expandedKey === wrongItemKey(item) }">
            <ArrowDown />
          </el-icon>
        </div>

        <!-- Expanded: Quiz Re-test -->
        <Transition name="expand">
          <div v-if="expandedKey === wrongItemKey(item)" class="border-t border-slate-100">
            <!-- Options (re-testable, only for structured items) -->
            <template v-if="item.options && item.options.length > 0">
              <div class="px-5 py-4 space-y-2 ml-10">
                <button
                  v-for="(opt, oIdx) in item.options"
                  :key="oIdx"
                  class="w-full text-left p-3 rounded-xl border transition-all duration-200 flex items-center gap-3"
                  :class="getRetestOptionClass(wrongItemKey(item), oIdx, item)"
                  :disabled="retestStates[wrongItemKey(item)]?.answered"
                  @click="handleRetestAnswer(wrongItemKey(item), oIdx, item)"
                >
                  <span class="w-6 h-6 rounded-lg border flex items-center justify-center text-[11px] font-bold flex-shrink-0"
                        :class="getRetestBadgeClass(wrongItemKey(item), oIdx, item)">
                    {{ String.fromCharCode(65 + oIdx) }}
                  </span>
                  <span class="text-sm">{{ opt }}</span>
                  <el-icon v-if="retestStates[wrongItemKey(item)]?.answered && oIdx === item.correctIndex" class="ml-auto text-emerald-500" :size="18"><CircleCheckFilled /></el-icon>
                  <el-icon v-else-if="retestStates[wrongItemKey(item)]?.answered && retestStates[wrongItemKey(item)]?.selected === oIdx && oIdx !== item.correctIndex" class="ml-auto text-red-500" :size="18"><CircleCloseFilled /></el-icon>
                </button>
              </div>

              <!-- Explanation (shown after answering) -->
              <div v-if="retestStates[wrongItemKey(item)]?.answered && item.explanation" class="px-5 pb-3 ml-10">
                <div class="bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <div class="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1">
                    <el-icon :size="12"><InfoFilled /></el-icon> 解析
                  </div>
                  <div class="text-sm text-slate-600 leading-relaxed">{{ item.explanation }}</div>
                </div>
              </div>
            </template>

            <!-- Legacy note-based wrong answer (no options) -->
            <template v-else>
              <div v-if="item.explanation" class="px-5 py-4 ml-10">
                <div class="bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <div class="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1">
                    <el-icon :size="12"><InfoFilled /></el-icon> 解析
                  </div>
                  <div class="text-sm text-slate-600 leading-relaxed">{{ item.explanation }}</div>
                </div>
              </div>
            </template>

            <!-- Reflection (if exists) -->
            <div v-if="item.reflection" class="px-5 pb-3 ml-10">
              <div class="bg-amber-50 rounded-xl p-4 border border-amber-100">
                <div class="text-xs font-bold text-amber-600 mb-1.5">💡 我的反思</div>
                <div class="text-sm text-amber-800 leading-relaxed whitespace-pre-wrap">{{ item.reflection }}</div>
              </div>
            </div>

            <!-- Wrong Note (separate from main notes) -->
            <div v-if="getWrongNote(item)" class="px-5 pb-3 ml-10">
              <div class="bg-blue-50 rounded-xl p-4 border border-blue-100">
                <div class="text-xs font-bold text-blue-600 mb-1.5 flex items-center justify-between">
                  <span>📝 错题笔记</span>
                  <button class="text-blue-400 hover:text-red-500 transition-colors" @click="deleteWrongNote(item)" title="删除笔记">
                    <el-icon :size="12"><Delete /></el-icon>
                  </button>
                </div>
                <div class="text-sm text-blue-800 leading-relaxed whitespace-pre-wrap">{{ getWrongNote(item) }}</div>
              </div>
            </div>

            <!-- Actions -->
            <div class="px-5 pb-4 flex items-center gap-2 ml-10">
              <button
                v-if="retestStates[wrongItemKey(item)]?.answered && item.options?.length > 0"
                class="px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors flex items-center gap-1.5"
                @click="resetRetest(wrongItemKey(item))"
              >
                <el-icon :size="12"><RefreshRight /></el-icon> 重测
              </button>
              <button
                class="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors flex items-center gap-1.5"
                @click="addWrongNote(item)"
              >
                <el-icon :size="12"><EditPen /></el-icon> 错题笔记
              </button>
              <button
                class="px-3 py-1.5 text-xs font-medium text-emerald-600 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors flex items-center gap-1.5"
                @click="markMastered(item)"
              >
                <el-icon :size="12"><CircleCheckFilled /></el-icon> 已掌握
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- ========== NOTES VIEW ========== -->
    <div v-else class="flex-1 overflow-y-auto p-4 space-y-3">
      <div v-if="filteredNotes.length === 0" class="flex flex-col items-center justify-center py-16 text-slate-400">
        <el-icon :size="40" class="mb-3"><Notebook /></el-icon>
        <p class="text-sm">{{ search ? '没有匹配的笔记' : '暂无笔记' }}</p>
        <p class="text-xs mt-1">选中课程内容文字即可添加笔记</p>
      </div>

      <div v-for="note in filteredNotes" :key="note.id"
        class="group bg-white rounded-xl border border-slate-100 hover:border-slate-200 hover:shadow-sm transition-all overflow-hidden">
        <div v-if="note.quote" class="px-4 pt-3 pb-1">
          <div class="text-xs text-slate-500 italic border-l-2 border-primary-300 pl-3 py-1 line-clamp-2">"{{ note.quote }}"</div>
        </div>
        <div class="px-4 py-3">
          <div class="text-sm text-slate-700 leading-relaxed line-clamp-4 whitespace-pre-wrap">{{ getPlainText(note.content) }}</div>
        </div>
        <div class="px-4 pb-3 flex items-center justify-between">
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <span class="px-1.5 py-0.5 rounded bg-slate-100" :class="{ 'bg-blue-50 text-blue-600': note.sourceType === 'ai' }">
              {{ note.sourceType === 'ai' ? 'AI' : '手动' }}
            </span>
            <span>{{ getNodeName(note.nodeId) }}</span>
            <span>{{ formatTime(note.createdAt) }}</span>
          </div>
          <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button class="p-1 rounded text-slate-400 hover:text-primary-600 hover:bg-primary-50 transition-colors" title="定位" @click="$emit('locate', note)">
              <el-icon :size="14"><Location /></el-icon>
            </button>
            <button class="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors" title="删除" @click="handleDelete(note)">
              <el-icon :size="14"><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { Notebook, Location, Delete, ArrowDown, CircleCheckFilled, CircleCloseFilled, InfoFilled, RefreshRight, EditPen } from '@element-plus/icons-vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useReviewStore } from '../stores/review'
import type { Note } from '../stores/types'
import { ElMessageBox, ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const reviewStore = useReviewStore()
const search = ref('')
const activeTab = ref('all')

defineProps<{
  initialTab?: string
}>()

defineEmits<{
  (e: 'locate', note: Note): void
}>()

defineExpose({ setTab: (tab: string) => { activeTab.value = tab } })

// ========== Notes Logic ==========
const allNotes = computed(() => noteStore.notes.filter(n => n.sourceType !== 'format' && n.sourceType !== 'wrong'))
const visibleTabs = computed(() => [
  { key: 'all', label: '全部', count: allNotes.value.length },
  { key: 'user', label: '手动', count: allNotes.value.filter(n => n.sourceType === 'user' || !n.sourceType).length },
  { key: 'ai', label: 'AI', count: allNotes.value.filter(n => n.sourceType === 'ai').length },
])

const filteredNotes = computed(() => {
  let notes = allNotes.value
  if (activeTab.value !== 'all' && activeTab.value !== 'wrong') {
    notes = notes.filter(n => {
      if (activeTab.value === 'user') return n.sourceType === 'user' || !n.sourceType
      return n.sourceType === activeTab.value
    })
  }
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    notes = notes.filter(n => n.content?.toLowerCase().includes(q) || n.quote?.toLowerCase().includes(q))
  }
  return notes.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
})

function getNodeName(nodeId: string) {
  return courseStore.nodes.find(n => n.node_id === nodeId)?.node_name || ''
}

function getPlainText(content: string) {
  return content?.replace(/[#*>`_~\[\]()!]/g, '').replace(/\n{2,}/g, '\n').trim().slice(0, 200) || ''
}

function formatTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function handleDelete(note: Note) {
  try {
    await ElMessageBox.confirm('确定删除这条笔记？', '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await noteStore.deleteNote(note.id)
    ElMessage.success('已删除')
  } catch {}
}

// ========== Wrong Answers Logic ==========
// Merge structured wrongAnswers with legacy note-based wrong answers

/** Stable key for a wrong-answer item. */
function wrongItemKey(item: any): string {
  return `${item.nodeId}_${item.timestamp}_${(item.question || '').slice(0, 60)}`
}

const wrongAnswers = computed(() => {
  const structured = [...reviewStore.wrongAnswers]
  const structuredQuestions = new Set(structured.map(w => w.question))
  
  // Parse legacy notes with sourceType 'wrong' that aren't in structured data
  const wrongNoteItems = noteStore.notes
    .filter(n => n.sourceType === 'wrong')
    .filter(n => !structuredQuestions.has(n.quote || ''))
    .map(n => {
      // Parse the formatted content to extract data
      const content = n.content || ''
      const questionMatch = content.match(/\*\*题目\*\*：(.+?)(?:\n|$)/)
      const explanationMatch = content.match(/\*\*解析\*\*：([\s\S]*?)(?:\n\n\*\*💡|$)/)
      const reflectionMatch = content.match(/\*\*💡 我的反思\*\*：\n([\s\S]*)$/)
      
      return {
        question: n.quote || questionMatch?.[1] || '未知题目',
        options: [] as string[],
        correctIndex: -1,
        userIndex: -1,
        explanation: explanationMatch?.[1]?.trim() || '',
        nodeId: n.nodeId || '',
        nodeName: getNodeName(n.nodeId || ''),
        timestamp: n.createdAt || 0,
        reviewCount: 0,
        reflection: reflectionMatch?.[1]?.trim() || '',
        _isLegacy: true
      }
    })
  
  return [...structured, ...wrongNoteItems].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
})

const expandedKey = ref<string | null>(null)
const retestStates = reactive<Record<string, { selected: number | null; answered: boolean }>>({})

// Wrong notes stored separately in localStorage
const wrongNotes = ref<Record<string, string>>(
  JSON.parse(localStorage.getItem('wrong_answer_notes') || '{}')
)

function saveWrongNotes() {
  localStorage.setItem('wrong_answer_notes', JSON.stringify(wrongNotes.value))
}

function getWrongNoteKey(item: any) {
  return `${item.nodeId}_${item.question.slice(0, 50)}`
}

function getWrongNote(item: any): string {
  if (!item) return ''
  return wrongNotes.value[getWrongNoteKey(item)] || ''
}

function toggleExpand(key: string) {
  expandedKey.value = expandedKey.value === key ? null : key
}

function handleRetestAnswer(key: string, optIdx: number, item: any) {
  if (retestStates[key]?.answered) return
  retestStates[key] = { selected: optIdx, answered: true }
  // Update review count
  if (optIdx === item.correctIndex) {
    reviewStore.markWrongAnswerReviewed(item.question, item.nodeId, false)
  }
}

function resetRetest(key: string) {
  retestStates[key] = { selected: null, answered: false }
}

function getRetestOptionClass(key: string, optIdx: number, item: any) {
  const state = retestStates[key]
  if (!state?.answered) {
    return 'border-slate-200 hover:border-primary-300 hover:bg-slate-50 text-slate-600'
  }
  if (optIdx === item.correctIndex) {
    return 'border-emerald-500 bg-emerald-50 text-emerald-700'
  }
  if (state.selected === optIdx && optIdx !== item.correctIndex) {
    return 'border-red-500 bg-red-50 text-red-700'
  }
  return 'border-slate-100 text-slate-400 opacity-60'
}

function getRetestBadgeClass(key: string, optIdx: number, item: any) {
  const state = retestStates[key]
  if (!state?.answered) {
    return 'border-slate-300 text-slate-500'
  }
  if (optIdx === item.correctIndex) {
    return 'border-emerald-500 bg-emerald-500 text-white'
  }
  if (state.selected === optIdx && optIdx !== item.correctIndex) {
    return 'border-red-500 bg-red-500 text-white'
  }
  return 'border-slate-200 text-slate-300'
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function addWrongNote(item: any) {
  const key = getWrongNoteKey(item)
  const existing = wrongNotes.value[key] || ''
  try {
    const result = await ElMessageBox.prompt('', '错题笔记', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: existing,
      inputPlaceholder: '记录你对这道题的理解、易错点、解题思路...',
      inputType: 'textarea',
    })
    const text = typeof result === 'string' ? result : (result as { value?: string }).value || ''
    if (text.trim()) {
      wrongNotes.value[key] = text.trim()
      saveWrongNotes()
      ElMessage.success('错题笔记已保存')
    }
  } catch {}
}

function deleteWrongNote(item: any) {
  if (!item) return
  delete wrongNotes.value[getWrongNoteKey(item)]
  saveWrongNotes()
  ElMessage.success('已删除')
}

function markMastered(item: any) {
  // Remove from structured wrongAnswers
  reviewStore.markWrongAnswerReviewed(item.question, item.nodeId, true)
  // Also remove legacy note-based wrong answers
  if ((item as any)._isLegacy) {
    const legacyNote = noteStore.notes.find(
      n => n.sourceType === 'wrong' && (n.quote === item.question || n.nodeId === item.nodeId) && n.createdAt === item.timestamp
    )
    if (legacyNote) {
      noteStore.deleteNote(legacyNote.id)
    }
  }
  expandedKey.value = null
  ElMessage.success('已标记为掌握')
}
</script>

<style scoped>
.expand-enter-active,
.expand-leave-active {
  transition: all 0.25s ease;
  max-height: 600px;
  opacity: 1;
}
.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
}
</style>
