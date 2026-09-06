<template>
  <div class="doc-analysis-view core-app-page core-app-page--flow" :class="{ 'is-report': phase === 'report' }">
    <div class="toolbar">
      <div class="toolbar-left">
        <router-link to="/resource-analysis" class="back-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回列表</span>
        </router-link>
        <h2 class="page-title">文档教学分析</h2>
      </div>
    </div>

    <div class="content-area">
      <!-- 上传阶段 -->
      <div v-if="phase === 'upload'" class="form-area">
        <div class="form-panel">
          <div class="form-row">
            <label>选择教学文档 <span class="required">*</span></label>
            <div class="file-row">
              <input
                ref="fileInputRef"
                type="file"
                accept=".docx,.pptx"
                class="file-input-hidden"
                @change="onFileChange"
              />
              <button type="button" class="file-trigger-btn" @click="triggerFileSelect">
                {{ selectedFile ? '重新选择' : '选择文件' }}
              </button>
              <span v-if="selectedFile" class="file-name">{{ selectedFile.name }}</span>
            </div>
            <p class="form-hint">支持 .docx（Word）和 .pptx（PPT）格式，最大 100 MB</p>
          </div>

          <div class="form-row">
            <label>课程名称 <span class="optional">（选填）</span></label>
            <input
              v-model="courseName"
              type="text"
              class="text-input"
              placeholder="填写课程名称有助于更精准的分析"
            />
          </div>

          <p v-if="formError" class="form-error">{{ formError }}</p>

          <div class="form-actions">
            <router-link to="/resource-analysis" class="action-btn secondary">返回</router-link>
            <button
              type="button"
              class="action-btn primary"
              :disabled="!selectedFile"
              @click="handleSubmit"
            >
              开始分析
            </button>
          </div>
        </div>
      </div>

      <!-- 分析中阶段 -->
      <div v-else-if="phase === 'analyzing'" class="analyzing-area">
        <div class="analyzing-card">
          <div class="analyzing-spinner" />
          <h3>正在分析文档</h3>
          <p class="analyzing-msg">{{ progressMessage }}</p>
          <div class="progress-bar-container">
            <div class="progress-bar-fill" :style="{ width: `${progressPercent}%` }" />
          </div>
          <p class="progress-text">{{ progressPercent }}%</p>
        </div>
      </div>

      <!-- 错误 -->
      <div v-else-if="phase === 'error'" class="error-area">
        <div class="error-card">
          <div class="error-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#e53e3e" stroke-width="2"/>
              <path d="M15 9L9 15M9 9l6 6" stroke="#e53e3e" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3>分析失败</h3>
          <p>{{ errorMessage }}</p>
          <button type="button" class="action-btn primary" @click="resetToUpload">重新上传</button>
        </div>
      </div>

      <!-- 报告阶段 -->
      <div v-else-if="phase === 'report' && result" class="report-area">
        <!-- 顶部维度 Tab 切换（总览 + 各维度，维度带分数角标） -->
        <div class="tab-bar">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            @click="switchTab(tab.key)"
          >
            {{ tab.label }}
            <span v-if="tab.score !== null" class="tab-score" :class="scoreClass(tab.score)">
              {{ tab.score }}
            </span>
          </button>
        </div>

        <!-- ========== 总览 Tab ========== -->
        <div v-show="activeTab === 'overview'" class="tab-panel">
          <!-- 综合得分雷达 + 各维度进度条 -->
          <div class="panel-grid">
            <!-- 综合得分 hero + 雷达图 -->
            <div class="panel-card radar-card">
              <div class="overall-hero">
                <div class="overall-hero-num" :class="scoreClass(result.overall_score)">{{ result.overall_score }}</div>
                <div class="overall-hero-label">综合得分</div>
              </div>
              <div ref="radarChartRef" class="chart-box radar-box" />
            </div>

            <!-- 各维度得分（只放简短描述，长文移到各维度 Tab） -->
            <div class="panel-card">
              <h3 class="panel-title">各维度得分</h3>
              <div class="score-list">
                <div
                  v-for="dim in result.dimension_scores"
                  :key="dim.dimension"
                  class="score-row score-row-clickable"
                  @click="switchTab(dim.dimension)"
                >
                  <div class="score-info">
                    <span class="score-name">{{ dim.dimension }}</span>
                    <span class="score-val" :class="scoreClass(dim.score)">{{ dim.score > 0 ? dim.score + '分' : '—' }}</span>
                  </div>
                  <div class="score-bar-bg">
                    <div class="score-bar-fill" :style="{ width: `${dim.score}%`, background: dimColor(dim.dimension) }" />
                  </div>
                  <p v-if="dimDesc(dim.dimension)" class="score-desc">{{ dimDesc(dim.dimension) }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 分析概要 / AI 总评摘要 -->
          <div class="panel-card">
            <div class="overview-head">
              <h3 class="panel-title overview-title">AI 总评摘要</h3>
              <div class="overview-meta">
                <span class="meta-pill">{{ result.file_name }}</span>
                <span class="meta-pill">{{ result.file_type.toUpperCase() }}</span>
                <span class="meta-pill">{{ result.total_segments }} 个段落</span>
              </div>
            </div>
            <p class="capability-body">{{ result.capability_summary }}</p>
          </div>

          <!-- 改进建议 -->
          <div v-if="result.improvement_suggestions.length" class="panel-card">
            <h3 class="panel-title">改进建议</h3>
            <ol class="improvement-list">
              <li v-for="(suggestion, idx) in result.improvement_suggestions" :key="idx">
                {{ suggestion }}
              </li>
            </ol>
          </div>

          <!-- 分段详情（折叠） -->
          <div v-if="result.segment_details.length" class="panel-card">
            <h3 class="panel-title">分段详情</h3>
            <div
              v-for="seg in result.segment_details"
              :key="seg.segment_index"
              class="segment-block"
            >
              <div class="segment-toggle" @click="toggleSegment(seg.segment_index)">
                <span class="toggle-icon" :class="{ open: expandedSegments.has(seg.segment_index) }">▶</span>
                <span class="toggle-label">段落 {{ seg.segment_index }}{{ seg.segment_title ? '：' + seg.segment_title : '' }}</span>
              </div>
              <div v-if="expandedSegments.has(seg.segment_index)" class="segment-body">
                <div
                  v-for="dim in seg.dimensions"
                  :key="dim.dimension"
                  class="seg-dim analysis-card"
                >
                  <div class="analysis-header">
                    <span class="analysis-name">{{ dim.dimension }}</span>
                    <span class="analysis-badge" :class="scoreClass(dim.score)">{{ dim.score }}分</span>
                  </div>
                  <div v-if="dim.strengths.length" class="seg-dim-section">
                    <span class="seg-dim-label good">优点</span>
                    <ul>
                      <li v-for="(s, i) in dim.strengths" :key="i">{{ s }}</li>
                    </ul>
                  </div>
                  <div v-if="dim.weaknesses.length" class="seg-dim-section">
                    <span class="seg-dim-label warn">不足</span>
                    <ul>
                      <li v-for="(w, i) in dim.weaknesses" :key="i">{{ w }}</li>
                    </ul>
                  </div>
                  <div v-if="dim.suggestions.length" class="seg-dim-section">
                    <span class="seg-dim-label info">建议</span>
                    <ul>
                      <li v-for="(sg, i) in dim.suggestions" :key="i">{{ sg }}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ========== 单维度 Tab ========== -->
        <div v-if="currentDimension" v-show="activeTab !== 'overview'" class="tab-panel">
          <div class="dimension-header">
            <h2 class="dimension-title">{{ currentDimension.dimension }}</h2>
            <span class="analysis-badge dimension-head-badge" :class="scoreClass(currentDimension.score)">
              {{ currentDimension.score }}分
            </span>
          </div>

          <!-- 维度总评 -->
          <div v-if="currentDimension.comments" class="panel-card">
            <h3 class="panel-title">维度评价</h3>
            <p class="capability-body">{{ currentDimension.comments }}</p>
          </div>

          <!-- 优点 / 不足 / 建议 -->
          <div class="panel-card">
            <h3 class="panel-title">详细分析</h3>
            <div class="seg-dim analysis-card">
              <div v-if="currentDimension.strengths.length" class="seg-dim-section">
                <span class="seg-dim-label good">优点</span>
                <ul>
                  <li v-for="(s, i) in currentDimension.strengths" :key="i">{{ s }}</li>
                </ul>
              </div>
              <div v-if="currentDimension.weaknesses.length" class="seg-dim-section">
                <span class="seg-dim-label warn">不足</span>
                <ul>
                  <li v-for="(w, i) in currentDimension.weaknesses" :key="i">{{ w }}</li>
                </ul>
              </div>
              <div v-if="currentDimension.suggestions.length" class="seg-dim-section">
                <span class="seg-dim-label info">建议</span>
                <ul>
                  <li v-for="(sg, i) in currentDimension.suggestions" :key="i">{{ sg }}</li>
                </ul>
              </div>
              <p
                v-if="!currentDimension.strengths.length && !currentDimension.weaknesses.length && !currentDimension.suggestions.length"
                class="empty-text"
              >
                该维度暂无详细分析
              </p>
            </div>
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="report-actions">
          <button type="button" class="action-btn secondary" @click="resetToUpload">分析新文档</button>
          <router-link to="/document-analysis/compare" class="action-btn secondary">历史对比</router-link>
          <button
            type="button"
            class="action-btn primary"
            :disabled="exporting"
            @click="handleExportReport"
          >
            <template v-if="exporting">
              <span class="export-spinner" />
              导出中...
            </template>
            <template v-else>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 6px;">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              导出报告
            </template>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { analyzeDocument, saveDocumentResult, getDocumentDetail } from '../api/document'
import type { DocumentAnalysisResult } from '../api/document'
import { exportDocumentReport } from '../lib/documentReportExport'

type Phase = 'upload' | 'analyzing' | 'report' | 'error'
const phase = ref<Phase>('upload')

const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const courseName = ref('')
const formError = ref('')

const progressMessage = ref('准备中...')
const progressPercent = ref(0)
const errorMessage = ref('')

const result = ref<DocumentAnalysisResult | null>(null)
const radarChartRef = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null

const expandedSegments = ref<Set<number>>(new Set())
const exporting = ref(false)

/** 当前激活的 Tab：'overview' 为总览，其余为某维度名称 */
const activeTab = ref<string>('overview')

/** 顶部 Tab 列表：总览 + 各维度（带分数角标），结构对齐视频报告 */
const tabs = computed(() => {
  const dims = result.value?.dimension_scores ?? []
  return [
    { key: 'overview', label: '总览', score: null as number | null },
    ...dims.map((d) => ({ key: d.dimension, label: d.dimension, score: d.score })),
  ]
})

/**
 * 各维度聚合详情：把分散在 segment_details 各段落里的 优点/不足/建议 按维度收拢，
 * 再合并维度自身的 comments / suggestions，供单维度 Tab 完整展示（不丢任何信息）。
 */
const dimensionDetail = computed(() => {
  const map: Record<string, {
    dimension: string
    score: number
    comments: string
    strengths: string[]
    weaknesses: string[]
    suggestions: string[]
  }> = {}
  for (const d of result.value?.dimension_scores ?? []) {
    map[d.dimension] = {
      dimension: d.dimension,
      score: d.score,
      comments: d.comments ?? '',
      strengths: [],
      weaknesses: [],
      suggestions: [...(d.suggestions ?? [])],
    }
  }
  for (const seg of result.value?.segment_details ?? []) {
    for (const ev of seg.dimensions ?? []) {
      const target = map[ev.dimension]
      if (!target) continue
      for (const s of ev.strengths ?? []) if (!target.strengths.includes(s)) target.strengths.push(s)
      for (const w of ev.weaknesses ?? []) if (!target.weaknesses.includes(w)) target.weaknesses.push(w)
      for (const g of ev.suggestions ?? []) if (!target.suggestions.includes(g)) target.suggestions.push(g)
    }
  }
  return map
})

/** 当前维度 Tab 对应的聚合详情 */
const currentDimension = computed(() =>
  activeTab.value === 'overview' ? null : (dimensionDetail.value[activeTab.value] ?? null),
)

/** 总览进度条下的一句简短描述：取该维度 comments 的首句，避免堆长文 */
function dimDesc(name: string): string {
  const c = dimensionDetail.value[name]?.comments ?? ''
  if (!c) return ''
  const first = c.split(/[。；;\n]/)[0]?.trim() ?? ''
  return first ? (first.length < c.trim().length ? first + '。' : first) : c
}

/** 切换 Tab：回到总览时重新初始化雷达图（v-show 隐藏时 ECharts 尺寸为 0，需重建） */
function switchTab(key: string) {
  activeTab.value = key
  if (key === 'overview') {
    nextTick(() => {
      radarChart?.resize()
      initRadarChart()
      radarChart?.resize()
    })
  }
}

function triggerFileSelect() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (ext !== 'docx' && ext !== 'pptx') {
    formError.value = '仅支持 .docx 和 .pptx 格式'
    selectedFile.value = null
    return
  }
  if (file.size > 100 * 1024 * 1024) {
    formError.value = '文件大小不能超过 100 MB'
    selectedFile.value = null
    return
  }
  formError.value = ''
  selectedFile.value = file
}

