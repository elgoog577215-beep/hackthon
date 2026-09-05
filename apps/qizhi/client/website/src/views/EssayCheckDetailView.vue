<template>
  <div class="essay-check-detail-view">
    <div class="toolbar">
      <div class="toolbar-left">
        <router-link to="/essay-check" class="back-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回列表</span>
        </router-link>
        <h2 class="page-title">论文检查详情</h2>
      </div>
      <div class="toolbar-right">
        <span v-if="isDemoMode" class="demo-badge">演示模式</span>
        <button
          v-if="reportData"
          type="button"
          class="export-btn"
          @click="handleExport"
          :disabled="exporting"
        >
          {{ exporting ? '导出中...' : '导出Word' }}
        </button>
        <button
          type="button"
          class="refresh-btn"
          :class="{ active: autoRefresh }"
          @click="autoRefresh = !autoRefresh"
        >
          {{ autoRefresh ? '✅' : '⏸' }} 自动刷新
        </button>
        <button type="button" class="refresh-btn" @click="fetchTask" :loading="loading">
          🔃 刷新
        </button>
      </div>
    </div>

    <div class="content-area" :class="{ 'loading-state': loading && !taskData }">
      <div v-if="loading && !taskData" class="spinner-container">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
      <div v-if="taskError" class="error-container">
        <p>{{ taskError }}</p>
        <button type="button" class="retry-btn" @click="fetchTask">重试</button>
      </div>

      <template v-if="taskData">
        <!-- 任务信息 -->
        <div class="task-info">
          <div class="header">
            <div class="header-left">
              <h3 class="filename">{{ taskData.filename }}</h3>
              <span class="status-badge" :class="statusBadgeClass(taskData.status)">{{ statusLabel(taskData.status) }}</span>
            </div>
          </div>

          <div class="meta-row">
            <div class="meta-item">
              <span class="meta-label">总页数</span>
              <span class="meta-value">{{ taskData.total_pages ?? '未知' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">当前阶段</span>
              <span class="meta-value">{{ taskData.current_stage || '-' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Task ID</span>
              <span class="meta-value meta-id">{{ taskData.micro_task_id }}</span>
            </div>
          </div>

          <!-- 进度统计 -->
          <div v-if="taskData.progress" class="stat-row">
            <div class="stat-card total">
              <div class="value">{{ taskData.progress.total_pages }}</div>
              <div class="label">总页数</div>
            </div>
            <div class="stat-card done">
              <div class="value">{{ taskData.progress.completed_pages }}</div>
              <div class="label">已完成</div>
            </div>
            <div class="stat-card fail">
              <div class="value">{{ taskData.progress.failed_pages }}</div>
              <div class="label">失败</div>
            </div>
            <div class="stat-card processing">
              <div class="value">{{ taskData.progress.processing_pages ?? 0 }}</div>
              <div class="label">处理中</div>
            </div>
            <div class="stat-card pending">
              <div class="value">{{ taskData.progress.pending_pages }}</div>
              <div class="label">等待中</div>
            </div>
          </div>

          <!-- 进度条 -->
          <div v-if="taskData.progress" class="custom-progress">
            <div class="progress-track">
              <div
                class="progress-fill"
                :class="{ 'is-complete': Math.round(displayedProgress) >= 100 }"
                :style="{ width: `${displayedProgress}%` }"
                role="progressbar"
                :aria-valuenow="Math.round(displayedProgress)"
                aria-valuemin="0"
                aria-valuemax="100"
              >
              </div>
            </div>
            <div class="progress-meta">
              <span class="progress-label">处理进度</span>
              <span class="progress-pct">{{ Math.round(displayedProgress) }}%</span>
            </div>
          </div>
        </div>

        <!-- 审查报告 -->
        <div v-if="reportData" class="report-section">
          <h3>审查报告</h3>
          <span class="score-badge" :class="'score-' + reportData.overall_score">{{ reportData.overall_score }}</span>
          <p class="report-summary">{{ reportData.summary }}</p>

          <div class="check-domains">
            <div v-for="(domain, idx) in reportData.check_domains" :key="idx" class="domain-block">
              <details :open="idx === 0">
                <summary>
                  <span class="domain-title">
                    <span class="domain-icon" :class="domainStatusClass(domain)">
                      {{ domainStatusIcon(domain) }}
                    </span>
                    {{ domain.domain }}
                  </span>
                  <span class="domain-stats" :class="'stats-' + domainStatusClass(domain)">
                    {{ domain.check_points.filter(cp => cp.passed).length }}/{{ domain.check_points.length }}
                    <span class="stats-label">{{ domainStatusLabel(domain) }}</span>
                  </span>
                </summary>
                <div class="check-points">
                  <div
                    v-for="(cp, i) in domain.check_points"
                    :key="i"
                    class="check-item"
                    :class="cp.passed ? 'check-passed' : 'check-failed'"
                  >
                    <span class="check-icon">{{ cp.passed ? '✅' : '❌' }}</span>
                    <div>
                      <div class="check-name">{{ cp.name }}</div>
                      <div v-if="cp.detail" class="check-detail">{{ cp.detail }}</div>
                    </div>
                  </div>
                </div>
              </details>
            </div>
          </div>

          <div v-if="reportData.reference_issues && reportData.reference_issues.length" class="report-issue">
            <h4>⚠️ 参考文献问题</h4>
            <ul>
              <li v-for="(issue, i) in reportData.reference_issues" :key="i">{{ issue }}</li>
            </ul>
          </div>

          <div v-if="reportData.recommendations && reportData.recommendations.length" class="report-issue">
            <h4>💡 修改建议</h4>
            <ul>
              <li v-for="(rec, i) in reportData.recommendations" :key="i">{{ rec }}</li>
            </ul>
          </div>
        </div>

        <!-- 逐页检查 -->
        <div v-if="pages.length > 0" class="page-viewer-section">
          <div class="viewer-toolbar">
            <h3>页面检查</h3>
            <div class="viewer-controls">
              <button type="button" class="nav-btn" @click="goPrev" :disabled="currentViewIndex <= 0">
                ‹
              </button>
              <div class="viewer-jump">
                <span>第</span>
                <input
                  type="number"
                  v-model.number="currentViewPage"
                  :min="1"
                  :max="totalPages"
                  class="jump-input"
                  @change="jumpToPage"
                />
                <span>/ {{ totalPages }} 页</span>
              </div>
              <button type="button" class="nav-btn" @click="goNext" :disabled="currentViewIndex >= visiblePages.length - 1">
                ›
              </button>
            </div>
            <label class="viewer-filter">
              <input type="checkbox" v-model="viewOnlyFailed" />
              只看检查不通过
            </label>
          </div>

          <div class="viewer-layout" :class="{ 'viewer-loading': viewerLoading }">
            <div class="viewer-image-pane">
              <img v-if="currentImageUrl" :src="currentImageUrl" :alt="`第 ${currentViewPage} 页`" />
              <div v-else class="viewer-image-placeholder">
                <span>加载中...</span>
              </div>
              <div class="viewer-page-label">
                <span class="page-status" :class="statusBadgeClass(currentPageData?.status)">
                  {{ currentPageData?.status || 'unknown' }}
                </span>
                <span class="page-type">{{ pageTypeLabel(currentPageData?.page_type) || '未知' }}</span>
              </div>
            </div>

            <div class="viewer-results-pane">
              <div class="results-header">
                <h4>检查结果</h4>
                <span class="results-count">{{ displayedResults.length }} 项</span>
              </div>
              <div class="results-list">
                <div
                  v-for="(cp, i) in displayedResults"
                  :key="i"
                  class="result-item"
                  :class="cp.passed ? 'passed' : 'failed'"
                >
                  <span class="result-icon">{{ cp.passed ? '✅' : '❌' }}</span>
                  <div class="result-body">
                    <div class="result-name">检查项：{{ cp.check_point || cp.name }}</div>
                    <div v-if="cp.detail" class="result-detail">{{ cp.detail }}</div>
                  </div>
                </div>
                <div v-if="displayedResults.length === 0" class="no-results">
                  暂无检查结果
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 导出选项弹窗 -->
    <div v-if="showExportOptions" class="export-overlay">
      <div class="export-modal export-options-modal">
        <h3>导出 Word 报告</h3>
        <p class="export-options-hint">请选择导出内容范围</p>
        <div class="export-scope-list">
          <label
            v-for="opt in exportScopeOptions"
            :key="opt.value"
            class="export-scope-option"
            :class="{ 'is-selected': exportScope === opt.value }"
          >
            <input
              v-model="exportScope"
              type="radio"
              name="detailExportScope"
              :value="opt.value"
            />
            <span class="export-scope-text">
              <span class="export-scope-label">{{ opt.label }}</span>
              <span class="export-scope-desc">{{ opt.description }}</span>
            </span>
          </label>
        </div>
        <div class="export-options-actions">
          <button type="button" class="export-cancel-btn" @click="cancelExportOptions">取消</button>
          <button type="button" class="export-confirm-btn" @click="confirmExport">确认导出</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  getEssayStatus,
  exportReports,
  ESSAY_EXPORT_SCOPE_OPTIONS,
  ESSAY_AUTO_REFRESH_INTERVAL_MS,
} from '../api/essayCheck'
import type { EssayStatusData, EssayReport, EssayPage, EssayExportScope } from '../api/essayCheck'

const route = useRoute()
const taskId = computed(() => route.params.id as string)
const isDemoMode = computed(() => taskId.value === '__demo-progress__')

const loading = ref(false)
const taskError = ref('')
const taskData = ref<EssayStatusData | null>(null)
const reportData = ref<EssayReport | null>(null)
const autoRefresh = ref(true)
const displayedProgress = ref(0)
const exporting = ref(false)
const showExportOptions = ref(false)
const exportScopeOptions = ESSAY_EXPORT_SCOPE_OPTIONS
const exportScope = ref<EssayExportScope>('summary_only')

let progressFrameId: number | null = null
let demoTimer: ReturnType<typeof setInterval> | null = null

function clampProgress(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

function animateProgressTo(target: number) {
  const nextTarget = clampProgress(target)

  if (progressFrameId !== null) {
    cancelAnimationFrame(progressFrameId)
    progressFrameId = null
  }

  const startValue = displayedProgress.value
  const change = nextTarget - startValue

  if (nextTarget >= 100) {
    displayedProgress.value = 100
    progressFrameId = null
    return
  }

  if (Math.abs(change) < 0.1) {
    displayedProgress.value = nextTarget
    return
  }

  const duration = 420
  const startTime = performance.now()

  const tick = (now: number) => {
    const elapsed = now - startTime
    const progress = Math.min(elapsed / duration, 1)
    displayedProgress.value = startValue + change * easeOutCubic(progress)

    if (progress < 1) {
      progressFrameId = requestAnimationFrame(tick)
    } else {
      displayedProgress.value = nextTarget
      progressFrameId = null
    }
  }

  progressFrameId = requestAnimationFrame(tick)
}

// 页面查看状态
const pages = ref<EssayPage[]>([])
const viewerLoading = ref(false)
const currentViewPage = ref(1)
const currentImageUrl = ref('')
const viewOnlyFailed = ref(false)

const totalPages = computed(() => taskData.value?.total_pages ?? 0)

const pagesMap = computed(() => {
  const m: Record<number, EssayPage> = {}
  for (const p of pages.value) m[p.page_number] = p
  return m
})

const currentPageData = computed(() => pagesMap.value[currentViewPage.value] ?? null)

const visiblePages = computed(() => {
  const result: number[] = []
  for (let i = 1; i <= totalPages.value; i++) {
    const page = pagesMap.value[i]
    if (!page) continue
    if (!viewOnlyFailed.value || hasFailedChecks(page)) {
      result.push(i)
    }
  }
  return result
})

const currentViewIndex = computed(() => visiblePages.value.indexOf(currentViewPage.value))

const POLL_INTERVAL_MS = ESSAY_AUTO_REFRESH_INTERVAL_MS

function createDemoTaskData(percentage: number): EssayStatusData {
  const clamped = clampProgress(percentage)
  const completedPages = Math.max(0, Math.min(20, Math.floor((clamped / 100) * 20)))
  const pendingPages = Math.max(0, 20 - completedPages)
  return {
    task_id: 'demo-task',
    micro_task_id: 'demo-task',
    filename: 'demo_thesis.pdf',
    status: clamped >= 100 ? 'completed' : 'processing',
    current_stage: clamped >= 100 ? '演示完成' : '演示处理中',
    progress: {
      total_pages: 20,
      completed_pages: completedPages,
      failed_pages: 0,
      pending_pages: pendingPages,
      processing_pages: clamped >= 100 ? 0 : 1,
      percentage: clamped,
    },
    pages: [
      {
        id: 'demo-page-1',
        page_number: 1,
        image_url: '',
        page_type: 'body',
        extracted_content: null,
        check_results: [
          { name: '格式检查', check_point: '标题格式', passed: clamped >= 30, detail: clamped >= 30 ? '通过' : '等待处理中' },
          { name: '内容检查', check_point: '摘要完整性', passed: clamped >= 70, detail: clamped >= 70 ? '通过' : '等待处理中' },
        ],
        status: clamped >= 100 ? 'completed' : 'processing',
        error_message: null,
        retry_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ],
    total_pages: 20,
    overall_score: null,
    summary: null,
    check_domains: null,
    reference_issues: null,
    recommendations: null,
  }
}

function startDemoMode() {
  if (demoTimer) clearInterval(demoTimer)
  displayedProgress.value = 0
  taskData.value = createDemoTaskData(0)
  pages.value = taskData.value.pages ?? []
  reportData.value = null
  currentViewPage.value = 1
  currentImageUrl.value = ''
  loading.value = false
  taskError.value = ''
  autoRefresh.value = false

  demoTimer = setInterval(() => {
    const current = taskData.value?.progress?.percentage ?? 0
    const next = Math.min(100, current + (current < 60 ? 7 : current < 90 ? 4 : 2))
    taskData.value = createDemoTaskData(next)
    pages.value = taskData.value.pages ?? []
    if (next >= 100 && demoTimer) {
      clearInterval(demoTimer)
      demoTimer = null
      displayedProgress.value = 100
    }
  }, 240)
}

watch(
  () => taskData.value?.progress?.percentage,
  (percentage) => {
    if (typeof percentage === 'number') {
      animateProgressTo(percentage)
      return
    }
    animateProgressTo(0)
  },
  { immediate: true },
)

const displayedResults = computed(() => {
  const page = currentPageData.value
  if (!page || !isValidCheckResults(page.check_results)) return []
  if (viewOnlyFailed.value) return page.check_results.filter((cp) => !cp.passed)
  return page.check_results
})

function isValidCheckResults(cr: unknown): cr is Array<{passed: boolean; name?: string; check_point?: string; detail?: string | null}> {
  if (!Array.isArray(cr) || cr.length === 0) return false
  // Every item must be an object with a boolean 'passed' field
  return cr.every(item => typeof item === 'object' && item !== null && 'passed' in item && typeof item.passed === 'boolean')
}

function hasFailedChecks(page: EssayPage): boolean {
  if (!isValidCheckResults(page.check_results)) return false
  return page.check_results.some((cp) => !cp.passed)
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    uploaded: '已上传', processing: '处理中', summarizing: '生成报告中',
    completed: '检查完成', failed: '检查失败', pending: '等待处理',
    classifying: '分类中', classified: '分类完成',
  }
  return map[status] ?? status
}

function statusBadgeClass(status?: string): string {
  const map: Record<string, string> = {
    completed: 'badge-success', failed: 'badge-danger',
    uploaded: 'badge-info', processing: 'badge-warning',
    summarizing: 'badge-warning',
  }
  return map[status ?? ''] ?? 'badge-info'
}

function pageTypeLabel(t?: string | null): string {
  const map: Record<string, string> = {
    cover: '封面', commitment: '承诺书', abstract_cn: '中文摘要',
    abstract_en: '英文摘要', toc: '目录', body: '正文',
    conclusion: '结论', references: '参考文献', appendix: '附录',
    task_sheet: '任务书', assessment_form: '考核表',
    expert_review: '专家评阅', defense_record: '答辩记录', unknown: '未知',
  }
  return t ? (map[t] ?? '未知') : '未知'
}

function domainStatusClass(domain: any): string {
  const passed = domain.check_points.filter((cp: any) => cp.passed).length
  if (passed === domain.check_points.length) return 'all-passed'
  if (passed === 0) return 'none-passed'
  return 'partial'
}

function domainStatusIcon(domain: any): string {
  const passed = domain.check_points.filter((cp: any) => cp.passed).length
  if (passed === domain.check_points.length) return '✓'
  if (passed === 0) return '✗'
  return '!'
}

function domainStatusLabel(domain: any): string {
  const passed = domain.check_points.filter((cp: any) => cp.passed).length
  if (passed === domain.check_points.length) return '项全通过'
  if (passed === 0) return '项均未通过'
  return `项通过，${domain.check_points.length - passed}项需关注`
}

// ── 数据加载 ──

async function fetchTask() {
  if (!taskId.value) return
  if (isDemoMode.value) {
    startDemoMode()
    return
  }
  loading.value = true
  taskError.value = ''
  try {
    const statusResp = await getEssayStatus(taskId.value)
    taskData.value = statusResp.data

    // 加载页面数据
    pages.value = statusResp.data.pages ?? []
    if (pages.value.length > 0) {
      loadCurrentImage()
    }

    // 根据任务状态自动决定是否开启刷新：completed 停止，否则继续
    autoRefresh.value = statusResp.data.status !== 'completed'

    // 从 status 响应中提取报告数据（微服务已合并到同一个接口）
    const d = statusResp.data as any
    if (d.overall_score && d.summary) {
      reportData.value = {
        task_id: d.micro_task_id,
        overall_score: d.overall_score,
        summary: d.summary,
        check_domains: d.check_domains ?? [],
        reference_issues: d.reference_issues,
        recommendations: d.recommendations,
      }
    } else {
      reportData.value = null
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '加载失败'
    taskError.value = msg
  } finally {
    loading.value = false
  }
}

function handleExport() {
  showExportOptions.value = true
}

function cancelExportOptions() {
  showExportOptions.value = false
  exportScope.value = 'summary_only'
}

async function confirmExport() {
  showExportOptions.value = false
  exporting.value = true
  try {
    await exportReports([taskId.value], exportScope.value, (progress) => {
      if ('status' in progress && progress.status === 'error') {
        throw new Error(progress.message || '导出失败')
      }
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '导出失败'
    alert(msg)
  } finally {
    exporting.value = false
  }
}

function loadCurrentImage() {
  const page = pagesMap.value[currentViewPage.value]
  currentImageUrl.value = page?.image_url ?? ''
}

function goToPage(num: number) {
  if (num < 1 || num > totalPages.value) return
  currentViewPage.value = num
  loadCurrentImage()
}

function goPrev() {
  const idx = currentViewIndex.value
  if (idx > 0) {
    const prev = visiblePages.value[idx - 1]
    if (prev !== undefined) goToPage(prev)
  }
}

function goNext() {
  const idx = currentViewIndex.value
  if (idx < visiblePages.value.length - 1) {
    const next = visiblePages.value[idx + 1]
    if (next !== undefined) goToPage(next)
  }
}

function jumpToPage() {
  if (currentViewPage.value) goToPage(currentViewPage.value)
}

// ── 自动刷新 ──
let timer: ReturnType<typeof setInterval> | null = null

watch(autoRefresh, (val) => {
  if (isDemoMode.value) return
  if (val) {
    timer = setInterval(() => { if (taskId.value) void fetchTask() }, POLL_INTERVAL_MS)
  } else {
    if (timer) clearInterval(timer)
    timer = null
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (progressFrameId !== null) cancelAnimationFrame(progressFrameId)
  if (demoTimer) clearInterval(demoTimer)
})

onMounted(() => {
  void fetchTask()
  if (isDemoMode.value) return
  // autoRefresh is true by default, start timer
  timer = setInterval(() => { if (taskId.value) void fetchTask() }, POLL_INTERVAL_MS)
})
</script>

<style scoped>
.essay-check-detail-view {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
}

.toolbar {
  background-color: transparent;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: none;
  flex-shrink: 0;
  max-width: 1400px;
  margin-left: auto;
  margin-right: auto;
  width: 100%;
}

.toolbar-left { display: flex; align-items: center; gap: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

.demo-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(103, 194, 58, 0.14);
  color: #4e7d2c;
  font-size: 12px;
  font-weight: 600;
}

.back-btn {
  display: flex; align-items: center; gap: 8px;
  background: none; border: none; cursor: pointer;
  padding: 8px; color: #333; font-size: 14px;
  text-decoration: none; transition: color 0.2s; border-radius: 4px;
}
.back-btn:hover { color: #C5D9FF; }

.page-title { font-size: 20px; font-weight: 600; color: #333; margin: 0; }

.refresh-btn {
  padding: 6px 12px; background: rgba(255,255,255,0.3); border: none;
  border-radius: 6px; cursor: pointer; font-size: 13px; color: #333;
  transition: background-color 0.2s;
}
.refresh-btn:hover { background: rgba(255,255,255,0.45); }
.refresh-btn.active { background: rgba(103,194,58,0.15); }

.export-btn {
  padding: 6px 16px;
  background: #409eff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #fff;
  font-weight: 500;
  transition: background-color 0.2s;
}
.export-btn:hover:not(:disabled) { background: #66b1ff; }
.export-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.export-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.export-modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 480px;
  max-height: 80vh;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.export-modal h3 {
  font-size: 16px;
  color: #333;
  margin: 0;
}

.export-options-hint {
  margin: 0;
  font-size: 13px;
  color: #888;
}

.export-scope-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.export-scope-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.export-scope-option:hover {
  border-color: #c6e2ff;
  background: rgba(64, 158, 255, 0.04);
}

.export-scope-option.is-selected {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.08);
}

.export-scope-option input[type="radio"] {
  margin-top: 3px;
  accent-color: #409eff;
  flex-shrink: 0;
}

.export-scope-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.export-scope-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.export-scope-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.export-options-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.export-cancel-btn {
  padding: 8px 20px;
  background: #f0f0f0;
  color: #666;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}
.export-cancel-btn:hover { background: #e0e0e0; }

.export-confirm-btn {
  padding: 8px 20px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}
.export-confirm-btn:hover { background: #66b1ff; }

.content-area {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  box-sizing: border-box;
  max-width: 1400px;
  margin-left: auto;
  margin-right: auto;
  width: 100%;
}

.error-container { text-align: center; padding: 48px 24px; color: #666; }
.retry-btn { margin-top: 12px; padding: 8px 16px; background: #C5D9FF; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }

.spinner-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 24px;
  color: #999;
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e8eef9;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.viewer-layout.viewer-loading {
  position: relative;
  opacity: 0.6;
  pointer-events: none;
}

/* 任务信息 */
.task-info {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  margin-bottom: 20px;
}
.task-info .header { margin-bottom: 16px; }
.header-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.filename {
  font-size: 17px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
  line-height: 1.4;
  word-break: break-all;
}

.meta-row {
  display: flex;
  gap: 24px;
  padding: 14px 18px;
  background: #f7f8fa;
  border-radius: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.meta-label {
  font-size: 12px;
  color: #909399;
  letter-spacing: 0.3px;
}
.meta-value {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}
.meta-id {
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  color: #606266;
  background: #eef0f4;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
}
.badge-success { background: #e8facd; color: #61714a; }
.badge-danger { background: #fdecea; color: #b3261e; }
.badge-warning { background: #fff8e6; color: #8a6d1d; }
.badge-info { background: #e8eef9; color: #4a5f8a; }

.stat-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; background: #f5f7fa; border-radius: 6px; padding: 16px; text-align: center; }
.stat-card .value { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.stat-card .label { font-size: 12px; color: #909399; }
.stat-card.total .value { color: #409eff; }
.stat-card.done .value { color: #67c23a; }
.stat-card.fail .value { color: #f56c6c; }
.stat-card.processing .value { color: #e6a23c; }
.stat-card.pending .value { color: #909399; }
.progress-text { font-size: 14px; color: #606266; margin-bottom: 16px; }

.custom-progress { margin-bottom: 16px; }
.custom-progress .progress-track {
  height: 14px;
  background: #f0f2f5;
  border-radius: 7px;
  overflow: hidden;
}
.custom-progress .progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #67c23a 0%, #8ed36d 50%, #67c23a 100%);
  background-size: 200% 100%;
  animation: progress-flow 1.6s linear infinite;
  border-radius: 999px;
  position: relative;
  overflow: hidden;
  transition: width 0.42s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: width;
}
.custom-progress .progress-fill.is-complete {
  animation: none;
  background-position: 0 0;
}
@keyframes progress-flow {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
.custom-progress .progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}
.custom-progress .progress-label { font-size: 13px; color: #909399; }
.custom-progress .progress-pct { font-size: 14px; font-weight: 600; color: #333; }

/* 审查报告 */
.report-section {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  margin-bottom: 20px;
}
.report-section h3 { font-size: 16px; margin-bottom: 16px; color: #333; }
.score-badge {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 4px;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 16px;
}
.score-合格 { background: #f0f9eb; color: #67c23a; }
.score-需修改 { background: #fdf6ec; color: #e6a23c; }
.score-不合格 { background: #fef0f0; color: #f56c6c; }
.report-summary { margin-bottom: 16px; color: #606266; font-size: 14px; line-height: 1.6; }

.check-domains { display: flex; flex-direction: column; gap: 8px; }
.domain-block details {
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #eee;
}
.domain-block summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  color: #333;
  list-style: none;
  gap: 8px;
}
.domain-block summary::-webkit-details-marker { display: none; }
.domain-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.domain-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.domain-icon.all-passed { background: #e8facd; color: #61714a; }
.domain-icon.partial { background: #fff8e6; color: #8a6d1d; }
.domain-icon.none-passed { background: #fdecea; color: #b3261e; }

.domain-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}
.stats-label {
  font-weight: 400;
  font-size: 12px;
}
.stats-all-passed { background: #e8facd; color: #61714a; }
.stats-partial { background: #fff8e6; color: #8a6d1d; }
.stats-none-passed { background: #fdecea; color: #b3261e; }
.domain-stats { font-size: 12px; color: #999; font-weight: 400; }
.check-points { padding: 0 16px 12px; }
.check-item {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid #f0f0f0;
  align-items: flex-start;
}
.check-icon { flex-shrink: 0; margin-top: 2px; }
.check-name { font-size: 13px; color: #606266; font-weight: 500; }
.check-detail { font-size: 12px; color: #909399; margin-top: 4px; }

.report-issue { margin-top: 20px; }
.report-issue h4 { font-size: 15px; margin-bottom: 8px; color: #333; }
.report-issue ul { margin-top: 8px; padding-left: 20px; color: #606266; font-size: 13px; line-height: 1.8; }

/* 页面查看 */
.page-viewer-section {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}
.viewer-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid #ebeef5;
}
.viewer-toolbar h3 { font-size: 16px; color: #333; margin: 0; }
.viewer-controls { display: flex; align-items: center; gap: 8px; }
.nav-btn {
  width: 32px; height: 32px;
  border-radius: 50%;
  border: 1px solid #ddd;
  background: #fff;
  cursor: pointer;
  font-size: 18px;
  color: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s;
}
.nav-btn:hover:not(:disabled) { background: #f0f0f0; }
.nav-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.viewer-jump { display: flex; align-items: center; gap: 4px; color: #606266; font-size: 13px; }
.jump-input {
  width: 50px; padding: 4px 6px;
  border: 1px solid #ddd; border-radius: 4px;
  font-size: 13px; text-align: center;
}
.viewer-filter {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: #606266; cursor: pointer;
}

.viewer-layout { display: flex; height: 75vh; }
.viewer-image-pane {
  width: 60%;
  background: #1a1a2e;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: auto;
}
.viewer-image-pane img { max-width: 100%; max-height: 100%; object-fit: contain; }
.viewer-image-placeholder { color: #888; font-size: 14px; }
.viewer-page-label {
  position: absolute; bottom: 0; left: 0; right: 0;
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px;
  background: rgba(0,0,0,0.6);
  color: #ccc; font-size: 13px;
}
.page-status.badge-success { color: #67c23a; }
.page-status.badge-danger { color: #f56c6c; }
.page-status.badge-warning { color: #e6a23c; }
.page-status.badge-info { color: #90caf9; }
.page-type { color: #999; }

.viewer-results-pane {
  width: 40%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #ebeef5;
}
.results-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px; border-bottom: 1px solid #eee;
}
.results-header h4 { font-size: 15px; color: #333; }
.results-count { font-size: 13px; color: #909399; }
.results-list { flex: 1; overflow-y: auto; padding: 0; }
.result-item { display: flex; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }
.result-item.passed { background: #f0f9eb; }
.result-item.failed { background: #fef0f0; }
.result-icon { font-size: 16px; flex-shrink: 0; margin-top: 2px; }
.result-body { flex: 1; }
.result-name { font-size: 14px; font-weight: 500; color: #333; margin-bottom: 4px; }
.result-detail { font-size: 12px; color: #606266; line-height: 1.6; }
.no-results { text-align: center; padding: 40px 20px; color: #909399; font-size: 14px; }

@media (max-width: 768px) {
  .toolbar { padding: 16px; }
  .content-area { padding: 16px; }
  .viewer-layout { flex-direction: column; height: auto; }
  .viewer-image-pane { width: 100%; height: 50vh; }
  .viewer-results-pane { width: 100%; }
}
</style>
