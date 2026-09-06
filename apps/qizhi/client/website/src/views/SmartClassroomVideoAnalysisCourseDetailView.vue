<template>
  <div class="sc-course-detail-view">
    <div class="toolbar-row">
      <router-link :to="backToListHref" class="back-btn">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>返回</span>
      </router-link>
      <div class="toolbar-main">
        <h2 class="page-title">{{ courseTitle }}</h2>
      </div>
    </div>

    <div class="content-row">
      <div class="back-slot" aria-hidden="true">
        <span class="back-btn back-btn--phantom">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回</span>
        </span>
      </div>
      <div class="content-main">
        <div v-if="itemsSorted.length === 0" class="empty-state">
          <p class="empty-title">暂无视频</p>
        </div>

        <div v-else class="task-grid">
          <div
            v-for="it in itemsSorted"
            :key="it.sub_id"
            class="task-card video-task-card"
          >
            <div class="card-thumb-wrap">
              <div class="card-thumb" aria-hidden="true">
                <svg class="thumb-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M10 9l5 3-5 3V9z" fill="currentColor"/>
                </svg>
              </div>
              <div
                v-if="statusOf(it) === 'analyzing'"
                class="progress-strip"
              >
                <span class="progress-spinner" aria-hidden="true" />
                <span class="progress-text">视频分析进度：{{ progressOf(it) }}%，预计{{ etaOf(it) }}小时后完成</span>
              </div>
            </div>
            <div class="card-info">
              <div class="card-type-badge video">视频</div>
              <h3 class="card-title">{{ it.title || it.sub_id }}</h3>
              <div class="card-meta">{{ it.date || '未填写日期' }}</div>
            </div>
            <div class="card-footer-actions">
              <button
                v-if="statusOf(it) === 'none'"
                type="button"
                class="action-apply"
                @click="applyAnalysis(it)"
              >
                申请分析资源
              </button>
              <button
                v-else-if="statusOf(it) === 'analyzing'"
                type="button"
                class="action-report-disabled"
                disabled
              >
                查看报告
              </button>
              <button
                v-else
                type="button"
                class="action-report-ready"
                @click="goReport(it)"
              >
                查看报告
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

type AnalysisStatus = 'none' | 'analyzing' | 'completed'

type LocalSubItem = {
  sub_id: string
  title: string
  date: string
  analysisStatus?: AnalysisStatus
  /** 分析进度 0–100，mock */
  analysisProgress?: number
  /** 预计剩余小时，mock */
  etaHours?: number
  /** 跳转报告页用的视频任务 id */
  reportTaskId?: string
}

const route = useRoute()
const router = useRouter()

const isMockMode = computed(() => import.meta.env.DEV && route.query?.mock === '1')

const courseId = computed(() => {
  const raw = String(route.params.courseId || '')
  try { return decodeURIComponent(raw) } catch { return raw }
})

const courseTitle = computed(() => `课程：${courseId.value}`)

const backToListHref = computed(() => {
  const q = isMockMode.value ? '?mock=1' : ''
  return `/smart-classroom-video-analysis${q}`
})

const storageKey = computed(() => `sc_video_analysis:course:${courseId.value}:subs`)

const items = ref<LocalSubItem[]>([])

/** sub_id -> interval id，用于 mock 分析进度动画 */
const tickers = new Map<string, ReturnType<typeof setInterval>>()

function loadLocal() {
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) { items.value = []; return }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) { items.value = []; return }
    items.value = parsed
      .filter((x) => x && typeof x === 'object')
      .map((x) => {
        const o = x as Record<string, unknown>
        return {
          sub_id: String(o.sub_id || ''),
          title: String(o.title || ''),
          date: String(o.date || ''),
          analysisStatus: normalizeStatus(o.analysisStatus),
          analysisProgress: typeof o.analysisProgress === 'number' ? o.analysisProgress : undefined,
          etaHours: typeof o.etaHours === 'number' ? o.etaHours : undefined,
          reportTaskId: o.reportTaskId != null ? String(o.reportTaskId) : undefined,
        } as LocalSubItem
      })
      .filter((x) => x.sub_id)
  } catch {
    items.value = []
  }
}

