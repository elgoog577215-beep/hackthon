<template>
  <div class="essay-check-list-view">
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">论文分析</h2>
        <router-link to="/essay-check/upload" class="btn-primary">上传论文</router-link>
        <button
          v-if="!selectMode && list.length > 0"
          type="button"
          class="btn-select-mode"
          @click="enterSelectMode"
        >
          批量选择
        </button>
        <template v-if="selectMode">
          <button
            type="button"
            class="btn-select-all"
            @click="toggleSelectAll"
          >
            {{ allSelected ? '取消全选' : '全选' }}
          </button>
          <button
            type="button"
            class="btn-select-page"
            @click="selectCurrentPage"
          >
            选中本页
          </button>
          <button
            type="button"
            class="btn-export"
            @click="handleBatchExport"
            :disabled="exporting || selectedIds.length === 0"
          >
            {{ exporting ? '导出中...' : `批量导出 (${selectedIds.length})` }}
          </button>
          <button
            type="button"
            class="btn-cancel-select"
            @click="exitSelectMode"
          >
            取消
          </button>
        </template>
      </div>
    </div>

    <div class="content-area">
      <!-- <section
        v-if="!error && overview"
        class="overview-panel"
        aria-label="总体报告"
      >
        <div class="overview-header">
          <h3 class="overview-title">总体报告</h3>
          <span class="overview-scope">全部历史 · 仅统计检查完成</span>
        </div>

        <div v-if="overview.total_completed === 0" class="overview-empty">
          暂无已完成的论文检查记录。上传 PDF 并完成审查后，将在此展示汇总数据。
        </div>

        <template v-else>
          <div class="overview-hero">
            <div class="hero-metric">
              <span class="hero-value">{{ overview.total_completed }}</span>
              <span class="hero-label">本已检查</span>
            </div>
            <div class="score-grid">
              <div class="score-card score-qualified">
                <span class="score-num">{{ overview.score_counts.qualified }}</span>
                <span class="score-name">合格</span>
                <span class="score-pct">{{ pct(overview.score_counts.qualified) }}</span>
              </div>
              <div class="score-card score-revision">
                <span class="score-num">{{ overview.score_counts.need_revision }}</span>
                <span class="score-name">需修改</span>
                <span class="score-pct">{{ pct(overview.score_counts.need_revision) }}</span>
              </div>
              <div class="score-card score-unqualified">
                <span class="score-num">{{ overview.score_counts.unqualified }}</span>
                <span class="score-name">不合格</span>
                <span class="score-pct">{{ pct(overview.score_counts.unqualified) }}</span>
              </div>
            </div>
          </div>

          <div v-if="overview.score_known < overview.total_completed" class="overview-hint">
            其中 {{ overview.total_completed - overview.score_known }} 本暂无总体结论数据，未计入上表三档比例。
          </div>

          <div class="problem-section">
            <h4 class="problem-title">出错最多的检查项</h4>
            <p class="problem-desc">按「至少有一篇在该域未通过」统计，占已完成论文比例</p>
            <ul v-if="overview.top_problem_domains.length" class="problem-bars">
              <li
                v-for="(item, idx) in overview.top_problem_domains"
                :key="item.domain"
                class="problem-row"
              >
                <span class="problem-rank">{{ idx + 1 }}</span>
                <div class="problem-body">
                  <div class="problem-label-row">
                    <span class="problem-domain">{{ item.domain }}</span>
                    <span class="problem-count">{{ item.paper_count }} 本 · {{ item.percentage }}%</span>
                  </div>
                  <div class="problem-track">
                    <div
                      class="problem-fill"
                      :style="{ width: barWidth(item.percentage) }"
                    />
                  </div>
                </div>
              </li>
            </ul>
            <p v-else class="problem-none">已完成论文中未发现汇总层面的检查域问题记录。</p>
          </div>
        </template>

        <p
          v-if="overview.other_status.processing > 0 || overview.other_status.failed > 0"
          class="overview-footnote"
        >
          另有
          <template v-if="overview.other_status.processing > 0">
            {{ overview.other_status.processing }} 本处理中
          </template>
          <template v-if="overview.other_status.processing > 0 && overview.other_status.failed > 0">、</template>
          <template v-if="overview.other_status.failed > 0">
            {{ overview.other_status.failed }} 本检查失败
          </template>
          ，未计入本报告。
        </p>
      </section> -->

      <div v-if="loading && list.length === 0" class="loading-container">
        <p>加载中...</p>
      </div>
      <div v-else-if="error" class="error-container">
        <p>加载失败，请稍后重试</p>
        <button type="button" class="retry-btn" @click="loadList">重试</button>
      </div>
      <div v-else-if="paginatedList.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="empty-title" v-if="list.length === 0">暂无论文检查任务</p>
        <p class="empty-desc" v-if="list.length === 0">点击「上传论文」提交 PDF 开始检查</p>
        <p class="empty-title" v-else>当前页无数据</p>
      </div>
      <div v-else class="task-grid">
        <div
          v-for="task in paginatedList"
          :key="task.id"
          class="task-card"
          :class="{ 'is-selected': selectedIds.includes(task.id), 'select-mode': selectMode }"
          role="button"
          tabindex="0"
          @click="selectMode ? toggleSelect(task.id) : goToDetail(task)"
          @keydown.enter="selectMode ? toggleSelect(task.id) : goToDetail(task)"
        >
          <div class="card-lower">
            <div class="card-header-row">
              <label
                v-if="selectMode"
                class="card-checkbox"
                @click.stop
                @keydown.stop
              >
                <input
                  type="checkbox"
                  :checked="selectedIds.includes(task.id)"
                  :disabled="task.status !== 'completed'"
                  @change="toggleSelect(task.id)"
                />
              </label>
              <h3 class="card-title">{{ task.filename }}</h3>
            </div>
            <div class="card-course">
              {{ task.total_pages ? `${task.total_pages} 页` : '页数未知' }} · {{ formatDate(task.create_time) }}
            </div>
            <div class="status-row">
              <div class="status-strip" :class="statusStripClass(task.status)">
                {{ statusLabel(task.status) }}
              </div>
              <span v-if="task.status === 'uploaded' || task.status === 'processing'" class="status-eta">
                处理中，请稍后刷新
              </span>
            </div>
            <button
              v-if="!selectMode"
              type="button"
              class="report-btn"
              @click.stop="goToDetail(task)"
            >
              {{ task.status === 'completed' ? '查看报告' : '查看详情' }}
            </button>
            <button
              v-if="!selectMode"
              type="button"
              class="delete-btn"
              @click.stop="handleDelete(task)"
            >
              删除
            </button>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="totalPages > 1" class="pagination">
        <button type="button" class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">
          ‹ 上一页
        </button>
        <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页（共 {{ list.length }} 条）</span>
        <button type="button" class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">
          下一页 ›
        </button>
      </div>
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
              name="exportScope"
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

    <!-- 导出进度弹窗 -->
    <div v-if="showExportModal" class="export-overlay">
      <div class="export-modal">
        <h3>{{ exportDone ? '导出完成' : exportGenerating ? '正在生成文件...' : '正在导出...' }}</h3>
        <div class="export-progress-bar">
          <div
            class="export-progress-fill"
            :style="{ width: exportPercent + '%' }"
            :class="{ 'is-generating': exportGenerating }"
          ></div>
        </div>
        <p class="export-info">
          <template v-if="exportDone">已完成 {{ generatingCurrent }} / {{ generatingTotal }}</template>
          <template v-else-if="exportGenerating">正在生成：{{ generatingCurrent }} / {{ generatingTotal }}</template>
          <template v-else>准备中...</template>
        </p>
        <div class="export-file-list">
          <div
            v-for="(item, idx) in exportLog"
            :key="idx"
            class="export-file-item"
            :class="item.status"
          >
            <span class="export-file-icon">
              {{ item.status === 'done' ? '✓' : item.status === 'skipped' ? '−' : '✗' }}
            </span>
            <span class="export-file-name">{{ item.filename }}</span>
            <span class="export-file-status">{{ item.message || (item.status === 'done' ? '已导出' : '已跳过') }}</span>
          </div>
        </div>
        <button
          v-if="exportDone"
          type="button"
          class="export-close-btn"
          @click="closeExportModal"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import {
  listEssays,
  getEssayOverview,
  deleteEssay,
  exportReports,
  ESSAY_EXPORT_SCOPE_OPTIONS,
  ESSAY_AUTO_REFRESH_INTERVAL_MS,
} from '../api/essayCheck'
import type { EssayTaskItem, EssayOverview, EssayExportScope, ExportProgress } from '../api/essayCheck'

