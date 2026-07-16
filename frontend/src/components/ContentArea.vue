<template>
  <div class="h-full flex flex-col relative">
    <!-- Reading Progress Bar - Positioned below header -->
    <div class="absolute top-0 left-0 right-0 h-1 bg-slate-100/50 z-10" v-if="scrollProgress > 0">
        <div class="h-full bg-gradient-to-r from-primary-400 to-primary-600 transition-all duration-300 ease-out shadow-[0_0_10px_rgba(99,102,241,0.5)]" :style="{ width: scrollProgress + '%' }"></div>
    </div>

    <div
        v-if="courseStore.currentCourseId && !isGenerationPreview"
        class="absolute top-3 right-3 z-20 inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium shadow-sm backdrop-blur-md"
        :class="learningSyncClass"
        :title="t('courseWorkspace.learningSession.title', '学习现场')"
    >
        <component :is="learningSyncIcon" :size="14" :class="{ 'animate-spin': learningSessionStore.status === 'syncing' || learningSessionStore.status === 'loading' }" />
        <span class="hidden sm:inline">{{ learningSyncLabel }}</span>
    </div>

    <!-- Image Lightbox -->
    <Teleport to="body">
        <transition name="fade">
            <div v-if="lightboxVisible" class="fixed inset-0 z-[100] bg-black/90 backdrop-blur-md flex items-center justify-center cursor-zoom-out" @click="lightboxVisible = false">
                <img :src="lightboxImage" class="max-w-[95vw] max-h-[95vh] object-contain rounded-lg shadow-2xl transition-transform duration-300 scale-100 hover:scale-[1.02]" alt="Full screen preview" />
                <button type="button" class="absolute top-4 right-4 text-white/50 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors" :aria-label="t('common.close', '关闭')" @click.stop="lightboxVisible = false">
                    <el-icon :size="32"><Close /></el-icon>
                </button>
            </div>
        </transition>
    </Teleport>

    <!-- Export Dialog -->
    <Teleport to="body">
        <transition name="fade-scale">
            <div v-if="exportDialog.visible" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <!-- Backdrop -->
                <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeExportDialog"></div>
                
                <!-- Dialog Content -->
                <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all">
                    <!-- Header -->
                    <div class="px-6 py-5 bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                                <el-icon class="text-white" :size="24"><Download /></el-icon>
                            </div>
                            <div>
                                <h3 class="text-lg font-bold text-white">{{ exportDialog.title }}</h3>
                                <p class="text-sm text-white/80">{{ exportDialog.subtitle }}</p>
                            </div>
                        </div>
                        <button @click="closeExportDialog" class="w-8 h-8 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/20 rounded-lg transition-all">
                            <el-icon :size="20"><Close /></el-icon>
                        </button>
                    </div>
                    
                    <!-- Body -->
                    <div class="p-6 space-y-4">
                        <!-- Export Scope -->
                        <div class="space-y-2">
                            <label class="text-sm font-medium text-slate-700">导出范围</label>
                            <div class="grid grid-cols-3 gap-2">
                                <button 
                                    v-for="scope in exportScopes" 
                                    :key="scope.value"
                                    @click="exportDialog.scope = scope.value"
                                    class="px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 border-2"
                                    :class="exportDialog.scope === scope.value 
                                        ? 'border-primary-500 bg-primary-50 text-primary-700' 
                                        : 'border-slate-100 bg-slate-50 text-slate-600 hover:border-slate-200 hover:bg-slate-100'"
                                >
                                    <div class="flex flex-col items-center gap-1">
                                        <el-icon :size="18"><component :is="scope.icon" /></el-icon>
                                        <span>{{ scope.label }}</span>
                                    </div>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Export Format -->
                        <div class="space-y-2">
                            <label class="text-sm font-medium text-slate-700">导出格式</label>
                            <div class="grid grid-cols-2 gap-3">
                                <button 
                                    v-for="fmt in exportFormats" 
                                    :key="fmt.value"
                                    @click="exportDialog.format = fmt.value"
                                    class="relative px-4 py-4 rounded-xl text-left transition-all duration-200 border-2 group"
                                    :class="exportDialog.format === fmt.value 
                                        ? 'border-primary-500 bg-primary-50/50' 
                                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'"
                                >
                                    <div class="flex items-start gap-3">
                                        <div class="w-10 h-10 rounded-lg flex items-center justify-center transition-colors"
                                            :class="exportDialog.format === fmt.value ? 'bg-primary-100' : 'bg-slate-100 group-hover:bg-slate-200'">
                                            <el-icon :size="20" :class="exportDialog.format === fmt.value ? 'text-primary-600' : 'text-slate-500'">
                                                <component :is="fmt.icon" />
                                            </el-icon>
                                        </div>
                                        <div class="flex-1">
                                            <div class="font-semibold text-slate-800">{{ fmt.label }}</div>
                                            <div class="text-xs text-slate-500 mt-0.5">{{ fmt.desc }}</div>
                                        </div>
                                        <div v-if="exportDialog.format === fmt.value" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary-500 flex items-center justify-center">
                                            <el-icon class="text-white" :size="12"><Check /></el-icon>
                                        </div>
                                    </div>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Export Preview -->
                        <div class="bg-slate-50 rounded-xl p-4 space-y-2">
                            <div class="flex items-center justify-between text-sm">
                                <span class="text-slate-500">预计导出</span>
                                <span class="font-semibold text-slate-800">{{ getExportCount }} 条笔记</span>
                            </div>
                            <div class="flex items-center justify-between text-sm">
                                <span class="text-slate-500">文件大小</span>
                                <span class="font-semibold text-slate-800">约 {{ getExportSize }}</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
                        <button @click="closeExportDialog" class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-200/50 rounded-lg transition-all">
                            取消
                        </button>
                        <button 
                            @click="executeExport" 
                            :disabled="exportDialog.loading"
                            class="px-5 py-2 bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-600 hover:to-primary-700 text-white text-sm font-medium rounded-lg shadow-lg shadow-primary-500/25 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <el-icon v-if="exportDialog.loading" class="is-loading"><Loading /></el-icon>
                            <el-icon v-else><Download /></el-icon>
                            {{ exportDialog.loading ? '导出中...' : '开始导出' }}
                        </button>
                    </div>
                </div>
            </div>
        </transition>
    </Teleport>

    <!-- Settings Dialog -->
    <Teleport to="body">
        <transition name="fade-scale">
            <div v-if="settingsDialog.visible" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeSettingsDialog"></div>
                <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform transition-all">
                    <div class="px-6 py-5 bg-gradient-to-r from-primary-500 to-primary-600 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                                <el-icon class="text-white" :size="24"><Setting /></el-icon>
                            </div>
                            <div>
                                <h3 class="text-lg font-bold text-white">阅读设置</h3>
                                <p class="text-sm text-white/80">自定义阅读体验</p>
                            </div>
                        </div>
                        <button @click="closeSettingsDialog" class="w-8 h-8 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/20 rounded-lg transition-all">
                            <el-icon :size="20"><Close /></el-icon>
                        </button>
                    </div>
                    <div class="p-6 space-y-6">
                        <!-- Font Size -->
                        <div class="space-y-3">
                            <div class="flex items-center justify-between">
                                <label class="text-sm font-medium text-slate-700">字体大小</label>
                                <span class="text-xs text-slate-500">{{ settingsDialog.fontSize }}px</span>
                            </div>
                            <el-slider v-model="settingsDialog.fontSize" :min="12" :max="24" :step="1" show-stops />
                            <div class="flex justify-between text-xs text-slate-400">
                                <span>小</span>
                                <span>中</span>
                                <span>大</span>
                            </div>
                        </div>
                        <!-- Line Height -->
                        <div class="space-y-3">
                            <div class="flex items-center justify-between">
                                <label class="text-sm font-medium text-slate-700">行高</label>
                                <span class="text-xs text-slate-500">{{ settingsDialog.lineHeight }}</span>
                            </div>
                            <el-slider v-model="settingsDialog.lineHeight" :min="1.2" :max="2.0" :step="0.1" show-stops />
                        </div>
                        <!-- Font Family -->
                        <div class="space-y-3">
                            <label class="text-sm font-medium text-slate-700">字体</label>
                            <div class="grid grid-cols-3 gap-2">
                                <button v-for="font in fontOptions" :key="font.value"
                                    @click="settingsDialog.fontFamily = font.value"
                                    class="px-3 py-2 rounded-xl text-sm transition-all border-2"
                                    :class="settingsDialog.fontFamily === font.value 
                                        ? 'border-primary-500 bg-primary-50 text-primary-700' 
                                        : 'border-slate-100 bg-slate-50 text-slate-600 hover:border-slate-200'"
                                    :style="{ fontFamily: font.value }">
                                    {{ font.label }}
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
                        <button @click="closeSettingsDialog" class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-200/50 rounded-lg transition-all">取消</button>
                        <button @click="applySettings" class="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-all flex items-center gap-2">
                            <el-icon><Check /></el-icon>应用设置
                        </button>
                    </div>
                </div>
            </div>
        </transition>
    </Teleport>

    <!-- Content List (Continuous Scroll) -->
    <div class="flex-1 overflow-auto p-3 lg:p-5 xl:p-6 relative custom-scrollbar" style="scroll-behavior: auto;" id="content-scroll-container" @mouseup="handleMouseUp" @click="handleContentClick">
        <InlineAnnotationLayer ref="annotationLayerRef" :notes="displayedQuotedNotes" @open="openInlineRecord" />
        <InlineRecordPopover
            :visible="inlineRecord.visible"
            :note="inlineRecord.note"
            :x="inlineRecord.x"
            :y="inlineRecord.y"
            :interactive="inlineRecord.interactive"
            :initial-edit="inlineRecord.initialEdit"
            :save-state="inlineRecord.saveState"
            @close="closeInlineRecord"
            @save="saveInlineRecord"
            @retry="retryInlineRecord"
            @undo="undoInlineRecord"
            @delete="deleteInlineRecord"
            @ask-ai="askAiFromInlineRecord"
        />

        <!-- Selection Menu -->
    <Teleport to="body">
      <transition name="scale-fade">
        <div v-if="selectionMenu.visible && !isGenerationPreview"
            id="selection-menu"
            class="fixed z-50 flex flex-col p-1.5 bg-white/95 backdrop-blur-xl rounded-lg shadow-[0_12px_40px_rgba(0,0,0,0.15)] border border-white/40 ring-1 ring-black/5 min-w-[300px] select-none"
            :style="{ 
                left: selectionMenu.x + 'px', 
                top: selectionMenu.y + 'px', 
                transform: selectionMenu.placement === 'bottom' ? 'translateX(-50%)' : 'translate(-50%, -100%)' 
            }"
            @mousedown.stop>
            
            <!-- Row 1: Quick Actions -->
            <div class="flex items-center gap-1 pb-1.5 mb-1.5 border-b border-slate-100">
                <el-tooltip :content="t('courseWorkspace.records.ask', '问 AI')" placement="top" :show-after="500">
                    <button @click="handleAsk" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-primary-600 hover:bg-primary-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><ChatDotRound /></el-icon> 
                        <span class="text-[10px] font-bold">{{ t('courseWorkspace.records.ask', '问 AI') }}</span>
                    </button>
                </el-tooltip>
                
                <div class="w-px h-6 bg-slate-100"></div>
                
                <el-tooltip :content="t('courseWorkspace.records.note', '记笔记')" placement="top" :show-after="500">
                    <button @click="handleAddNote" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-amber-600 hover:bg-amber-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><ChatLineSquare /></el-icon> 
                        <span class="text-[10px] font-bold">{{ t('courseWorkspace.records.note', '记笔记') }}</span>
                    </button>
                </el-tooltip>
                
                <div class="w-px h-6 bg-slate-100"></div>
                
                <el-tooltip :content="t('courseWorkspace.records.later', '稍后处理')" placement="top" :show-after="500">
                    <button @click="laterMenuVisible = !laterMenuVisible" class="flex-1 relative z-10 flex flex-col items-center justify-center gap-0.5 px-2 py-1.5 rounded-xl text-slate-600 hover:text-rose-600 hover:bg-rose-50 transition-all group active:scale-95">
                        <el-icon class="text-lg mb-0.5"><Timer /></el-icon>
                        <span class="text-[10px] font-bold">{{ t('courseWorkspace.records.later', '稍后处理') }}</span>
                    </button>
                </el-tooltip>
            </div>

            <div v-if="laterMenuVisible" class="grid grid-cols-3 gap-1 pb-1.5 mb-1.5 border-b border-slate-100">
                <button class="record-later-option" @click="handleLater('issue')">{{ t('courseWorkspace.records.issue', '这里不懂') }}</button>
                <button class="record-later-option" @click="handleLater('review_task')">{{ t('courseWorkspace.records.review', '需要复习') }}</button>
                <button class="record-later-option" @click="handleLater('bookmark')">{{ t('courseWorkspace.records.bookmark', '仅做书签') }}</button>
            </div>

            <!-- Row 2: Formatting -->
            <div class="flex items-center justify-between px-1">
                <!-- Colors -->
                <div class="flex gap-1.5 bg-slate-50 p-1 rounded-lg">
                    <button v-for="color in [
                            { name: 'yellow', class: 'bg-yellow-400' },
                            { name: 'green', class: 'bg-green-400' },
                            { name: 'blue', class: 'bg-blue-400' },
                            { name: 'pink', class: 'bg-pink-400' },
                            { name: 'orange', class: 'bg-orange-400' }
                            ]" :key="color.name"
                            class="w-4 h-4 rounded-full border border-black/5 hover:scale-125 hover:border-black/10 transition-transform relative cursor-pointer"
                            :class="color.class"
                            @click="applyFormat('highlight', color.name)"
                            :title="color.name">
                    </button>
                </div>
                
                <!-- Styles -->
                <div class="flex gap-1">
                    <el-tooltip content="加粗 (Ctrl+B)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 font-bold text-sm transition-colors" @click="applyFormat('bold')">B</button>
                    </el-tooltip>
                    <el-tooltip content="下划线 (Ctrl+U)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 underline text-sm transition-colors" @click="applyFormat('underline', 'solid')">U</button>
                    </el-tooltip>
                    <el-tooltip content="波浪线 (Ctrl+I)" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 decoration-wavy underline text-sm transition-colors" @click="applyFormat('underline', 'wavy')">~</button>
                    </el-tooltip>
                    <el-tooltip content="清除格式" placement="bottom" :show-after="500">
                        <button class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-600 text-sm transition-colors" @click="clearFormats()">✕</button>
                    </el-tooltip>
                </div>
            </div>
            
            <!-- Arrow -->
            <div v-if="selectionMenu.placement === 'bottom'" class="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-t border-l border-white/40 rotate-45 shadow-[-2px_-2px_4px_rgba(0,0,0,0.02)]" :style="{ marginLeft: selectionMenu.arrowOffset + 'px' }"></div>
            <div v-else class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-b border-r border-white/40 rotate-45 shadow-[4px_4px_4px_rgba(0,0,0,0.05)]" :style="{ marginLeft: selectionMenu.arrowOffset + 'px' }"></div>
        </div>
      </transition>
    </Teleport>

      <div v-if="flatNodes.length > 0" class="flex w-full h-full relative">


        <!-- Main Content Column -->
        <div class="flex-1 min-w-0 px-2 sm:px-3 lg:px-4 xl:px-6 pb-24 sm:pb-28 lg:pb-32 pt-2 sm:pt-3 lg:pt-4">
            <div
                ref="virtualListRef"
                class="relative w-full mt-8 sm:mt-10 lg:mt-12"
                :style="{ height: totalNodesHeight + 'px' }"
            >
                <div
                    v-for="(node, index) in visibleNodes"
                    :key="node.node_id"
                    class="absolute left-0 right-0"
                    :style="{ transform: `translateY(${nodeTop(visibleNodeStart + index)}px)` }"
                >
                    <CourseNode
                        :node="node"
                        :index="getChapterIndex(node, visibleNodeStart + index)"
                        :font-size="fontSize"
                        :font-family="fontFamily"
                        :line-height="lineHeight"
                        :records="inlineRecordsForNode(node.node_id)"
                        :search-words="searchTokens"
                        :is-streaming="node.generation_status === 'generating'"
                        :generation-preview="isGenerationPreview"
                        :can-improve-blocks="!isGenerationPreview && courseStore.currentCourseSourceFormat === 'canonical'"
                        @start-practice="handleStartPractice"
                        @open-record="openInlineRecord"
                        @improve-block="emit('improveBlock', $event)"
                    />
                </div>
            </div>
        </div>
        
      </div>
      
      <!-- Mobile Notes Drawer moved to end -->

      <!-- Empty Selection Guide -->
      <div v-else-if="!courseStore.currentCourseId" class="flex flex-col items-center justify-center h-full text-slate-400 animate-in fade-in zoom-in duration-500">
          <div class="w-32 h-32 bg-slate-50 rounded-full flex items-center justify-center mb-6 shadow-inner relative overflow-hidden">
              <div class="absolute inset-0 bg-gradient-to-tr from-slate-100 to-transparent opacity-50"></div>
              <el-icon :size="48" class="opacity-30 text-slate-500"><Notebook /></el-icon>
          </div>
          <h3 class="text-xl font-bold text-slate-600 mb-2">开始您的学习之旅</h3>
          <p class="text-sm font-medium opacity-60">请从左侧选择一个课程或章节开始阅读</p>
      </div>
      
      <!-- Loading State -->
      <div v-else-if="isGenerationPreview" class="generation-empty-state">
          <LoaderCircle :size="22" class="generation-empty-state__spin" />
          <div>
              <strong>{{ t('courseGeneration.workspace.preparing', '正在准备课程结构') }}</strong>
              <span>{{ t('courseGeneration.workspace.contentWillAppear', '目录与正文会随着真实生成结果逐步出现') }}</span>
          </div>
      </div>

      <div v-else class="flex flex-col items-center justify-center h-64 gap-4">
          <div class="w-12 h-12 border-4 border-primary-200 border-t-primary-500 rounded-full animate-spin"></div>
          <p class="text-sm text-slate-500 font-medium animate-pulse">正在加载精彩内容...</p>
      </div>

    </div>


    <!-- Back to Top Button -->
    <Teleport to="body">
        <transition name="back-to-top">
            <button v-if="showBackToTop" 
                    class="back-to-top p-3 bg-white/90 backdrop-blur-md border border-slate-200 rounded-full shadow-lg text-slate-500 hover:text-primary-600 hover:border-primary-300 hover:shadow-xl hover:shadow-primary-100/50 transition-all active:scale-95"
                    :style="backToTopStyle"
                    @click="scrollToTop">
                <el-icon :size="20"><ArrowUp /></el-icon>
            </button>
        </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick, reactive } from 'vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useLearningSessionStore } from '../stores/learningSession'