function normalizeStatus(v: unknown): AnalysisStatus | undefined {
  if (v === 'none' || v === 'analyzing' || v === 'completed') return v
  return undefined
}

function saveLocal() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify(items.value))
  } catch {
    //
  }
}

function normalizeDateStr(s: string): string {
  const t = s.trim()
  if (!t) return ''
  return t.replace(/\//g, '-')
}

const itemsSorted = computed(() => {
  const list = [...items.value]
  list.sort((a, b) => {
    const da = Date.parse(normalizeDateStr(a.date) || '')
    const db = Date.parse(normalizeDateStr(b.date) || '')
    if (Number.isFinite(da) && Number.isFinite(db)) return db - da
    if (Number.isFinite(db)) return 1
    if (Number.isFinite(da)) return -1
    return (b.date || '').localeCompare(a.date || '')
  })
  return list
})

function statusOf(it: LocalSubItem): AnalysisStatus {
  return it.analysisStatus ?? 'none'
}

function progressOf(it: LocalSubItem): number {
  const p = it.analysisProgress
  if (typeof p === 'number' && Number.isFinite(p)) return Math.min(100, Math.max(0, Math.round(p)))
  return 0
}

function etaOf(it: LocalSubItem): number {
  const h = it.etaHours
  if (typeof h === 'number' && Number.isFinite(h) && h > 0) return Math.round(h * 10) / 10
  return 2
}

function applyAnalysis(it: LocalSubItem) {
  const idx = items.value.findIndex((x) => x.sub_id === it.sub_id)
  if (idx === -1) return
  const row = items.value[idx]
  if (!row) return
  row.analysisStatus = 'analyzing'
  row.analysisProgress = 12
  row.etaHours = 3
  saveLocal()
  startAnalyzingMock(it.sub_id)
}

function startAnalyzingMock(subId: string) {
  stopTicker(subId)
  const started = Date.now()
  const t = setInterval(() => {
    const idx = items.value.findIndex((x) => x.sub_id === subId)
    if (idx === -1) {
      stopTicker(subId)
      return
    }
    const row = items.value[idx]
    if (!row || row.analysisStatus !== 'analyzing') {
      stopTicker(subId)
      return
    }
    const elapsed = (Date.now() - started) / 1000
    row.analysisProgress = Math.min(99, 12 + Math.floor(elapsed * 8))
    row.etaHours = Math.max(0.5, 3 - elapsed / 25)
    saveLocal()
    if (row.analysisProgress >= 99) {
      stopTicker(subId)
      row.analysisStatus = 'completed'
      row.analysisProgress = 100
      row.reportTaskId = resolveReportTaskId(subId)
      saveLocal()
    }
  }, 800)
  tickers.set(subId, t)
}

function stopTicker(subId: string) {
  const t = tickers.get(subId)
  if (t) {
    clearInterval(t)
    tickers.delete(subId)
  }
}

/** 报告页任务 id：mock 用内置 demo；否则用 sub_id 衍生（后端接入后可换为真实 task id） */
function resolveReportTaskId(subId: string): string {
  if (isMockMode.value) return 'task-demo-1'
  return `sc-report-${subId}`
}

function goReport(it: LocalSubItem) {
  const id = it.reportTaskId?.trim()
  if (!id) return
  router.push(`/resource-analysis/report/${encodeURIComponent(id)}`)
}

onMounted(() => {
  loadLocal()
  if (isMockMode.value && items.value.length === 0) {
    items.value = [
      { sub_id: 'mock-sub-20260312', title: '第1讲：课程介绍与问题引入', date: '2026-03-12', analysisStatus: 'none' },
      { sub_id: 'mock-sub-20260319', title: '第2讲：信息架构与导航设计', date: '2026-03-19', analysisStatus: 'analyzing', analysisProgress: 38, etaHours: 2.5 },
      { sub_id: 'mock-sub-20260326', title: '第3讲：交互原型与可用性', date: '2026-03-26', analysisStatus: 'completed', analysisProgress: 100, reportTaskId: 'task-demo-1' },
    ]
    saveLocal()
    items.value.filter((x) => x.analysisStatus === 'analyzing').forEach((x) => startAnalyzingMock(x.sub_id))
  } else {
    items.value.filter((x) => x.analysisStatus === 'analyzing').forEach((x) => startAnalyzingMock(x.sub_id))
  }
})

onBeforeUnmount(() => {
  tickers.forEach((t) => clearInterval(t))
  tickers.clear()
})
</script>

<style scoped>
.sc-course-detail-view {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
}

.toolbar-row,
.content-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding-left: var(--toolbar-pad-left, 102px);
  padding-right: 24px;
  box-sizing: border-box;
}