function handleSubmit() {
  if (!selectedFile.value) return
  formError.value = ''
  phase.value = 'analyzing'
  progressMessage.value = '正在上传文档...'
  progressPercent.value = 0

  analyzeDocument(selectedFile.value, courseName.value, {
    onProgress(msg, progress) {
      progressMessage.value = msg
      progressPercent.value = Math.min(99, progress)
    },
    async onDone(data) {
      result.value = data
      activeTab.value = 'overview'
      saveDocumentResult(data).catch(() => {})
      phase.value = 'report'
      await nextTick()
      initRadarChart()
    },
    onError(err) {
      errorMessage.value = err.message
      phase.value = 'error'
    },
  })
}

function resetToUpload() {
  phase.value = 'upload'
  selectedFile.value = null
  courseName.value = ''
  formError.value = ''
  result.value = null
  activeTab.value = 'overview'
  expandedSegments.value = new Set()
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function toggleSegment(idx: number) {
  const s = new Set(expandedSegments.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedSegments.value = s
}

async function handleExportReport() {
  if (!result.value || exporting.value) return
  exporting.value = true
  try {
    await exportDocumentReport(result.value)
  } catch (err) {
    console.error('导出报告失败:', err)
    alert('导出报告失败，请重试')
  } finally {
    exporting.value = false
  }
}

function scoreClass(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
}

/** 维度配色板：与视频报告各维度进度条同款的多彩色板，按维度顺序循环取色 */
const DIM_COLORS = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#9a60b4']
function dimColor(name: string): string {
  const list = result.value?.dimension_scores ?? []
  const idx = list.findIndex((d) => d.dimension === name)
  return DIM_COLORS[(idx >= 0 ? idx : 0) % DIM_COLORS.length] ?? '#5470c6'
}

function initRadarChart() {
  if (!radarChartRef.value || !result.value) return
  radarChart = echarts.init(radarChartRef.value)
  const rd = result.value.radar_data ?? []
  radarChart.setOption({
    tooltip: {},
    radar: {
      indicator: rd.map((d) => ({ name: d.dimension, max: d.fullScore || 100 })),
      radius: '65%',
      axisName: { color: '#666' },
    },
    series: [{
      type: 'radar',
      data: [{
        value: rd.map((d) => d.score),
        name: '得分',
        areaStyle: { color: 'rgba(19, 88, 228, 0.2)' },
        lineStyle: { color: '#1358e4', width: 2 },
        itemStyle: { color: '#1358e4' },
      }],
    }],
  }, true)
}

function handleResize() {
  radarChart?.resize()
}

const route = useRoute()

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  const recordId = route.query.recordId as string | undefined
  if (recordId) {
    try {
      const data = await getDocumentDetail(recordId)
      result.value = data
      activeTab.value = 'overview'
      phase.value = 'report'
      await nextTick()
      initRadarChart()
    } catch {
      // record not found, stay on upload phase
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  radarChart?.dispose()
})
</script>

<style scoped>
.doc-analysis-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}
/* 报告态加宽，让六维度两栏更舒展（比视频报告稍宽） */
.doc-analysis-view.is-report {
  max-width: 1400px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #555;
  text-decoration: none;
  font-size: 14px;
  padding: 6px 10px;
  border-radius: 8px;
  transition: background 0.15s;
}
.back-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1a1a1a;
}