import CourseNode from './CourseNode.vue'
import InlineAnnotationLayer from './InlineAnnotationLayer.vue'
import InlineRecordPopover from './InlineRecordPopover.vue'
import { Download, Notebook, Close, ChatLineSquare, Timer, ArrowUp, ChatDotRound, Loading, Setting, Check } from '@element-plus/icons-vue'

import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import logger from '../utils/logger'
import { captureViewportAnchor, resolvedAnchorScrollTop } from '@/utils/learning-position'
import { buildTextQuoteAnchor, resolveTextQuoteAnchor } from '@/utils/text-anchor'
import { t } from '@/shared/i18n'
import { Cloud, CloudOff, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { CourseBlockEditTarget, Note } from '@/stores/types'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')


const props = defineProps<{
  sideAiPanelVisible?: boolean
}>()

const emit = defineEmits<{
  (e: 'quoteAsk', payload: { text: string; nodeId: string; anchor?: Record<string, unknown> }): void
  (e: 'startPractice', node: any): void
  (e: 'improveBlock', payload: CourseBlockEditTarget): void
}>()

const laterMenuVisible = ref(false)
const annotationLayerRef = ref<InstanceType<typeof InlineAnnotationLayer> | null>(null)

// Handle clicks inside content (Copy buttons, etc.)
const handleContentClick = async (e: MouseEvent) => {
    const target = e.target as HTMLElement

    // Handle Copy Button
    const btn = target.closest('.copy-btn') as HTMLElement
    if (btn) {
        const code = decodeURIComponent(btn.dataset.code || '')
        if (code) {
            try {
                await navigator.clipboard.writeText(code)
                const originalHTML = btn.innerHTML
                btn.innerHTML = '<span class="text-green-400 font-bold">OK</span>'
                btn.classList.add('bg-green-500/20')
                setTimeout(() => {
                    btn.innerHTML = originalHTML
                    btn.classList.remove('bg-green-500/20')
                }, 2000)
                ElMessage.success('代码已复制')
            } catch (err) {
                ElMessage.error('复制失败')
            }
        }
        return
    }
    
    // Handle Image Click (Lightbox)
    if (target.tagName === 'IMG' && target.closest('.content-render')) {
        lightboxImage.value = (target as HTMLImageElement).src
        lightboxVisible.value = true
    }
}

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const workspaceStore = useCourseWorkspaceStore()
const learningSessionStore = useLearningSessionStore()
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const learningSyncLabel = computed(() => t(
    `courseWorkspace.learningSession.${learningSessionStore.status}`,
    learningSessionStore.status,
))
const learningSyncIcon = computed(() => {
    if (learningSessionStore.status === 'loading' || learningSessionStore.status === 'syncing') return LoaderCircle
    if (learningSessionStore.status === 'offline') return CloudOff
    if (learningSessionStore.status === 'conflict') return TriangleAlert
    return Cloud
})
const learningSyncClass = computed(() => {
    if (learningSessionStore.status === 'offline') return 'border-amber-200 bg-amber-50/95 text-amber-800'
    if (learningSessionStore.status === 'conflict') return 'border-red-200 bg-red-50/95 text-red-700'
    if (learningSessionStore.status === 'pending' || learningSessionStore.status === 'syncing') return 'border-sky-200 bg-white/95 text-sky-700'
    return 'border-slate-200 bg-white/90 text-slate-600'
})
const selectionMenu = ref({ visible: false, x: 0, y: 0, arrowOffset: 0, placement: 'top', text: '', range: null as Range | null })
const noteSearchQuery = ref('')
const activeNoteFilter = ref('notes')

// Note filter states
const selectedTagFilter = ref('')
const selectedCategoryFilter = ref('')
const selectedPriorityFilter = ref<'low' | 'medium' | 'high' | ''>('')

// Export dialog state
const exportDialog = reactive({
    visible: false,
    title: '导出笔记',
    subtitle: '选择导出范围和格式',
    type: 'notes' as 'notes' | 'mistakes',
    scope: 'all' as 'all' | 'filtered' | 'current',
    format: 'markdown' as 'markdown' | 'json',
    loading: false
})

// Export scope options
const exportScopes: { value: 'all' | 'filtered' | 'current', label: string, icon: string }[] = [
    { value: 'all', label: '全部', icon: 'Collection' },
    { value: 'filtered', label: '已筛选', icon: 'Filter' },
    { value: 'current', label: '当前视图', icon: 'View' }
]

// Export format options
const exportFormats: { value: 'markdown' | 'json', label: string, desc: string, icon: string }[] = [
    { value: 'markdown', label: 'Markdown', desc: '适合阅读和编辑', icon: 'Document' },
    { value: 'json', label: 'JSON', desc: '结构化数据格式', icon: 'DataLine' }
]

// Computed export count
const getExportCount = computed(() => {
    let notes: any[] = []
    if (exportDialog.type === 'mistakes') {
        notes = noteStore.notes.filter((n: any) => n.sourceType === 'wrong' || n.content.includes('#错题'))
    } else {
        notes = noteStore.notes.filter(note => !note.recordType || note.recordType === 'note')
    }
    
    if (exportDialog.scope === 'filtered') {
        notes = notes.filter((note: any) => {
            if (selectedTagFilter.value && !note.tags?.includes(selectedTagFilter.value)) return false
            if (selectedCategoryFilter.value && note.category !== selectedCategoryFilter.value) return false
            if (selectedPriorityFilter.value && note.priority !== selectedPriorityFilter.value) return false
            return true
        })
    } else if (exportDialog.scope === 'current') {
        notes = notes.filter((note: any) => {
            if (activeNoteFilter.value === 'mistakes') {
                return note.sourceType === 'wrong' || note.content.includes('#错题')
            }
            return note.sourceType !== 'wrong' && !note.content.includes('#错题')
        })
    }
    
    return notes.length
})

// Computed export size estimate
const getExportSize = computed(() => {
    const count = getExportCount.value
    if (count === 0) return '0 KB'
    const avgSize = exportDialog.format === 'markdown' ? 2 : 5 // KB per note estimate
    const totalSize = count * avgSize
    if (totalSize < 1024) return `${totalSize} KB`
    return `${(totalSize / 1024).toFixed(1)} MB`
})

// Close export dialog
const closeExportDialog = () => {
    exportDialog.visible = false
    exportDialog.loading = false
}

// Execute export
const executeExport = async () => {
    exportDialog.loading = true
    
    try {
        let notes: any[] = []
        
        if (exportDialog.type === 'mistakes') {
            notes = noteStore.notes.filter((n: any) => n.sourceType === 'wrong' || n.content.includes('#错题'))
        } else {
            notes = noteStore.notes.filter(note => !note.recordType || note.recordType === 'note')
        }
        
        // Apply scope filter
        if (exportDialog.scope === 'filtered') {
            notes = notes.filter((note: any) => {
                if (selectedTagFilter.value && !note.tags?.includes(selectedTagFilter.value)) return false
                if (selectedCategoryFilter.value && note.category !== selectedCategoryFilter.value) return false
                if (selectedPriorityFilter.value && note.priority !== selectedPriorityFilter.value) return false
                return true
            })
        } else if (exportDialog.scope === 'current') {
            notes = notes.filter((note: any) => {
                if (activeNoteFilter.value === 'mistakes') {
                    return note.sourceType === 'wrong' || note.content.includes('#错题')
                }
                return note.sourceType !== 'wrong' && !note.content.includes('#错题')
            })
        }
        
        if (notes.length === 0) {
            ElMessage.warning('没有可导出的内容')
            exportDialog.loading = false
            return
        }
        
        if (exportDialog.format === 'markdown') {
            await exportToMarkdown(notes, exportDialog.type)
            ElMessage.success(`成功导出 ${notes.length} 条笔记为 Markdown`)
        } else {
            await exportToJSON(notes, exportDialog.type)
            ElMessage.success(`成功导出 ${notes.length} 条笔记为 JSON`)
        }
        
        closeExportDialog()
    } catch (error) {
        logger.error('Export failed:', error)
        ElMessage.error('导出失败，请重试')
    } finally {
        exportDialog.loading = false
    }
}

// Export to Markdown
const exportToMarkdown = async (notes: any[], type: 'notes' | 'mistakes') => {
    const title = type === 'mistakes' ? '错题本' : '学习笔记'
    let markdown = `# ${title}\n\n`
    markdown += `导出时间: ${dayjs().format('YYYY-MM-DD HH:mm')}\n\n`
    markdown += `共 ${notes.length} 条记录\n\n---\n\n`
    
    notes.forEach((note: any, index: number) => {
        if (type === 'mistakes') {
            markdown += `## 错题 ${index + 1}\n\n`
        } else {
            const noteType = note.sourceType === 'ai' ? 'AI问答' : 
                           note.sourceType === 'wrong' ? '错题' : '笔记'
            markdown += `## ${noteType} ${index + 1}\n\n`
        }
        
        if (note.category) {
            markdown += `**分类:** ${note.category}\n\n`
        }
        if (note.tags?.length) {
            markdown += `**标签:** ${note.tags.join(', ')}\n\n`
        }
        if (note.priority) {
            const priorityText: Record<string, string> = { high: '高', medium: '中', low: '低' }
            markdown += `**优先级:** ${priorityText[note.priority as string] || note.priority}\n\n`
        }
        
        markdown += `**来源章节:** ${getNodeName(note.nodeId)}\n\n`
        markdown += `**内容:**\n${note.content}\n\n`
        
        if (note.quote) {
            markdown += `**原文引用:**\n> ${note.quote}\n\n`
        }
        if (note.aiResponse) {
            markdown += `**AI回复:**\n${note.aiResponse}\n\n`
        }
        
        markdown += `**记录时间:** ${dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')}\n\n`
        markdown += '---\n\n'
    })
    
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const fileName = type === 'mistakes' ? '错题本' : '学习笔记'
    a.download = `${fileName}_${dayjs().format('YYYYMMDD')}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
}

// Export to JSON
const exportToJSON = async (notes: any[], type: 'notes' | 'mistakes') => {
    const data = {
        exportType: type,
        exportTime: dayjs().format('YYYY-MM-DD HH:mm'),
        totalCount: notes.length,
        courseName: courseStore.currentCourse?.course_name || '未知课程',
        notes: notes.map((note: any) => ({
            id: note.id,
            type: note.sourceType || 'note',
            nodeId: note.nodeId,
            nodeName: getNodeName(note.nodeId),
            content: note.content,
            quote: note.quote,
            aiResponse: note.aiResponse,
            category: note.category,
            tags: note.tags || [],
            priority: note.priority,
            createdAt: note.createdAt,
            formattedDate: dayjs(note.createdAt).format('YYYY-MM-DD HH:mm')
        }))
    }
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const fileName = type === 'mistakes' ? '错题本' : '学习笔记'
    a.download = `${fileName}_${dayjs().format('YYYYMMDD')}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
}

// Settings dialog state
const settingsDialog = reactive({
    visible: false,
    fontSize: 16,
    fontFamily: 'system-ui, -apple-system, sans-serif',
    lineHeight: 1.6
})

// Font options
const fontOptions = [
    { value: 'system-ui, -apple-system, sans-serif', label: '系统默认' },
    { value: '"Noto Serif SC", "Source Han Serif SC", serif', label: '思源宋体' },
    { value: '"Noto Sans SC", "Source Han Sans SC", sans-serif', label: '思源黑体' },
    { value: '"JetBrains Mono", "Fira Code", monospace', label: '等宽字体' }
]

// Close settings dialog
const closeSettingsDialog = () => {
    settingsDialog.visible = false
}

// Apply settings
const applySettings = () => {
    courseStore.setUiSettings({
        fontSize: settingsDialog.fontSize,
        fontFamily: settingsDialog.fontFamily as 'sans' | 'serif' | 'mono',
        lineHeight: settingsDialog.lineHeight
    })
    ElMessage.success('设置已应用')
    closeSettingsDialog()
}

const scrollProgress = ref(0)
const lightboxVisible = ref(false)
const lightboxImage = ref('')

const debounce = <T extends (...args: any[]) => void>(fn: T, delay: number): ((...args: Parameters<T>) => void) => {
    let timeout: ReturnType<typeof setTimeout> | null = null
    return (...args: Parameters<T>) => {
        if (timeout) clearTimeout(timeout)
        timeout = setTimeout(() => fn(...args), delay)
    }
}

const refreshInlineAnnotations = () => annotationLayerRef.value?.refresh()
const debouncedRefreshAnnotations = debounce(refreshInlineAnnotations, 100)

let rafUpdateId: number | null = null
const rafRefreshAnnotations = () => {
    if (rafUpdateId) cancelAnimationFrame(rafUpdateId)
    rafUpdateId = requestAnimationFrame(() => {
        refreshInlineAnnotations()
        rafUpdateId = null
    })
}

// Watch for scroll requests from sidebar
/**
 * 智能滚动：近距离平滑滚动，远距离做精美瞬移动画
 * @param container 滚动容器
 * @param targetTop 目标 scrollTop 值（远距离时仅作粗定位，之后会精修）
 * @param threshold 距离阈值（px），超过则使用瞬移动画，默认 1500
 */
const smartScrollTo = (container: HTMLElement, targetTop: number, threshold = 1500): Promise<void> => {
    return new Promise((resolve) => {
        const distance = Math.abs(container.scrollTop - targetTop)
        if (distance < threshold) {
            container.scrollTo({ top: targetTop, behavior: 'smooth' })
            setTimeout(resolve, Math.min(distance * 0.5, 600))
        } else {
            // 远距离：淡出 → 瞬移 → 淡入（不使用 scale 避免布局抖动）
            container.style.transition = 'opacity 150ms ease-in'
            container.style.opacity = '0'
            setTimeout(() => {
                container.scrollTop = targetTop
                container.style.transition = 'opacity 200ms ease-out'
                void container.offsetHeight
                container.style.opacity = '1'
                setTimeout(() => {
                    container.style.transition = ''
                    container.style.opacity = ''
                    resolve()
                }, 210)
            }, 160)
        }
    })
}

/**
 * 智能滚动到指定元素，使用 getBoundingClientRect 计算精确位置
 * @param el 目标元素
 * @param container 滚动容器
 * @param topOffset 元素顶部距容器顶部的期望距离（px）
 */
const scrollToElementInContainer = async (el: HTMLElement, container: HTMLElement, topOffset = 20): Promise<void> => {
    const elRect = el.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()
    const targetTop = Math.max(0, container.scrollTop + (elRect.top - containerRect.top) - topOffset)
    await smartScrollTo(container, targetTop)
}

watch(() => courseStore.scrollToNodeId, async (nodeId) => {
    if (!nodeId) return
    
    isManualScrolling.value = true
    
    const scrollContainer = document.getElementById('content-scroll-container')
    if (!scrollContainer) { isManualScrolling.value = false; return }
    
    // 先精确匹配 node_id，找不到则按名称模糊匹配
    let targetNodeId = nodeId
    let index = flatNodes.value.findIndex(n => n.node_id === targetNodeId)
    if (index === -1) {
        const match = flatNodes.value.find(n => 
            n.node_name === nodeId || 
            n.node_name?.includes(nodeId) || 
            nodeId.includes(n.node_name || '')
        )
        if (match) {
            targetNodeId = match.node_id
            index = flatNodes.value.findIndex(n => n.node_id === targetNodeId)
        }
    }

    // 禁用动画：新渲染的节点有 fade-in-up + translateY(10px) 和 animationDelay，
    // 会导致 getBoundingClientRect 在动画完成前返回错误位置
    scrollContainer.classList.add('skip-animations')

    if (index !== -1) {
        await renderAroundIndex(index)
        const targetTop = (virtualListRef.value?.offsetTop ?? 0) + nodeTop(index) - 20
        scrollContainer.scrollTop = Math.max(0, targetTop)
        scheduleWindowUpdate(scrollContainer)
        await nextTick()
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(undefined))))
    }
    
    let element: HTMLElement | null = null
    for (let attempt = 0; attempt < 20; attempt++) {
        element = document.getElementById(`node-${targetNodeId}`)
        if (element) break
        await new Promise(r => setTimeout(r, 60))
    }
    
    if (element) {
        // 直接跳转到目标位置
        const rect = element.getBoundingClientRect()
        const containerRect = scrollContainer.getBoundingClientRect()
        const targetTop = Math.max(0, scrollContainer.scrollTop + (rect.top - containerRect.top) - 20)
        scrollContainer.scrollTop = targetTop

        // 二次校准
        await new Promise(r => setTimeout(r, 100))
        const rect2 = element.getBoundingClientRect()
        const containerRect2 = scrollContainer.getBoundingClientRect()
        const offset = rect2.top - containerRect2.top - 20
        if (Math.abs(offset) > 3) {
            scrollContainer.scrollTop += offset
        }
    }
    
    // 恢复动画
    scrollContainer.classList.remove('skip-animations')
    setTimeout(() => { isManualScrolling.value = false }, 600)
})

