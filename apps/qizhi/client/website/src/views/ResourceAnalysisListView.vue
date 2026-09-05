<template>
  <div class="resource-analysis-list-view core-app-page core-app-page--flow">
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">资源分析</h2>
      </div>
      <div class="toolbar-right">
        <div class="dropdown-wrapper">
          <button
            type="button"
            class="dropdown-btn is-capsule-primary"
            @click="toggleCreateAnalysis"
          >
            <svg
              class="dropdown-btn-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M12 5v14M5 12h14"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
            <span>新建分析</span>
          </button>
          <div v-if="showCreateAnalysis" class="dropdown-menu">
            <div class="dropdown-item" @click="goSmartClassroomAnalysis">智云课堂视频分析</div>
            <div class="dropdown-item" @click="openLocalVideoModal">本地视频分析</div>
            <div class="dropdown-item" @click="goDocumentAnalysis">文档教学分析</div>
            <div class="dropdown-item" @click="goDocumentCompare">文档对比分析</div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-area">
      <div v-if="loading" class="loading-container">
        <p>加载中...</p>
      </div>
      <div v-else-if="error" class="error-container">
        <p>加载失败，请稍后重试</p>
        <button type="button" class="retry-btn" @click="loadList">重试</button>
      </div>
      <div v-else-if="list.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="empty-title">暂无分析任务</p>
        <p class="empty-desc">点击右上角「新建分析」，选择智云课堂或本地上传视频</p>
      </div>
      <div v-else class="task-grid">
        <div
          v-for="task in list"
          :key="task.id"
          class="task-card"
          role="button"
          tabindex="0"
          @click="goToReport(task)"
          @keydown.enter="goToReport(task)"
        >
          <div class="card-thumb" :class="{ 'card-thumb--document': task.type === 'document' }" @click.stop>
            <template v-if="task.type === 'document'">
              <div class="card-thumb-placeholder card-thumb-placeholder--document">
                <span class="doc-decor" aria-hidden="true">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="#1358e4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="rgba(19,88,228,0.08)"/>
                    <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="#1358e4" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </span>
                <span class="type-badge type-badge--document">文档分析</span>
              </div>
            </template>
            <template v-else>
              <img
                v-if="task.coverUrl"
                :src="task.coverUrl"
                alt=""
                class="card-thumb-img"
              />
              <div v-else class="card-thumb-placeholder">
                <span class="play-decor" aria-hidden="true">
                  <svg width="56" height="56" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="28" cy="28" r="27" stroke="rgba(0,0,0,0.12)" stroke-width="2"/>
                    <path d="M22 18L40 28L22 38V18Z" fill="rgba(0,0,0,0.22)"/>
                  </svg>
                </span>
              </div>
              <span class="type-badge type-badge--video">视频分析</span>
            </template>
          </div>
          <div class="card-lower">
            <h3 class="card-title" :title="task.name">{{ task.name }}</h3>
            <div class="card-course" :title="courseInfoLine(task)">{{ courseInfoLine(task) }}</div>
            <div class="status-row">
              <div
                class="status-strip"
                :class="statusStripClass(task.status)"
              >
                {{ statusLabel(task.status) }}
              </div>
              <span v-if="analysisEtaCountdownText(task)" class="status-eta">{{ analysisEtaCountdownText(task) }}</span>
            </div>
            <button
              type="button"
              class="report-btn"
              @click.stop="goToReport(task)"
            >
              查看报告
            </button>
          </div>
        </div>
      </div>
    </div>

    <LocalVideoAnalysisModal
      :visible="showLocalVideoModal"
      @close="closeLocalVideoModal"
      @submitted="onLocalVideoSubmitted"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { isVideoTaskPollingActive } from '../api/video'