/* Upload form */
.form-area {
  display: flex;
  justify-content: center;
  padding-top: 40px;
}
.form-panel {
  width: 100%;
  max-width: 520px;
  background: #fff;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.form-row {
  margin-bottom: 20px;
}
.form-row label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #333;
}
.required {
  color: #e53e3e;
}
.optional {
  color: #999;
  font-weight: 400;
}
.file-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.file-input-hidden {
  display: none;
}
.file-trigger-btn {
  padding: 8px 16px;
  border: 1px dashed #ccc;
  border-radius: 8px;
  background: #fafafa;
  cursor: pointer;
  font-size: 14px;
  color: #555;
  transition: border-color 0.15s, background 0.15s;
}
.file-trigger-btn:hover {
  border-color: #1358e4;
  background: #f0f4ff;
  color: #1358e4;
}
.file-name {
  font-size: 13px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}
.form-hint {
  font-size: 12px;
  color: #999;
  margin-top: 6px;
}
.text-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.text-input:focus {
  border-color: #1358e4;
}
.form-error {
  color: #e53e3e;
  font-size: 13px;
  margin-bottom: 12px;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.action-btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  transition: background 0.15s, opacity 0.15s;
}
.action-btn.primary {
  background: #1358e4;
  color: #fff;
}
.action-btn.primary:hover {
  background: #0f49c4;
}
.action-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.action-btn.secondary {
  background: #f0f0f0;
  color: #555;
}
.action-btn.secondary:hover {
  background: #e0e0e0;
}