// Watch for focus note requests (AI Teacher Mode)
watch(() => courseStore.focusNoteId, (noteId) => {
    if (noteId) {
        // Wait for DOM update (highlights to be applied)
        nextTick(() => {
            scrollToNote(noteId)
        })
    }
})

const isManualScrolling = ref(false)
const activeNoteId = ref<string | null>(null)
const hoveredNoteId = ref<string | null>(null)
const inlineRecord = reactive({
    visible: false,
    x: 0,
    y: 0,
    note: null as Note | null,
    interactive: false,
    initialEdit: false,
    saveState: 'idle' as 'idle' | 'saving' | 'saved' | 'local_only',
})
const fontSize = computed(() => courseStore.uiSettings.fontSize)
const fontFamily = computed(() => courseStore.uiSettings.fontFamily)
const lineHeight = computed(() => courseStore.uiSettings.lineHeight)

// Notes Logic
const flatNodes = computed(() => {
    if (!courseStore.treeData || courseStore.treeData.length === 0) return []
    const nodes: any[] = []
    const traverse = (data: any[]) => {
        for (const node of data) {
            nodes.push(node)
            if (node.children && node.children.length > 0) {
                traverse(node.children)
            }
        }
    }
    traverse(courseStore.treeData)
    if (!isGenerationPreview.value) return nodes
    return nodes.filter(node => (
        node.node_id === courseStore.currentNode?.node_id
        || Boolean(node.node_content)
        || ['generating', 'completed', 'error'].includes(String(node.generation_status || ''))
    ))
})

// --- Performance Optimization: windowed rendering ---
// ponytail: keep this local until dynamic-height edge cases justify a virtual-list dependency.
const VIRTUAL_BUFFER_PX = 1400
const VIRTUAL_MIN_ITEMS = 24
const VIRTUAL_JUMP_PADDING = 10
const virtualListRef = ref<HTMLElement | null>(null)
const renderWindow = ref({ start: 0, end: VIRTUAL_MIN_ITEMS })
const measuredNodeHeights = reactive(new Map<string, number>())
let virtualRafId = 0

const nodeGap = () => {
    if (window.innerWidth >= 1024) return 48
    if (window.innerWidth >= 640) return 40
    return 32
}

const estimatedNodeHeight = (node: any) => {
    const contentLength = (node.node_content || '').length
    if (node.node_level === 1) return 520
    if (node.node_level === 2) return 460 + Math.min(contentLength * 0.22, 560)
    return Math.max(190, Math.min(760, 150 + contentLength * 0.28))
}

const nodeHeight = (node: any) => measuredNodeHeights.get(node.node_id) ?? estimatedNodeHeight(node)