import { listUnifiedAnalysisTasks, RESOURCE_ANALYSIS_FORCE_REFRESH_EVENT, isDocumentHistoryId, getDocumentRecordId } from '../api/resourceAnalysis'
import type { UnifiedAnalysisTask, AnalysisTaskStatus } from '../api/resourceAnalysis'
import LocalVideoAnalysisModal from '../components/LocalVideoAnalysisModal.vue'

const router = useRouter()
const showCreateAnalysis = ref(false)
const showLocalVideoModal = ref(false)
const loading = ref(true)
const error = ref<string | null>(null)
const list = ref<UnifiedAnalysisTask[]>([])
/** 定时刷新，驱动「预计剩余」倒计时文案 */
const clockTick = ref(Date.now())
/** 列表数据最近一次加载的时刻：用于在两次轮询之间平滑倒计时后端预估 */
const listLoadedAt = ref(Date.now())
const FORCE_REFRESH_EVENT = RESOURCE_ANALYSIS_FORCE_REFRESH_EVENT
const forceRefreshHandler = () => {
  void loadList()
}

function courseInfoLine(task: UnifiedAnalysisTask): string {
  if (task.type === 'document') return formatDate(task.createdAt)
  const parts = [task.courseName, task.teacherName, task.college].filter((x) => !!x && String(x).trim())
  if (parts.length) return parts.join(' · ')
  return formatDate(task.createdAt)
}

function statusLabel(status: AnalysisTaskStatus): string {
  const map: Record<AnalysisTaskStatus, string> = {
    unstarted: '待分析',
    waiting: '分析中',
    success: '分析完成',
    failed: '分析失败',
  }
  return map[status] ?? status
}

/**
 * 本地分析的预计剩余时间：用后端按「视频时长 + 排队数量 + 部署并发」算出的
 * estimatedSeconds（已含排在它前面的视频的等待时间），并在两次轮询之间用 clockTick
 * 平滑倒计时。云端分析没有该预估（estimatedSeconds 为 null）→ 不显示时间。
 */
function analysisEtaCountdownText(task: UnifiedAnalysisTask): string {
  if (task.type !== 'video') return ''
  if (task.status !== 'waiting') return ''
  const est = task.estimatedSeconds
  if (est == null || !Number.isFinite(est) || est <= 0) return ''
  const elapsedSec = Math.max(0, (clockTick.value - listLoadedAt.value) / 1000)
  const remainSec = est - elapsedSec
  if (remainSec <= 30) return '即将完成'
  const totalMin = Math.max(1, Math.ceil(remainSec / 60))
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  let part = ''
  if (h > 0 && m > 0) part = `${h}小时${m}分钟`
  else if (h > 0) part = `${h}小时`
  else part = `${m}分钟`
  return `预计剩余约${part}`
}

function statusStripClass(status: AnalysisTaskStatus): string {
  if (status === 'success') return 'status-completed'
  if (status === 'failed') return 'status-failed'
  if (status === 'unstarted') return 'status-pending'
  if (status === 'waiting') return 'status-analyzing'
  return 'status-pending'
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

async function loadList() {
  loading.value = true
  error.value = null
  try {
    list.value = await listUnifiedAnalysisTasks()
    listLoadedAt.value = Date.now()
  } catch (e) {
    console.error('[ResourceAnalysis] 加载列表失败', e)
    error.value = 'failed'
    list.value = []
  } finally {
    loading.value = false
  }
}

function goToReport(task: UnifiedAnalysisTask) {
  if (isDocumentHistoryId(task.id)) {
    router.push({ path: '/document-analysis', query: { recordId: getDocumentRecordId(task.id) } })
    return
  }
  router.push(`/resource-analysis/report-new/${encodeURIComponent(task.id)}`)
}

function toggleCreateAnalysis() {
  showCreateAnalysis.value = !showCreateAnalysis.value
}

function goSmartClassroomAnalysis() {
  showCreateAnalysis.value = false
  router.push('/smart-classroom-video-analysis')
}

function goDocumentAnalysis() {
  showCreateAnalysis.value = false
  router.push('/document-analysis')
}

function goDocumentCompare() {
  showCreateAnalysis.value = false
  router.push('/document-analysis/compare')
}

function openLocalVideoModal() {
  showCreateAnalysis.value = false
  showLocalVideoModal.value = true
}

function closeLocalVideoModal() {
  showLocalVideoModal.value = false
}

function onLocalVideoSubmitted(taskId: string) {
  router.push(`/resource-analysis/report-new/${encodeURIComponent(taskId)}`)
}

function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.dropdown-wrapper')) {
    showCreateAnalysis.value = false
  }
}

