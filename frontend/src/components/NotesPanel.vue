<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0 pr-14">
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
    <div v-if="activeTab === 'wrong' && !drillMode" class="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
      <!-- 闯关练习入口 -->
      <div v-if="wrongAnswers.filter(w => w.options && w.options.length > 0).length > 0" class="mb-2">
        <button @click="startDrill" class="w-full py-3 px-4 bg-gradient-to-r from-orange-400 to-rose-500 text-white rounded-xl font-medium text-sm flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-orange-200/50 transition-all active:scale-[0.98]">
          <el-icon :size="16"><TrophyBase /></el-icon> 闯关练习 · {{ wrongAnswers.filter(w => w.options && w.options.length > 0).length }} 题
        </button>
      </div>

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
            <div class="text-sm text-slate-800 font-medium leading-relaxed"><MarkdownRenderer :content="item.question" /></div>
            <div class="flex items-center gap-2 mt-2 text-xs text-slate-400">
              <span>{{ item.nodeName }}</span>
              <span>·</span>
              <span>{{ formatTime(item.timestamp) }}</span>
              <span v-if="item.reviewCount !== 0" class="px-1.5 py-0.5 rounded" :class="item.reviewCount < 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'">{{ formatScore(item.reviewCount) }}</span>
            </div>
          </div>
          <el-icon :size="14" class="text-slate-400 mt-1 transition-transform duration-200" :class="{ 'rotate-180': expandedKey === wrongItemKey(item) }">
            <ArrowDown />
          </el-icon>
        </div>

        <!-- Expanded: Quiz Re-test -->
        <Transition name="expand">
          <div v-if="expandedKey === wrongItemKey(item)" class="border-t border-slate-100">
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
                  <span class="text-sm"><MarkdownRenderer :content="opt" /></span>
                  <el-icon v-if="retestStates[wrongItemKey(item)]?.answered && oIdx === item.correctIndex" class="ml-auto text-emerald-500" :size="18"><CircleCheckFilled /></el-icon>
                  <el-icon v-else-if="retestStates[wrongItemKey(item)]?.answered && retestStates[wrongItemKey(item)]?.selected === oIdx && oIdx !== item.correctIndex" class="ml-auto text-red-500" :size="18"><CircleCloseFilled /></el-icon>
                </button>
              </div>
              <div v-if="retestStates[wrongItemKey(item)]?.answered && item.explanation" class="px-5 pb-3 ml-10">
                <div class="bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <div class="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1">
                    <el-icon :size="12"><InfoFilled /></el-icon> 解析
                  </div>
                  <div class="text-sm text-slate-600 leading-relaxed"><MarkdownRenderer :content="item.explanation" /></div>
                </div>
              </div>
            </template>
            <template v-else>
              <div v-if="item.explanation" class="px-5 py-4 ml-10">
                <div class="bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <div class="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1">
                    <el-icon :size="12"><InfoFilled /></el-icon> 解析
                  </div>
                  <div class="text-sm text-slate-600 leading-relaxed"><MarkdownRenderer :content="item.explanation" /></div>
                </div>
              </div>
            </template>
            <div v-if="item.reflection" class="px-5 pb-3 ml-10">
              <div class="bg-amber-50 rounded-xl p-4 border border-amber-100">
                <div class="text-xs font-bold text-amber-600 mb-1.5">💡 我的反思</div>
                <div class="text-sm text-amber-800 leading-relaxed whitespace-pre-wrap">{{ item.reflection }}</div>
              </div>
            </div>
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
            <!-- 文字草稿笔记 -->
            <div v-if="item.textDraft" class="px-5 pb-3 ml-10">
              <button v-if="!draftExpanded[wrongItemKey(item) + '_text']"
                class="px-3 py-1.5 text-xs font-medium text-violet-600 bg-violet-50 hover:bg-violet-100 rounded-lg transition-colors flex items-center gap-1.5"
                @click="draftExpanded[wrongItemKey(item) + '_text'] = true">
                📝 查看文字笔记
              </button>
              <div v-else class="bg-violet-50 rounded-xl p-4 border border-violet-100">
                <div class="text-xs font-bold text-violet-600 mb-1.5 flex items-center justify-between">
                  <span>📝 文字草稿</span>
                  <button class="text-violet-400 hover:text-violet-600 transition-colors" @click="draftExpanded[wrongItemKey(item) + '_text'] = false">
                    <el-icon :size="12"><ArrowDown /></el-icon>
                  </button>
                </div>
                <div class="text-sm text-violet-800 leading-relaxed whitespace-pre-wrap">{{ item.textDraft }}</div>
              </div>
            </div>
            <!-- 图画草稿笔记 -->
            <div v-if="item.drawingDraft" class="px-5 pb-3 ml-10">
              <button v-if="!draftExpanded[wrongItemKey(item) + '_draw']"
                class="px-3 py-1.5 text-xs font-medium text-orange-600 bg-orange-50 hover:bg-orange-100 rounded-lg transition-colors flex items-center gap-1.5"
                @click="draftExpanded[wrongItemKey(item) + '_draw'] = true">
                🎨 查看图画笔记
              </button>
              <div v-else class="bg-orange-50 rounded-xl p-4 border border-orange-100">
                <div class="text-xs font-bold text-orange-600 mb-1.5 flex items-center justify-between">
                  <span>🎨 图画草稿</span>
                  <button class="text-orange-400 hover:text-orange-600 transition-colors" @click="draftExpanded[wrongItemKey(item) + '_draw'] = false">
                    <el-icon :size="12"><ArrowDown /></el-icon>
                  </button>
                </div>
                <img :src="item.drawingDraft" class="max-w-full rounded-lg border border-orange-200" alt="图画草稿" @error="($event.target as HTMLImageElement).style.display='none'" />
              </div>
            </div>
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

    <!-- ========== 闯关练习模式 ========== -->
    <div v-else-if="activeTab === 'wrong' && drillMode" class="flex-1 flex flex-col overflow-hidden">
      <!-- 顶部进度条 -->
      <div class="px-5 pt-4 pb-3 flex-shrink-0">
        <div class="flex items-center justify-between mb-2">
          <button @click="exitDrill" class="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1 transition-colors">
            <el-icon :size="12"><ArrowLeft /></el-icon> 返回错题本
          </button>
          <span class="text-xs text-slate-500 font-medium">{{ drillIndex + 1 }} / {{ drillQuestions.length }}</span>
        </div>
        <div class="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div class="h-full bg-gradient-to-r from-orange-400 to-rose-500 rounded-full transition-all duration-300" :style="{ width: drillProgress + '%' }"></div>
        </div>
      </div>

      <!-- 答题完成页 -->
      <div v-if="drillFinished" class="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-orange-400 to-rose-500 flex items-center justify-center text-white mb-4">
          <el-icon :size="32"><TrophyBase /></el-icon>
        </div>
        <h3 class="text-lg font-bold text-slate-800 mb-1">练习完成</h3>
        <p class="text-sm text-slate-500 mb-6">共 {{ drillResults.length }} 题</p>
        <div class="flex gap-6 mb-6">
          <div class="text-center">
            <div class="text-2xl font-bold text-emerald-500">{{ drillResults.filter(r => r.correct).length }}</div>
            <div class="text-xs text-slate-400 mt-1">答对</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-bold text-red-500">{{ drillResults.filter(r => !r.correct).length }}</div>
            <div class="text-xs text-slate-400 mt-1">答错</div>
          </div>
          <div class="text-center">
            <div class="text-2xl font-bold text-purple-500">{{ drillResults.filter(r => r.mastered).length }}</div>
            <div class="text-xs text-slate-400 mt-1">已掌握</div>
          </div>
        </div>
        <div v-if="drillResults.length > 0" class="w-full max-w-xs space-y-1.5 mb-6">
          <div v-for="(r, i) in drillResults" :key="i" class="flex items-center gap-2 text-xs px-3 py-2 rounded-lg" :class="r.correct ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'">
            <el-icon :size="14"><CircleCheckFilled v-if="r.correct" /><CircleCloseFilled v-else /></el-icon>
            <span class="truncate flex-1">{{ r.question }}</span>
            <span v-if="r.mastered" class="text-purple-500 font-medium flex-shrink-0">已掌握</span>
          </div>
        </div>
        <button @click="exitDrill" class="px-6 py-2.5 bg-gradient-to-r from-orange-400 to-rose-500 text-white rounded-xl font-medium text-sm hover:shadow-lg transition-all">
          返回错题本
        </button>
      </div>

      <!-- 答题中 -->
      <div v-else-if="drillCurrent" class="flex-1 flex flex-col overflow-y-auto p-5">
        <div class="flex-1">
          <!-- 题目 -->
          <div class="mb-6">
            <div class="text-base text-slate-800 font-medium leading-relaxed"><MarkdownRenderer :content="drillCurrent.question" /></div>
            <div class="text-xs text-slate-400 mt-2">{{ drillCurrent.nodeName }}</div>
          </div>
          <!-- 选项 -->
          <div class="space-y-2.5">
            <button
              v-for="(opt, oIdx) in drillCurrent.options"
              :key="oIdx"
              class="w-full text-left p-4 rounded-xl border-2 transition-all duration-200 flex items-center gap-3"
              :class="drillOptionClass(oIdx)"
              :disabled="drillAnswered"
              @click="drillSelectOption(oIdx)"
            >
              <span class="w-7 h-7 rounded-lg border-2 flex items-center justify-center text-xs font-bold flex-shrink-0"
                    :class="drillBadgeClass(oIdx)">
                {{ String.fromCharCode(65 + oIdx) }}
              </span>
              <span class="text-sm flex-1"><MarkdownRenderer :content="opt" /></span>
              <el-icon v-if="drillAnswered && oIdx === drillCurrent.correctIndex" class="text-emerald-500" :size="20"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="drillAnswered && drillSelected === oIdx && oIdx !== drillCurrent.correctIndex" class="text-red-500" :size="20"><CircleCloseFilled /></el-icon>
            </button>
          </div>
          <!-- 解析 -->
          <div v-if="drillAnswered && drillCurrent.explanation" class="mt-4 bg-slate-50 rounded-xl p-4 border border-slate-100">
            <div class="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1">
              <el-icon :size="12"><InfoFilled /></el-icon> 解析
            </div>
            <div class="text-sm text-slate-600 leading-relaxed"><MarkdownRenderer :content="drillCurrent.explanation" /></div>
          </div>
          <!-- 草稿按钮 -->
          <div v-if="!drillAnswered" class="mt-4 flex items-center gap-2">
            <button
              class="px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5"
              :class="drillTextDraftVisible ? 'bg-blue-500 text-white' : 'bg-blue-50 text-blue-600 hover:bg-blue-100'"
              @click="drillTextDraftVisible = !drillTextDraftVisible"
            >
              <el-icon :size="12"><EditPen /></el-icon> 文字草稿
            </button>
            <button
              class="px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5"
              :class="drillDrawingOverlayVisible ? 'bg-orange-500 text-white' : 'bg-orange-50 text-orange-600 hover:bg-orange-100'"
              @click="drillDrawingOverlayVisible = !drillDrawingOverlayVisible"
            >
              🎨 图画草稿
            </button>
          </div>
        </div>
        <!-- 底部操作 -->
        <div class="pt-4 flex-shrink-0">
          <button v-if="!drillAnswered" @click="drillConfirm" :disabled="drillSelected === null"
            class="w-full py-3 rounded-xl font-medium text-sm transition-all"
            :class="drillSelected !== null ? 'bg-primary-500 text-white hover:bg-primary-600' : 'bg-slate-100 text-slate-400 cursor-not-allowed'">
            确认答案
          </button>
          <button v-else @click="drillNext"
            class="w-full py-3 bg-gradient-to-r from-orange-400 to-rose-500 text-white rounded-xl font-medium text-sm hover:shadow-lg transition-all flex items-center justify-center gap-1.5">
            {{ drillIndex >= drillQuestions.length - 1 ? '查看结果' : '下一题' }}
            <el-icon :size="14"><ArrowRight /></el-icon>
          </button>
        </div>
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
        class="group bg-white rounded-xl border border-slate-100 hover:border-slate-200 hover:shadow-sm transition-all overflow-hidden cursor-pointer"
        @click="$emit('viewDetail', note)">
        <div v-if="note.quote" class="px-4 pt-3 pb-1">
          <div class="text-xs text-slate-500 italic border-l-2 border-primary-300 pl-3 py-1 line-clamp-2"><MarkdownRenderer :content="note.quote" /></div>
        </div>
        <div class="px-4 py-3">
          <div class="text-sm text-slate-700 leading-relaxed line-clamp-4"><MarkdownRenderer :content="note.content" /></div>
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

  <!-- 闯关练习草稿面板 (Teleport 到 body) -->
  <Teleport to="body">
    <TextDraftPanel
      v-model:visible="drillTextDraftVisible"
      :question-index="0"
    />
  </Teleport>
  <Teleport to="body">
    <DrawingOverlay
      v-model:visible="drillDrawingOverlayVisible"
      :question-index="0"
    />
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { Notebook, Location, Delete, ArrowDown, CircleCheckFilled, CircleCloseFilled, InfoFilled, RefreshRight, EditPen, TrophyBase, ArrowRight, ArrowLeft } from '@element-plus/icons-vue'
import TextDraftPanel from './TextDraftPanel.vue'
import DrawingOverlay from './DrawingOverlay.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useReviewStore } from '../stores/review'
import { useDraftStore } from '../stores/draft'
import type { Note } from '../stores/types'
import { ElMessageBox, ElMessage } from 'element-plus'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const reviewStore = useReviewStore()
const draftStore = useDraftStore()
const search = ref('')
const activeTab = ref('all')
const draftExpanded = reactive<Record<string, boolean>>({})
const drillTextDraftVisible = ref(false)
const drillDrawingOverlayVisible = ref(false)