const nodeLayout = computed(() => {
    const offsets: number[] = []
    let total = 0
    for (const node of flatNodes.value) {
        offsets.push(total)
        total += nodeHeight(node) + nodeGap()
    }
    return { offsets, total }
})

const totalNodesHeight = computed(() => nodeLayout.value.total)
const visibleNodeStart = computed(() => renderWindow.value.start)

const visibleNodes = computed(() => {
    const nodes = flatNodes.value || []
    const start = Math.min(renderWindow.value.start, nodes.length)
    const end = Math.min(Math.max(renderWindow.value.end, start), nodes.length)
    return nodes.slice(start, end)
})

const nodeTop = (index: number) => nodeLayout.value.offsets[index] ?? 0

const windowForScroll = (container: HTMLElement) => {
    const nodes = flatNodes.value
    if (nodes.length === 0) return { start: 0, end: 0 }

    const listOffsetTop = virtualListRef.value?.offsetTop ?? 0
    const top = Math.max(0, container.scrollTop - listOffsetTop - VIRTUAL_BUFFER_PX)
    const bottom = Math.max(top, container.scrollTop - listOffsetTop + container.clientHeight + VIRTUAL_BUFFER_PX)
    const offsets = nodeLayout.value.offsets

    let start = 0
    while (start < nodes.length - 1 && (offsets[start + 1] ?? 0) < top) start += 1

    let end = start + 1
    while (end < nodes.length && (offsets[end] ?? 0) < bottom) end += 1

    if (end - start < VIRTUAL_MIN_ITEMS) {
        const extra = Math.ceil((VIRTUAL_MIN_ITEMS - (end - start)) / 2)
        start = Math.max(0, start - extra)
        end = Math.min(nodes.length, Math.max(end + extra, start + VIRTUAL_MIN_ITEMS))
    }

    return { start, end }
}

const setRenderWindow = (next: { start: number; end: number }) => {
    if (renderWindow.value.start === next.start && renderWindow.value.end === next.end) return
    renderWindow.value = next
}

const measureVisibleNodeHeights = () => {
    let changed = false
    for (const node of visibleNodes.value) {
        const el = document.getElementById(`node-${node.node_id}`)
        if (!el) continue
        const measured = Math.ceil(el.getBoundingClientRect().height)
        if (measured > 0 && Math.abs((measuredNodeHeights.get(node.node_id) ?? 0) - measured) > 2) {
            measuredNodeHeights.set(node.node_id, measured)
            changed = true
        }
    }
    if (changed) debouncedRefreshAnnotations()
}

const scheduleWindowUpdate = (container?: HTMLElement | null) => {
    if (virtualRafId) return
    virtualRafId = requestAnimationFrame(() => {
        virtualRafId = 0
        const scrollContainer = container || document.getElementById('content-scroll-container')
        if (scrollContainer) setRenderWindow(windowForScroll(scrollContainer))
        nextTick(() => measureVisibleNodeHeights())
    })
}

const renderAroundIndex = async (index: number) => {
    const nodes = flatNodes.value
    if (index < 0 || index >= nodes.length) return
    setRenderWindow({
        start: Math.max(0, index - VIRTUAL_JUMP_PADDING),
        end: Math.min(nodes.length, index + VIRTUAL_JUMP_PADDING + 1),
    })
    await nextTick()
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(undefined))))
    measureVisibleNodeHeights()
}

// 为 level 2 节点计算章节编号（跳过 root），其他 level 返回原始 index（仅用于动画延迟）
const chapterIndexMap = computed(() => {
    const map = new Map<string, number>()
    let chapterCount = 0
    for (const node of flatNodes.value) {
        if (node.node_level === 2) {
            map.set(node.node_id, chapterCount++)
        }
    }
    return map
})

function getChapterIndex(node: any, flatIndex: number): number {
    if (node.node_level === 2) {
        return chapterIndexMap.value.get(node.node_id) ?? flatIndex
    }
    return flatIndex
}


watch(() => flatNodes.value.length, () => {
    setRenderWindow({
        start: Math.min(renderWindow.value.start, Math.max(0, flatNodes.value.length - 1)),
        end: Math.min(Math.max(renderWindow.value.end, VIRTUAL_MIN_ITEMS), flatNodes.value.length),
    })
    nextTick(() => scheduleWindowUpdate())
})

watch(
    () => isGenerationPreview.value
        ? courseStore.nodes.map(node => `${node.node_id}:${node.node_content?.length || 0}:${node.generation_status || ''}`).join('|')
        : '',
    () => {
        for (const node of courseStore.nodes) {
            if (node.generation_status === 'generating') measuredNodeHeights.delete(node.node_id)
        }
        scheduleWindowUpdate()
    },
    { flush: 'post' },
)

// Reset when course changes significantly
watch(() => courseStore.currentCourseId, () => {
    measuredNodeHeights.clear()
    renderWindow.value = { start: 0, end: VIRTUAL_MIN_ITEMS }
})
// ------------------------------------------------

const nodeNameMap = computed(() => new Map(flatNodes.value.map(n => [n.node_id, n.node_name])))

// Export functions have been replaced by the new export dialog

const isSearching = ref(false)
const debouncedSearchQuery = ref('')
const searchTokens = computed(() => {
    const query = debouncedSearchQuery.value.toLowerCase().trim()
    if (!query) return []
    return query.split(/\s+/).filter(Boolean)
})


// Debounce logic
let searchTimeout: ReturnType<typeof setTimeout> | null = null
const handleSearchInput = (val: string) => {
    const nextVal = val || ''
    if (!nextVal.trim()) {
        debouncedSearchQuery.value = ''
        isSearching.value = false
        if (searchTimeout) clearTimeout(searchTimeout)
        return
    }
    isSearching.value = true
    if (searchTimeout) clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => {
        debouncedSearchQuery.value = nextVal
        isSearching.value = false
    }, 300)
}

watch(noteSearchQuery, (val) => {
    handleSearchInput(val)
})

// Also react to global search from App header
watch(() => courseStore.globalSearchQuery, (val) => {
    handleSearchInput(val || '')
})

const isMistakeNote = (note: any) => {
    if (note.sourceType === 'wrong') return true
    return note.content.includes('**错题记录**') || note.content.includes('#错题')
}

const noteColorPalette = ['amber', 'emerald', 'sky', 'violet', 'orange', 'rose']
const defaultNoteStyle = { dot: 'bg-amber-400', highlight: 'bg-amber-200/50 border-b-2 border-amber-400 hover:bg-amber-300/50', border: 'border-amber-200/80', badge: 'text-amber-600 bg-amber-50 border-amber-100', quote: 'border-amber-400' }

const noteColorMap: Record<string, { dot: string; highlight: string; border: string; badge: string; quote: string }> = {
    amber: defaultNoteStyle,
    emerald: { dot: 'bg-emerald-400', highlight: 'bg-emerald-200/50 border-b-2 border-emerald-400 hover:bg-emerald-300/50', border: 'border-emerald-200/80', badge: 'text-emerald-600 bg-emerald-50 border-emerald-100', quote: 'border-emerald-400' },
    sky: { dot: 'bg-sky-400', highlight: 'bg-sky-200/50 border-b-2 border-sky-400 hover:bg-sky-300/50', border: 'border-sky-200/80', badge: 'text-sky-600 bg-sky-50 border-sky-100', quote: 'border-sky-400' },
    violet: { dot: 'bg-violet-400', highlight: 'bg-violet-200/50 border-b-2 border-violet-400 hover:bg-violet-300/50', border: 'border-violet-200/80', badge: 'text-violet-600 bg-violet-50 border-violet-100', quote: 'border-violet-400' },
    orange: { dot: 'bg-orange-400', highlight: 'bg-orange-200/50 border-b-2 border-orange-400 hover:bg-orange-300/50', border: 'border-orange-200/80', badge: 'text-orange-600 bg-orange-50 border-orange-100', quote: 'border-orange-400' },
    rose: { dot: 'bg-rose-400', highlight: 'bg-rose-200/50 border-b-2 border-rose-400 hover:bg-rose-300/50', border: 'border-rose-200/80', badge: 'text-rose-600 bg-rose-50 border-rose-100', quote: 'border-rose-400' },
    purple: { dot: 'bg-purple-400', highlight: 'bg-purple-200/50 border-b-2 border-purple-400 hover:bg-purple-300/50', border: 'border-purple-200/80', badge: 'text-purple-600 bg-purple-50 border-purple-100', quote: 'border-purple-400' },
    red: { dot: 'bg-red-400', highlight: 'bg-red-200/50 border-b-2 border-red-400 hover:bg-red-300/50', border: 'border-red-200/80', badge: 'text-red-600 bg-red-50 border-red-100', quote: 'border-red-400' }
}

const formatHighlightMap: Record<string, string> = {
    yellow: 'bg-yellow-200/50 hover:bg-yellow-300/50',
    green: 'bg-green-200/50 hover:bg-green-300/50',
    blue: 'bg-blue-200/50 hover:bg-blue-300/50',
    pink: 'bg-pink-200/50 hover:bg-pink-300/50',
    orange: 'bg-orange-200/50 hover:bg-orange-300/50',
    purple: 'bg-purple-200/50 hover:bg-purple-300/50'
}

const hashSeed = (value: string) => {
    let hash = 0
    for (let i = 0; i < value.length; i++) {
        hash = (hash * 31 + value.charCodeAt(i)) % 100000
    }
    return hash
}

const pickPaletteColor = (seed: string) => {
    if (noteColorPalette.length === 0) return 'amber'
    const index = hashSeed(seed) % noteColorPalette.length
    return noteColorPalette[index] ?? 'amber'
}

const resolveNoteColor = (note: any) => {
    if (!note) return 'amber'
    if (note.sourceType === 'ai') return 'purple'
    if (isMistakeNote(note)) return 'red'
    if (note.color && note.color !== 'transparent' && note.color !== 'blue') return note.color
    const seed = note.highlightId || note.id || `${note.nodeId}-${note.createdAt}`
    return pickPaletteColor(seed)
}

const noteHighlightClass = (color: string) => (noteColorMap[color] || defaultNoteStyle).highlight

const noteSearchText = (note: any) => {
    const nodeName = nodeNameMap.value.get(note.nodeId) || ''
    const parts = [note.content, note.quote, note.anno_summary, note.title, nodeName]
    return parts.filter(Boolean).join(' ').toLowerCase()
}

const noteMatchesSearch = (note: any, tokens: string[]) => {
    if (tokens.length === 0) return true
    const text = noteSearchText(note)
    return tokens.every(token => text.includes(token))
}

const visibleNotes = computed(() => {
    const nodeIds = new Set(flatNodes.value.map(n => n.node_id))
    let notes = noteStore.notes.filter(n => nodeIds.has(n.nodeId) && (!n.recordType || n.recordType === 'note'))
    
    // Filter by Type
    if (activeNoteFilter.value === 'mistakes') {
        notes = notes.filter(n => isMistakeNote(n))
    } else {
        // 'notes' tab: Exclude mistakes
        notes = notes.filter(n => !isMistakeNote(n))
    }

    // Filter by Tag
    if (selectedTagFilter.value) {
        notes = notes.filter(n => n.tags?.includes(selectedTagFilter.value))
    }

    // Filter by Category
    if (selectedCategoryFilter.value) {
        notes = notes.filter(n => n.category === selectedCategoryFilter.value)
    }

    // Filter by Priority
    if (selectedPriorityFilter.value) {
        notes = notes.filter(n => n.priority === selectedPriorityFilter.value)
    }

    if (searchTokens.value.length > 0) {
        notes = notes.filter(n => noteMatchesSearch(n, searchTokens.value))
    }
    
    // Sort by Chapter Order then Time
    const nodeOrder = new Map(flatNodes.value.map((n, i) => [n.node_id, i]))
    notes.sort((a, b) => {
        const orderA = nodeOrder.get(a.nodeId) ?? -1
        const orderB = nodeOrder.get(b.nodeId) ?? -1
        if (orderA !== orderB) return orderA - orderB
        return a.createdAt - b.createdAt
    })
    
    return notes
})

const quotedNotes = computed(() => visibleNotes.value.filter(n => n.quote && n.quote.trim().length > 0))
const displayedQuotedNotes = computed(() => quotedNotes.value.filter(n => n.sourceType !== 'format'))
const inlineRecordsForNode = (nodeId: string) => displayedQuotedNotes.value.filter(note => note.nodeId === nodeId)

watch(() => [visibleNotes.value.length, flatNodes.value], () => {
    nextTick(() => {
        reapplyHighlights()
        debouncedRefreshAnnotations()
    })
}, { deep: true })

watch(() => courseStore.uiSettings.fontSize, () => {
    nextTick(() => {
        debouncedRefreshAnnotations()
    })
})

