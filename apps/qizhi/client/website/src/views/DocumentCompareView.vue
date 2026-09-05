<template>
  <div class="doc-compare-view core-app-page core-app-page--flow">
    <div class="toolbar">
      <div class="toolbar-left">
        <router-link to="/document-analysis" class="back-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回分析</span>
        </router-link>
        <h2 class="page-title">文档横向对比</h2>
      </div>
    </div>

    <div class="content-area">
      <!-- 选择阶段 -->
      <div v-if="viewPhase === 'select'" class="select-phase">
        <div class="panel-card">
          <div class="select-header">
            <h3 class="section-title">选择分析结果进行对比</h3>
            <p class="select-hint">请选择 2 ~ 4 项分析结果</p>
          </div>

          <div v-if="history.length === 0" class="empty-history">
            <p>暂无历史分析记录</p>
            <p class="empty-sub">完成文档分析后，结果会自动保存到此处</p>
          </div>

          <div v-else class="history-list">
            <label
              v-for="(entry, idx) in history"
              :key="idx"
              class="history-item"
              :class="{ 'is-selected': selectedIndices.has(idx) }"
            >
              <input
                type="checkbox"
                :checked="selectedIndices.has(idx)"
                :disabled="!selectedIndices.has(idx) && selectedIndices.size >= 4"
                @change="toggleSelection(idx)"
              />
              <div class="item-info">
                <span class="item-name">{{ entry.file_name }}</span>
                <span class="item-score" :class="scoreClass(entry.overall_score)">
                  {{ entry.overall_score }}分
                </span>
              </div>
              <span class="item-time">{{ formatTime(entry.create_time) }}</span>
              <button type="button" class="item-delete" title="删除" @click.prevent.stop="handleRemove(idx)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </button>
            </label>
          </div>

          <div class="select-actions">
            <button
              type="button"
              class="action-btn secondary"
              :disabled="history.length === 0"
              @click="handleClearAll"
            >
              清空历史
            </button>
            <button
              type="button"
              class="action-btn primary"
              :disabled="selectedIndices.size < 2"
              @click="startCompare"
            >
              开始对比（{{ selectedIndices.size }}）
            </button>
          </div>
        </div>
      </div>

      <!-- 对比阶段 -->
      <div v-else class="compare-phase">
        <div class="compare-toolbar">
          <button type="button" class="action-btn secondary" @click="backToSelect">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="margin-right: 4px;">
              <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            重新选择
          </button>
        </div>

        <!-- 总分对比 -->
        <div class="panel-card">
          <h3 class="section-title">总分对比</h3>
          <div class="overall-row">
            <div
              v-for="(item, idx) in compareItems"
              :key="idx"
              class="overall-item"
            >
              <div class="overall-color" :style="{ background: COLORS[idx] }" />
              <span class="overall-name">{{ item.result.file_name }}</span>
              <span class="overall-score" :class="scoreClass(item.result.overall_score)">
                {{ item.result.overall_score }}
              </span>
            </div>
          </div>
        </div>

        <!-- 雷达图对比 -->
        <div class="panel-card">
          <h3 class="section-title">多维度雷达对比</h3>
          <div ref="radarChartRef" class="chart-box" style="height: 400px;" />
        </div>

        <!-- 维度得分表 -->
        <div class="panel-card">
          <h3 class="section-title">维度得分对比</h3>
          <div class="compare-table-wrap">
            <table class="compare-table">
              <thead>
                <tr>
                  <th class="dim-col">维度</th>
                  <th
                    v-for="(item, idx) in compareItems"
                    :key="idx"
                    class="score-col"
                  >
                    <span class="th-color" :style="{ background: COLORS[idx] }" />
                    {{ item.result.file_name }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="dim in allDimensions" :key="dim">
                  <td class="dim-col">{{ dim }}</td>
                  <td
                    v-for="(item, idx) in compareItems"
                    :key="idx"
                    class="score-col"
                    :class="scoreClass(getDimScore(item, dim))"
                  >
                    {{ getDimScore(item, dim) }}
                  </td>
                </tr>
                <tr class="total-row">
                  <td class="dim-col"><strong>总分</strong></td>
                  <td
                    v-for="(item, idx) in compareItems"
                    :key="idx"
                    class="score-col"
                    :class="scoreClass(item.result.overall_score)"
                  >
                    <strong>{{ item.result.overall_score }}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { listDocumentHistory, getDocumentDetail, deleteDocumentRecord } from '../api/document'
import type { DocHistoryItem, DocumentAnalysisResult } from '../api/document'

interface CompareItem {
  id: string
  result: DocumentAnalysisResult
  timestamp: string
}

const COLORS = ['#1358e4', '#38a169', '#d69e2e', '#e53e3e']

type ViewPhase = 'select' | 'compare'
const viewPhase = ref<ViewPhase>('select')

const history = ref<DocHistoryItem[]>([])
const selectedIndices = ref<Set<number>>(new Set())
const compareItems = ref<CompareItem[]>([])

const radarChartRef = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null

onMounted(async () => {
  try {
    history.value = await listDocumentHistory()
  } catch {
    history.value = []
  }
})

/** All unique dimension names across selected items */
const allDimensions = computed<string[]>(() => {
  const dims = new Set<string>()
  for (const item of compareItems.value) {
    for (const d of item.result.dimension_scores) {
      dims.add(d.dimension)
    }
  }
  return Array.from(dims)
})

function scoreClass(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function toggleSelection(idx: number) {
  const s = new Set(selectedIndices.value)
  if (s.has(idx)) {
    s.delete(idx)
  } else if (s.size < 4) {
    s.add(idx)
  }
  selectedIndices.value = s
}

async function handleRemove(idx: number) {
  const item = history.value[idx]
  if (!item) return
  try {
    await deleteDocumentRecord(item.id)
    history.value.splice(idx, 1)
  } catch {
    // ignore
  }
  selectedIndices.value = new Set()
}

async function handleClearAll() {
  if (!confirm('确定清空所有历史记录？')) return
  await Promise.all(history.value.map((h) => deleteDocumentRecord(h.id).catch(() => {})))
  history.value = []
  selectedIndices.value = new Set()
}

async function startCompare() {
  const sorted = Array.from(selectedIndices.value).sort((a, b) => a - b)
  const selectedHistory = sorted
    .map((index) => history.value[index])
    .filter((item): item is DocHistoryItem => item !== undefined)

  if (selectedHistory.length < 2) {
    selectedIndices.value = new Set()
    return
  }

  const details = await Promise.all(
    selectedHistory.map(async (h) => {
      const result = await getDocumentDetail(h.id)
      return { id: h.id, result, timestamp: h.create_time }
    }),
  )
  compareItems.value = details
  viewPhase.value = 'compare'
  await nextTick()
  initRadarChart()
}

function backToSelect() {
  viewPhase.value = 'select'
  compareItems.value = []
  radarChart?.dispose()
  radarChart = null
}

function getDimScore(entry: CompareItem, dimName: string): number {
  const found = entry.result.dimension_scores.find((d) => d.dimension === dimName)
  return found?.score ?? 0
}

function initRadarChart() {
  if (!radarChartRef.value || compareItems.value.length === 0) return

  // Use radar_data from the first item to define indicators, fallback to dimension_scores
  const firstItem = compareItems.value[0]
  if (!firstItem) return

  radarChart = echarts.init(radarChartRef.value)
  const radarData = firstItem.result.radar_data
  const indicator =
    radarData && radarData.length
      ? radarData.map((d) => ({ name: d.dimension, max: d.fullScore || 100 }))
      : allDimensions.value.map((name) => ({ name, max: 100 }))

  const series = compareItems.value.map((item, idx) => {
    const values =
      radarData && radarData.length
        ? radarData.map((rd) => {
            const found = item.result.radar_data?.find((d) => d.dimension === rd.dimension)
            if (found) return found.score
            const fallback = item.result.dimension_scores.find((d) => d.dimension === rd.dimension)
            return fallback?.score ?? 0
          })
        : allDimensions.value.map((dim) => getDimScore(item, dim))

    return {
      value: values,
      name: item.result.file_name,
      lineStyle: { color: COLORS[idx], width: 2 },
      areaStyle: { color: COLORS[idx], opacity: 0.08 },
      itemStyle: { color: COLORS[idx] },
    }
  })

  radarChart.setOption(
    {
      tooltip: {},
      legend: {
        data: compareItems.value.map((item) => item.result.file_name),
        bottom: 0,
        textStyle: { fontSize: 12 },
      },
      radar: {
        indicator,
        radius: '60%',
        axisName: { color: '#666', fontSize: 12 },
      },
      series: [
        {
          type: 'radar',
          data: series,
        },
      ],
    },
    true,
  )
}

function handleResize() {
  radarChart?.resize()
}

window.addEventListener('resize', handleResize)
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  radarChart?.dispose()
})
</script>