/* Analyzing */
.analyzing-area {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}
.analyzing-card {
  text-align: center;
  max-width: 400px;
}
.analyzing-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e0e0e0;
  border-top-color: #1358e4;
  border-radius: 50%;
  margin: 0 auto 20px;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.analyzing-card h3 {
  font-size: 18px;
  margin-bottom: 8px;
}
.analyzing-msg {
  color: #666;
  font-size: 14px;
  margin-bottom: 16px;
}
.progress-bar-container {
  width: 100%;
  height: 6px;
  background: #e8e8e8;
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: #1358e4;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.progress-text {
  font-size: 13px;
  color: #999;
  margin-top: 8px;
}

/* Error */
.error-area {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}
.error-card {
  text-align: center;
  max-width: 400px;
}
.error-icon {
  margin-bottom: 16px;
}
.error-card h3 {
  font-size: 18px;
  margin-bottom: 8px;
  color: #e53e3e;
}
.error-card p {
  color: #666;
  font-size: 14px;
  margin-bottom: 20px;
  word-break: break-word;
}

/* ===== Report：对齐视频分析报告页的视觉语言 ===== */
.report-area {
  /* 设计令牌：与视频报告页同款，统一颜色 / 圆角 / 阴影 / 间距 */
  --brand: #1358e4;
  --brand-soft: #eef3fd;
  --ink: #161b22;
  --ink-2: #41474f;
  --ink-3: #8a9099;
  --line: #ecedf0;
  --card-bg: #ffffff;
  --radius-card: 14px;
  --shadow-card: 0 1px 2px rgba(16, 24, 40, 0.04), 0 6px 20px rgba(16, 24, 40, 0.05);
  --gap: 24px;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
}