defineProps<{
  initialTab?: string
}>()

defineEmits<{
  (e: 'locate', note: Note): void
  (e: 'viewDetail', note: Note): void
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
  // 只显示当前课程的错题
  const currentNodeIds = new Set(courseStore.nodes.map(n => n.node_id))
  const structured = reviewStore.wrongAnswers.filter(w => currentNodeIds.has(w.nodeId))
  const structuredQuestions = new Set(structured.map(w => w.question))
  
  // Parse legacy notes with sourceType 'wrong' that aren't in structured data
  const wrongNoteItems = noteStore.notes
    .filter(n => n.sourceType === 'wrong')
    .filter(n => currentNodeIds.has(n.nodeId || ''))
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

// ========== 闯关练习 ==========
const drillMode = ref(false)
const drillQuestions = ref<any[]>([])
const drillIndex = ref(0)
const drillSelected = ref<number | null>(null)
const drillAnswered = ref(false)
const drillResults = ref<Array<{ question: string, correct: boolean, mastered: boolean }>>([])
const drillFinished = ref(false)

const drillCurrent = computed(() => drillQuestions.value[drillIndex.value] || null)
const drillProgress = computed(() => drillQuestions.value.length > 0 ? Math.round(((drillIndex.value + (drillAnswered.value ? 1 : 0)) / drillQuestions.value.length) * 100) : 0)

function startDrill() {
  // 只取有选项的结构化错题，打乱顺序
  const eligible = wrongAnswers.value.filter(w => w.options && w.options.length > 0 && w.correctIndex >= 0)
  if (eligible.length === 0) {
    ElMessage.warning('没有可练习的选择题')
    return
  }
  drillQuestions.value = [...eligible].sort(() => Math.random() - 0.5)
  drillIndex.value = 0
  drillSelected.value = null
  drillAnswered.value = false
  drillResults.value = []
  drillFinished.value = false
  drillTextDraftVisible.value = false
  drillDrawingOverlayVisible.value = false
  // 加载第一题的草稿到 draftStore
  draftStore.clearAll()
  loadDrillDrafts(0)
  drillMode.value = true
}

function drillSelectOption(idx: number) {
  if (drillAnswered.value) return
  drillSelected.value = idx
}

function drillConfirm() {
  if (drillSelected.value === null || !drillCurrent.value) return
  drillAnswered.value = true
  const correct = drillSelected.value === drillCurrent.value.correctIndex
  // 保存修改后的草稿回错题记录
  saveDrillDrafts(drillIndex.value)
  const mastered = reviewStore.updateDrillResult(drillCurrent.value.question, drillCurrent.value.nodeId, correct)
  drillResults.value.push({ question: drillCurrent.value.question, correct, mastered })
}

function drillNext() {
  if (drillIndex.value >= drillQuestions.value.length - 1) {
    drillFinished.value = true
    drillTextDraftVisible.value = false
    drillDrawingOverlayVisible.value = false
    draftStore.clearAll()
    return
  }
  drillIndex.value++
  drillSelected.value = null
  drillAnswered.value = false
  // 加载下一题的草稿
  draftStore.clearAll()
  loadDrillDrafts(drillIndex.value)
}

function exitDrill() {
  // 中途退出时，保存当前题的草稿
  saveDrillDrafts(drillIndex.value)
  drillMode.value = false
  drillFinished.value = false
  drillTextDraftVisible.value = false
  drillDrawingOverlayVisible.value = false
  draftStore.clearAll()
}

/** 从错题记录加载草稿到 draftStore（用 index=0 作为当前题的 key） */
function loadDrillDrafts(idx: number) {
  const q = drillQuestions.value[idx]
  if (!q) return
  if (q.textDraft) draftStore.setTextDraft(0, q.textDraft)
  if (q.drawingDraft) draftStore.setDrawingDraft(0, q.drawingDraft)
}

/** 将 draftStore 中的草稿保存回错题记录 */
function saveDrillDrafts(idx: number) {
  const q = drillQuestions.value[idx]
  if (!q) return
  const text = draftStore.getTextDraft(0)
  const drawing = draftStore.getDrawingDraft(0)
  // 更新 drillQuestions 中的引用（它们是 wrongAnswers 的浅拷贝）
  // 需要找到 reviewStore 中的原始记录并更新
  const original = reviewStore.wrongAnswers.find(
    w => w.question === q.question && w.nodeId === q.nodeId
  )
  if (original) {
    original.textDraft = text || undefined
    original.drawingDraft = drawing || undefined
    reviewStore.persistQuizData()
  }
}

function drillOptionClass(oIdx: number): string {
  if (!drillAnswered.value) {
    return drillSelected.value === oIdx
      ? 'border-primary-400 bg-primary-50 text-primary-700'
      : 'border-slate-200 hover:border-primary-300 hover:bg-slate-50 text-slate-600'
  }
  if (oIdx === drillCurrent.value?.correctIndex) {
    return 'border-emerald-500 bg-emerald-50 text-emerald-700'
  }
  if (drillSelected.value === oIdx && oIdx !== drillCurrent.value?.correctIndex) {
    return 'border-red-500 bg-red-50 text-red-700'
  }
  return 'border-slate-100 text-slate-400 opacity-60'
}

function drillBadgeClass(oIdx: number): string {
  if (!drillAnswered.value) {
    return drillSelected.value === oIdx
      ? 'border-primary-400 bg-primary-500 text-white'
      : 'border-slate-300 text-slate-500'
  }
  if (oIdx === drillCurrent.value?.correctIndex) {
    return 'border-emerald-500 bg-emerald-500 text-white'
  }
  if (drillSelected.value === oIdx && oIdx !== drillCurrent.value?.correctIndex) {
    return 'border-red-500 bg-red-500 text-white'
  }
  return 'border-slate-200 text-slate-300'
}

function formatScore(reviewCount: number): string {
  if (reviewCount < 0) return `答对 ${Math.abs(reviewCount)} 次`
  if (reviewCount === 0) return '未练习'
  return `答错 ${reviewCount} 次`
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