.toolbar-row {
  flex-shrink: 0;
  padding-top: 16px;
  padding-bottom: 8px;
  background-color: transparent;
  box-shadow: none;
}

.toolbar-main {
  flex: 1;
  min-width: 0;
}

.content-row {
  flex: 1;
  min-height: 0;
  padding-top: 16px;
  padding-bottom: 24px;
  overflow-y: auto;
}

.back-slot {
  flex-shrink: 0;
}

.content-main {
  flex: 1;
  min-width: 0;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: #333;
  font-size: 14px;
  text-decoration: none;
  transition: color 0.2s;
  border-radius: 4px;
}
.back-btn:hover { color: #C5D9FF; }

.back-btn--phantom {
  visibility: hidden;
  pointer-events: none;
  user-select: none;
}

.empty-state {
  text-align: center;
  padding: 28px 12px 8px;
}
.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

/* 与资源分析列表 task-card 一致 */
.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.task-card.video-task-card {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s;
}
.task-card.video-task-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-thumb-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: linear-gradient(145deg, #e8eef9 0%, #d5e3f7 100%);
  flex-shrink: 0;
}

.card-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(19, 88, 228, 0.35);
}

.thumb-icon {
  opacity: 0.9;
}

.progress-strip {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 10px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 10px;
  background: #0069b5;
  display: flex;
  align-items: center;
  gap: 10px;
  box-sizing: border-box;
}

.progress-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  flex-shrink: 0;
  animation: spin 0.75s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.progress-text {
  font-size: 12px;
  color: #fff;
  line-height: 1.35;
  flex: 1;
  min-width: 0;
}

.card-info {
  padding: 16px 16px 12px;
  flex: 1;
  min-width: 0;
}

.card-type-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
  margin-bottom: 6px;
}
.card-type-badge.video { background: #e3f2fd; color: #1565c0; }

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  margin: 0 0 6px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta { font-size: 13px; color: #666; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.card-footer-actions {
  padding: 0 16px 16px;
}

.action-apply {
  width: 100%;
  padding: 8px 16px;
  background: #d5e4ff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: filter 0.2s, background-color 0.2s;
}
.action-apply:hover {
  filter: brightness(0.98);
}

.action-report-disabled {
  width: 100%;
  padding: 8px 16px;
  background: #f0f0f0;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  color: #b0b0b0;
  cursor: not-allowed;
}

.action-report-ready {
  width: 100%;
  padding: 8px 16px;
  background: #ebffee;
  border: 1px solid #209114;
  border-radius: 8px;
  font-size: 14px;
  color: #1b7a0f;
  cursor: pointer;
  transition: filter 0.2s, background-color 0.2s;
}
.action-report-ready:hover {
  filter: brightness(0.97);
}

@media (max-width: 640px) {
  .toolbar-row,
  .content-row {
    padding-right: 16px;
  }
  .task-grid {
    grid-template-columns: 1fr;
    gap: 14px;
  }
}
</style>