const POLL_INTERVAL_MS = 5 * 1000
const COUNTDOWN_TICK_MS = 60 * 1000
let pollTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null

function hasUnfinishedTasks(): boolean {
  return list.value.some((t) => isVideoTaskPollingActive(t.status))
}

async function pollListIfNeeded() {
  if (!hasUnfinishedTasks()) return
  if (loading.value) return
  await loadList()
}

onMounted(() => {
  loadList()
  window.addEventListener('click', handleClickOutside)
  window.addEventListener(FORCE_REFRESH_EVENT, forceRefreshHandler)
  pollTimer = setInterval(() => {
    void pollListIfNeeded()
  }, POLL_INTERVAL_MS)
  countdownTimer = setInterval(() => {
    clockTick.value = Date.now()
  }, COUNTDOWN_TICK_MS)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (countdownTimer) clearInterval(countdownTimer)
  window.removeEventListener('click', handleClickOutside)
  window.removeEventListener(FORCE_REFRESH_EVENT, forceRefreshHandler)
})
</script>

<style scoped>
/* 标题栏与内容区同宽 1280px 居中（与「我的资源」对齐） */
.resource-analysis-list-view {
  --toolbar-content-gap: 48px;
  --page-content-width: 1280px;
}

.resource-analysis-list-view.core-app-page--flow .toolbar,
.resource-analysis-list-view.core-app-page--flow .content-area {
  width: min(calc(100% - 32px), var(--page-content-width));
  max-width: var(--page-content-width);
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
}

.resource-analysis-list-view.core-app-page--flow .toolbar {
  padding-left: 0;
  padding-right: 0;
}

.resource-analysis-list-view.core-app-page--flow .content-area {
  margin-left: auto;
  margin-right: auto;
}

.dropdown-wrapper {
  position: relative;
  flex-shrink: 0;
  z-index: 10;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  min-width: 200px;
  z-index: 1000;
  padding: 8px;
}

.dropdown-item {
  padding: 12px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: background-color 0.2s;
  border-radius: 4px;
}

.dropdown-item:hover {
  background-color: #f5f5f5;
}