const router = useRouter()
const loading = ref(true)
const error = ref<string | null>(null)
const list = ref<EssayTaskItem[]>([])
const overview = ref<EssayOverview | null>(null)

// 分页
const PAGE_SIZE = 15
const currentPage = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(list.value.length / PAGE_SIZE)))
const paginatedList = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return list.value.slice(start, start + PAGE_SIZE)
})

function goToPage(page: number) {
  currentPage.value = Math.max(1, Math.min(page, totalPages.value))
}

// 批量选择模式
const selectMode = ref(false)
const selectedIds = ref<string[]>([])
const exporting = ref(false)

function enterSelectMode() {
  selectMode.value = true
  selectedIds.value = []
}

function exitSelectMode() {
  selectMode.value = false
  selectedIds.value = []
}

const allSelected = computed(() => {
  const completedIds = list.value.filter((t) => t.status === 'completed').map((t) => t.id)
  return completedIds.length > 0 && completedIds.every((id) => selectedIds.value.includes(id))
})

function toggleSelectAll() {
  if (allSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = list.value
      .filter((t) => t.status === 'completed')
      .map((t) => t.id)
  }
}

function selectCurrentPage() {
  selectedIds.value = paginatedList.value
    .filter((t: EssayTaskItem) => t.status === 'completed')
    .map((t: EssayTaskItem) => t.id)
}

