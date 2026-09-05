<template>
  <div class="v2-report-page" :class="{ 'print-mode': printMode }">
    <div v-if="loading" class="loading-state">
      <div class="spinner" />
      <p>正在加载分析报告...</p>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadReport()">重试</button>
    </div>

    <template v-else-if="videoInfo">
      <!-- 顶部标题栏 -->
      <div class="header-bar">
        <div class="header-left">
          <button type="button" class="report-back-btn" aria-label="返回" @click="handleBack">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <div class="header-titles">
            <h1 class="page-title">课堂教学视频分析报告</h1>
            <div class="header-meta">
              <span class="status-badge" :class="videoInfo.status">{{ statusLabel(videoInfo.status) }}</span>
              <span v-if="friendlyVideoName" class="header-meta-item">{{ friendlyVideoName }}</span>
              <span v-if="videoInfo.create_time" class="header-meta-item">{{ videoInfo.create_time }}</span>
            </div>
          </div>
        </div>
        <div class="header-right">
          <button
            v-if="canStartAnalysis || startingAnalysis"
            type="button"
            class="action-btn action-btn-primary"
            :disabled="!canStartAnalysis || startingAnalysis"
            @click="handleStartAnalysis"
          >
            {{ startingAnalysis ? '启动中...' : '开始分析' }}
          </button>
          <button
            type="button"
            class="action-btn action-btn-export"
            :disabled="!canExportReport || exportingReport"
            :title="exportReportButtonTitle"
            @click="handleExportReport"
          >
            <svg
              class="action-btn-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M12 3v12m0 0l4-4m-4 4l-4-4"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
            <span>{{ exportingReport ? '导出中...' : '导出报告' }}</span>
          </button>
          <MoreOptionsMenu v-model:open="showMoreOptions">
            <button
              type="button"
              :disabled="!currentVideoId || renaming"
              @click="openRenameModal"
            >
              {{ renaming ? '重命名中...' : '重命名' }}
            </button>
            <button
              type="button"
              class="is-danger"
              :disabled="!currentVideoId || deleting"
              @click="handleDelete"
            >
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </MoreOptionsMenu>
        </div>
      </div>

      <!-- 视频播放器（始终显示，不依赖分析状态） -->
      <div class="panel-card video-player-card" v-if="videoUrl">
        <video ref="videoPlayerRef" :src="videoUrl" controls class="video-player" />
      </div>

      <!-- 分析尚未完成提示 -->
      <div v-if="!report" class="video-info-card">
        <h2 class="video-name">{{ videoInfo.name }}</h2>
        <div class="video-meta">
          <span class="status-badge" :class="videoInfo.status">
            {{ statusLabel(videoInfo.status) }}
          </span>
          <span class="meta-item">创建时间：{{ videoInfo.create_time }}</span>
        </div>
        <div class="video-placeholder">
          <p>视频分析{{ videoInfo.status === 'waiting' ? '进行中' : '尚未开始' }}</p>
          <p class="placeholder-hint">分析完成后将自动展示五维度评估报告</p>
          <button
            v-if="canStartAnalysis"
            type="button"
            class="action-btn action-btn-primary start-analysis-btn"
            :disabled="startingAnalysis"
            @click="handleStartAnalysis"
          >
            {{ startingAnalysis ? '启动中...' : '开始分析' }}
          </button>
        </div>
      </div>

      <!-- Tab 切换（仅分析完成后显示） -->
      <div v-if="report" class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
          <span v-if="tab.key !== 'overview'" class="tab-score" :class="scoreClass(scores[tab.scoreKey] ?? 0)">
            {{ fmtScore(scores[tab.scoreKey]) }}
          </span>
        </button>
      </div>

      <!-- ========== 总览 Tab ========== -->
      <div v-show="activeTab === 'overview'" class="tab-panel overview-tab-panel">
        <div class="panel-grid">
          <!-- 雷达图 + 综合得分 -->
          <div class="panel-card radar-card">
            <div class="overall-hero">
              <div class="overall-hero-num" :class="scoreClass(scores.overall ?? 0)">{{ fmtScore(scores.overall) }}</div>
              <div class="overall-hero-label">综合得分</div>
            </div>
            <div ref="radarChartRef" class="chart-box" style="height: 320px;" />
          </div>

          <!-- 各维度得分 -->
          <div class="panel-card">
            <h3 class="panel-title">各维度得分</h3>
            <div class="score-list">
              <div
                v-for="item in dimensionScores"
                :key="item.key"
                class="score-row"
              >
                <div class="score-info">
                  <span class="score-name">{{ item.name }}</span>
                  <span class="score-val" :class="scoreClass(item.score)">{{ item.score > 0 ? item.score + '分' : '—' }}</span>
                </div>
                <div class="score-bar-bg">
                  <div class="score-bar-fill" :style="{ width: item.score + '%', background: item.color }" />
                </div>
                <p class="score-desc">{{ item.desc }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- AI 总评 -->
        <div class="panel-card">
          <h3 class="panel-title">AI 总评摘要</h3>
          <div class="summary-body" v-html="renderedSummary" />
        </div>

        <!-- 改进建议 -->
        <div class="panel-card">
          <h3 class="panel-title">总体改进建议</h3>
          <ul v-if="suggestions.length" class="suggestion-list">
            <li v-for="(s, i) in suggestions" :key="i">{{ s }}</li>
          </ul>
          <p v-else class="empty-text">暂无建议</p>
        </div>

        <!-- 能力概述（仅在数据存在时显示，兼容旧报告） -->
        <div v-if="capabilitySummary" class="panel-card capability-card">
          <h3 class="panel-title">能力概述</h3>
          <p class="capability-body">{{ capabilitySummary }}</p>
        </div>

        <!-- 改进建议（结构化，仅在数据存在时显示） -->
        <div v-if="improvementSuggestions.length" class="panel-card improvement-card">
          <h3 class="panel-title">改进建议</h3>
          <ol class="improvement-list">
            <li v-for="(item, idx) in improvementSuggestions" :key="idx">{{ item }}</li>
          </ol>
        </div>
      </div>

      <!-- ========== 教学表达 Tab ========== -->
      <div v-show="activeTab === 'expression'" class="tab-panel">
        <div class="expression-header">
          <h2 class="expression-title">教学表达</h2>
          <p class="expression-subtitle">字幕文本 · 逐分钟音量曲线 · 语言精炼度（口头禅）</p>
        </div>

        <div class="panel-card speech-rate-card">
          <div class="speech-rate-header">
            <h3 class="panel-title" style="margin:0; border:none; padding:0;">语速分析 (CPM)</h3>
            <div class="speech-rate-stat-text" v-if="speechRate">
              平均 {{ Number(speechRate.avg_cpm ?? 0).toFixed(1) }} CPM · 最大 {{ Number(speechRate.max_cpm ?? 0).toFixed(1) }} CPM · 最小 {{ Number(speechRate.min_cpm ?? 0).toFixed(1) }} CPM
            </div>
          </div>
          <div class="chart-scroll-wrap">
            <div ref="speechRateChartRef" class="chart-box-scroll" style="height: 260px;" />
          </div>
        </div>

        <div class="panel-card volume-card">
          <div class="volume-header">
            <h3 class="panel-title" style="margin:0; border:none; padding:0;">音量分析</h3>
            <div class="volume-stat-text" v-if="volume">
              平均 {{ Number(volume.avg_spl ?? 0).toFixed(1) }} dB · 最大 {{ Number(volume.max_spl ?? 0).toFixed(1) }} dB · 最小 {{ Number(volume.min_spl ?? 0).toFixed(1) }} dB
            </div>
          </div>
          <div class="chart-scroll-wrap">
            <div ref="volumeChartRef" class="chart-box-scroll" style="height: 340px;" />
          </div>
        </div>

        <div class="panel-card conciseness-card">
          <div class="conciseness-header">
            <h3 class="panel-title" style="margin:0; border:none; padding:0;">语言精炼度</h3>
            <span class="conciseness-meta" v-if="conciseness">
              （冗余填充词占比 {{ (Number(conciseness.filler_word_ratio ?? 0) * 100).toFixed(1) }}%，共 {{ conciseness.filler_word_count }} 次）
            </span>
          </div>
          <div class="conciseness-body">
            <div class="conciseness-chart">
              <div ref="fillerChartRef" class="chart-box" style="height: 280px;" />
            </div>
            <div class="conciseness-examples">
              <div
                v-for="(item, idx) in (conciseness?.top_filler_words as Array<Record<string, unknown>> ?? []).slice(0, 3)"
                :key="idx"
                class="example-group"
              >
                <div class="example-title">{{ item.term }} ×{{ item.count }}</div>
                <ul class="example-list">
                  <li
                    v-for="(ex, eidx) in (item.examples as Array<Record<string, unknown>> ?? []).slice(0, 3)"
                    :key="eidx"
                  >
                    <span class="example-time">{{ formatTime(ex.start) }}</span>
                    <span class="example-text">{{ ex.text }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ========== 教学设计 Tab ========== -->
      <div v-show="activeTab === 'design'" class="tab-panel">
        <div class="design-header">
          <h2 class="design-title">教学设计</h2>
          <p class="design-subtitle">课堂环节占比 · 导入/总结环节分析 · 信息密度曲线</p>
        </div>

        <div class="panel-grid">
          <div class="panel-card">
            <h3 class="panel-title">课堂环节占比</h3>
            <div ref="designPieRef" class="chart-box" style="height: 320px;" />
          </div>
          <div class="panel-card analysis-cards">
            <!-- 导入环节 -->
            <div class="analysis-card" v-if="introAnalysis">
              <div class="analysis-header">
                <span class="analysis-name">课程导入环节</span>
                <span class="analysis-badge" :class="scoreClass(toScore(introAnalysis.score))">{{ fmtScoreCn(introAnalysis.score) }}</span>
              </div>
              <div class="analysis-meta" v-if="introAnalysis.exists">
                <span class="meta-label">存在：</span>是（{{ introAnalysis.time_range }}）
              </div>
              <div class="analysis-meta" v-else-if="introAnalysis.exists === false">
                <span class="meta-label">存在：</span>否
              </div>
              <p class="analysis-desc" v-if="introAnalysis.description">{{ introAnalysis.description }}</p>
              <p class="analysis-eval" v-if="introAnalysis.evaluation">{{ introAnalysis.evaluation }}</p>
              <p class="analysis-eval" v-else-if="introAnalysis.comment">{{ introAnalysis.comment }}</p>
            </div>
            <!-- 总结环节 -->
            <div class="analysis-card" v-if="conclusionAnalysis">
              <div class="analysis-header">
                <span class="analysis-name">总结环节</span>
                <span class="analysis-badge" :class="scoreClass(toScore(conclusionAnalysis.score))">{{ fmtScoreCn(conclusionAnalysis.score) }}</span>
              </div>
              <div class="analysis-meta" v-if="conclusionAnalysis.exists">
                <span class="meta-label">存在：</span>是（{{ conclusionAnalysis.time_range }}）
              </div>
              <div class="analysis-meta" v-else-if="conclusionAnalysis.exists === false">
                <span class="meta-label">存在：</span>否
              </div>
              <p class="analysis-desc" v-if="conclusionAnalysis.description">{{ conclusionAnalysis.description }}</p>
              <p class="analysis-eval" v-if="conclusionAnalysis.evaluation">{{ conclusionAnalysis.evaluation }}</p>
              <p class="analysis-eval" v-else-if="conclusionAnalysis.comment">{{ conclusionAnalysis.comment }}</p>
            </div>
          </div>
        </div>

        <div class="panel-card density-card">
          <h3 class="panel-title">信息密度曲线</h3>
          <div class="chart-scroll-wrap">
            <div ref="densityChartRef" class="chart-box-scroll" style="height: 340px;" />
          </div>
        </div>

        <div class="panel-card segment-list-card" v-if="segments.length">
          <div class="segment-toggle" @click="showSegments = !showSegments">
            <span class="toggle-icon" :class="{ open: showSegments }">▶</span>
            <span class="toggle-label">查看完整环节列表</span>
          </div>
          <div v-show="showSegments" class="segment-table-wrap">
            <table class="data-table">
              <thead>
                <tr><th>类型</th><th>开始</th><th>结束</th></tr>
              </thead>
              <tbody>
                <tr v-for="(seg, i) in segments" :key="i">
                  <td><span class="tag">{{ seg.type }}</span></td>
                  <td>{{ seg.start_time }}</td>
                  <td>{{ seg.end_time }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ========== 知识呈现 Tab ========== -->
      <div v-show="activeTab === 'knowledge'" class="tab-panel">
        <div class="section-header">
          <h2 class="section-title">知识呈现</h2>
          <p class="section-subtitle">知识点分布 · 高频关键词</p>
        </div>
        <div class="panel-grid single-col">
          <div class="panel-card">
            <h3 class="panel-title">知识点分布</h3>
            <div ref="knowledgeTreeRef" class="chart-box" style="height: 360px;" />
          </div>
          <div class="panel-card">
            <h3 class="panel-title">高频关键词</h3>
            <WordCloudChart
              v-if="wordCloudWords.length"
              :words="wordCloudWords"
              :width="520"
              :height="400"
            />
            <p v-else class="empty-text">暂无词云数据</p>
          </div>
        </div>
      </div>

      <!-- ========== 互动质量 Tab ========== -->
      <div v-show="activeTab === 'interaction'" class="tab-panel">
        <div class="interaction-header">
          <h2 class="interaction-title">互动质量</h2>
          <p class="interaction-subtitle">互动事件与类型 · 互动间隔（纯讲授段） · 五何互动交流图</p>
        </div>

        <div class="panel-card scatter-card">
          <h3 class="panel-title">互动时间轴</h3>
          <div ref="interactionScatterRef" class="chart-box" style="height: 340px;" />
          <div class="interaction-summary" v-if="interactionEvents.length">
            互动总数 {{ interactionEvents.length }} 次；
            超过 12 分钟无互动的纯讲授段：{{ interactionGaps.length }} 段。
            <span v-if="interactionGaps.length">
              建议插入互动时间点：{{ interactionGaps.map(g => (g.suggestion as { time?: string } | undefined)?.time).filter(Boolean).join('、') }}
            </span>
          </div>
        </div>

        <div class="panel-grid">
          <div class="panel-card">
            <h3 class="panel-title">五何分布</h3>
            <div ref="whPieRef" class="chart-box" style="height: 280px;" />
          </div>
          <div class="panel-card" v-if="interactionEvents.length">
            <h3 class="panel-title">互动类型统计</h3>
            <div class="type-stat-list">
              <div v-for="(count, type) in typeStatistics" :key="type" class="type-stat-row">
                <span class="type-name">{{ type }}</span>
                <span class="type-count">{{ count }} 次</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-card event-list-card" v-if="interactionEvents.length">
          <div class="event-toggle" @click="showEvents = !showEvents">
            <span class="toggle-icon" :class="{ open: showEvents }">▶</span>
            <span class="toggle-label">查看互动事件明细</span>
          </div>
          <div v-show="showEvents" class="event-table-wrap">
            <table class="data-table">
              <thead>
                <tr><th>时间</th><th>类型</th><th>内容</th></tr>
              </thead>
              <tbody>
                <tr v-for="(evt, i) in interactionEvents" :key="i">
                  <td>{{ evt.start_time }} - {{ evt.end_time }}</td>
                  <td><span class="tag">{{ evt.type }}</span></td>
                  <td class="ellipsis">{{ evt.text || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ========== 思政融合 Tab ========== -->
      <div v-show="activeTab === 'ideology'" class="tab-panel">
        <div class="section-header" v-if="ideologyEvents.length">
          <h2 class="section-title">思政融合</h2>
          <p class="section-subtitle">思政事件时间轴 · 融入自然度评价</p>
        </div>
        <div v-if="ideologyEvents.length" class="ideology-list">
          <div
            v-for="(evt, i) in ideologyEvents"
            :key="i"
            class="ideology-card"
          >
            <div class="ideology-header">
              <div class="ideology-title-row">
                <span class="ideology-title">{{ evt.title || '思政事件' }}</span>
                <button
                  v-if="videoUrl && evt.start != null"
                  type="button"
                  class="ideology-seek-btn"
                  :aria-label="`从 ${formatTime(evt.start)} 开始播放`"
                  :title="`从 ${formatTime(evt.start)} 开始播放`"
                  @click="seekIdeologyEvent(evt)"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M10 8.5L16 12L10 15.5V8.5Z" fill="currentColor"/>
                  </svg>
                </button>
              </div>
              <span class="ideology-score-badge" :class="scoreClass(toScore(evt.integration_score))">
                融入度 {{ fmtScoreCn(evt.integration_score) }}
              </span>
            </div>
            <div class="ideology-meta">{{ formatTime(evt.start) }} - {{ formatTime(evt.end) }}</div>
            <p class="ideology-desc">{{ evt.content }}</p>
            <p class="ideology-eval" v-if="evt.integration_evaluation">{{ evt.integration_evaluation }}</p>
          </div>
        </div>
        <div v-else class="panel-card empty-card">
          <p class="empty-text">未检测到思政融合事件</p>
        </div>
      </div>
    </template>

    <ConfirmDialogModal
      v-model="showLeaveAnalysisModal"
      variant="info"
      title="开始分析"
      message="视频已上传但尚未开始分析，是否现在开始分析？"
      confirm-label="开始分析"
      cancel-label="直接离开"
      :pending="startingAnalysis"
      @confirm="confirmLeaveStartAnalysis"
      @cancel="confirmLeaveWithoutAnalysis"
    />

    <ConfirmDialogModal
      v-model="showStartAnalysisErrorModal"
      variant="info"
      title="提示"
      :message="startAnalysisErrorMessage"
      single-button
      confirm-label="知道了"
      @confirm="showStartAnalysisErrorModal = false"
      @cancel="showStartAnalysisErrorModal = false"
    />

    <ConfirmDialogModal
      v-model="showExportPendingModal"
      variant="info"
      title="导出报告"
      :message="exportPendingMessage"
      single-button
      confirm-label="知道了"
      @confirm="showExportPendingModal = false"
      @cancel="showExportPendingModal = false"
    />

    <DeleteConfirmModal
      v-model="showDeleteVideoModal"
      title="删除视频"
      entity-kind="视频"
      :entity-name="deleteVideoEntityName"
      :pending="deleting"
      @cancel="closeDeleteVideoModal"
      @confirm="confirmDeleteVideo"
    />

    <div v-if="showRenameModal" class="modal-overlay">
      <div class="modal-content rename-modal">
        <div class="modal-header">
          <h3>重命名视频</h3>
          <button
            type="button"
            class="modal-close"
            @click="closeRenameModal"
            aria-label="关闭"
          >
            &times;
          </button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>视频名称</label>
            <input
              v-model.trim="renameInput"
              type="text"
              class="form-input"
              placeholder="输入新视频名称"
              @keydown.enter="confirmRename"
            />
          </div>
          <p v-if="renameError" class="rename-error">{{ renameError }}</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn secondary" @click="closeRenameModal">取消</button>
          <button
            type="button"
            class="action-btn"
            :disabled="!renameInput || renaming"
            @click="confirmRename"
          >
            {{ renaming ? '保存中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import {
  getVideoDetail,
  resolveVideoMediaUrl,
  startVideoAnalysis,
  isVideoTaskPollingActive,
  operateVideo,
  removeRegisteredVideoTask,
  downloadBlobAsFile,
  type VideoDetail,
  type AnalysisMode,
} from '../api/video'
import { OperationEnum } from '../api/types'
import { notifyResourceAnalysisListRefresh } from '../api/resourceAnalysis'
import type { ReportPdfChart, ReportPdfInput } from '../lib/reportPdf'
import { marked } from 'marked'
import ConfirmDialogModal from '../components/ConfirmDialogModal.vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import MoreOptionsMenu from '../components/MoreOptionsMenu.vue'
import {
  scoreClass, fmtScore, fmtScoreCn, toScore,
  formatTime, timeStrToSeconds, statusLabel, stripMarkdown,
} from '../lib/videoReportUtils'
import { useVideoCharts } from '../composables/useVideoCharts'
import WordCloudChart from '../components/charts/WordCloudChart.vue'
import type { HotWord } from '../components/charts/WordCloudChart.vue'

const route = useRoute()
const router = useRouter()

/** 返回资源分析列表 */
function handleBack() {
  router.push('/resource-analysis')
}
const loading = ref(false)
const error = ref('')
const report = ref<Record<string, unknown> | null>(null)
const videoInfo = ref<VideoDetail | null>(null)
const activeTab = ref('overview')
const startingAnalysis = ref(false)
const exportingReport = ref(false)
/** 导出报告时进入打印模式：展开全部 Tab、隐藏交互控件，配合 window.print() 生成 PDF */
const printMode = ref(false)
const showMoreOptions = ref(false)
const showRenameModal = ref(false)
const renameInput = ref('')
const renameError = ref('')
const renaming = ref(false)
const deleting = ref(false)
const showDeleteVideoModal = ref(false)
const showExportPendingModal = ref(false)
const exportPendingMessage = ref('')
const showLeaveAnalysisModal = ref(false)
const showStartAnalysisErrorModal = ref(false)
const startAnalysisErrorMessage = ref('')
const pendingLeaveRoute = ref<RouteLocationNormalized | null>(null)
/** 用户已确认直接离开，放行下一次路由跳转，避免守卫重复弹窗 */
const skipUnstartedLeavePrompt = ref(false)

const currentVideoId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' && id.trim() ? id.trim() : null
})

const deleteVideoEntityName = computed(() => {
  const n = (videoInfo.value?.name || '').trim()
  return n || '该视频'
})

const POLL_INTERVAL_MS = 5 * 1000
let detailPollTimer: ReturnType<typeof setInterval> | null = null

const canStartAnalysis = computed(() => {
  if (!videoInfo.value) return false
  const s = videoInfo.value.status
  if (s !== 'unstarted' && s !== 'failed') return false
  return Boolean(route.params.id)
})

const shouldPromptLeaveForUnstarted = computed(() => videoInfo.value?.status === 'unstarted')

const canExportReport = computed(() => {
  if (!videoInfo.value) return false
  return videoInfo.value.status === 'success' && Boolean(currentVideoId.value)
})

const exportReportButtonTitle = computed(() => {
  if (canExportReport.value) return '下载分析报告到本地'
  if (!videoInfo.value) return ''
  const s = videoInfo.value.status
  if (s === 'failed') return '分析失败，无法导出'
  if (s === 'waiting') return '分析进行中，完成后可导出'
  if (s === 'unstarted') return '请先开始分析，完成后可导出'
  return '分析完成后可导出'
})

const tabs = [
  { key: 'overview', label: '总览', scoreKey: 'overall' },
  { key: 'expression', label: '教学表达', scoreKey: 'expression' },
  { key: 'design', label: '教学设计', scoreKey: 'design' },
  { key: 'knowledge', label: '知识呈现', scoreKey: 'knowledge' },
  { key: 'interaction', label: '互动质量', scoreKey: 'interaction' },
  { key: 'ideology', label: '思政融合', scoreKey: 'ideology' },
]

const scores = computed(() => {
  const rd = (report.value?.radar_data as Array<Record<string, unknown>> | undefined) ?? []
  const map: Record<string, number> = {}
  const keyMap: Record<string, string> = {
    '教学表达': 'expression',
    '教学设计': 'design',
    '知识呈现': 'knowledge',
    '互动质量': 'interaction',
    '思政融合': 'ideology',
    '综合得分': 'overall',
  }
  for (const item of rd) {
    const key = keyMap[String(item.dimension ?? '')]
    if (key) map[key] = Number(item.score ?? 0)
  }
  return map
})

const dimensionScores = computed(() => [
  { key: 'expression', name: '教学表达', score: scores.value.expression ?? 0, color: '#5470c6', desc: '语速适中度、语言精炼度与音量稳定性' },
  { key: 'design', name: '教学设计', score: scores.value.design ?? 0, color: '#91cc75', desc: '环节丰富度、导入与总结质量' },
  { key: 'knowledge', name: '知识呈现', score: scores.value.knowledge ?? 0, color: '#fac858', desc: '知识结构合理性与要素覆盖完整性' },
  { key: 'interaction', name: '互动质量', score: scores.value.interaction ?? 0, color: '#ee6666', desc: '互动类型丰富度与间隔合理性' },
  { key: 'ideology', name: '思政融合', score: scores.value.ideology ?? 0, color: '#73c0de', desc: '思政事件存在性与融入自然度' },
])

/** 友好视频名：若名称看起来是自动生成的 id（纯英数、无中文/空格）则视为「无名」，返回空 */
const friendlyVideoName = computed(() => {
  const name = (videoInfo.value?.name ?? '').trim()
  if (!name) return ''
  const looksLikeId = /^[A-Za-z0-9_-]{6,}$/.test(name)
  return looksLikeId ? '' : name
})

const aiSummary = computed(() => {
  const raw = report.value?.ai_summary
  if (typeof raw === 'string') {
    return { summary: raw, suggestions: [] }
  }
  return (raw as Record<string, unknown> | undefined) ?? {}
})

const renderedSummary = computed(() => {
  const raw = aiSummary.value?.summary as string | undefined
  if (!raw) return '<p>暂无总评</p>'
  return marked.parse(raw, { async: false }) as string
})

const videoUrl = computed(() => {
  const path = videoInfo.value?.path
  return path ? resolveVideoMediaUrl(path) : undefined
})

const suggestions = computed(() => {
  const s = aiSummary.value?.suggestions as string[] | undefined
  return s ?? []
})

const capabilitySummary = computed(() => {
  const raw = report.value?.capability_summary
  return typeof raw === 'string' ? raw : ''
})

const improvementSuggestions = computed(() => {
  const raw = report.value?.improvement_suggestions
  return Array.isArray(raw) ? (raw as string[]) : []
})

const showSegments = ref(false)
const showEvents = ref(false)

// 各维度数据
const speechRate = computed(() =>
  (report.value?.teaching_expression as Record<string, unknown> | undefined)?.speech_rate_analysis as Record<string, unknown> | undefined
)
const volume = computed(() =>
  (report.value?.teaching_expression as Record<string, unknown> | undefined)?.volume_analysis as Record<string, unknown> | undefined
)
const conciseness = computed(() =>
  (report.value?.teaching_expression as Record<string, unknown> | undefined)?.language_conciseness as Record<string, unknown> | undefined
)
const introAnalysis = computed(() =>
  (report.value?.teaching_design as Record<string, unknown> | undefined)?.introduction_analysis as Record<string, unknown> | undefined
)
const conclusionAnalysis = computed(() =>
  (report.value?.teaching_design as Record<string, unknown> | undefined)?.conclusion_analysis as Record<string, unknown> | undefined
)
const segments = computed(() =>
  ((report.value?.teaching_design as Record<string, unknown> | undefined)?.segments as Array<Record<string, unknown>> | undefined) ?? []
)
const typeDistribution = computed(() =>
  ((report.value?.teaching_design as Record<string, unknown> | undefined)?.type_distribution as Array<Record<string, unknown>> | undefined) ?? []
)
const densityData = computed(() =>
  ((report.value?.teaching_design as Record<string, unknown> | undefined)?.information_density as Record<string, unknown> | undefined)?.result as number[] | undefined ?? []
)
const densityMeta = computed(() =>
  (report.value?.teaching_design as Record<string, unknown> | undefined)?.information_density as Record<string, unknown> | undefined
)
const wordCloud = computed(() =>
  ((report.value?.knowledge_presentation as Record<string, unknown> | undefined)?.word_cloud as Array<Record<string, unknown>> | undefined) ?? []
)
const knowledgeTree = computed(() =>
  ((report.value?.knowledge_presentation as Record<string, unknown> | undefined)?.knowledge_tree as Array<Record<string, unknown>> | undefined) ?? []
)
const interactionEvents = computed(() =>
  ((report.value?.interaction_quality as Record<string, unknown> | undefined)?.interaction_events as Array<Record<string, unknown>> | undefined) ?? []
)
const interactionGaps = computed(() =>
  ((report.value?.interaction_quality as Record<string, unknown> | undefined)?.interaction_gaps as Array<Record<string, unknown>> | undefined) ?? []
)
const typeStatistics = computed(() =>
  (report.value?.interaction_quality as Record<string, unknown> | undefined)?.type_statistics as Record<string, number> | undefined ?? {}
)
const whDistribution = computed(() =>
  (report.value?.interaction_quality as Record<string, unknown> | undefined)?.wh_distribution as Record<string, Record<string, unknown>> | undefined ?? {}
)
const ideologyEvents = computed(() =>
  ((report.value?.ideological_integration as Record<string, unknown> | undefined)?.ideological_events as Array<Record<string, unknown>> | undefined) ?? []
)
const wordCloudWords = computed<HotWord[]>(() =>
  wordCloud.value.map((r) => ({ text: String(r.word ?? ''), count: Number(r.weight ?? 0) })).filter((w) => w.text)
)

const videoPlayerRef = ref<HTMLVideoElement | null>(null)

function seekVideoToTime(timeSec: number) {
  if (!Number.isFinite(timeSec)) return
  const el = videoPlayerRef.value
  if (!el) return
  const t = Math.max(0, timeSec)
  try {
    el.currentTime = t
  } catch {
    return
  }
  try {
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  } catch {
    //
  }
  void el.play().catch(() => {
    // 浏览器可能拦截自动播放；用户已点击图表，通常可播
  })
}

function seekIdeologyEvent(evt: Record<string, unknown>) {
  const start = Number(evt.start)
  if (!Number.isFinite(start)) return
  seekVideoToTime(start)
}

const charts = useVideoCharts(seekVideoToTime)
const {
  radarChartRef, speechRateChartRef, volumeChartRef, fillerChartRef,
  designPieRef, densityChartRef, knowledgeTreeRef, interactionScatterRef, whPieRef,
} = charts


function shouldPollReport(): boolean {
  if (loading.value) return false
  if (!videoInfo.value) return false
  return isVideoTaskPollingActive(videoInfo.value.status)
}

function startReportPolling() {
  if (detailPollTimer) return
  detailPollTimer = setInterval(() => {
    if (!shouldPollReport()) return
    void loadReport({ silent: true })
  }, POLL_INTERVAL_MS)
}

function stopReportPolling() {
  if (!detailPollTimer) return
  clearInterval(detailPollTimer)
  detailPollTimer = null
}

function handleStartAnalysis() {
  const id = route.params.id as string
  if (!id || !canStartAnalysis.value) return
  // 固定本地大模型分析，不再弹选择框：直接发起分析
  void runAnalysis('local')
}

async function runAnalysis(mode: AnalysisMode) {
  const id = route.params.id as string
  if (!id || !canStartAnalysis.value) {
    return
  }
  startingAnalysis.value = true
  try {
    await startVideoAnalysis(id, mode)
    await loadReport({ silent: true })
  } catch (e) {
    startAnalysisErrorMessage.value = e instanceof Error ? e.message : '启动分析失败'
    showStartAnalysisErrorModal.value = true
  } finally {
    startingAnalysis.value = false
  }
}

function confirmLeaveWithoutAnalysis() {
  showLeaveAnalysisModal.value = false
  const to = pendingLeaveRoute.value
  pendingLeaveRoute.value = null
  if (!to) return
  skipUnstartedLeavePrompt.value = true
  void router.push(to).finally(() => {
    skipUnstartedLeavePrompt.value = false
  })
}

async function confirmLeaveStartAnalysis() {
  showLeaveAnalysisModal.value = false
  pendingLeaveRoute.value = null
  await handleStartAnalysis()
}

/** 横向滚动型图表（语速/音量/信息密度）在打印时改为占满页宽，避免被页边裁掉 */
function fitScrollChartsForPrint() {
  charts.fitScrollChartsForPrint()
}

/** afterprint 兜底定时器：个别环境（iframe/策略限制等）afterprint 可能不触发，超时强制收尾 */
let printResetTimer: number | null = null

/**
 * 导出报告为 PDF（原生排版，pdf-lib）：文字可选中、图表为高清图片、文件小。
 * 复用 printMode 短暂展开全部 Tab，使隐藏 Tab 里的 ECharts 获得尺寸后可被 getDataURL 截取。
 */
async function handleExportReport() {
  if (!canExportReport.value || !report.value || exportingReport.value) return
  exportingReport.value = true
  printMode.value = true
  try {
    // 等待全部 Tab 展开进入布局后，重建并定格所有图表（含此前未渲染的隐藏 Tab）
    await nextTick()
    initAllCharts()
    fitScrollChartsForPrint()
    charts.chartMap.forEach((chart) => {
      chart.resize()
      chart.setOption({ animation: false })
    })
    await new Promise((resolve) => setTimeout(resolve, 250))
    await nextTick()

    const grab = (el: HTMLDivElement | null, caption: string): ReportPdfChart | null => {
      const url = charts.getChartDataURL(el)
      return url ? { caption, dataUrl: url } : null
    }
    const keep = (...xs: (ReportPdfChart | null)[]) => xs.filter((c): c is ReportPdfChart => !!c)

    const input: ReportPdfInput = {
      title: '课堂教学视频分析报告',
      videoName: friendlyVideoName.value,
      date: videoInfo.value?.create_time ?? '',
      statusLabel: statusLabel(videoInfo.value?.status ?? ''),
      overall: scores.value.overall ?? 0,
      dimensions: dimensionScores.value.map((d) => ({ key: d.key, name: d.name, score: d.score, color: d.color, desc: d.desc })),
      summary: stripMarkdown((aiSummary.value?.summary as string | undefined) ?? ''),
      suggestions: suggestions.value,
      dimensionCharts: {
        overview: keep(grab(radarChartRef.value, '综合能力雷达图')),
        expression: keep(grab(speechRateChartRef.value, '语速变化'), grab(volumeChartRef.value, '音量变化'), grab(fillerChartRef.value, '口头语统计')),
        design: keep(grab(designPieRef.value, '教学环节分布'), grab(densityChartRef.value, '信息密度变化')),
        knowledge: keep(grab(knowledgeTreeRef.value, '知识结构')),
        interaction: keep(grab(interactionScatterRef.value, '互动事件分布'), grab(whPieRef.value, '提问类型分布')),
        ideology: [],
      },
    }

    // 按需加载 pdf-lib（仅导出时拉取，不进报告页主 chunk）
    const { buildReportPdf } = await import('../lib/reportPdf')
    const bytes = await buildReportPdf(input)
    const blob = new Blob([new Uint8Array(bytes)], { type: 'application/pdf' })
    downloadBlobAsFile(blob, `${friendlyVideoName.value || '课堂教学视频分析报告'}.pdf`)
  } catch (e) {
    exportPendingMessage.value = e instanceof Error ? e.message : '导出失败，请稍后再试'
    showExportPendingModal.value = true
  } finally {
    printMode.value = false
    exportingReport.value = false
    await nextTick()
    initAllCharts()
    charts.resizeAll()
  }
}

/** 打印布局生效后按页宽重排图表：避免画布按屏宽(最大 1200px)栅格化导致 A4 页面右侧被裁切 */
function onBeforePrint() {
  if (!printMode.value) return
  charts.resizeAll()
}

/** 打印结束/取消后恢复：退出打印模式并将图表恢复为正常（滚动宽度 + 动画）渲染 */
function onAfterPrint() {
  if (!printMode.value) return
  if (printResetTimer != null) {
    window.clearTimeout(printResetTimer)
    printResetTimer = null
  }
  printMode.value = false
  exportingReport.value = false
  document.body.classList.remove('report-print-active')
  nextTick(() => {
    initAllCharts()
    charts.resizeAll()
  })
}

function openRenameModal() {
  if (!currentVideoId.value) return
  renameInput.value = videoInfo.value?.name ?? ''
  renameError.value = ''
  showRenameModal.value = true
}

function closeRenameModal() {
  showRenameModal.value = false
  renameError.value = ''
}

async function confirmRename() {
  const id = currentVideoId.value
  if (!id) return
  const newName = renameInput.value.trim()
  if (!newName) {
    renameError.value = '请输入视频名称'
    return
  }
  renameError.value = ''
  renaming.value = true
  try {
    await operateVideo({
      id,
      name: newName,
      operation: OperationEnum.UPDATE,
    })
    await loadReport({ silent: true })
    closeRenameModal()
  } catch (e) {
    renameError.value = e instanceof Error ? e.message : '重命名失败'
  } finally {
    renaming.value = false
  }
}

function closeDeleteVideoModal() {
  if (deleting.value) return
  showDeleteVideoModal.value = false
}

function handleDelete() {
  if (!currentVideoId.value) return
  showDeleteVideoModal.value = true
}

async function confirmDeleteVideo() {
  const id = currentVideoId.value
  if (!id || deleting.value) return
  deleting.value = true
  try {
    await operateVideo({
      id,
      name: null,
      operation: OperationEnum.DELETE,
    })
    removeRegisteredVideoTask(id)
    notifyResourceAnalysisListRefresh()
    showDeleteVideoModal.value = false
    skipUnstartedLeavePrompt.value = true
    await router.push('/resource-analysis')
  } catch (e) {
    console.error('删除失败:', e)
  } finally {
    deleting.value = false
    skipUnstartedLeavePrompt.value = false
  }
}

async function loadReport(options?: { silent?: boolean }) {
  const id = route.params.id as string
  if (!id) {
    if (!options?.silent) error.value = '缺少视频 ID'
    return
  }
  const silent = options?.silent ?? false
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const video = await getVideoDetail(id)
    if (!video) {
      if (!silent) error.value = '视频不存在或暂无权限'
      return
    }
    videoInfo.value = video
    if (video.status === 'success' && video.analysis_result) {
      report.value = video.analysis_result
    } else if (video.status !== 'success') {
      report.value = null
    }
  } catch (e: unknown) {
    if (!silent) error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    if (!silent) loading.value = false
  }
  // loading 关闭后内容区 DOM 才渲染，再初始化图表
  if (report.value) {
    await nextTick()
    initAllCharts()
  }
  if (shouldPollReport()) startReportPolling()
  else stopReportPolling()
}

function initAllCharts() {
  if (!report.value) return
  charts.initRadarChart(report.value)
  charts.initSpeechRateChart(speechRate.value)
  charts.initVolumeChart(volume.value)
  charts.initFillerChart(conciseness.value)
  charts.initDesignPie(typeDistribution.value)
  charts.initDensityChart(densityData.value, densityMeta.value)
  charts.initKnowledgeTree(knowledgeTree.value)
  charts.initInteractionScatter(interactionEvents.value, typeStatistics.value, interactionGaps.value)
  charts.initWhPie(whDistribution.value as Record<string, Record<string, unknown>>)
}

function switchTab(key: string) {
  activeTab.value = key
  nextTick(() => {
    charts.resizeAll()
    setTimeout(() => {
      initAllCharts()
      charts.resizeAll()
    }, 50)
  })
}

onMounted(() => {
  void loadReport()
  window.addEventListener('beforeprint', onBeforePrint)
  window.addEventListener('afterprint', onAfterPrint)
})

watch(
  () => route.params.id,
  async () => {
    stopReportPolling()
    report.value = null
    videoInfo.value = null
    await loadReport()
  }
)

onBeforeRouteLeave((to) => {
  if (skipUnstartedLeavePrompt.value) return true
  if (!shouldPromptLeaveForUnstarted.value) return true
  pendingLeaveRoute.value = to
  showLeaveAnalysisModal.value = true
  return false
})

onBeforeUnmount(() => {
  stopReportPolling()
  window.removeEventListener('beforeprint', onBeforePrint)
  window.removeEventListener('afterprint', onAfterPrint)
  if (printResetTimer != null) window.clearTimeout(printResetTimer)
  document.body.classList.remove('report-print-active')
  charts.dispose()
})
</script>

<style scoped>
.v2-report-page {
  /* 设计令牌：统一颜色 / 圆角 / 阴影 / 间距，呈现更高级一致的观感 */
  --brand: #1358e4;
  --brand-hover: #0f47c4;
  --brand-soft: #eef3fd;
  --ink: #161b22;       /* 标题 */
  --ink-2: #41474f;     /* 正文 */
  --ink-3: #8a9099;     /* 次要 */
  --line: #ecedf0;
  --card-bg: #ffffff;
  --radius-card: 14px;
  --radius-ctl: 10px;
  --shadow-card: 0 1px 2px rgba(16, 24, 40, 0.04), 0 6px 20px rgba(16, 24, 40, 0.05);
  --gap: 24px;
  /* 全宽纯色背景、内容居中限宽 1200px：去掉两侧透出的全局渐变背景图 */
  padding: 28px max(24px, calc((100% - 1200px) / 2)) 56px;
  background: #f6f7f9;
  min-height: 100vh;
  color: var(--ink-2);
}

.loading-state,
.error-state {
  text-align: center;
  padding: 100px 20px;
  color: #666;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e0e0e0;
  border-top-color: #1358e4;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  margin-top: 12px;
  padding: 8px 24px;
  background: #1358e4;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

/* 视频信息卡片（分析未完成时） */
.video-info-card {
  background: var(--card-bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: 32px 24px;
  text-align: center;
  margin-bottom: var(--gap);
}

.video-name {
  font-size: 20px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 12px;
}

.video-meta {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  color: #666;
  font-size: 14px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.status-badge::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-badge.unstarted {
  background: #f1f3f5;
  color: #8a9099;
}

.status-badge.waiting {
  background: var(--brand-soft);
  color: var(--brand);
}

.status-badge.success {
  background: #e8f6ec;
  color: #16a34a;
}

.status-badge.failed {
  background: #fdecec;
  color: #dc4446;
}

.video-placeholder {
  padding: 48px 24px;
  background: #f8f9fb;
  border: 1px solid var(--line);
  border-radius: var(--radius-ctl);
  color: var(--ink-3);
}

/* 进行中脉冲指示：传达「正在分析」的动态感 */
.video-placeholder::before {
  content: '';
  display: block;
  width: 14px;
  height: 14px;
  margin: 0 auto 18px;
  border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 0 0 rgba(19, 88, 228, 0.32);
  animation: pulse-ring 1.8s ease-out infinite;
}

@keyframes pulse-ring {
  0% { box-shadow: 0 0 0 0 rgba(19, 88, 228, 0.30); }
  70% { box-shadow: 0 0 0 16px rgba(19, 88, 228, 0); }
  100% { box-shadow: 0 0 0 0 rgba(19, 88, 228, 0); }
}

.video-placeholder p:first-of-type {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--ink);
}

.placeholder-hint {
  font-size: 13px;
  color: var(--ink-3);
}

/* 顶部标题栏 */
.header-bar {
  background: var(--card-bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  padding: 18px 24px;
  margin-bottom: var(--gap);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  box-shadow: var(--shadow-card);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.header-titles {
  min-width: 0;
}

.header-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
}

.header-meta-item {
  font-size: 13px;
  color: var(--ink-3);
}
.header-meta-item + .header-meta-item::before {
  content: '·';
  margin-right: 10px;
  color: #c7ccd3;
}
.report-back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  color: #333;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.report-back-btn:hover {
  background: #f2f3f5;
  border-color: #d0d0d0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.action-btn-icon {
  flex-shrink: 0;
}

.action-btn:hover:not(:disabled):not(.action-btn-primary) {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
}

.action-btn-primary {
  background-color: #1358e4;
  border-color: #1358e4;
  color: #fff;
}

.action-btn-primary:hover:not(:disabled) {
  background-color: #0f47c4;
  border-color: #0f47c4;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.secondary {
  background: #e0e0e0;
  color: #333;
}

.action-btn.secondary:hover:not(:disabled) {
  background: #d0d0d0;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.modal-content {
  width: 520px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.modal-header {
  padding: 14px 18px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.modal-close {
  background: none;
  border: none;
  font-size: 22px;
  line-height: 1;
  color: #666;
  cursor: pointer;
  padding: 0 4px;
}

.modal-body {
  padding: 18px;
}

.modal-body .form-row {
  margin-bottom: 0;
}

.modal-body .form-row label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  color: #333;
}

.modal-body .form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
}

.modal-body .form-input:focus {
  outline: none;
  border-color: #1358e4;
}

.rename-error {
  margin: 10px 0 0;
  font-size: 13px;
  color: #c62828;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 18px;
  border-top: 1px solid #f0f0f0;
}

.start-analysis-btn {
  margin-top: 16px;
}

.page-title {
  font-size: 19px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.2px;
  margin: 0;
  line-height: 1.3;
}

/* 综合得分 hero（总览雷达卡内） */
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

/* Tab 栏 */
.tab-bar {
  display: flex;
  gap: 2px;
  margin-bottom: var(--gap);
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

.tab-btn.active .tab-score {
  background: var(--brand-soft);
  color: var(--brand);
}

/* 面板 */
.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  animation: fadeIn 0.3s ease;
}
/* 由父级 gap 统一控制间距，清除子项历史外边距，避免双倍留白 */
.tab-panel > * {
  margin-bottom: 0;
}

.overview-tab-panel {
  gap: var(--gap);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.panel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--gap);
  margin-bottom: 0;
}

.panel-grid.single-col {
  grid-template-columns: 1fr;
}

@media (max-width: 768px) {
  .panel-grid {
    grid-template-columns: 1fr;
  }
}

.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  padding: 24px;
  box-shadow: var(--shadow-card);
}

.video-player-card {
  padding: 0;
  overflow: hidden;
  margin-bottom: var(--gap);
}

.video-player {
  width: 100%;
  max-height: 480px;
  display: block;
  border-radius: 10px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: -0.1px;
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.chart-box {
  width: 100%;
}

/* 总览 - 得分列表 */
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
}

.score-high { color: #16a34a; }
.score-mid { color: #d99a06; }
.score-low { color: #dc4446; }
.score-none { color: #9aa0a6; }

/* 总览 - AI 总评 */
.summary-body {
  font-size: 14px;
  color: var(--ink-2);
  line-height: 1.85;
  /* 中文按全宽排版，避免 ch 单位（基于 0 字宽）把中文限到约半个卡片、造成右侧大片留白与频繁换行 */
}

.summary-body :deep(h1),
.summary-body :deep(h2),
.summary-body :deep(h3) {
  font-size: 15px;
  color: #333;
  margin: 12px 0 8px;
}

.summary-body :deep(p) {
  margin: 8px 0;
}

.summary-body :deep(ul) {
  margin: 8px 0;
  padding-left: 20px;
}

.summary-body :deep(li) {
  margin: 4px 0;
}

/* 改进建议 */
.suggestion-list {
  margin: 0;
  padding-left: 20px;
  font-size: 14px;
  color: #444;
  line-height: 1.8;
}

.suggestion-list li {
  margin: 6px 0;
}

/* 能力概述 */
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
  counter-reset: none;
}

.improvement-list li {
  margin: 8px 0;
  padding-left: 4px;
}

.improvement-list li::marker {
  color: var(--brand);
  font-weight: 600;
}

/* 评价卡片 */
.comment-card {
  border-left: 4px solid #1358e4;
}

.comment-badge {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 4px;
  margin-bottom: 10px;
}

.comment-badge.score-high { background: #e8f6ec; color: #16a34a; }
.comment-badge.score-mid { background: #fdf3e0; color: #b8810a; }
.comment-badge.score-low { background: #fdecec; color: #dc4446; }
.comment-badge.score-none { background: #f1f3f5; color: #8a9099; }

.comment-text {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  margin: 0;
}

/* 数据表格 */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 11px 14px;
  text-align: left;
  border-bottom: 1px solid var(--line);
}

.data-table th {
  color: var(--ink-3);
  font-weight: 600;
  background: #fafbfc;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover td {
  background: var(--brand-soft);
}

.data-table .tag {
  display: inline-block;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;
}

.data-table .ellipsis {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 词云：高频词图整体偏大，限制到约一半宽度并居中（第 5 项反馈） */
.word-cloud-wrap {
  width: 100%;
  max-width: 50%;
  margin: 0 auto;
  min-height: 160px;
  background: #fafafa;
  border-radius: 8px;
  padding: 12px;
  box-sizing: border-box;
}

/* 窄屏（单栏）下放宽到满宽，避免词云过小 */
@media (max-width: 768px) {
  .word-cloud-wrap {
    max-width: 100%;
  }
}

.word-cloud-svg {
  width: 100%;
  height: auto;
  display: block;
}

.word-cloud-text {
  cursor: default;
  transition: opacity 0.2s;
}

.word-cloud-text:hover {
  opacity: 0.6;
}

/* 思政卡片 */
.ideology-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ideology-card {
  background: var(--card-bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  padding: 22px 24px;
  box-shadow: var(--shadow-card);
}

.ideology-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.ideology-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.ideology-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  min-width: 0;
}

.ideology-seek-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(19, 88, 228, 0.1);
  color: #1358e4;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, transform 0.05s;
}

.ideology-seek-btn:hover {
  background: rgba(19, 88, 228, 0.18);
  color: #0f47c4;
}

.ideology-seek-btn:active {
  transform: scale(0.96);
}

.ideology-score-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 10px;
}

.ideology-score-badge.score-high { background: #e8f6ec; color: #16a34a; }
.ideology-score-badge.score-mid { background: #fdf3e0; color: #b8810a; }
.ideology-score-badge.score-low { background: #fdecec; color: #dc4446; }
.ideology-score-badge.score-none { background: #f1f3f5; color: #8a9099; }

.ideology-meta {
  font-size: 12px;
  color: #888;
  margin-bottom: 8px;
}

.ideology-desc {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  margin: 0;
}

.empty-text {
  color: #999;
  font-size: 14px;
  text-align: center;
  padding: 40px;
}

.empty-card {
  margin-top: 0;
}

/* ===== 教学表达 ===== */
.expression-header {
  margin-bottom: 16px;
}

.expression-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 4px;
  padding-left: 12px;
  border-left: 4px solid #1358e4;
}

.expression-subtitle {
  font-size: 13px;
  color: #888;
  margin: 0 0 0 16px;
}

.volume-card {
  margin-bottom: 16px;
}

.chart-scroll-wrap {
  overflow-x: auto;
  width: 100%;
}

.speech-rate-card .chart-scroll-wrap,
.volume-card .chart-scroll-wrap,
.density-card .chart-scroll-wrap {
  cursor: crosshair;
}

.scatter-card .chart-box {
  cursor: crosshair;
}

.speech-rate-card {
  margin-bottom: 16px;
}

.speech-rate-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
  flex-wrap: wrap;
}

.speech-rate-stat-text {
  font-size: 13px;
  color: #666;
}

.volume-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
  flex-wrap: wrap;
}

.volume-stat-text {
  font-size: 13px;
  color: #666;
}

.conciseness-card {
  padding: 20px;
}

.conciseness-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.conciseness-meta {
  font-size: 13px;
  color: #666;
}

.conciseness-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 768px) {
  .conciseness-body {
    grid-template-columns: 1fr;
  }
}

.conciseness-examples {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.example-group {
  background: #fafafa;
  border-radius: 8px;
  padding: 12px 16px;
  border-left: 3px solid #1358e4;
}

.example-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.example-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
  font-size: 13px;
  color: #555;
  line-height: 1.7;
}

.example-list li {
  margin: 6px 0;
  display: flex;
  gap: 8px;
}

.example-time {
  color: #1358e4;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
  font-size: 12px;
}

.example-text {
  color: #555;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ===== 教学设计 ===== */
.design-header {
  margin-bottom: 16px;
}

.design-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 4px;
  padding-left: 12px;
  border-left: 4px solid #1358e4;
}

.design-subtitle {
  font-size: 13px;
  color: #888;
  margin: 0 0 0 16px;
}

.analysis-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.analysis-card {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  border-left: 3px solid #1358e4;
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
.analysis-badge.score-none { background: #f1f3f5; color: #8a9099; }

.analysis-meta {
  font-size: 13px;
  color: #555;
  margin-bottom: 8px;
}

.meta-label {
  color: #888;
}

.analysis-desc {
  font-size: 14px;
  color: #333;
  line-height: 1.7;
  margin: 0 0 8px;
}

.analysis-eval {
  font-size: 13px;
  color: #666;
  line-height: 1.7;
  margin: 0;
}

.density-card {
  margin-bottom: 16px;
}

.segment-list-card {
  padding: 0;
  overflow: hidden;
}

.segment-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
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
}

.toggle-icon.open {
  transform: rotate(90deg);
}

.toggle-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.segment-table-wrap {
  padding: 0 20px 16px;
}

/* ===== 互动质量 ===== */
.interaction-header {
  margin-bottom: 16px;
}

.interaction-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 4px;
  padding-left: 12px;
  border-left: 4px solid #1358e4;
}

.interaction-subtitle {
  font-size: 13px;
  color: #888;
  margin: 0 0 0 16px;
}

.scatter-card {
  margin-bottom: 16px;
}

.interaction-summary {
  margin-top: 12px;
  font-size: 13px;
  color: #666;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
}

.type-stat-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.type-stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
}

.type-name {
  color: #444;
}

.type-count {
  color: #1358e4;
  font-weight: 600;
}

.event-list-card {
  padding: 0;
  overflow: hidden;
}

.event-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  cursor: pointer;
  background: #fff;
  transition: background 0.2s;
}

.event-toggle:hover {
  background: #f8f9fa;
}

.event-table-wrap {
  padding: 0 20px 16px;
}

/* ===== 通用标题区 ===== */
.section-header {
  margin-bottom: 16px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 4px;
  padding-left: 12px;
  border-left: 4px solid #1358e4;
}

.section-subtitle {
  font-size: 13px;
  color: #888;
  margin: 0 0 0 16px;
}

.ideology-eval {
  font-size: 13px;
  color: #666;
  line-height: 1.7;
  margin: 8px 0 0;
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

/* ===== 导出报告（打印为 PDF）===== */
/* 打印模式下展开全部 Tab：!important 覆盖 v-show 写入的 inline display:none */
.print-mode .tab-panel {
  display: block !important;
}
/* 同理展开默认折叠的明细表（环节列表 / 互动事件明细），确保全部内容进入 PDF */
.print-mode .segment-table-wrap,
.print-mode .event-table-wrap {
  display: block !important;
}
/* 滚动型图表占满页宽，避免横向滚动内容被裁切 */
.print-mode .chart-scroll-wrap {
  overflow: visible !important;
}
.print-mode .chart-box-scroll {
  width: 100% !important;
}

@media print {
  .v2-report-page {
    background: #fff !important;
    padding: 0 !important;
    /* 收起屏幕态 1200px 限宽，按页宽排版，避免内容/图表超出 A4 右边界被裁切 */
    max-width: 100% !important;
    width: 100% !important;
  }
  /* 多列网格在窄页改为单列，图表获得整页宽度、更清晰 */
  .panel-grid {
    grid-template-columns: 1fr !important;
  }
  /* 长表格允许跨页：整段不拆 → 改为按行分页并重复表头，避免被页边裁断 */
  .segment-list-card,
  .event-list-card,
  .data-table {
    break-inside: auto;
  }
  .data-table thead {
    display: table-header-group;
  }
  .data-table tr {
    break-inside: avoid;
  }
  /* 仅保留报告内容：隐藏返回按钮、顶栏操作、Tab 栏、视频播放器、明细折叠开关。
     综合得分已随新 UI 移到总览 Tab 的雷达卡片（.overall-hero），打印时随总览页保留，
     故顶栏右侧操作可整体隐藏（旧 :not(.overall-box) 例外已无对应元素）。 */
  .report-back-btn,
  .header-right > *,
  .tab-bar,
  .video-player-card,
  .segment-toggle,
  .event-toggle,
  .ideology-seek-btn {
    display: none !important;
  }
  /* 每个维度 Tab 另起一页；总览在首页 */
  .tab-panel {
    page-break-before: always;
    break-before: page;
  }
  .tab-panel.overview-tab-panel {
    page-break-before: avoid;
    break-before: auto;
  }
  /* 卡片尽量不跨页拆分 */
  .panel-card {
    break-inside: avoid;
    box-shadow: none !important;
    border: 1px solid #e5e7eb !important;
  }
  /* 保留图表/进度条/标签等背景色 */
  .v2-report-page,
  .v2-report-page * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
}
</style>

<!-- 非 scoped：仅在本页导出（body.report-print-active）且打印时隐藏全局导航等外层内容 -->
<style>
@media print {
  @page {
    size: A4 portrait;
    margin: 12mm;
  }
  body.report-print-active nav.navbar,
  body.report-print-active .back-to-top {
    display: none !important;
  }
  body.report-print-active {
    background: #fff !important;
  }
}
</style>