const reapplyHighlights = () => {
    // 1. Cleanup orphans
    // Identify active highlight IDs from quotedNotes
    const activeIds = new Set(quotedNotes.value.map(n => n.highlightId))
    
    document.querySelectorAll('.highlight-marker, .format-marker').forEach(el => {
        // ID format: highlightId or highlightId-part-*
        const id = el.id ? el.id.split('-part-')[0] : ''
        
        if (!id || !activeIds.has(id)) {
             // Unwrap orphan highlight
             const parent = el.parentNode
             while (el.firstChild) parent?.insertBefore(el.firstChild, el)
             parent?.removeChild(el)
        }
    })

    // 2. Group notes by nodeId to minimize DOM traversal
    const notesByNode = new Map<string, any[]>()
    quotedNotes.value.forEach(note => {
        if (document.getElementById(note.highlightId)) return // Skip already highlighted
        
        if (!notesByNode.has(note.nodeId)) {
            notesByNode.set(note.nodeId, [])
        }
        notesByNode.get(note.nodeId)?.push(note)
    })

    // 3. Process each node (chapter) once
    notesByNode.forEach((notes, nodeId) => {
        const nodeEl = document.getElementById('node-' + nodeId)
        if (!nodeEl) return
        
        // Advanced Text Search & Highlight Strategy (Robust "Strip Whitespace" Match)
        // 1. Get all text nodes and build a map ONCE per chapter
        const textNodes: { node: Node, text: string, length: number }[] = []
        let fullTextStripped = ''
        const mapIndices: { index: number, node: Node, offset: number }[] = []
        
        const walker = document.createTreeWalker(nodeEl, NodeFilter.SHOW_TEXT)
        let currentNode
        while (currentNode = walker.nextNode()) {
            const text = currentNode.textContent || ''
            if (!text) continue 
            
            // Build map: for every character in stripped text, record where it came from
            for (let i = 0; i < text.length; i++) {
                const char = text[i]
                if (!char || /\s/.test(char)) {
                    continue
                }
                    mapIndices.push({
                        index: fullTextStripped.length,
                        node: currentNode,
                        offset: i
                    })
                    fullTextStripped += char
            }
            
            textNodes.push({
                node: currentNode,
                text: text,
                length: text.length
            })
        }
        
        // 2. Apply all notes for this chapter
        notes.forEach(note => {
            // Normalize quote (Strip all whitespace)
            const normalize = (str: string) => str.replace(/\s+/g, '')
            const quoteStripped = normalize(note.quote)
            
            if (!quoteStripped) return
    
            const textPosition = note.anchor?.text_position as Record<string, unknown> | undefined
            const resolved = resolveTextQuoteAnchor(fullTextStripped, quoteStripped, {
                start: 0,
                end: 0,
                prefix: normalize(String(textPosition?.prefix || '')),
                suffix: normalize(String(textPosition?.suffix || '')),
                occurrence: Number(textPosition?.occurrence || 0),
            })
            const matchIndex = resolved.start
            
            if (matchIndex !== -1) {
                 const startIndex = matchIndex
                 const endIndex = matchIndex + quoteStripped.length - 1 // Inclusive for map lookup
                 
                if (startIndex < mapIndices.length && endIndex < mapIndices.length) {
                    const startMap = mapIndices[startIndex]
                    const endMap = mapIndices[endIndex]
                    if (!startMap || !endMap) return
                    
                    const startNode = startMap.node
                    const startOffset = startMap.offset
                    const endNode = endMap.node
                    const endOffset = endMap.offset + 1 // Exclusive end offset
                     
                     try {
                         // Create Range
                         const startNodeIdx = textNodes.findIndex(t => t.node === startNode)
                         const endNodeIdx = textNodes.findIndex(t => t.node === endNode)
                        if (startNodeIdx === -1 || endNodeIdx === -1) return
                         
                         if (startNode === endNode) {
                             const range = document.createRange()
                             range.setStart(startNode, startOffset)
                             range.setEnd(endNode, endOffset)
                             wrapRange(range, note.highlightId, note.id)
                         } else {
                             // Start Node Part
                             const range1 = document.createRange()
                             range1.setStart(startNode, startOffset)
                            const startNodeText = textNodes[startNodeIdx]
                            if (!startNodeText) return
                            range1.setEnd(startNode, startNodeText.text.length)
                             wrapRange(range1, note.highlightId + '-part-start', note.id)
                             
                             // Middle Nodes
                             for (let i = startNodeIdx + 1; i < endNodeIdx; i++) {
                                const nodeEntry = textNodes[i]
                                if (!nodeEntry) continue
                                const rangeM = document.createRange()
                                rangeM.selectNodeContents(nodeEntry.node)
                                 // Only wrap if it contains non-whitespace
                                if (nodeEntry.text.trim().length > 0) {
                                     wrapRange(rangeM, note.highlightId + '-part-' + i, note.id)
                                 }
                             }
                             
                             // End Node Part
                             const range2 = document.createRange()
                             range2.setStart(endNode, 0)
                             range2.setEnd(endNode, endOffset)
                             wrapRange(range2, note.highlightId, note.id)
                             
                             // Ensure main ID is on the first part for positioning
                             const firstWrapper = document.getElementById(note.highlightId + '-part-start')
                             if (firstWrapper) firstWrapper.id = note.highlightId
                         }
                     } catch (e) {
                         logger.warn('Highlight range creation failed', e)
                     }
                 }
            }
        })
    })
    window.setTimeout(() => annotationLayerRef.value?.refresh(), 0)
}



const applyFormat = (style: string, value?: string) => {
    if (!selectionMenu.value.range || !selectionMenu.value.text) return
    
    // Determine Note Style early (needed for toggle check)
    let noteStyle = style
    if (style === 'underline') noteStyle = value || 'solid'
    
    // Find Node ID
    let nodeId = ''
    let curr: Node | null = selectionMenu.value.range.startContainer
    while(curr && !nodeId) {
        if (curr.nodeType === 1 && (curr as Element).id.startsWith('node-')) {
            nodeId = (curr as Element).id.replace('node-', '')
        }
        curr = curr.parentNode
    }
    
    // Toggle logic: check if an identical format note already exists
    if (nodeId) {
        // For highlight: match any existing highlight (regardless of color)
        // For bold/solid/wavy: match by exact style
        const existingNote = noteStore.notes.find(
            (n) =>
                n.sourceType === 'format' &&
                n.nodeId === nodeId &&
                n.quote === selectionMenu.value.text &&
                (style === 'highlight' ? n.style === 'highlight' : n.style === noteStyle)
        )
        if (existingNote) {
            // For highlight with different color: delete old, then continue to create new (replace)
            const isHighlightReplace = style === 'highlight' && existingNote.color !== (value || 'yellow')
            
            // Remove the existing format note
            noteStore.deleteNote(existingNote.id)
            // Remove DOM highlight span by unwrapping its inner text
            if (existingNote.highlightId) {
                const spans = document.querySelectorAll(`[id^="${existingNote.highlightId}"]`)
                spans.forEach((span) => {
                    const parent = span.parentNode
                    if (parent) {
                        while (span.firstChild) {
                            parent.insertBefore(span.firstChild, span)
                        }
                        parent.removeChild(span)
                    }
                })
            }
            
            // If highlight replace (different color), continue to create new note below
            // Otherwise (same color toggle off, or non-highlight toggle), return early
            if (!isHighlightReplace) {
                selectionMenu.value.visible = false
                window.getSelection()?.removeAllRanges()
                return
            }
        }
    }
    
    const highlightId = 'highlight-' + Math.random().toString(36).substr(2, 9)
    
    // Determine color based on style
    let color = 'transparent'
    if (style === 'highlight') color = value || 'yellow'
    
    if (nodeId) {
        noteStore.createNote({
            id: 'note-' + Math.random().toString(36).substr(2, 9),
            nodeId,
            highlightId,
            quote: selectionMenu.value.text,
            content: '', // Empty content implies annotation only
            color,
            createdAt: Date.now(),
            sourceType: 'format',
            style: noteStyle as any
        })
        
        selectionMenu.value.visible = false
        window.getSelection()?.removeAllRanges()
    }
}

const clearFormats = () => {
    if (!selectionMenu.value.text) return
    
    // Find nodeId from selection range
    let nodeId = ''
    if (selectionMenu.value.range) {
        let curr: Node | null = selectionMenu.value.range.startContainer
        while (curr && !nodeId) {
            if (curr.nodeType === 1 && (curr as Element).id.startsWith('node-')) {
                nodeId = (curr as Element).id.replace('node-', '')
            }
            curr = curr.parentNode
        }
    }
    if (!nodeId) return
    
    // Find all format notes matching this selection
    const formatNotes = noteStore.notes.filter(
        (n) =>
            n.sourceType === 'format' &&
            n.nodeId === nodeId &&
            n.quote === selectionMenu.value.text
    )
    
    // Delete each note and unwrap its DOM span
    formatNotes.forEach((note) => {
        noteStore.deleteNote(note.id)
        if (note.highlightId) {
            const spans = document.querySelectorAll(`[id^="${note.highlightId}"]`)
            spans.forEach((span) => {
                const parent = span.parentNode
                if (parent) {
                    while (span.firstChild) {
                        parent.insertBefore(span.firstChild, span)
                    }
                    parent.removeChild(span)
                }
            })
        }
    })
    
    selectionMenu.value.visible = false
    window.getSelection()?.removeAllRanges()
}

const setHovered = (noteId: string | null, event?: MouseEvent) => {
    hoveredNoteId.value = noteId
    // 1. Clean up old highlights
    document.querySelectorAll('.pulse-highlight').forEach(el => el.classList.remove('pulse-highlight'))
    
    // 2. Add new highlights and show preview
    if (noteId) {
        const note = noteStore.notes.find(n => n.id === noteId)
        if (note && note.highlightId) {
            const els = document.querySelectorAll(`[id^="${note.highlightId}"]`)
            els.forEach(el => el.classList.add('pulse-highlight'))
        }
        
        if (note && event && !inlineRecord.interactive) {
            inlineRecord.visible = true
            inlineRecord.x = event.clientX
            inlineRecord.y = event.clientY - 10
            inlineRecord.note = note
            inlineRecord.initialEdit = false
            inlineRecord.saveState = note.syncState || 'saved'
        }
    } else if (!inlineRecord.interactive) {
        inlineRecord.visible = false
        inlineRecord.note = null
    }
}

const wrapRange = (range: Range, id: string, noteId: string) => {
    try {
        // Skip empty ranges
        if (range.toString().length === 0) return
        
        const note = noteStore.notes.find(n => n.id === noteId)
        const span = document.createElement('span')
        span.id = id
        
        // Dynamic Class based on Note Type/Style
        // Non-highlight formats (bold/solid/wavy) use format-marker to avoid
        // .highlight-marker CSS pollution (yellow background/border)
        let className = 'transition-colors cursor-pointer '
        
        if (note?.sourceType === 'format') {
            if (note.style === 'bold') {
                className += 'format-marker font-bold '
            } else if (note.style === 'solid') { // Underline solid
                className += 'format-marker border-b-2 border-slate-800 '
            } else if (note.style === 'wavy') {
                className += 'format-marker underline decoration-wavy decoration-slate-800 '
            } else if (note.color && note.color !== 'transparent') {
                // Highlight — keep highlight-marker for colored background
                const colorClass = formatHighlightMap[note.color] || 'bg-yellow-200/50 hover:bg-yellow-300/50'
                className += 'highlight-marker ' + colorClass + ' '
            }
        } else if (note?.sourceType === 'ai') {
            // AI Teacher Style
            className += 'highlight-marker ' + noteHighlightClass('purple') + ' '
        } else {
            // Default Note Style
            const resolvedColor = resolveNoteColor(note)
            className += 'highlight-marker ' + noteHighlightClass(resolvedColor) + ' '
        }
        
        span.className = className
        
        span.onclick = (e) => {
            e.stopPropagation()
            if (note && note.sourceType !== 'format') {
                openInlineRecord({ note, x: e.clientX, y: e.clientY })
            }
        }
        // Add hover effects with preview
        span.onmouseenter = (e) => setHovered(noteId, e as MouseEvent)
        span.onmouseleave = () => setHovered(null)
        
        range.surroundContents(span)
    } catch (e) {
        // Ignore
    }
}