function toggleSelect(id: string) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

// 导出选项
const showExportOptions = ref(false)

// 导出进度弹窗
const showExportModal = ref(false)
const exportDone = ref(false)
const exportGenerating = ref(false)
const exportGeneratingMsg = ref('')
const generatingCurrent = ref(0)
const generatingTotal = ref(0)
const exportLog = ref<{ filename: string; status: string; message?: string }[]>([])
const exportScopeOptions = ESSAY_EXPORT_SCOPE_OPTIONS
const exportScope = ref<EssayExportScope>('summary_only')

const exportPercent = computed(() => {
  if (generatingTotal.value === 0) return 0
  return Math.round((generatingCurrent.value / generatingTotal.value) * 100)
})

function cancelExportOptions() {
  showExportOptions.value = false
  exportScope.value = 'summary_only'
}

function closeExportModal() {
  showExportModal.value = false
  exportDone.value = false
  exportGenerating.value = false
  generatingCurrent.value = 0
  generatingTotal.value = 0
  exportLog.value = []
  exportScope.value = 'summary_only'
}

function handleBatchExport() {
  if (selectedIds.value.length === 0) return
  showExportOptions.value = true
}

async function confirmExport() {
  showExportOptions.value = false
  exporting.value = true
  showExportModal.value = true
  exportDone.value = false
  exportGenerating.value = false
  exportLog.value = []
  generatingCurrent.value = 0
  generatingTotal.value = selectedIds.value.filter((id) => {
    const task = list.value.find((t) => t.id === id)
    return task && task.status === 'completed'
  }).length
  try {
    await exportReports(selectedIds.value, exportScope.value, (progress) => {
      if ('generating' in progress) {
        exportGenerating.value = true
        exportGeneratingMsg.value = progress.message
      } else if (progress.phase === 'generating') {
        generatingCurrent.value = progress.current
        exportLog.value.push({
          filename: progress.filename,
          status: 'done',
        })
      }
    })
    generatingCurrent.value = generatingTotal.value
    exportDone.value = true
    exportGenerating.value = false
    selectedIds.value = []
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '导出失败'
    alert(msg)
    showExportModal.value = false
    exportDone.value = false
  } finally {
    exporting.value = false
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    uploaded: '已上传',
    processing: '处理中',
    summarizing: '生成报告中',
    completed: '检查完成',
    failed: '检查失败',
  }
  return map[status] ?? status
}