<style scoped>
.doc-compare-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
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

.content-area {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Panel card (matches DocumentAnalysisView) */
.panel-card {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #1a1a1a;
}

/* Select phase */
.select-header {
  margin-bottom: 16px;
}
.select-hint {
  font-size: 13px;
  color: #999;
  margin-top: 4px;
}

.empty-history {
  text-align: center;
  padding: 32px 0;
  color: #999;
  font-size: 14px;
}
.empty-sub {
  font-size: 13px;
  margin-top: 4px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.history-item:hover {
  background: #fafafa;
}
.history-item.is-selected {
  border-color: #1358e4;
  background: #f0f4ff;
}
.history-item input[type="checkbox"] {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  accent-color: #1358e4;
  cursor: pointer;
}

.item-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.item-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-score {
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.item-score.score-high { color: #38a169; }
.item-score.score-mid { color: #d69e2e; }
.item-score.score-low { color: #e53e3e; }

.item-time {
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
}
.item-delete {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #bbb;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.item-delete:hover {
  background: #fee;
  color: #e53e3e;
}

.select-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

/* Buttons (matching DocumentAnalysisView) */
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
.action-btn.secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Compare phase */
.compare-toolbar {
  margin-bottom: 4px;
}

/* Overall scores row */
.overall-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
.overall-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #fafafa;
  border-radius: 10px;
  flex: 1;
  min-width: 180px;
}
.overall-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}
.overall-name {
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.overall-score {
  font-size: 20px;
  font-weight: 700;
  flex-shrink: 0;
}
.overall-score.score-high { color: #38a169; }
.overall-score.score-mid { color: #d69e2e; }
.overall-score.score-low { color: #e53e3e; }

/* Radar chart */
.chart-box {
  width: 100%;
}

/* Comparison table */
.compare-table-wrap {
  overflow-x: auto;
}
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.compare-table th,
.compare-table td {
  padding: 10px 14px;
  text-align: center;
  border-bottom: 1px solid #f0f0f0;
}
.compare-table th {
  background: #f8f9fb;
  font-weight: 500;
  color: #555;
  white-space: nowrap;
}
.compare-table .dim-col {
  text-align: left;
  font-weight: 500;
  color: #333;
  min-width: 100px;
}
.compare-table .score-col {
  min-width: 80px;
}
.compare-table .score-col.score-high { color: #38a169; }
.compare-table .score-col.score-mid { color: #d69e2e; }
.compare-table .score-col.score-low { color: #e53e3e; }
.compare-table .total-row td {
  border-top: 2px solid #e0e0e0;
  border-bottom: none;
  background: #f8f9fb;
}

.th-color {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
}

@media (max-width: 640px) {
  .overall-row {
    flex-direction: column;
  }
  .overall-item {
    min-width: 0;
  }
}
</style>