const scrollToNote = (noteId: string) => {
    const note = noteStore.notes.find(n => n.id === noteId)
    if (!note) {
        logger.warn('Note not found:', noteId)
        return
    }

    activeNoteId.value = note.id
    const scrollContainer = document.getElementById('content-scroll-container')

    const flashNoteCard = () => {
        nextTick(() => {
            const noteEl = document.getElementById(note.id)
            if (noteEl) {
                noteEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                noteEl.classList.add('flash-card', 'ring-4', 'ring-primary-200')
                setTimeout(() => noteEl.classList.remove('flash-card', 'ring-4', 'ring-primary-200'), 1000)
            }
        })
    }

    // First, try to scroll to the highlight in content area (preferred)
    if (note.highlightId) {
        const highlightEl = document.getElementById(note.highlightId)
        if (highlightEl && scrollContainer) {
            scrollToElementInContainer(highlightEl, scrollContainer).then(() => {
                highlightEl.classList.add('pulse-highlight')
                setTimeout(() => highlightEl.classList.remove('pulse-highlight'), 1500)
            })
            flashNoteCard()
            return
        }
    }

    // If no highlight or highlight not found, scroll to the node
    if (note.nodeId) {
        const nodeEl = document.getElementById(`node-${note.nodeId}`)
        if (nodeEl && scrollContainer) {
            scrollToElementInContainer(nodeEl, scrollContainer).then(() => {
                nodeEl.classList.add('pulse-highlight')
                setTimeout(() => nodeEl.classList.remove('pulse-highlight'), 1500)
            })
        } else {
            courseStore.scrollToNode(note.nodeId)
        }
    }

    flashNoteCard()
}

// Content size changes can move inline anchors after fonts and formulas settle.
let resizeObserver: ResizeObserver | null = null

const handleGlobalKeydown = (e: KeyboardEvent) => {
    if (isGenerationPreview.value) return
    // Only handle if Ctrl or Meta is pressed
    if (!(e.ctrlKey || e.metaKey)) return

    const key = e.key.toLowerCase()
    
    // Formatting Shortcuts
    if (['b', 'i', 'u'].includes(key)) {
        e.preventDefault()
        const selection = window.getSelection()
        if (selection && selection.toString().trim()) {
            // Show menu if not visible, or just apply directly
            if (!selectionMenu.value.visible) {
                 const range = selection.getRangeAt(0)
                 selectionMenu.value = {
                     visible: false,
                     x: 0, y: 0,
                     arrowOffset: 0,
                     placement: 'top',
                     text: selection.toString(),
                     range: range
                 }
            }
            
            if (key === 'b') applyFormat('bold')
            else if (key === 'i') applyFormat('underline', 'wavy') // Use wavy for italic/emphasis
            else if (key === 'u') applyFormat('underline', 'solid')
        }
    }
}

const getNodeName = (nodeId: string) => {
    const node = flatNodes.value.find(n => n.node_id === nodeId)
    return node ? node.node_name : '未知章节'
}

onMounted(() => {
    window.addEventListener('keydown', handleGlobalKeydown)
    
    resizeObserver = new ResizeObserver(() => {
        debouncedRefreshAnnotations()
        scheduleWindowUpdate()
    })

    const scrollContainer = document.getElementById('content-scroll-container')
    if (scrollContainer) {
        resizeObserver.observe(scrollContainer)
    }
    
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleGlobalKeydown)
    if (resizeObserver) resizeObserver.disconnect()
})

// Watch for DOM updates to re-attach observer to new note elements
watch(() => visibleNotes.value, () => {
    nextTick(() => {
        reapplyHighlights()
        refreshInlineAnnotations()
    })
}, { deep: true })





// Selection Handling
const handleMouseUp = (_e: MouseEvent) => {
    if (isGenerationPreview.value) {
        selectionMenu.value.visible = false
        return
    }
    // Check if clicked on image
    const target = _e.target as HTMLElement
    if (target.tagName === 'IMG' && target.closest('.prose')) {
        lightboxImage.value = (target as HTMLImageElement).src
        lightboxVisible.value = true
        return
    }

    // Prevent selection menu during scroll
    if (isManualScrolling.value) return
    
    const selection = window.getSelection()
    if (selection && selection.toString().trim().length > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        
        // Detect Scale of the Teleport Target (Body)
        // Similar to note positioning, we must account for global scaling (e.g. transform on body/app)
        const body = document.body
        const bodyRect = body.getBoundingClientRect()
        let scaleX = 1
        let scaleY = 1
        if (body.offsetWidth > 0) scaleX = bodyRect.width / body.offsetWidth
        if (body.offsetHeight > 0) scaleY = bodyRect.height / body.offsetHeight
        
        // Safety clamp
        if (scaleX < 0.1 || scaleX > 10) scaleX = 1
        if (scaleY < 0.1 || scaleY > 10) scaleY = 1
        
        const isScaled = Math.abs(scaleX - 1) > 0.005 || Math.abs(scaleY - 1) > 0.005

        // Initial Calculation
        let effectiveViewportWidth = window.innerWidth
        let x = 0
        let y = 0
        
        if (isScaled) {
            // Context is scaled (likely transform on body), fixed positioning is relative to body
            effectiveViewportWidth = window.innerWidth / scaleX
            x = (rect.left - bodyRect.left) / scaleX + (rect.width / scaleX) / 2
            y = (rect.top - bodyRect.top) / scaleY - 12
        } else {
            // Standard Viewport (No scale)
            x = rect.left + rect.width / 2
            y = rect.top - 12
        }
        
        const originalX = x
        let placement = 'top'

        // Initial estimate (safe default to avoid large jumps)
        const ESTIMATED_WIDTH = 280
        if (x + (ESTIMATED_WIDTH / 2) > effectiveViewportWidth - 20) x = effectiveViewportWidth - (ESTIMATED_WIDTH / 2) - 20
        if (x - (ESTIMATED_WIDTH / 2) < 20) x = (ESTIMATED_WIDTH / 2) + 20

        selectionMenu.value = {
            visible: true,
            x: x, 
            y: y, 
            arrowOffset: originalX - x,
            placement: placement,
            text: selection.toString(),
            range: range
        }

        // Precise Adjustment after Render (Fix for P1: Scaling/Overflow Alignment)
        nextTick(() => {
            const menuEl = document.getElementById('selection-menu')
            if (menuEl) {
                // Use offsetWidth/Height to get the "layout" size, ignoring the scale-in animation
                // getBoundingClientRect() would return the scaled-down size during the transition
                const actualWidth = menuEl.offsetWidth
                const actualHeight = menuEl.offsetHeight
                
                // Re-calculate X based on ACTUAL width
                let newX = originalX
                
                // Prevent overflow right (allow closer to edge: 5px)
                if (newX + (actualWidth / 2) > effectiveViewportWidth - 5) {
                    newX = effectiveViewportWidth - (actualWidth / 2) - 5
                }
                // Prevent overflow left (allow closer to edge: 5px)
                if (newX - (actualWidth / 2) < 5) {
                    newX = (actualWidth / 2) + 5
                }
                
                // Re-calculate Arrow Offset
                let newArrowOffset = originalX - newX
                
                // Clamp arrow (allow closer to edge, e.g. 6px from edge)
                const maxOffset = (actualWidth / 2) - 6 
                if (newArrowOffset > maxOffset) newArrowOffset = maxOffset
                if (newArrowOffset < -maxOffset) newArrowOffset = -maxOffset
                
                // Re-calculate Y (Placement)
                // Need to recalculate base Y/Bottom in correct coordinate space
                let newY = isScaled ? ((rect.top - bodyRect.top) / scaleY - 12) : (rect.top - 12)
                let newPlacement = 'top'
                
                // Check top overflow with ACTUAL height
                if (newY - actualHeight < 60) {
                     newY = isScaled ? ((rect.bottom - bodyRect.top) / scaleY + 12) : (rect.bottom + 12)
                     newPlacement = 'bottom'
                }
                
                // Update State
                selectionMenu.value.x = newX
                selectionMenu.value.y = newY
                selectionMenu.value.arrowOffset = newArrowOffset
                selectionMenu.value.placement = newPlacement
            }
        })
    } else {
        selectionMenu.value.visible = false
    }
}

const selectedNodeFromMenu = () => {
    const range = selectionMenu.value.range
    if (!range) return null

    let current: globalThis.Node | null = range.commonAncestorContainer
    if (current.nodeType === globalThis.Node.TEXT_NODE) {
        current = current.parentNode
    }
    const element = current instanceof Element ? current : current?.parentElement
    const nodeEl = element?.closest('[id^="node-"]')
    const nodeId = nodeEl?.id.replace('node-', '')
    return nodeId ? courseStore.nodes.find((node) => node.node_id === nodeId) || null : null
}

const selectedNodeIdFromMenu = () => selectedNodeFromMenu()?.node_id || ''

const handleAsk = () => {
    if (!selectionMenu.value.text) return

    const text = selectionMenu.value.text
    const nodeId = selectedNodeIdFromMenu()
    const nodeElement = nodeId ? document.getElementById(`node-${nodeId}`) : null
    const anchor = selectionMenu.value.range && nodeElement
        ? buildTextQuoteAnchor(selectionMenu.value.range, nodeElement, text)
        : undefined

    emit('quoteAsk', { text, nodeId, anchor })
    
    // Hide menu
    selectionMenu.value.visible = false
}

const handleLater = async (recordType: 'issue' | 'review_task' | 'bookmark') => {
    const quote = selectionMenu.value.text.trim()
    const nodeId = selectedNodeIdFromMenu()
    if (!quote || !nodeId) {
        ElMessage.warning(t('courseWorkspace.records.locationMissing', '无法定位选区所在章节'))
        return
    }
    const nodeElement = document.getElementById(`node-${nodeId}`)
    const anchor = selectionMenu.value.range && nodeElement
        ? buildTextQuoteAnchor(selectionMenu.value.range, nodeElement, selectionMenu.value.text)
        : undefined
    await noteStore.createLater(recordType, {
        nodeId,
        quote,
        anchor,
        title: recordType === 'issue'
            ? t('courseWorkspace.records.issueTitle', '未解决问题')
            : recordType === 'review_task'
                ? t('courseWorkspace.records.reviewTitle', '复习任务')
                : t('courseWorkspace.records.bookmarkTitle', '阅读书签'),
    })
    laterMenuVisible.value = false
    selectionMenu.value.visible = false
    window.getSelection()?.removeAllRanges()
}

const handleAddNote = async () => {
    const range = selectionMenu.value.range
    const quote = selectionMenu.value.text.trim()
    const nodeId = selectedNodeIdFromMenu()
    const nodeElement = nodeId ? document.getElementById(`node-${nodeId}`) : null
    if (!range || !quote || !nodeId || !nodeElement) {
        ElMessage.warning(t('courseWorkspace.records.locationMissing', '无法定位选区所在章节'))
        return
    }
    const noteId = `note-${crypto.randomUUID()}`
    const note: Note = {
        id: noteId,
        nodeId,
        highlightId: `hl-${noteId}`,
        quote,
        content: '',
        color: pickPaletteColor(noteId),
        createdAt: Date.now(),
        sourceType: 'user',
        recordType: 'note',
        status: 'active',
        anchor: buildTextQuoteAnchor(range, nodeElement, selectionMenu.value.text),
        syncState: 'local_only',
    }
    noteStore.addNote(note)
    selectionMenu.value.visible = false
    laterMenuVisible.value = false
    window.getSelection()?.removeAllRanges()
    await nextTick()
    reapplyHighlights()
    openInlineRecord({ note, x: selectionMenu.value.x, y: selectionMenu.value.y }, true)
}

const openInlineRecord = (
    payload: { note: Note; x: number; y: number },
    initialEdit = false,
) => {
    activeNoteId.value = payload.note.id
    inlineRecord.visible = true
    inlineRecord.note = payload.note
    inlineRecord.x = payload.x
    inlineRecord.y = payload.y
    inlineRecord.interactive = true
    inlineRecord.initialEdit = initialEdit
    inlineRecord.saveState = payload.note.syncState || (payload.note.revision ? 'saved' : 'local_only')
}

const closeInlineRecord = async () => {
    const note = inlineRecord.note
    if (note && !note.revision && !note.content.trim()) await noteStore.deleteNote(note.id)
    inlineRecord.visible = false
    inlineRecord.note = null
    inlineRecord.interactive = false
    inlineRecord.initialEdit = false
}

const saveInlineRecord = async (payload: { note: Note; content: string }) => {
    inlineRecord.saveState = 'saving'
    payload.note.content = payload.content
    const saved = payload.note.revision
        ? await noteStore.updateNote(payload.note.id, payload.content)
        : await noteStore.createNote(payload.note)
    const current = noteStore.notes.find(item => item.id === payload.note.id) || payload.note
    inlineRecord.note = current
    inlineRecord.saveState = saved ? 'saved' : 'local_only'
}

const retryInlineRecord = async (note: Note) => {
    inlineRecord.saveState = 'saving'
    const saved = await noteStore.retryNote(note.id)
    inlineRecord.note = noteStore.notes.find(item => item.id === note.id) || note
    inlineRecord.saveState = saved ? 'saved' : 'local_only'
}

const undoInlineRecord = async (note: Note) => {
    await noteStore.deleteNote(note.id)
    inlineRecord.visible = false
    inlineRecord.note = null
    inlineRecord.interactive = false
    inlineRecord.initialEdit = false
    reapplyHighlights()
}