function statusStripClass(status: string): string {
  if (status === 'completed') return 'status-completed'
  if (status === 'failed') return 'status-failed'
  if (status === 'uploaded' || status === 'processing' || status === 'summarizing') return 'status-analyzing'
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

function pct(count: number): string {
  const total = overview.value?.total_completed ?? 0
  if (total <= 0) return '—'
  return `${Math.round((count / total) * 100)}%`
}

function barWidth(percentage: number): string {
  const max = overview.value?.top_problem_domains[0]?.percentage ?? 100
  const scale = max > 0 ? (percentage / max) * 100 : 0
  return `${Math.max(4, Math.min(100, scale))}%`
}

async function loadOverview() {
  try {
    const resp = await getEssayOverview()
    overview.value = resp.data
  } catch (e) {
    console.error('[EssayCheck] 加载总体报告失败', e)
    overview.value = null
  }
}

async function loadList() {
  loading.value = true
  error.value = null
  const [listResult, overviewResult] = await Promise.allSettled([
    listEssays(),
    getEssayOverview(),
  ])
  if (listResult.status === 'fulfilled') {
    list.value = listResult.value.data
    if (currentPage.value > totalPages.value) currentPage.value = 1
  } else {
    console.error('[EssayCheck] 加载列表失败', listResult.reason)
    error.value = 'failed'
    list.value = []
  }
  if (overviewResult.status === 'fulfilled') {
    overview.value = overviewResult.value.data
  } else {
    console.error('[EssayCheck] 加载总体报告失败', overviewResult.reason)
    overview.value = null
  }
  loading.value = false
}

function goToDetail(task: EssayTaskItem) {
  router.push(`/essay-check/${encodeURIComponent(task.id)}`)
}

async function handleDelete(task: EssayTaskItem) {
  if (!confirm(`确定要删除「${task.filename}」吗？`)) return
  try {
    await deleteEssay(task.id)
    list.value = list.value.filter((t: EssayTaskItem) => t.id !== task.id)
    await loadOverview()
  } catch (e) {
    console.error('[EssayCheck] 删除失败', e)
    alert('删除失败，请稍后重试')
  }
}

const POLL_INTERVAL_MS = ESSAY_AUTO_REFRESH_INTERVAL_MS
let pollTimer: ReturnType<typeof setInterval> | null = null

function hasUnfinishedTasks(): boolean {
  return list.value.some((t) => t.status !== 'completed' && t.status !== 'failed')
}

async function pollListIfNeeded() {
  if (!hasUnfinishedTasks()) return
  if (loading.value) return
  await loadList()
}

onMounted(() => {
  loadList()
  pollTimer = setInterval(() => {
    void pollListIfNeeded()
  }, POLL_INTERVAL_MS)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.essay-check-list-view {
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

.toolbar-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.btn-primary {
  padding: 8px 16px;
  font-size: 14px;
  height: 40px;
  width: 100px;
  color: #333;
  background-color: rgba(255, 255, 255, 0.3);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-primary:hover { background-color: rgba(255, 255, 255, 0.45); }

.btn-select-mode {
  padding: 8px 16px;
  font-size: 14px;
  height: 40px;
  color: #333;
  background-color: rgba(255, 255, 255, 0.3);
  border: 1px solid #ddd;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s;
}
.btn-select-mode:hover { background-color: rgba(255, 255, 255, 0.45); }

.btn-select-all {
  padding: 8px 14px;
  font-size: 14px;
  height: 40px;
  color: #409eff;
  background: rgba(64, 158, 255, 0.1);
  border: 1px solid #409eff;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-select-all:hover { background: rgba(64, 158, 255, 0.2); }

.btn-select-page {
  padding: 8px 14px;
  font-size: 14px;
  height: 40px;
  color: #409eff;
  background: rgba(64, 158, 255, 0.1);
  border: 1px solid #409eff;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-select-page:hover { background: rgba(64, 158, 255, 0.2); }

.btn-export {
  padding: 8px 16px;
  font-size: 14px;
  height: 40px;
  min-width: 140px;
  color: #fff;
  background-color: #409eff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 500;
  transition: background-color 0.2s;
}
.btn-export:hover:not(:disabled) { background-color: #66b1ff; }
.btn-export:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-cancel-select {
  padding: 8px 14px;
  font-size: 14px;
  height: 40px;
  color: #666;
  background: #f0f0f0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-cancel-select:hover { background: #e0e0e0; }

.overview-panel {
  margin-bottom: 24px;
  padding: 20px 24px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 4px 20px rgba(64, 100, 180, 0.08);
}

.overview-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.overview-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #333;
}

.overview-scope {
  font-size: 12px;
  color: #888;
}

.overview-empty {
  font-size: 14px;
  color: #666;
  line-height: 1.6;
}

.overview-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 20px;
}

.hero-metric {
  min-width: 120px;
  padding: 12px 20px;
  border-radius: 12px;
  background: linear-gradient(135deg, #5b8def 0%, #7ba3f7 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.hero-value {
  font-size: 36px;
  font-weight: 700;
  line-height: 1.1;
}

.hero-label {
  font-size: 14px;
  opacity: 0.92;
  margin-top: 4px;
}

.score-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, minmax(100px, 1fr));
  gap: 12px;
  min-width: 280px;
}

.score-card {
  padding: 12px 14px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.score-qualified { background: rgba(103, 194, 58, 0.12); border: 1px solid rgba(103, 194, 58, 0.35); }
.score-revision { background: rgba(230, 162, 60, 0.12); border: 1px solid rgba(230, 162, 60, 0.35); }
.score-unqualified { background: rgba(245, 108, 108, 0.12); border: 1px solid rgba(245, 108, 108, 0.35); }

.score-num { font-size: 26px; font-weight: 700; color: #333; }
.score-name { font-size: 13px; color: #555; }
.score-pct { font-size: 12px; color: #888; }

.overview-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: #888;
}

.problem-section {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.problem-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.problem-desc {
  margin: 0 0 14px;
  font-size: 12px;
  color: #888;
}

.problem-bars {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.problem-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.problem-rank {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(64, 158, 255, 0.15);
  color: #409eff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.problem-body { flex: 1; min-width: 0; }

.problem-label-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}

.problem-domain {
  color: #333;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-count {
  flex-shrink: 0;
  color: #666;
  font-size: 12px;
}

.problem-track {
  height: 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.problem-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #409eff, #79bbff);
  transition: width 0.3s ease;
}

.problem-none {
  margin: 0;
  font-size: 13px;
  color: #888;
}

.overview-footnote {
  margin: 16px 0 0;
  font-size: 12px;
  color: #999;
}

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

.loading-container, .error-container { text-align: center; padding: 48px 24px; color: #666; }
.retry-btn { margin-top: 12px; padding: 8px 16px; background: #C5D9FF; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }

.empty-state { text-align: center; padding: 48px 24px; }
.empty-icon { color: #bbb; margin-bottom: 20px; }
.empty-title { font-size: 18px; font-weight: 600; color: #333; margin: 0 0 12px 0; }
.empty-desc { font-size: 14px; color: #666; margin: 0 0 24px 0; }

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, 385px);
  gap: 20px;
  justify-content: center;
  align-content: start;
}

.task-card {
  width: 385px;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s, background-color 0.15s;
  box-sizing: border-box;
  border: 2px solid transparent;
}
.task-card:hover {
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
}

/* 选择模式下选中态 */
.task-card.is-selected {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.task-card.select-mode:not(.is-selected) {
  border-color: #eee;
}

.card-lower {
  flex: 1;
  min-height: 0;
  background: transparent;
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  box-sizing: border-box;
}

.card-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.card-checkbox {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  cursor: pointer;
}
.card-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #409eff;
}
.card-checkbox input[type="checkbox"]:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: #333;
  margin: 0;
  line-height: 1.35;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-course {
  font-size: 13px;
  font-weight: 400;
  color: #666;
  line-height: 1.4;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  width: 100%;
  min-height: 26px;
}

.status-strip {
  width: 112px;
  height: 26px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
}

.status-eta {
  font-size: 12px;
  font-weight: 400;
  color: #7a7f8c;
  line-height: 1.3;
  flex: 1 1 auto;
  min-width: 0;
}

.status-strip.status-completed { background: #e8facd; color: #61714a; }
.status-strip.status-analyzing { background: #fff8e6; color: #8a6d1d; }
.status-strip.status-pending { background: #e8eef9; color: #4a5f8a; }
.status-strip.status-failed { background: #fdecea; color: #b3261e; }

.report-btn {
  margin-top: auto;
  width: 100%;
  padding: 10px 16px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 14px;
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

.delete-btn {
  margin-top: 4px;
  width: 100%;
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: #c0392b;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
  box-sizing: border-box;
}
.delete-btn:hover {
  background: #fdf0ef;
  border-color: #c0392b;
}

/* 分页 */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px 0 0;
}

.page-btn {
  padding: 6px 16px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #333;
  transition: background-color 0.2s;
}
.page-btn:hover:not(:disabled) { background: #f0f0f0; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.page-info {
  font-size: 13px;
  color: #666;
}

@media (max-width: 768px) {
  .toolbar { padding: 16px; }
  .content-area { padding: 16px; }
  .task-grid { grid-template-columns: minmax(0, 385px); justify-content: center; }
  .task-card { width: 100%; max-width: 385px; }
}

/* 导出进度弹窗 */
.export-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
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

/* 导出选项弹窗 */
.export-options-modal {
  width: 480px !important;
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
  transition: background-color 0.2s;
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
  transition: background-color 0.2s;
}
.export-confirm-btn:hover { background: #66b1ff; }

.export-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
  cursor: pointer;
  user-select: none;
}
.export-option input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #409eff;
  cursor: pointer;
}

.export-progress-bar {
  height: 8px;
  background: #f0f2f5;
  border-radius: 4px;
  overflow: hidden;
}

.export-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #409eff, #66b1ff);
  border-radius: 4px;
  transition: width 0.3s ease;
}
.export-progress-fill.is-generating {
  background: linear-gradient(90deg, #e6a23c, #f0c060, #e6a23c);
  background-size: 200% 100%;
  animation: generating-shimmer 1.2s linear infinite;
}
@keyframes generating-shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}

.export-info {
  font-size: 14px;
  color: #606266;
  margin: 0;
  text-align: center;
}

.export-file-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
}

.export-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #fafafa;
  font-size: 13px;
}

.export-file-item.done { background: #f0f9eb; }
.export-file-item.skipped { background: #f5f5f5; }
.export-file-item.error { background: #fef0f0; }

.export-file-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.export-file-item.done .export-file-icon { background: #e8facd; color: #61714a; }
.export-file-item.skipped .export-file-icon { background: #e8eef9; color: #4a5f8a; }
.export-file-item.error .export-file-icon { background: #fdecea; color: #b3261e; }

.export-file-name {
  flex: 1;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.export-file-status {
  color: #909399;
  font-size: 12px;
  flex-shrink: 0;
}

.export-close-btn {
  padding: 8px 24px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  align-self: center;
  transition: background-color 0.2s;
}
.export-close-btn:hover { background: #66b1ff; }
</style>