/* ===== 顶部维度 Tab 栏（对齐视频报告页 .tab-bar / .tab-btn / .tab-score） ===== */
.tab-bar {
  display: flex;
  gap: 2px;
  padding: 5px;
  background: #eceef1;
  border-radius: 12px;
  overflow-x: auto;
}
.tab-btn {
  flex: 1 1 0;
  justify-content: center;
  padding: 9px 16px;
  background: transparent;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  color: var(--ink-2);
  cursor: pointer;
  transition: background 0.18s, color 0.18s, box-shadow 0.18s;
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}
.tab-btn:hover:not(.active) {
  color: var(--brand);
}
.tab-btn.active {
  background: #fff;
  color: var(--brand);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.12);
}
.tab-score {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 999px;
  background: #e1e4e9;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
/* 角标按得分着色（与得分色板一致） */
.tab-score.score-high { background: #e8f6ec; color: #16a34a; }
.tab-score.score-mid { background: #fdf3e0; color: #b8810a; }
.tab-score.score-low { background: #fdecec; color: #dc4446; }

/* Tab 面板：内部区块用统一间距纵向排列 */
.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 单维度 Tab 顶部大标题（左侧蓝条，仿视频页 section-title） */
.dimension-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dimension-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
  padding-left: 12px;
  border-left: 4px solid var(--brand);
}
.dimension-head-badge {
  font-size: 13px;
}

.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  padding: 24px;
  box-shadow: var(--shadow-card);
}

.panel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--gap);
}
@media (max-width: 768px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}