const deleteInlineRecord = async (note: Note) => {
    try {
        await ElMessageBox.confirm(
            t('inlineRecords.deleteConfirm', '删除这条学习记录？'),
            t('common.delete', '删除'),
            { confirmButtonText: t('common.delete', '删除'), cancelButtonText: t('common.cancel', '取消') },
        )
        await noteStore.deleteNote(note.id)
        await closeInlineRecord()
        reapplyHighlights()
    } catch (error) {
        if (error !== 'cancel' && error !== 'close') ElMessage.error(t('inlineRecords.deleteFailed', '删除失败'))
    }
}

const askAiFromInlineRecord = (note: Note) => {
    emit('quoteAsk', { text: note.quote || note.content, nodeId: note.nodeId, anchor: note.anchor })
    void closeInlineRecord()
}



const handleStartPractice = (node: any) => {
    courseStore.selectNode(node)
    workspaceStore.mode = 'practice'
    emit('startPractice', node)
}


// Watch visible notes to re-apply highlights and update positions
watch(visibleNotes, () => {
    // Wait for DOM update
    nextTick(() => {
        reapplyHighlights()
        debouncedRefreshAnnotations()
    })
}, { deep: true })

watch(visibleNodes, () => {
    nextTick(() => {
        measureVisibleNodeHeights()
        reapplyHighlights()
        debouncedRefreshAnnotations()
    })
}, { flush: 'post' })

// Watch for focus mode changes to recalculate note positions
watch(() => courseStore.isFocusMode, (newVal, oldVal) => {
    if (oldVal && !newVal) {
        // Exiting focus mode - wait for layout to settle then update positions
        nextTick(() => {
            setTimeout(() => {
                reapplyHighlights()
                refreshInlineAnnotations()
            }, 300) // Wait for transition to complete
        })
    }
})

const showBackToTop = ref(false)

// Compute dynamic right offset for back-to-top button — synced with AI button
const backToTopStyle = computed(() => {
  if (props.sideAiPanelVisible) {
    return { right: 'calc(33vw + 1rem)' }
  }
  return { right: '1.5rem' }
})

const handleScroll = (e: Event) => {
    const target = e.target as HTMLElement
    showBackToTop.value = target.scrollTop > 500
    
    // Update Progress
    if (target.scrollHeight > target.clientHeight) {
        scrollProgress.value = (target.scrollTop / (target.scrollHeight - target.clientHeight)) * 100
    }
    
    rafRefreshAnnotations()
    scheduleWindowUpdate(target)
    
    // 实时检测当前可见节点，同步左侧树
    if (!isManualScrolling.value) {
        detectCurrentVisibleNode(target)
    }
    
    saveSemanticPosition(target)
}

let _detectRafId = 0
const detectCurrentVisibleNode = (container: HTMLElement) => {
    if (_detectRafId) return // 节流：每帧最多检测一次
    _detectRafId = requestAnimationFrame(() => {
        _detectRafId = 0
        const containerTop = container.getBoundingClientRect().top + 100 // 偏移量，对应 sticky header
        const nodes = visibleNodes.value
        // 如果侧边栏剥离了根节点，检测时也跳过 level 1
        const skipRoot = courseStore.courseTree.length === 1 
            && courseStore.courseTree[0]?.children 
            && courseStore.courseTree[0].children.length > 0
        let bestNode: any = null
        let bestDist = Infinity
        
        for (let i = nodes.length - 1; i >= 0; i--) {
            if (skipRoot && nodes[i].node_level === 1) continue
            const el = document.getElementById(`node-${nodes[i].node_id}`)
            if (!el) continue
            const top = el.getBoundingClientRect().top
            // 找到最接近且在视口顶部以上或刚好在顶部的节点
            const dist = top - containerTop
            if (dist <= 0 && Math.abs(dist) < bestDist) {
                bestDist = Math.abs(dist)
                bestNode = nodes[i]
            }
        }
        // 如果没有在顶部以上的，取第一个可见的（跳过 root）
        if (!bestNode) {
            for (const n of nodes) {
                if (skipRoot && n.node_level === 1) continue
                const el = document.getElementById(`node-${n.node_id}`)
                if (!el) continue
                const top = el.getBoundingClientRect().top - containerTop
                if (top >= 0) {
                    bestNode = n
                    break
                }
            }
        }
        
        if (bestNode && courseStore.currentNode?.node_id !== bestNode.node_id) {
            courseStore.setCurrentNodeSilent(bestNode)
        }
    })
}

const saveSemanticPosition = debounce((container: HTMLElement) => {
    if (isGenerationPreview.value || isManualScrolling.value || !courseStore.currentCourseId || !courseStore.currentNode) return
    const node = courseStore.currentNode
    const nodeElement = document.getElementById(`node-${node.node_id}`)
    if (!nodeElement) return
    const containerTop = container.getBoundingClientRect().top + 100
    learningSessionStore.updatePosition({
        courseId: courseStore.currentCourseId,
        courseVersionId: courseStore.currentCourseVersionId,
        nodeId: node.node_id,
        nodeName: node.node_name,
        anchor: captureViewportAnchor(nodeElement, containerTop),
        fallbackScrollTop: container.scrollTop,
    })
}, 550)

const scrollToTop = () => {
    const container = document.getElementById('content-scroll-container')
    if (container) {
        renderWindow.value = { start: 0, end: Math.min(VIRTUAL_MIN_ITEMS, flatNodes.value.length) }
        smartScrollTo(container, 0)
    }
}

const handleViewportResize = () => {
    debouncedRefreshAnnotations()
    scheduleWindowUpdate()
}

const legacyReadingPosition = (courseId: string) => {
    let nodeId = ''
    let scrollTop = Number(localStorage.getItem(`scroll-pos-${courseId}`) || 0)
    let hasLegacy = localStorage.getItem(`scroll-pos-${courseId}`) !== null
    try {
        const stats = JSON.parse(localStorage.getItem('learning_stats') || '{}')
        const position = stats?.lastReadPosition?.[courseId]
        hasLegacy = hasLegacy || !!position
        nodeId = String(position?.nodeId || '')
        if (!scrollTop && Number.isFinite(Number(position?.scrollTop))) scrollTop = Number(position.scrollTop)
    } catch { /* corrupted legacy state is ignored */ }
    if (hasLegacy && !nodeId) nodeId = flatNodes.value.find(node => node.node_level > 1 && node.node_content)?.node_id || ''
    const node = flatNodes.value.find(item => item.node_id === nodeId)
    return { hasLegacy, nodeId, nodeName: node?.node_name || '', scrollTop: Math.max(0, scrollTop || 0) }
}

const restoreLearningPosition = async () => {
    const snapshot = learningSessionStore.snapshot
    if (!snapshot) return
    const container = document.getElementById('content-scroll-container')
    if (!container) return

    const resolved = learningSessionStore.resolution?.resolved_anchor
    const nodeId = resolved?.node_id || snapshot.node_id
    const index = flatNodes.value.findIndex(node => node.node_id === nodeId)
    if (index < 0) return

    isManualScrolling.value = true
    await renderAroundIndex(index)
    const roughTop = (virtualListRef.value?.offsetTop ?? 0) + nodeTop(index) - 20
    container.scrollTop = Math.max(0, roughTop)
    scheduleWindowUpdate(container)
    await nextTick()
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))

    let nodeElement: HTMLElement | null = null
    for (let attempt = 0; attempt < 20; attempt++) {
        nodeElement = document.getElementById(`node-${nodeId}`)
        if (nodeElement) break
        await new Promise(resolve => setTimeout(resolve, 60))
    }
    if (!nodeElement) {
        isManualScrolling.value = false
        return
    }

    const blockId = resolved?.block_id || snapshot.content_anchor?.block_id || ''
    let blockElements = Array.from(nodeElement.querySelectorAll<HTMLElement>('[data-content-block-id]'))
    let blockElement = blockElements.find(element => element.dataset.contentBlockId === blockId) || null
    for (let attempt = 0; blockId && !blockElement && attempt < 8; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 80))
        blockElements = Array.from(nodeElement.querySelectorAll<HTMLElement>('[data-content-block-id]'))
        blockElement = blockElements.find(element => element.dataset.contentBlockId === blockId) || null
    }
    if (blockElement) {
        const blockIndex = blockElements.indexOf(blockElement)
        container.scrollTop = resolvedAnchorScrollTop(
            container,
            blockElement,
            blockElements[blockIndex + 1] || null,
            resolved?.progress ?? snapshot.content_anchor?.progress ?? 0,
        )
    } else if (snapshot.source === 'legacy_migration' && snapshot.fallback_scroll_top > 0) {
        container.scrollTop = Math.min(snapshot.fallback_scroll_top, Math.max(0, container.scrollHeight - container.clientHeight))
    } else {
        await scrollToElementInContainer(nodeElement, container)
    }

    const node = flatNodes.value[index]
    if (node) courseStore.setCurrentNodeSilent(node)
    scheduleWindowUpdate(container)
    learningSessionStore.restored = true
    const contentChanged = learningSessionStore.resolution?.content_changed
    ElMessage({
        type: 'success',
        message: contentChanged
            ? t('courseWorkspace.learningSession.contentUpdated', '课程内容已更新，已定位到对应内容')
            : t('courseWorkspace.learningSession.restored', '已继续上次学习'),
        offset: 78,
    })
    setTimeout(() => { isManualScrolling.value = false }, 350)
}

let initializedLearningCourseId = ''
let contentMounted = false
const initializeLearningPosition = async () => {
    const courseId = courseStore.currentCourseId
    if (isGenerationPreview.value || !contentMounted || !courseId || courseStore.loading || !flatNodes.value.length || initializedLearningCourseId === courseId) return
    initializedLearningCourseId = courseId
    const snapshot = await learningSessionStore.load(courseId)
    if (!snapshot) {
        const legacy = legacyReadingPosition(courseId)
        if (legacy.hasLegacy) {
            learningSessionStore.migrateLegacy(
                courseId,
                courseStore.currentCourseVersionId,
                legacy.nodeId,
                legacy.nodeName,
                legacy.scrollTop,
            )
        }
    }
    if (learningSessionStore.snapshot) await restoreLearningPosition()
}

watch(
    () => [courseStore.currentCourseId, courseStore.loading, flatNodes.value.length, courseStore.currentCourseProjection] as const,
    async ([courseId, loading, count, projection], previous) => {
        const previousCourseId = previous?.[0]
        if (previousCourseId && previousCourseId !== courseId && learningSessionStore.courseId === previousCourseId) {
            await learningSessionStore.flush()
            initializedLearningCourseId = ''
        }
        if (courseId && !loading && count > 0 && projection === 'published') await initializeLearningPosition()
    },
    { immediate: true, flush: 'post' },
)

const flushLearningSnapshot = () => { void learningSessionStore.flush() }
const handleLearningVisibility = () => {
    if (document.visibilityState === 'hidden') flushLearningSnapshot()
}

onMounted(() => {
    contentMounted = true
    learningSessionStore.bindConnectivity()
    window.addEventListener('pagehide', flushLearningSnapshot)
    document.addEventListener('visibilitychange', handleLearningVisibility)
    document.addEventListener('mousedown', (e) => {
        if (selectionMenu.value.visible && !(e.target as HTMLElement).closest('#content-scroll-container')) {
            selectionMenu.value.visible = false
        }
    })

    const container = document.getElementById('content-scroll-container')
    if (container) {
        container.addEventListener('scroll', handleScroll)
        scheduleWindowUpdate(container)
    }
    
    window.addEventListener('resize', handleViewportResize)
    
    setTimeout(() => {
        reapplyHighlights()
        refreshInlineAnnotations()
        void initializeLearningPosition()
    }, 1000)

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => {
            setTimeout(refreshInlineAnnotations, 200)
        })
    }
})

onUnmounted(() => {
    contentMounted = false
    flushLearningSnapshot()
    window.removeEventListener('pagehide', flushLearningSnapshot)
    document.removeEventListener('visibilitychange', handleLearningVisibility)
    window.removeEventListener('resize', handleViewportResize)
    const container = document.getElementById('content-scroll-container')
    container?.removeEventListener('scroll', handleScroll)
    if (_detectRafId) cancelAnimationFrame(_detectRafId)
    if (virtualRafId) cancelAnimationFrame(virtualRafId)
})

defineExpose({
    startPractice: handleStartPractice,
})
</script>