.loading-container, .error-container { text-align: center; padding: 48px 24px; color: #666; }
.retry-btn { margin-top: 12px; padding: 8px 16px; background: #C5D9FF; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }

.empty-state { text-align: center; padding: 48px 24px; }
.empty-icon { color: #bbb; margin-bottom: 20px; }
.empty-title { font-size: 18px; font-weight: 600; color: #333; margin: 0 0 12px 0; }
.empty-desc { font-size: 14px; color: #666; margin: 0 0 24px 0; }

/* 4 列等分 + 24px 间距；卡片宽度随 content-area 等比缩放（封面略减、下方信息区略增高） */
.task-grid {
  --task-card-gap: 24px;
  --task-card-ratio-w: 385;
  --task-card-ratio-h: 448;
  --task-thumb-ratio-h: 248;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--task-card-gap);
  width: 100%;
  box-sizing: border-box;
  align-items: start;
}

.task-card {
  container-type: inline-size;
  width: 100%;
  max-width: none;
  height: auto;
  aspect-ratio: var(--task-card-ratio-w) / var(--task-card-ratio-h);
  border-radius: clamp(10px, 3.12cqw, 12px);
  overflow: hidden;
  background: #fff;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: box-shadow 0.2s;
  box-sizing: border-box;
}
.task-card:hover {
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
}
.task-card:focus-visible {
  outline: 2px solid rgba(19, 88, 228, 0.45);
  outline-offset: 2px;
}

.card-thumb {
  flex: 0 0 calc(100% * var(--task-thumb-ratio-h) / var(--task-card-ratio-h));
  height: calc(100% * var(--task-thumb-ratio-h) / var(--task-card-ratio-h));
  min-height: 0;
  background: #d9d9d9;
  position: relative;
  overflow: hidden;
}

.card-thumb--document {
  background: linear-gradient(135deg, #eef3ff 0%, #dce6fa 100%);
}

.card-thumb-placeholder--document {
  flex-direction: column;
  gap: 12px;
  background: transparent;
}

.doc-decor {
  display: flex;
  align-items: center;
  justify-content: center;
}

.type-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

.type-badge--video {
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
}

.type-badge--document {
  position: static;
  background: rgba(19, 88, 228, 0.12);
  color: #1358e4;
}

.card-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}

.card-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #d9d9d9;
  pointer-events: none;
}

.play-decor {
  display: flex;
  align-items: center;
  justify-content: center;
}

.play-decor svg {
  width: clamp(40px, 14.55cqw, 56px);
  height: auto;
}

.card-lower {
  flex: 1 1 auto;
  min-height: 0;
  background: #fff;
  padding: clamp(8px, 3.64cqw, 14px) clamp(10px, 3.64cqw, 14px) clamp(10px, 3.64cqw, 14px);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: clamp(5px, 2.08cqw, 8px);
  box-sizing: border-box;
}

/* 字号按设计稿 385px 宽等比缩放（3.9cqw ≈ 15px @ 385px） */
.card-title {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
  font-size: clamp(12px, 3.9cqw, 15px);
  font-weight: 700;
  color: #333;
  margin: 0;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-course {
  flex-shrink: 0;
  width: 100%;
  min-width: 0;
  font-size: clamp(11px, 3.38cqw, 13px);
  font-weight: 400;
  color: #666;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: clamp(4px, 1.56cqw, 6px) clamp(6px, 2.08cqw, 8px);
  width: 100%;
  min-height: clamp(22px, 6.75cqw, 26px);
}

.status-strip {
  width: clamp(84px, 29.1cqw, 112px);
  height: clamp(22px, 6.75cqw, 26px);
  border-radius: clamp(3px, 1.04cqw, 4px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(10px, 3.12cqw, 12px);
  font-weight: 500;
  flex-shrink: 0;
}

.status-eta {
  font-size: clamp(10px, 3.12cqw, 12px);
  font-weight: 400;
  color: #7a7f8c;
  line-height: 1.3;
  flex: 1 1 auto;
  min-width: 0;
}

.status-strip.status-completed {
  background: #e8facd;
  color: #61714a;
}

.status-strip.status-analyzing {
  background: #fff8e6;
  color: #8a6d1d;
}

.status-strip.status-pending {
  background: #e8eef9;
  color: #4a5f8a;
}

.status-strip.status-failed {
  background: #fdecea;
  color: #b3261e;
}

.report-btn {
  margin-top: auto;
  width: 100%;
  padding: clamp(8px, 2.6cqw, 10px) clamp(12px, 4.16cqw, 16px);
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: clamp(8px, 2.6cqw, 10px);
  font-size: clamp(12px, 3.64cqw, 14px);
  font-weight: 500;
  color: #333;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
  box-sizing: border-box;
}
.report-btn:hover {
  background: #fafafa;
  border-color: #d0d0d0;
}

@media (max-width: 1200px) {
  .task-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .task-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    --task-card-gap: 20px;
  }
}

@media (max-width: 640px) {
  .task-grid {
    grid-template-columns: minmax(0, 1fr);
    --task-card-gap: 20px;
  }
}
</style>