.chart-box {
  width: 100%;
}
/* 雷达卡纵向 flex，让雷达图区填满卡片高度（与右侧六维进度条卡等高，消除雷达下方留白） */
.radar-card {
  display: flex;
  flex-direction: column;
}
.radar-box {
  flex: 1 1 auto;
  min-height: 360px;
}

/* 卡片标题：底部分隔线 */
.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: -0.1px;
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

/* 综合得分 hero（雷达卡内） */
.overall-hero {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 10px;
  padding: 4px 0 8px;
}
.overall-hero-num {
  font-size: 44px;
  font-weight: 800;
  line-height: 1;
  color: var(--brand);
  font-variant-numeric: tabular-nums;
}
.overall-hero-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-3);
}

/* 各维度得分列表（进度条样式与视频页一致） */
.score-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.score-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
/* 可点击跳转到对应维度 Tab */
.score-row-clickable {
  cursor: pointer;
  padding: 8px;
  margin: -8px;
  border-radius: 8px;
  transition: background 0.15s;
}
.score-row-clickable:hover {
  background: var(--brand-soft);
}
.score-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.score-name {
  font-size: 14px;
  font-weight: 500;
  color: #444;
}
.score-val {
  font-size: 14px;
  font-weight: 700;
}
.score-bar-bg {
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.8s ease;
}
.score-desc {
  font-size: 12px;
  color: #888;
  margin: 0;
  line-height: 1.5;
}

/* 得分文字色（与视频页统一） */
.score-high { color: #16a34a; }
.score-mid { color: #d99a06; }
.score-low { color: #dc4446; }

/* 空态文案（仿视频页 .empty-text） */
.empty-text {
  color: #999;
  font-size: 14px;
  text-align: center;
  padding: 24px;
  margin: 0;
}

/* 分析概要 */
.overview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.overview-title {
  margin: 0;
  padding: 0;
  border: none;
}
.overview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.meta-pill {
  padding: 3px 11px;
  background: var(--brand-soft);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  color: var(--brand);
}
.capability-body {
  font-size: 14px;
  color: var(--ink-2);
  line-height: 1.85;
  margin: 0;
}

/* 改进建议（结构化编号列表） */
.improvement-list {
  margin: 0;
  padding-left: 22px;
  font-size: 14px;
  color: #444;
  line-height: 1.8;
}
.improvement-list li {
  margin: 8px 0;
  padding-left: 4px;
}
.improvement-list li::marker {
  color: var(--brand);
  font-weight: 600;
}

/* 分段详情：折叠开关样式仿视频页 .segment-toggle */
.segment-block {
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  margin-bottom: 12px;
  overflow: hidden;
}
.segment-block:last-child {
  margin-bottom: 0;
}
.segment-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  cursor: pointer;
  background: #fff;
  transition: background 0.2s;
}
.segment-toggle:hover {
  background: #f8f9fa;
}
.toggle-icon {
  font-size: 12px;
  color: #666;
  transition: transform 0.2s;
  flex-shrink: 0;
}
.toggle-icon.open {
  transform: rotate(90deg);
}
.toggle-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.segment-body {
  padding: 0 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 维度子卡：仿视频页 .analysis-card（浅灰底 + 左侧蓝条） */
.seg-dim.analysis-card {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  border-left: 3px solid var(--brand);
}
.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.analysis-name {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}
.analysis-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 10px;
}
.analysis-badge.score-high { background: #e8f6ec; color: #16a34a; }
.analysis-badge.score-mid { background: #fdf3e0; color: #b8810a; }
.analysis-badge.score-low { background: #fdecec; color: #dc4446; }

.seg-dim-section {
  margin-bottom: 8px;
}
.seg-dim-section:last-child {
  margin-bottom: 0;
}
.seg-dim-label {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}
.seg-dim-label.good {
  background: #e8f6ec;
  color: #16a34a;
}
.seg-dim-label.warn {
  background: #fdf3e0;
  color: #b8810a;
}
.seg-dim-label.info {
  background: var(--brand-soft);
  color: var(--brand);
}
.seg-dim-section ul {
  padding-left: 20px;
  margin: 4px 0 0;
  font-size: 13px;
  color: #555;
  line-height: 1.7;
}

/* Report bottom */
.report-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 12px 0;
}
.export-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  margin-right: 6px;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
}
</style>