<style scoped>
.generation-empty-state { height:260px; display:flex; align-items:center; justify-content:center; gap:13px; color:var(--lz-text-muted); }
.generation-empty-state__spin { flex:0 0 auto; color:var(--lz-brand); animation:generation-empty-spin .9s linear infinite; }
.generation-empty-state div { min-width:0; display:flex; flex-direction:column; gap:3px; }
.generation-empty-state strong { color:var(--lz-text-strong); font-size:13px; }
.generation-empty-state span { font-size:11px; }
@keyframes generation-empty-spin { to { transform:rotate(360deg); } }
.record-later-option {
    min-height: 30px;
    border-radius: 6px;
    padding: 4px 7px;
    background: #f8fafc;
    color: #475569;
    font-size: 11px;
    font-weight: 600;
}
.record-later-option:hover { background: #fff1f2; color: #be123c; }
/* ContentArea Styles */

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.scale-fade-enter-active,
.scale-fade-leave-active {
  transition: all 0.2s ease;
}

.scale-fade-enter-from,
.scale-fade-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

:deep(.glass-dialog-clean) {
    background: rgba(255, 255, 255, 0.9) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-radius: 24px;
    box-shadow: 
        0 0 0 1px rgba(255, 255, 255, 0.2),
        0 20px 40px -12px rgba(0, 0, 0, 0.12), 
        0 0 0 1px rgba(0,0,0,0.02);
    border: none;
    overflow: hidden;
}

:deep(.glass-dialog-clean .el-dialog__header) {
    margin-right: 0;
    padding: 24px 28px 16px;
    border-bottom: 1px solid rgba(0,0,0,0.03);
}

:deep(.glass-dialog-clean .el-dialog__title) {
    font-weight: 800;
    color: #1e293b;
    font-size: 1.25rem;
    letter-spacing: -0.02em;
}

:deep(.glass-dialog-clean .el-dialog__body) {
    padding: 24px 28px;
}

:deep(.glass-dialog-clean .el-dialog__footer) {
    padding: 16px 28px 24px;
    border-top: 1px solid rgba(0,0,0,0.03);
    background: rgba(250, 250, 255, 0.5);
}

:deep(.glass-dialog) {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.5);
}

:deep(.el-dialog__header) {
    margin-right: 0;
    padding: 20px 24px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}

:deep(.el-dialog__title) {
    font-weight: 800;
    color: #1e293b;
    font-size: 1.125rem;
}

:deep(.el-dialog__body) {
    padding: 24px;
}

.dashed-line {
    background-image: linear-gradient(to right, #cbd5e1 50%, rgba(255,255,255,0) 0%);
    background-position: bottom;
    background-size: 6px 1px;
    background-repeat: repeat-x;
    background-color: transparent !important;
}

.format-marker {
    transition: all 0.2s ease;
    cursor: pointer;
}

.highlight-marker {
    mix-blend-mode: multiply;
    border-radius: 2px;
    background-color: rgba(251, 191, 36, 0.3);
    border-bottom: 2px solid #f59e0b;
    transition: all 0.2s ease;
    /* 统一高亮高度，模拟荧光笔效果 */
    line-height: 1.4em;
    padding: 0.1em 0;
    box-decoration-clone: clone;
    -webkit-box-decoration-clone: clone;
}

.highlight-marker:hover {
    background-color: rgba(251, 191, 36, 0.5);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
}

.pulse-highlight {
    animation: pulse-glow 1.5s infinite ease-in-out;
    background-color: rgba(251, 191, 36, 0.6) !important;
    box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);
}

.flash-card {
    animation: card-flash 1s ease;
}

@keyframes pulse-glow {
    0% { background-color: rgba(251, 191, 36, 0.4); box-shadow: 0 0 0px rgba(245, 158, 11, 0.2); }
    50% { background-color: rgba(251, 191, 36, 0.7); box-shadow: 0 0 12px rgba(245, 158, 11, 0.6); }
    100% { background-color: rgba(251, 191, 36, 0.4); box-shadow: 0 0 0px rgba(245, 158, 11, 0.2); }
}

@keyframes card-flash {
    0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
    30% { box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.3); border-color: #818cf8; transform: scale(1.02); }
    100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); transform: scale(1); }
}

.flash-highlight {
    animation: flash 1s ease;
}

@keyframes flash {
    0%, 100% { background-color: rgba(251, 191, 36, 0.3); }
    50% { background-color: rgba(251, 191, 36, 0.8); box-shadow: 0 0 10px rgba(245, 158, 11, 0.5); }
}

.back-to-top {
    position: fixed;
    bottom: 8.5rem;
    z-index: 50;
    transition: all 0.3s ease;
}

/* back-to-top transition animations */

.back-to-top-enter-active,
.back-to-top-leave-active {
    transition: all 0.3s ease;
}

.back-to-top-enter-from,
.back-to-top-leave-to {
    opacity: 0;
    transform: translateY(20px);
}

.notes-expand-tab {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 48px;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-right: none;
    border-radius: 8px 0 0 8px;
    color: #94a3b8;
    cursor: pointer;
    transition: all 0.2s ease;
}

.notes-expand-tab:hover {
    color: #6366f1;
    background: #eef2ff;
    border-color: #c7d2fe;
    width: 28px;
}

.note-underline {
    position: relative;
}

.note-underline::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -6px;
    height: 6px;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='6' viewBox='0 0 120 6'><polyline points='0,4 20,4 20,1 40,1 40,4 60,4 60,1 80,1 80,4 100,4 100,1 120,1' fill='none' stroke='%2394a3b8' stroke-width='1.5' stroke-linejoin='miter' stroke-linecap='square'/></svg>");
    background-repeat: repeat-x;
    background-size: 120px 6px;
    opacity: 0;
    transition: opacity 0.2s ease;
    pointer-events: none;
}

.group:hover .note-underline::after {
    opacity: 0.8;
}

:deep(.glass-input-clean .el-input__wrapper) {
    background-color: rgba(255, 255, 255, 0.6) !important;
    box-shadow: none !important;
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 8px 12px;
    transition: all 0.3s ease;
}

:deep(.glass-input-clean .el-input__wrapper:hover) {
    background-color: rgba(255, 255, 255, 0.8) !important;
    border-color: rgba(255, 255, 255, 0.8);
}

:deep(.glass-input-clean .el-input__wrapper.is-focus) {
    background-color: white !important;
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08) !important;
}

.glass-panel-floating {
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
}

.glass-panel-floating:hover {
    background: rgba(255, 255, 255, 0.85);
    border-color: rgba(255, 255, 255, 0.8);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.06);
}


:deep(.glass-input-clean .el-input__inner) {
    color: #334155;
    font-weight: 500;
}

/* Content Render Styles */
.content-render :deep(h1),
.content-render :deep(h2),
.content-render :deep(h3),
.content-render :deep(h4) {
    font-weight: 600;
    color: #1e293b;
    margin-top: 2rem;
    margin-bottom: 1rem;
}

.content-render :deep(h2) {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.content-render :deep(h3) {
    font-size: 1.125rem;
    font-weight: 600;
}

.content-render :deep(p) {
    color: #475569;
    line-height: inherit;
    margin-bottom: 1.25rem;
    font-size: inherit !important;
}

.content-render :deep(a) {
    color: #4f46e5;
    text-decoration: none;
    font-weight: 500;
}

.content-render :deep(a:hover) {
    text-decoration: underline;
}

.content-render :deep(strong) {
    color: #334155;
    font-weight: 600;
}

.content-render :deep(code) {
    color: #4f46e5;
    background: rgba(79, 70, 229, 0.08);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.content-render :deep(pre) {
    background: #1e293b;
    border-radius: 0.75rem;
    padding: 1rem;
    margin: 1.25rem 0;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    overflow-x: auto;
}

.content-render :deep(pre code) {
    background: transparent;
    color: #e2e8f0;
    padding: 0;
}

.content-render :deep(ul),
.content-render :deep(ol) {
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.content-render :deep(li) {
    color: #475569;
    font-size: inherit !important;
    line-height: inherit;
    margin: 0.375rem 0;
}

.content-render :deep(blockquote) {
    border-left: 3px solid #818cf8;
    background: linear-gradient(to right, rgba(79, 70, 229, 0.05), transparent);
    padding-left: 1.25rem;
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
    margin: 1.25rem 0;
    font-style: normal;
    color: #475569;
    font-weight: 500;
}

/* Note Detail Dialog Styles */
:deep(.note-detail-dialog) {
    background: rgba(255, 255, 255, 0.97) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-radius: 20px;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.2),
        0 24px 48px -12px rgba(0, 0, 0, 0.15),
        0 0 0 1px rgba(0,0,0,0.02);
    border: none;
    overflow: hidden;
}

:deep(.note-detail-dialog .el-dialog__header) {
    margin-right: 0;
    padding: 20px 24px 16px;
    border-bottom: 1px solid rgba(0,0,0,0.04);
}

:deep(.note-detail-dialog .el-dialog__title) {
    font-weight: 700;
    color: #1e293b;
    font-size: 1.125rem;
}

:deep(.note-detail-dialog .el-dialog__body) {
    padding: 24px;
    max-height: 60vh;
    overflow-y: auto;
}

:deep(.note-detail-dialog .el-dialog__footer) {
    padding: 16px 24px 20px;
    border-top: 1px solid rgba(0,0,0,0.04);
}

.note-detail-content {
    background: linear-gradient(135deg, #fafbfc 0%, #f8f9fb 100%);
    padding: 24px;
    border-radius: 16px;
    border: 1px solid rgba(0,0,0,0.04);
    min-height: 120px;
}

.note-content-markdown {
    color: #334155;
    line-height: 1.8;
    font-size: 15px;
}

.note-content-markdown :deep(h1),
.note-content-markdown :deep(h2),
.note-content-markdown :deep(h3),
.note-content-markdown :deep(h4),
.note-content-markdown :deep(h5),
.note-content-markdown :deep(h6) {
    font-weight: 600;
    color: #1e293b;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    line-height: 1.4;
}

.note-content-markdown :deep(h1) {
    font-size: 1.5rem;
    font-weight: 700;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 0.5rem;
}

.note-content-markdown :deep(h2) {
    font-size: 1.25rem;
    font-weight: 600;
}

.note-content-markdown :deep(h3) {
    font-size: 1.125rem;
    font-weight: 600;
}

.note-content-markdown :deep(h4) {
    font-size: 1rem;
    font-weight: 600;
}

.note-content-markdown :deep(p) {
    margin-bottom: 1rem;
    color: #475569;
}

.note-content-markdown :deep(strong) {
    color: #1e293b;
    font-weight: 600;
}

.note-content-markdown :deep(em) {
    color: #64748b;
    font-style: italic;
}

.note-content-markdown :deep(code) {
    color: #4f46e5;
    background: rgba(79, 70, 229, 0.08);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.note-content-markdown :deep(pre) {
    background: #1e293b;
    border-radius: 0.75rem;
    padding: 1rem;
    margin: 1rem 0;
    overflow-x: auto;
}

.note-content-markdown :deep(pre code) {
    background: transparent;
    color: #e2e8f0;
    padding: 0;
}

.note-content-markdown :deep(ul),
.note-content-markdown :deep(ol) {
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.note-content-markdown :deep(li) {
    margin: 0.375rem 0;
}

.note-content-markdown :deep(blockquote) {
    border-left: 3px solid #818cf8;
    background: linear-gradient(to right, rgba(79, 70, 229, 0.05), transparent);
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    border-radius: 0 0.5rem 0.5rem 0;
}

/* Table Styles */
.note-content-markdown :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 14px;
    border-radius: 0.5rem;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.note-content-markdown :deep(thead) {
    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
}

.note-content-markdown :deep(th) {
    padding: 0.75rem 1rem;
    text-align: left;
    font-weight: 600;
    color: #1e293b;
    border-bottom: 2px solid #cbd5e1;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.note-content-markdown :deep(td) {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #e2e8f0;
    color: #475569;
}

.note-content-markdown :deep(tr:hover) {
    background: rgba(79, 70, 229, 0.03);
}

.note-content-markdown :deep(tr:last-child td) {
    border-bottom: none;
}

.note-content-markdown :deep(a) {
    color: #4f46e5;
    text-decoration: none;
    font-weight: 500;
}

.note-content-markdown :deep(a:hover) {
    text-decoration: underline;
}

.note-content-markdown :deep(hr) {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 1.5rem 0;
}

.note-content-markdown :deep(img) {
    max-width: 100%;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

/* Preview Card Markdown Overrides */
.note-preview-content :deep(h1),
.note-preview-content :deep(h2),
.note-preview-content :deep(h3),
.note-preview-content :deep(h4),
.note-preview-content :deep(h5),
.note-preview-content :deep(h6) {
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    margin: 0.25rem 0 !important;
    line-height: 1.4 !important;
    color: #334155;
}

.note-preview-content :deep(p) {
    margin-bottom: 0.25rem !important;
    font-size: 0.875rem !important;
}

.note-preview-content :deep(ul),
.note-preview-content :deep(ol) {
    margin: 0.25rem 0 !important;
    padding-left: 1rem !important;
}

.note-preview-content :deep(pre),
.note-preview-content :deep(blockquote),
.note-preview-content :deep(table) {
    margin: 0.5rem 0 !important;
    font-size: 0.75rem !important;
}

.note-preview-content :deep(.katex) {
    font-size: 1em !important;
}
</style>
