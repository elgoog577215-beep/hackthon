<template>
  <div class="resource-analysis-report-view">
    <div class="report-content">
    <div class="top-bar">
      <div class="left-section">
        <router-link to="/resource-analysis" class="back-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </router-link>
        <h2 class="file-name">{{ pageTitle }}</h2>
      </div>
      <div
        v-if="detail?.type === 'video'"
        class="right-section"
      >
        <button
          type="button"
          class="action-btn"
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

    <div class="content-area" :class="{ 'content-area-video': detail?.type === 'video' }">
      <div v-if="loading" class="loading-container">
        <p>加载中...</p>
      </div>
      <div v-else-if="!detail" class="error-container">
        <p>未找到该分析报告</p>
        <router-link to="/resource-analysis" class="retry-btn">返回列表</router-link>
      </div>
      <template v-else>
        <!-- 视频报告：原视频 + 分析结果 -->
        <template v-if="detail.type === 'video'">
          <!-- 状态提示：报告未找到或分析未完成 -->
          <section v-if="reportNotFound" class="status-banner status-banner-warn">
            <div class="status-banner-inner">
              <span class="status-banner-icon">⚠️</span>
              <div class="status-banner-text">
                <strong>未找到该分析报告</strong>
                <p class="status-banner-desc">以下为视频预览，您可在此查看或等待后续维护接口上线后管理该任务。</p>
              </div>
            </div>
          </section>
          <section v-else-if="isVideoNotCompleted" class="status-banner">
            <div class="status-banner-inner">
              <span class="status-banner-icon">⏳</span>
              <div class="status-banner-text">
                <strong>{{ videoStatusLabel }}</strong>
                <p class="status-banner-desc">{{ videoStatusBannerDesc }}</p>
              </div>
            </div>
          </section>

          <div class="video-report-body">
            <div class="report-section-panel">
            <div class="video-report-grid">
            <div class="video-report-col">
            <!-- 视频部分：始终显示，不受分析状态影响 -->
            <div class="report-card video-card">
              <h4 class="report-subtitle">原视频</h4>
              <div class="video-wrapper">
              <div v-if="!detail.data.videoUrl" class="video-placeholder">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                  <path d="M10 9l5 3-5 3V9z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <p>视频播放区</p>
              </div>
              <div v-else class="video-player-wrap">
                <div v-if="videoLoading" class="video-loading">正在加载视频...</div>
                <div v-else-if="videoError" class="video-error">视频加载失败，请稍后重试</div>
                <video
                  v-else
                  ref="videoPlayerRef"
                  :src="videoPlayableSrc || detail.data.videoUrl"
                  controls
                  class="video-player"
                  @error="onVideoTagError"
                  @timeupdate="onVideoTimeUpdate"
                  @loadedmetadata="onVideoTimeUpdate"
                />
              </div>
            </div>
            <div class="video-meta">
              <span>{{ detail.data.courseName }}</span>
              <span>{{ detail.data.teacherName }}</span>
              <span v-if="detail.data.college">{{ detail.data.college }}</span>
            </div>

            <div
              v-if="!isVideoNotCompleted && hasVolumeChart"
              class="video-volume-block"
            >
              <div class="volume-chart-container volume-chart-container--under-video">
                <div class="volume-chart-header">
                  <span class="volume-chart-title">音量变化趋势 (dB)</span>
                </div>
                <VolumeChart
                  :data="volumeData"
                  :duration-sec="videoDurationSec"
                  :progress-percent="videoPlayProgressPercent"
                  @seek="onVolumeSeek"
                />
              </div>
            </div>
            </div>

            <template v-if="showVideoReportBottom && detail.data.report">
              <div class="report-card teach-expr-card">
                <div class="report-card-header">
                  <h4 class="report-card-title">教学表达分析</h4>
                  <div class="report-card-header-extra">
                    <span v-if="teachingExpressionScore != null" class="report-card-score">{{ formatRadarScore(teachingExpressionScore) }} 分</span>
                  </div>
                </div>
                <div class="report-card-body">
                  <p v-if="hasVolumeChart" class="report-text report-text-secondary volume-moved-hint">
                    音量变化曲线已移至上方视频播放区下方，可与播放进度对照查看。
                  </p>
                  <template v-if="hasVolumeChart && getStr(detail.data.report?.teach_db_result, 'suggestion')">
                    <p class="report-text report-text-secondary">{{ getStr(detail.data.report?.teach_db_result, 'suggestion') }}</p>
                  </template>
                  <template v-else-if="hasData(detail.data.report?.teach_db_result) && !hasVolumeChart">
                    <p v-if="getStr(detail.data.report.teach_db_result, 'speed')" class="report-text">{{ getStr(detail.data.report.teach_db_result, 'speed') }}</p>
                    <p v-if="getStr(detail.data.report.teach_db_result, 'volume')" class="report-text">{{ getStr(detail.data.report.teach_db_result, 'volume') }}</p>
                    <p v-if="getStr(detail.data.report.teach_db_result, 'suggestion')" class="report-text report-text-secondary">{{ getStr(detail.data.report.teach_db_result, 'suggestion') }}</p>
                    <template v-if="!getStr(detail.data.report.teach_db_result, 'speed') && !getStr(detail.data.report.teach_db_result, 'volume')">
                      <pre class="report-json">{{ formatSection(detail.data.report.teach_db_result) }}</pre>
                    </template>
                  </template>
                  <div v-else class="empty-state">暂无数据</div>
                </div>
              </div>

              <div class="report-card interaction-card">
                <div class="report-card-header">
                  <h4 class="report-card-title">质量互动与深度</h4>
                  <div class="report-card-header-extra">
                    <span v-if="interactionQualityScore != null" class="report-card-score">{{ formatRadarScore(interactionQualityScore) }} 分</span>
                  </div>
                </div>
                <div class="report-card-body">
                  <div class="wh-card-layout">
                    <DonutChart
                      v-if="teachWhSlices"
                      :slices="teachWhSlices"
                      aria-label="五何互动占比环形图"
                    />
                    <div v-else class="empty-state empty-state-chart">暂无数据</div>
                  </div>
                  <div v-if="teachQuestionTypeStats?.length" class="question-type-stats">
                    <p class="report-text report-text-secondary">提问类型分布</p>
                    <div class="question-type-grid">
                      <span v-for="item in teachQuestionTypeStats" :key="item.type" class="question-type-tag">
                        {{ item.type }} {{ item.count }} 次
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            </div>

            <div v-if="hasVideoReportSideCol" class="video-report-col">
            <div v-if="!isVideoNotCompleted && hasVideoRadarChart" class="report-card radar-card">
              <div class="report-card-header">
                <h4 class="report-card-title">整体评估预览</h4>
                <div class="report-card-header-extra">
                  <span v-if="overallRadarScore != null" class="report-card-score">{{ formatRadarScore(overallRadarScore) }} 分</span>
                </div>
              </div>
              <div class="report-card-body radar-card-body">
                <RadarChart :labels="radarLabels" :values="radarValues" />
              </div>
            </div>

            <template v-if="showVideoReportBottom && detail.data.report">
              <div class="report-card teach-structure-card">
                <div class="report-card-header">
                  <h4 class="report-card-title">教学结构设计</h4>
                  <div class="report-card-header-extra">
                    <span v-if="teachingStructureScore != null" class="report-card-score">{{ formatRadarScore(teachingStructureScore) }} 分</span>
                    <button
                      v-if="shouldShowTeachSummaryToggle"
                      class="transcript-toggle-btn"
                      @click="toggleTeachSummary"
                    >
                      {{ isTeachSummaryCollapsed ? '展开全部' : '收起' }}
                      <span class="toggle-icon" :class="{ 'is-expanded': !isTeachSummaryCollapsed }">▼</span>
                    </button>
                  </div>
                </div>
                <div class="report-card-body">
                  <template v-if="teachSummarySections.length > 0">
                    <div class="teach-summary-list" :class="{ 'is-collapsed': isTeachSummaryCollapsed }">
                      <div v-for="(section, sIdx) in displayedTeachSummarySections" :key="sIdx" class="teach-section">
                        <div v-if="section.summary" class="teach-summary-text">{{ section.summary }}</div>
                        <div v-if="section.fileStructure && section.fileStructure.length > 0" class="teach-timeline">
                          <div v-for="(item, iIdx) in section.fileStructure" :key="iIdx" class="timeline-item">
                            <div class="timeline-marker">
                              <span class="timeline-dot"></span>
                              <span v-if="iIdx !== section.fileStructure.length - 1" class="timeline-line"></span>
                            </div>
                            <div class="timeline-content">
                              <div class="timeline-header">
                                <span class="timeline-type">{{ item.type }}</span>
                                <span class="timeline-time">{{ item.start_time }} - {{ item.end_time }}</span>
                              </div>
                              <div class="timeline-body">
                                <p class="timeline-desc">{{ item.content }}</p>
                                <div v-if="item.keypoint" class="timeline-keypoint">
                                  <span class="keypoint-label">关键点：</span>
                                  <span class="keypoint-text">{{ item.keypoint }}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-if="isTeachSummaryCollapsed && shouldShowTeachSummaryToggle" class="transcript-fade" />
                  </template>
                  <template v-else-if="hasData(detail.data.report?.teach_summary)">
                    <p v-if="getStr(detail.data.report.teach_summary, 'text')" class="report-text">{{ getStr(detail.data.report.teach_summary, 'text') }}</p>
                    <p v-if="getStr(detail.data.report.teach_summary, 'rhythm')" class="report-text report-text-secondary">{{ getStr(detail.data.report.teach_summary, 'rhythm') }}</p>
                    <template v-else-if="!getStr(detail.data.report.teach_summary, 'text') && !getStr(detail.data.report.teach_summary, 'rhythm')">
                      <pre class="report-json">{{ formatSection(detail.data.report.teach_summary) }}</pre>
                    </template>
                  </template>
                  <div v-else-if="!teachPhaseSlices" class="empty-state">暂无数据</div>
                  <div class="wh-card-layout">
                    <DonutChart
                      v-if="teachPhaseSlices"
                      :slices="teachPhaseSlices"
                      aria-label="课堂环节占比环形图"
                    />
                  </div>
                </div>
              </div>

              <div class="report-card word-cloud-card">
                <div class="report-card-header">
                  <h4 class="report-card-title">知识呈现与结构</h4>
                  <div class="report-card-header-extra">
                    <span v-if="knowledgePresentationScore != null" class="report-card-score">{{ formatRadarScore(knowledgePresentationScore) }} 分</span>
                  </div>
                </div>
                <div class="report-card-body">
                  <WordCloudChart v-if="knowledgeHotWords.length" :words="knowledgeHotWords" />
                  <div v-else class="empty-state empty-state-square">暂无数据</div>
                </div>
              </div>

              <div class="report-card ideology-card">
                <div class="report-card-header">
                  <h4 class="report-card-title">思政元素融合度</h4>
                  <div class="report-card-header-extra">
                    <span v-if="ideologyIntegrationScore != null" class="report-card-score">{{ formatRadarScore(ideologyIntegrationScore) }} 分</span>
                  </div>
                </div>
                <div class="report-card-body">
                  <template v-if="ideologySummaryItems.length">
                    <div v-for="(item, idx) in ideologySummaryItems" :key="idx" class="ideology-item">
                      <div class="ideology-item-header">
                        <span class="ideology-item-title">{{ item.title }}</span>
                        <span v-if="item.timeRange" class="ideology-item-time">{{ item.timeRange }}</span>
                      </div>
                      <p class="report-text">{{ item.content }}</p>
                    </div>
                  </template>
                  <template v-else-if="ideologySummaryText">
                    <p class="report-text">{{ ideologySummaryText }}</p>
                  </template>
                  <div v-else class="empty-state">暂无数据</div>
                </div>
              </div>
            </template>
            </div>
            </div>
            </div>

          <!-- 相关视频推荐：已隐藏 -->
          <section v-if="false" class="related-section">
            <h3 class="section-title">推荐视频</h3>
            <div class="related-grid">
              <router-link
                v-for="item in relatedVideos.slice(0, 8)"
                :key="item.id"
                :to="`/resource-analysis/report/${item.id}`"
                class="related-tab"
              >
                <div class="related-tab-cover-wrap">
                  <div class="related-tab-cover">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                      <path d="M10 9l5 3-5 3V9z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                </div>
                <div class="related-tab-content">
                  <div class="related-tab-title">{{ item.title }}</div>
                  <div class="related-tab-subtitle">{{ item.subTitle }}</div>
                  <div class="related-tab-radar-summary">
                    <div class="related-tab-radar" aria-hidden="true">
                      <svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
                        <polygon points="60,12 102,36 102,84 60,108 18,84 18,36" fill="rgba(19,88,228,0.12)" stroke="rgba(19,88,228,0.35)" />
                        <polygon points="60,28 88,44 88,76 60,92 32,76 32,44" fill="rgba(19,88,228,0.2)" stroke="rgba(19,88,228,0.5)" />
                      </svg>
                    </div>
                    <p class="related-tab-summary">{{ recommendedSummaryText(item.title) }}</p>
                  </div>
                </div>
              </router-link>
            </div>
          </section>
          </div>
        </template>

        <!-- 文本/PPT 报告：仅分析结果 -->
        <template v-else>
          <section class="report-section">
            <h3 class="section-title">雷达图</h3>
            <div class="report-card">
              <div class="report-card-header">
                <h4 class="report-card-title">总体评价</h4>
                <div class="report-card-header-extra"></div>
              </div>
              <div class="report-card-body">
                <p class="report-text">{{ detail.data.report.summary }}</p>
              </div>
            </div>
            <div v-if="detail.data.report.teachingRhythm" class="report-card">
              <div class="report-card-header">
                <h4 class="report-card-title">内容节奏</h4>
                <div class="report-card-header-extra"></div>
              </div>
              <div class="report-card-body">
                <p class="report-text">{{ detail.data.report.teachingRhythm }}</p>
              </div>
            </div>
            <div v-if="detail.data.report.interaction" class="report-card">
              <div class="report-card-header">
                <h4 class="report-card-title">可读性与结构</h4>
                <div class="report-card-header-extra"></div>
              </div>
              <div class="report-card-body">
                <p class="report-text">{{ detail.data.report.interaction }}</p>
              </div>
            </div>
            <div v-if="detail.data.report.boardDesign" class="report-card">
              <div class="report-card-header">
                <h4 class="report-card-title">结构设计</h4>
                <div class="report-card-header-extra"></div>
              </div>
              <div class="report-card-body">
                <p class="report-text">{{ detail.data.report.boardDesign }}</p>
              </div>
            </div>
            <div v-if="detail.data.report.suggestions?.length" class="report-card">
              <div class="report-card-header">
                <h4 class="report-card-title">改进建议</h4>
                <div class="report-card-header-extra"></div>
              </div>
              <div class="report-card-body">
                <ul class="report-list">
                  <li v-for="(item, i) in detail.data.report.suggestions" :key="i">{{ item }}</li>
                </ul>
              </div>
            </div>
          </section>
          <p class="mock-tip"></p>
        </template>
      </template>
    </div>
    </div>
  </div>

  <!-- 重命名弹窗 -->
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
        <p v-if="renameError" class="rename-error">操作失败，请稍后重试</p>
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
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import { getMockAnalysisReport, isVideoTaskId } from '../api/resourceAnalysis'
import {
  getVideoTaskDetail,
  isVideoTaskPollingActive,
  operateVideo,
  resolveVideoMediaUrl,
  startVideoAnalysis,
  exportVideoAnalysisReport,
  downloadBlobAsFile,
  removeRegisteredVideoTask,
} from '../api/video'
import { OperationEnum } from '../api/types'
import type { VideoTaskDetail } from '../api/video'
import type { MockAnalysisReport } from '../api/resourceAnalysis'
import { notifyResourceAnalysisListRefresh } from '../api/resourceAnalysis'
import { buildAuthorizationHeader } from '../api/authToken'
import ConfirmDialogModal from '../components/ConfirmDialogModal.vue'
import DeleteConfirmModal from '../components/DeleteConfirmModal.vue'
import MoreOptionsMenu from '../components/MoreOptionsMenu.vue'
import RadarChart from '../components/charts/RadarChart.vue'
import DonutChart from '../components/charts/DonutChart.vue'
import type { DonutSlice } from '../components/charts/DonutChart.vue'
import WordCloudChart from '../components/charts/WordCloudChart.vue'
import VolumeChart from '../components/charts/VolumeChart.vue'
import {
  tryParseJsonLike,
  asAnalysisReportRecord,
  extractTranscriptSegments,
  formatSec,
  parseTimeToSeconds,
  formatSection,
  hasData,
  getStr,
  getArr,
  getNum,
  parseTeachSummary,
  parseKnowledgeTree,
  parseKnowledgeGraph,
  parseVolumeData,
  parseRadarChartInput,
  collectKnowledgeTitles,
  isNonEmptyReportRecord,
  formatRadarScore,
} from '../lib/reportParsers'
import type {
  KnowledgeNode,
  KnowledgeGraphNodeData,
  TranscriptSegment,
  TeachSection,
  TeachSegment,
} from '../lib/reportParsers'

/** 路由 `props: true` 注入的 `:id`；声明后可消除多根组件下的 extraneous attrs 警告 */
const props = defineProps<{ id?: string }>()

type ReportDetail =
  | { type: 'video'; data: VideoTaskDetail }
  | { type: 'generic'; data: { name: string; report: MockAnalysisReport } }

// 知识点树递归组件
const KnowledgeTreeNode = {
  name: 'KnowledgeTreeNode',
  props: {
    node: {
      type: Object as () => KnowledgeNode,
      required: true
    }
  },
  setup(props: { node: KnowledgeNode }) {
    const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
    const isLeaf = computed(() => !hasChildren.value)
    return { hasChildren, isLeaf }
  },
  template: `
    <div class="knowledge-node" :class="{ 'is-leaf': isLeaf, 'is-root': node.level === 0 }">
      <div class="knowledge-node-content">
        <div class="knowledge-node-marker">
          <span class="knowledge-node-icon">{{ isLeaf ? '•' : '▸' }}</span>
          <span v-if="hasChildren" class="knowledge-node-branch"></span>
        </div>
        <div class="knowledge-node-body">
          <div class="knowledge-node-title">{{ node.title }}</div>
          <div v-if="node.start_time && node.end_time" class="knowledge-node-time">
            {{ node.start_time }} - {{ node.end_time }}
          </div>
        </div>
      </div>
      <div v-if="hasChildren" class="knowledge-node-children">
        <KnowledgeTreeNode
          v-for="(child, idx) in node.children"
          :key="idx"
          :node="child"
        />
      </div>
    </div>
  `
}

// 知识图谱递归组件（带展开/收起功能）
const KnowledgeGraphNodeComp = {
  name: 'KnowledgeGraphNodeComp',
  props: {
    node: {
      type: Object as () => KnowledgeGraphNodeData,
      required: true
    }
  },
  setup(props: { node: KnowledgeGraphNodeData }) {
    const isExpanded = ref(true)
    const showDetails = ref(false)
    const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
    const hasDetails = computed(() => !!props.node.details)
    const isLeaf = computed(() => !hasChildren.value)

    const toggleExpand = () => { isExpanded.value = !isExpanded.value }
    const toggleDetails = () => { showDetails.value = !showDetails.value }

    return { isExpanded, showDetails, hasChildren, hasDetails, isLeaf, toggleExpand, toggleDetails }
  },
  template: `
    <div class="graph-node" :class="{ 'is-leaf': isLeaf, 'is-root': node.level === 0 }">
      <div class="graph-node-content">
        <div class="graph-node-left">
          <button v-if="hasChildren" class="graph-expand-btn" @click="toggleExpand">
            <span class="expand-icon" :class="{ 'is-expanded': isExpanded }">▸</span>
          </button>
          <span v-else class="graph-leaf-dot">•</span>
        </div>
        <div class="graph-node-body">
          <div class="graph-node-header">
            <span class="graph-node-title">{{ node.word }}</span>
            <div class="graph-node-meta">
              <span v-if="node.time_range" class="graph-node-time">
                {{ node.time_range.start }} - {{ node.time_range.end }}
              </span>
              <button v-if="hasDetails" class="graph-details-btn" @click="toggleDetails">
                {{ showDetails ? '收起' : '详情' }}
              </button>
            </div>
          </div>
          <div v-if="showDetails && hasDetails" class="graph-node-details">
            {{ node.details }}
          </div>
        </div>
      </div>
      <div v-if="hasChildren && isExpanded" class="graph-node-children">
        <KnowledgeGraphNodeComp
          v-for="(child, idx) in node.children"
          :key="idx"
          :node="child"
        />
      </div>
    </div>
  `
}

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const detail = ref<ReportDetail | null>(null)
/** 视频报告：有详情但缺少可展示的分析报告区块时提示（由业务逻辑置位） */
const reportNotFound = ref(false)
const videoPlayableSrc = ref<string | null>(null)
const videoLoading = ref(false)
const videoError = ref<string | null>(null)
const videoTriedBlobFallback = ref(false)
/** 原视频播放器，供转写时间戳跳转 */
const videoPlayerRef = ref<HTMLVideoElement | null>(null)

/** 从转写片段起始时间（秒）跳转播放 */
function seekVideoToSegmentStart(startSec: number) {
  if (!Number.isFinite(startSec)) return
  const el = videoPlayerRef.value
  if (!el) return
  const t = Math.max(0, startSec)
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
    // 浏览器可能因未用户手势拦截自动播放，用户已点击按钮通常可播；忽略静默失败
  })
}

// 视频任务：重命名 / 删除
const currentVideoId = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return null
  return detail.value.data.id
})
const showMoreOptions = ref(false)
const showRenameModal = ref(false)
const renameInput = ref('')
const renameError = ref('')
const renaming = ref(false)
const deleting = ref(false)
const startingAnalysis = ref(false)
const exportingReport = ref(false)

const showStartAnalysisErrorModal = ref(false)
const showExportPendingModal = ref(false)
const showLeaveAnalysisModal = ref(false)
const pendingLeaveRoute = ref<RouteLocationNormalized | null>(null)
/** 用户已确认直接离开，放行下一次路由跳转，避免守卫重复弹窗 */
const skipUnstartedLeavePrompt = ref(false)
const exportPendingMessage = ref('')
const startAnalysisErrorMessage = ref('')
const showDeleteVideoModal = ref(false)
const deleteVideoEntityName = computed(() => {
  if (detail.value?.type === 'video') {
    const n = (detail.value.data.videoName || '').trim()
    return n || '该视频'
  }
  return '该视频'
})

const canStartAnalysis = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  const s = detail.value.data.status
  // 仅在「待启动 / 失败」时允许手动启动；其余状态视为进行中或已完成
  if (s !== 'unstarted' && s !== 'failed') return false
  return Boolean(currentVideoId.value)
})

const shouldPromptLeaveForUnstarted = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  return detail.value.data.status === 'unstarted'
})

/** 分析完成（success）后方可导出 */
const canExportReport = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  return detail.value.data.status === 'success' && Boolean(currentVideoId.value)
})

const exportReportButtonTitle = computed(() => {
  if (canExportReport.value) return '下载分析报告到本地'
  if (!detail.value || detail.value.type !== 'video') return ''
  const s = detail.value.data.status
  if (s === 'failed') return '分析失败，无法导出'
  if (s === 'waiting') return '分析进行中，完成后可导出'
  if (s === 'unstarted') return '请先开始分析，完成后可导出'
  return '分析完成后可导出'
})

async function handleStartAnalysis() {
  const id = currentVideoId.value
  if (!id) return
  if (!canStartAnalysis.value) return
  startingAnalysis.value = true
  try {
    await startVideoAnalysis(id)
    await loadDetail()
    if (shouldPollDetail()) startDetailPolling()
  } catch (e) {
    const msg = e instanceof Error ? e.message : '启动分析失败'
    startAnalysisErrorMessage.value = msg
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

function buildExportFilename(): string {
  const base =
    detail.value?.type === 'video'
      ? (detail.value.data.videoName || '视频分析报告').trim()
      : '视频分析报告'
  const safe = base.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
  return `${safe || '视频分析报告'}.docx`
}

async function handleExportReport() {
  const id = currentVideoId.value
  if (!id || !canExportReport.value) return
  exportingReport.value = true
  try {
    const blob = await exportVideoAnalysisReport(id)
    downloadBlobAsFile(blob, buildExportFilename())
  } catch (e) {
    exportPendingMessage.value =
      e instanceof Error ? e.message : '导出失败，请稍后再试'
    showExportPendingModal.value = true
  } finally {
    exportingReport.value = false
  }
}

function openRenameModal() {
  if (!currentVideoId.value) return
  renameInput.value = detail.value?.type === 'video' ? detail.value.data.videoName : ''
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
    // 刷新详情，确保名称一致
    await loadDetail()
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
  const id = currentVideoId.value
  if (!id) return
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
    router.push('/resource-analysis')
  } catch (e) {
    console.error('删除失败:', e)
  } finally {
    deleting.value = false
  }
}

const POLL_INTERVAL_MS = 5 * 1000
let detailPollTimer: ReturnType<typeof setInterval> | null = null

// 语音转写折叠状态
const isTranscriptCollapsed = ref(true)
const TRANSCRIPT_PREVIEW_COUNT = 5
const toggleTranscript = () => {
  isTranscriptCollapsed.value = !isTranscriptCollapsed.value
}

// 转写片段永远渲染全部：收起状态靠 CSS 限高 + 内部滚动，不再截断 DOM。
// 这样「展开全部」前用户也能滚动查看完整内容，而不是只看前几条。
const displayedTranscriptSegments = computed(() => transcriptSegments.value)

// 是否显示"展开/收起"按钮
const shouldShowTranscriptToggle = computed(() => {
  return transcriptSegments.value.length > TRANSCRIPT_PREVIEW_COUNT
})

// 教学环节总结折叠状态
const isTeachSummaryCollapsed = ref(true)
const TEACH_SUMMARY_PREVIEW_COUNT = 3
const toggleTeachSummary = () => {
  isTeachSummaryCollapsed.value = !isTeachSummaryCollapsed.value
}

// 教学环节总结数据
const teachSummarySections = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return []
  const report = detail.value.data.report as Record<string, unknown> | undefined
  let ts = detail.value.data.report?.teach_summary
  if (!ts) {
    const design = asAnalysisReportRecord(report?.teaching_design)
    const segments = design?.segments
    if (Array.isArray(segments) && segments.length) {
      ts = [{ file_structure: segments }]
    }
  }
  return parseTeachSummary(ts)
})

// 教学环节总结同样永远渲染全部，收起靠 CSS 限高 + 内部滚动。
const displayedTeachSummarySections = computed(() => teachSummarySections.value)

// 是否显示"展开/收起"按钮
const shouldShowTeachSummaryToggle = computed(() => {
  return teachSummarySections.value.length > TEACH_SUMMARY_PREVIEW_COUNT
})

// ---------- 五何互动（teach_wh 环形图） ----------
const WH_CATEGORIES: { key: string; color: string }[] = [
  { key: '若何', color: '#5C8DF6' },
  { key: '是何', color: '#5FD3B3' },
  { key: '为何', color: '#6B5FE3' },
  { key: '如何', color: '#F2B84B' },
  { key: '由何', color: '#E06B5A' },
]

const teachWhSlices = computed<DonutSlice[] | null>(() => {
  if (!detail.value || detail.value.type !== 'video') return null
  const report = detail.value.data.report as Record<string, unknown> | undefined
  let raw = detail.value.data.report?.teach_wh
  if (!Array.isArray(raw) || raw.length === 0) {
    const whDist = asAnalysisReportRecord(report?.interaction_quality)?.wh_distribution
    if (whDist && typeof whDist === 'object') {
      const expanded: Record<string, unknown>[] = []
      for (const [category, infoRaw] of Object.entries(whDist as Record<string, unknown>)) {
        const info = asAnalysisReportRecord(infoRaw)
        if (!info) continue
        const count = typeof info.count === 'number' ? Math.round(info.count) : 0
        for (let i = 0; i < count; i++) {
          expanded.push({ category })
        }
      }
      raw = expanded
    }
  }
  if (!Array.isArray(raw)) return null
  const counts = new Map<string, number>()
  for (const cat of WH_CATEGORIES) counts.set(cat.key, 0)
  for (const item of raw) {
    const cat = (item as { category?: unknown })?.category
    if (typeof cat === 'string' && counts.has(cat)) {
      counts.set(cat, (counts.get(cat) ?? 0) + 1)
    }
  }
  const total = Array.from(counts.values()).reduce((a, b) => a + b, 0)
  if (total === 0) return null
  return WH_CATEGORIES
    .map((c) => ({
      key: c.key,
      color: c.color,
      count: counts.get(c.key) ?? 0,
      percent: (counts.get(c.key) ?? 0) / total,
    }))
    .filter((s) => s.count > 0)
})

// ---------- 课堂环节占比 ----------
const PHASE_PALETTE = [
  '#5B8DEE', '#F2B84B', '#5FD3B3', '#E06B5A', '#6B5FE3',
  '#F28ADC', '#A0D468', '#4BC0C0', '#FFA07A', '#9370DB',
  '#20B2AA', '#FFB347',
]

const teachPhaseSlices = computed<DonutSlice[] | null>(() => {
  const sections = teachSummarySections.value
  if (!sections.length) return null
  const durations = new Map<string, number>()
  for (const section of sections) {
    for (const seg of section.fileStructure) {
      const type = (seg.type ?? '').trim() || '未知'
      const dur = parseTimeToSeconds(seg.end_time) - parseTimeToSeconds(seg.start_time)
      if (!Number.isFinite(dur) || dur <= 0) continue
      durations.set(type, (durations.get(type) ?? 0) + dur)
    }
  }
  const total = Array.from(durations.values()).reduce((a, b) => a + b, 0)
  if (total === 0) return null
  const entries = Array.from(durations.entries()).sort((a, b) => b[1] - a[1])
  return entries.map(([type, duration], i) => ({
    key: type,
    color: PHASE_PALETTE[i % PHASE_PALETTE.length] ?? '#5B8DEE',
    count: 0,
    duration,
    percent: duration / total,
  }))
})

// ---------- 知识点词云热词 ----------
const ZH_SPLIT_RE = /[的与和到在及对为以其等了是有、，。·？！：；,.\?!:;()（）\s]+/
const WORD_CLOUD_MAX = 50

const knowledgeHotWords = computed<Array<{ text: string; count: number }>>(() => {
  if (!detail.value || detail.value.type !== 'video') return []
  const report = detail.value.data.report as Record<string, unknown> | undefined
  const cloudRaw =
    report?.word_cloud ??
    asAnalysisReportRecord(report?.knowledge_presentation)?.word_cloud
  if (Array.isArray(cloudRaw) && cloudRaw.length) {
    return cloudRaw
      .map((w) => {
        if (!w || typeof w !== 'object') return null
        const o = w as Record<string, unknown>
        const text = String(o.word ?? o.text ?? '').trim()
        const count =
          typeof o.weight === 'number'
            ? o.weight
            : typeof o.count === 'number'
              ? o.count
              : 1
        return text ? { text, count } : null
      })
      .filter((x): x is { text: string; count: number } => x != null)
      .slice(0, WORD_CLOUD_MAX)
  }

  const raw = detail.value.data.report?.teach_knowledge
  const data = tryParseJsonLike(raw)
  if (!Array.isArray(data)) return []
  const titles: string[] = []
  for (const entry of data) collectKnowledgeTitles(entry, titles)
  if (!titles.length) return []
  const counts = new Map<string, number>()
  for (const t of titles) {
    for (const part of t.split(ZH_SPLIT_RE)) {
      const p = part.trim()
      if (!p) continue
      const hasNonAscii = /[^\x00-\x7F]/.test(p)
      if (hasNonAscii) {
        // 中文：长度 2-6
        if ([...p].length < 2 || [...p].length > 6) continue
      } else {
        // 英文/数字：长度 1-8
        if (p.length < 1 || p.length > 8) continue
      }
      counts.set(p, (counts.get(p) ?? 0) + 1)
    }
  }
  const entries = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])
  return entries.slice(0, WORD_CLOUD_MAX).map(([text, count]) => ({ text, count }))
})


const pageTitle = computed(() => {
  if (!detail.value) return '分析报告'
  if (detail.value.type === 'video') {
    return `${detail.value.data.videoName} 分析报告`
  }
  return '分析报告'
})

/** 视频任务未完成（待分析/分析中/失败），用于显示状态提示 */
const isVideoNotCompleted = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  return detail.value.data.status !== 'success'
})

/**
 * 是否展示下方「文本分析 / 教学分析 / 音量」等报告区。
 * 原先与「未完成」绑定，导致分析中阶段即使后端已在 analysis_result 里写入部分内容也不渲染。
 * 规则：完成态始终展示；分析中（stage1/stage2 无固定先后）若 report 已有字段则先行展示。
 */
const showVideoReportBottom = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  if (detail.value.data.status === 'success') return true
  return isNonEmptyReportRecord(detail.value.data.report)
})

/** 右侧列：雷达图、词云、饼图等可视化卡片 */
const hasVideoReportSideCol = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return false
  if (!isVideoNotCompleted.value && hasVideoRadarChart.value) return true
  if (showVideoReportBottom.value && detail.value.data.report) return true
  return false
})

/** 未完成时的横幅说明（有部分内容时提示可向下查看） */
const videoStatusBannerDesc = computed(() => {
  if (!detail.value || detail.value.type !== 'video') {
    return '该任务尚未完成分析，您可先观看视频，分析完成后将自动显示结果。'
  }
  if (detail.value.data.status === 'success') return ''
  if (showVideoReportBottom.value && isNonEmptyReportRecord(detail.value.data.report)) {
    return '下方已展示当前可用的分析内容；完整报告将在分析结束后自动刷新。'
  }
  return '该任务尚未完成分析，您可先观看视频，分析完成后将自动显示结果。'
})

/** 未完成时的状态文案 */
const videoStatusLabel = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return ''
  const s = detail.value.data.status
  if (s === 'waiting') return '分析中'
  if (s === 'unstarted') return '待分析'
  if (s === 'failed') return '分析失败'
  return '未完成'
})


const transcriptSegments = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return []
  return extractTranscriptSegments(detail.value.data.report)
})

const audioDurationText = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return ''
  const report = detail.value.data.report as any
  const dur = report?.audio_duration
  const n = typeof dur === 'number' ? dur : Number(dur)
  return Number.isFinite(n) && n > 0 ? formatSec(n) : ''
})

async function loadVideoPlayableSrc(rawUrl: string | undefined) {
  if (videoPlayableSrc.value && videoPlayableSrc.value.startsWith('blob:')) {
    URL.revokeObjectURL(videoPlayableSrc.value)
  }
  videoPlayableSrc.value = null
  videoError.value = null
  videoTriedBlobFallback.value = false
  if (!rawUrl) return

  videoPlayableSrc.value = resolveVideoMediaUrl(rawUrl) ?? rawUrl
}

async function tryBlobFallbackForAuth(rawUrl: string) {
  const authorization = buildAuthorizationHeader()
  if (!authorization) return
  const fullUrl = resolveVideoMediaUrl(rawUrl) ?? rawUrl
  videoLoading.value = true
  try {
    const resp = await fetch(fullUrl, {
      method: 'GET',
      headers: { Authorization: authorization },
    })
    if (!resp.ok) throw new Error(`视频加载失败（${resp.status}）`)
    const blob = await resp.blob()
    if (blob.type && /json|text/i.test(blob.type)) {
      throw new Error('视频加载失败（返回内容非视频）')
    }
    if (videoPlayableSrc.value && videoPlayableSrc.value.startsWith('blob:')) {
      URL.revokeObjectURL(videoPlayableSrc.value)
    }
    videoPlayableSrc.value = URL.createObjectURL(blob)
  } finally {
    videoLoading.value = false
  }
}

function onVideoTagError() {
  if (!detail.value || detail.value.type !== 'video') return
  const rawUrl = detail.value.data.videoUrl
  if (!rawUrl) {
    videoError.value = '视频地址为空，无法播放'
    return
  }

  // 首次播放失败：尝试使用带 Authorization 的 blob 兜底一次
  if (!videoTriedBlobFallback.value) {
    videoTriedBlobFallback.value = true
    videoError.value = '视频直连播放失败，正在尝试使用登录凭证加载...'
    void tryBlobFallbackForAuth(rawUrl).catch((e) => {
      videoError.value = e instanceof Error ? e.message : '视频无法播放（鉴权加载失败）'
    })
    return
  }

  if (!videoError.value) videoError.value = '视频无法播放（请检查后端视频地址/鉴权/Range 支持）'
}

/** 从报告里取雷达数据（兼容 radar_chart 与错误字段名 radar chart） */
const videoRadarSeries = computed((): { labels: string[]; values: number[] } | null => {
  if (detail.value?.type !== 'video') return null
  const report = detail.value.data.report as Record<string, unknown> | undefined
  if (!report) return null
  const raw = report.radar_chart ?? report.radar_data ?? report['radar chart']
  return parseRadarChartInput(raw)
})

const hasVideoRadarChart = computed(() => {
  const s = videoRadarSeries.value
  return !!(s && s.labels.length >= 3 && s.labels.length === s.values.length)
})

const radarLabels = computed(() => videoRadarSeries.value?.labels ?? [])
const radarValues = computed(() => videoRadarSeries.value?.values ?? [])

/** 按维度关键词从 radar_chart 匹配单项得分（用于卡片标题栏） */
function getRadarScoreByKeywords(keywords: string[]): number | null {
  const series = videoRadarSeries.value
  if (!series || !keywords.length) return null
  for (let i = 0; i < series.labels.length; i++) {
    const label = series.labels[i] ?? ''
    if (keywords.some((kw) => label.includes(kw) || kw.includes(label))) {
      const v = series.values[i]
      return v != null && Number.isFinite(v) ? v : null
    }
  }
  return null
}

const teachingExpressionScore = computed(() =>
  getRadarScoreByKeywords(['教学表达', '讲授质量', '表达']),
)
const interactionQualityScore = computed(() =>
  getRadarScoreByKeywords(['互动质量', '互动']),
)
const teachingStructureScore = computed(() =>
  getRadarScoreByKeywords(['教学设计', '教学结构', '课程导入', '教学节奏', '课堂总结', '设计']),
)
const knowledgePresentationScore = computed(() =>
  getRadarScoreByKeywords(['知识呈现', '知识']),
)
const ideologyIntegrationScore = computed(() =>
  getRadarScoreByKeywords(['思政', '思政融合']),
)
const overallRadarScore = computed(() => {
  const fromDim = getRadarScoreByKeywords(['综合得分', '综合'])
  if (fromDim != null) return fromDim
  if (detail.value?.type === 'video') {
    const report = detail.value.data.report as Record<string, unknown> | undefined
    const radarData = report?.radar_data
    if (Array.isArray(radarData)) {
      for (const item of radarData) {
        if (!item || typeof item !== 'object') continue
        const dim = String((item as Record<string, unknown>).dimension ?? '')
        if (!dim.includes('综合')) continue
        const score = (item as Record<string, unknown>).score
        if (typeof score === 'number' && Number.isFinite(score)) return score
      }
    }
  }
  const vals = radarValues.value
  if (vals.length < 3) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

interface IdeologySummaryItem {
  title: string
  content: string
  timeRange: string
}

const ideologySummaryItems = computed<IdeologySummaryItem[]>(() => {
  if (!detail.value || detail.value.type !== 'video') return []
  const report = detail.value.data.report as Record<string, unknown> | undefined

  const eventsRaw =
    asAnalysisReportRecord(report?.ideological_integration)?.ideological_events ??
    asAnalysisReportRecord(report?.class_education_summary)?.summary
  if (Array.isArray(eventsRaw) && eventsRaw.length) {
    const items: IdeologySummaryItem[] = []
    for (const entry of eventsRaw) {
      if (!entry || typeof entry !== 'object') continue
      const e = entry as Record<string, unknown>
      const result = e.result as Record<string, unknown> | undefined
      const title = String(result?.title ?? e.title ?? '').trim()
      const content = String(result?.content ?? e.content ?? '').trim()
      if (!title && !content) continue
      const start = typeof e.start === 'number' ? e.start : Number(e.start)
      const end = typeof e.end === 'number' ? e.end : Number(e.end)
      const timeRange =
        Number.isFinite(start) && Number.isFinite(end)
          ? `${formatSec(start)} - ${formatSec(end)}`
          : ''
      items.push({
        title: title || '思政事件',
        content: content || '—',
        timeRange,
      })
    }
    if (items.length) return items
  }

  const raw = detail.value.data.report?.class_education_summary
  const data = tryParseJsonLike(raw)
  if (!data || typeof data !== 'object') return []
  const summary = (data as Record<string, unknown>).summary
  if (!Array.isArray(summary)) return []
  const items: IdeologySummaryItem[] = []
  for (const entry of summary) {
    if (!entry || typeof entry !== 'object') continue
    const e = entry as Record<string, unknown>
    const result = e.result as Record<string, unknown> | undefined
    const title = String(result?.title ?? e.title ?? '').trim()
    const content = String(result?.content ?? e.content ?? '').trim()
    if (!title && !content) continue
    const start = typeof e.start === 'number' ? e.start : Number(e.start)
    const end = typeof e.end === 'number' ? e.end : Number(e.end)
    const timeRange =
      Number.isFinite(start) && Number.isFinite(end)
        ? `${formatSec(start)} - ${formatSec(end)}`
        : ''
    items.push({
      title: title || '思政事件',
      content: content || '—',
      timeRange,
    })
  }
  return items
})

const ideologySummaryText = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return ''
  if (ideologySummaryItems.value.length) return ''
  const raw = detail.value.data.report?.class_education_summary
  const data = tryParseJsonLike(raw)
  if (!data || typeof data !== 'object') return ''
  const obj = data as Record<string, unknown>
  if (typeof obj.summary === 'string') return obj.summary.trim()
  return getStr(obj, 'text')
})

const teachQuestionTypeStats = computed<Array<{ type: string; count: number }> | null>(() => {
  if (!detail.value || detail.value.type !== 'video') return null
  const raw = detail.value.data.report?.teach_question
  const data = tryParseJsonLike(raw)
  if (!data || typeof data !== 'object') return null
  const reportObj = detail.value.data.report as Record<string, unknown> | undefined
  const stats =
    (data as Record<string, unknown>).statistics ??
    asAnalysisReportRecord(reportObj?.interaction_quality)?.type_statistics
  if (!stats || typeof stats !== 'object') return null
  const entries: Array<{ type: string; count: number }> = []
  for (const [type, val] of Object.entries(stats as Record<string, unknown>)) {
    if (typeof val === 'number' && val > 0) {
      entries.push({ type, count: val })
      continue
    }
    if (!val || typeof val !== 'object') continue
    const count = (val as Record<string, unknown>).count
    if (typeof count === 'number' && count > 0) entries.push({ type, count })
  }
  return entries.length ? entries.sort((a, b) => b.count - a.count) : null
})


// 相关视频 Mock：排除当前报告对应的 id，避免推荐自己
const MOCK_RELATED_VIDEOS = [
  { id: 'task-demo-1', title: '高等数学第一章绪论', subTitle: '高等数学A · 张老师' },
  { id: 'task-demo-2', title: '大学物理实验-单摆', subTitle: '大学物理实验 · 李老师' },
  { id: 'task-demo-extra', title: '线性代数-矩阵运算', subTitle: '线性代数 · 王老师' },
]

const relatedVideos = computed(() => {
  const currentId = detail.value?.type === 'video' ? detail.value.data.id : ''
  return MOCK_RELATED_VIDEOS.filter((v) => v.id !== currentId).slice(0, 3)
})

function recommendedSummaryText(title: string): string {
  if (!detail.value || detail.value.type !== 'video') {
    return `${title}：课堂节奏清晰、讲解层次分明，建议保持提问互动频次并适度提升板书信息密度...`
  }
  const report = detail.value.data.report
  const summaryText =
    getStr(report?.teach_summary as Record<string, unknown> | undefined, 'text') ||
    getStr(report?.class_summary as Record<string, unknown> | undefined, 'text') ||
    getStr(report?.teach_db_result as Record<string, unknown> | undefined, 'suggestion')
  const compact = summaryText.trim()
  if (!compact) {
    return `${title}：课堂节奏清晰、讲解层次分明，建议保持提问互动频次并适度提升板书信息密度...`
  }
  return compact.length > 62 ? `${compact.slice(0, 62)}...` : `${compact}...`
}


const whLabels: Record<string, string> = {
  what: '何事',
  why: '何故',
  how: '如何',
  when: '何时',
  where: '何地',
}

function hasTeachWh(obj: Record<string, unknown> | undefined): boolean {
  if (!obj) return false
  return ['what', 'why', 'how', 'when', 'where'].some((k) => getStr(obj, k))
}



// 音量数据计算属性
const volumeData = computed(() => {
  if (!detail.value || detail.value.type !== 'video') return []
  const report = detail.value.data.report as Record<string, unknown> | undefined
  const fromDb = parseVolumeData(detail.value.data.report?.teach_db_result)
  if (fromDb.length) return fromDb
  const volumeAnalysis = asAnalysisReportRecord(
    asAnalysisReportRecord(report?.teaching_expression)?.volume_analysis,
  )
  return parseVolumeData(volumeAnalysis)
})

const hasVolumeChart = computed(() => volumeData.value.length > 0)

const videoDurationSec = computed(() => {
  const el = videoPlayerRef.value
  if (el && Number.isFinite(el.duration) && el.duration > 0) return el.duration
  if (!detail.value || detail.value.type !== 'video') return 0
  const report = detail.value.data.report as Record<string, unknown> | undefined
  const dur = report?.audio_duration
  const n = typeof dur === 'number' ? dur : Number(dur)
  if (Number.isFinite(n) && n > 0) return n
  const segs = transcriptSegments.value
  if (segs.length) return Math.max(...segs.map((s) => s.end))
  return 0
})

const videoPlayProgressRatio = ref(0)

const videoPlayProgressPercent = computed(() =>
  Math.max(0, Math.min(100, videoPlayProgressRatio.value * 100)),
)

function onVideoTimeUpdate() {
  const el = videoPlayerRef.value
  if (!el || !Number.isFinite(el.duration) || el.duration <= 0) {
    videoPlayProgressRatio.value = 0
    return
  }
  videoPlayProgressRatio.value = el.currentTime / el.duration
}

function onVolumeSeek(ratio: number) {
  const dur = videoDurationSec.value
  if (!dur || !Number.isFinite(ratio)) return
  seekVideoToSegmentStart(Math.max(0, Math.min(1, ratio)) * dur)
}

async function loadDetail() {
  const isMockMode = import.meta.env.DEV && route.query.mock === '1'
  if (isMockMode) {
    loading.value = false
    reportNotFound.value = false
    detail.value = {
      type: 'video',
      data: {
        id: 'mock-video-report',
        videoName: '示例课程视频（Mock）',
        college: '计算机学院',
        courseName: '教育技术导论',
        teacherName: '张老师',
        status: 'success',
        progress: 100,
        createdAt: new Date().toISOString(),
        videoUrl: '',
        report: {
          teach_summary: {
            text: '课堂导入清晰，核心概念讲解有层次，互动提问频次适中，建议在案例讨论环节增加学生复述与板书总结。',
          },
          class_summary: {
            text: '整体课堂节奏稳定，教学目标达成度较高，学生参与度表现良好。',
          },
          teach_db_result: {
            suggestion: '语速整体平稳，可在重点概念处适度放慢并增加停顿。',
          },
          transcript: [
            { start: 0, end: 12, text: '同学们好，今天我们学习教学设计的核心流程。' },
            { start: 13, end: 28, text: '首先我们看目标分析，再看学习活动设计。' },
            { start: 29, end: 46, text: '这里请大家思考：为什么先做学习者分析？' },
            { start: 47, end: 65, text: '我们用一个真实课堂案例来说明。' },
            { start: 66, end: 88, text: '最后总结：目标、活动、评价要对齐。' },
          ],
        },
      },
    }
    return
  }

  const rawId =
    typeof props.id === 'string' && props.id !== '' ? props.id : String((route.params.id as string | undefined) ?? '')
  // 兼容 id 中包含斜杠等特殊字符（列表页/新模块会 encodeURIComponent）
  let id = rawId
  try {
    id = decodeURIComponent(rawId)
  } catch {
    id = rawId
  }
  if (!id) {
    detail.value = null
    reportNotFound.value = false
    loading.value = false
    return
  }
  loading.value = true
  reportNotFound.value = false
  try {
    if (isVideoTaskId(id)) {
      const videoDetail = await getVideoTaskDetail(id)
      detail.value = videoDetail ? { type: 'video', data: videoDetail } : null
    } else {
      const genericDetail = await getMockAnalysisReport(id)
      detail.value = genericDetail ? { type: 'generic', data: genericDetail } : null
    }
  } catch {
    detail.value = null
    reportNotFound.value = false
  } finally {
    loading.value = false
  }
}

function shouldPollDetail(): boolean {
  if (loading.value) return false
  if (!detail.value) return false
  if (detail.value.type !== 'video') return false
  return isVideoTaskPollingActive(detail.value.data.status)
}

function startDetailPolling() {
  if (detailPollTimer) return
  detailPollTimer = setInterval(() => {
    if (!shouldPollDetail()) return
    void loadDetail()
  }, POLL_INTERVAL_MS)
}

function stopDetailPolling() {
  if (!detailPollTimer) return
  clearInterval(detailPollTimer)
  detailPollTimer = null
}

onMounted(async () => {
  await loadDetail()
  // 进入即查一次，随后未完成才轮询
  if (shouldPollDetail()) startDetailPolling()
})

watch(() => route.params.id, async () => {
  stopDetailPolling()
  await loadDetail()
  if (shouldPollDetail()) startDetailPolling()
})

watch(
  () => (detail.value?.type === 'video' ? detail.value.data.status : undefined),
  () => {
    if (shouldPollDetail()) startDetailPolling()
    else stopDetailPolling()
  }
)

watch(
  () => (detail.value?.type === 'video' ? detail.value.data.videoUrl : undefined),
  (url) => {
    void loadVideoPlayableSrc(url)
  },
  { immediate: true }
)

onBeforeRouteLeave((to) => {
  if (skipUnstartedLeavePrompt.value) return true
  if (!shouldPromptLeaveForUnstarted.value) return true
  pendingLeaveRoute.value = to
  showLeaveAnalysisModal.value = true
  return false
})

onBeforeUnmount(() => {
  stopDetailPolling()
  if (videoPlayableSrc.value && videoPlayableSrc.value.startsWith('blob:')) {
    URL.revokeObjectURL(videoPlayableSrc.value)
  }
})
</script>

<style scoped>
.resource-analysis-report-view {
  width: 100%;
  min-height: calc(100vh - 64px);
  background-color: transparent;
  display: flex;
  flex-direction: column;
}

.report-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

/* 顶部操作栏（与 ResourceView .top-bar 一致） */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 16px 24px;
  background-color: rgba(255, 255, 255, 0.4);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
}

.left-section {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.back-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #333;
  text-decoration: none;
  transition: color 0.2s;
  border-radius: 4px;
  flex-shrink: 0;
}
.back-btn:hover { color: #C5D9FF; }

.file-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.right-section {
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
.action-btn:hover:not(:disabled) {
  border-color: #C5D9FF;
  background-color: #f8f9ff;
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.secondary {
  background: #e0e0e0;
  color: #333;
}
.action-btn.secondary:hover {
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
  border: none;
  background: none;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.modal-body { padding: 16px 18px; }
.modal-footer {
  padding: 14px 18px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.form-row label {
  display: block;
  font-size: 14px;
  color: #333;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #e6e6e6;
  outline: none;
}
.form-input:focus { border-color: #C5D9FF; }

.rename-error {
  color: #c62828;
  font-size: 13px;
  margin-top: 10px;
}

/* 正文区 */
.content-area {
  flex: 1;
  padding: 0;
  max-width: 100%;
  width: 100%;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .report-content {
    padding: 16px;
  }
  .top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .right-section {
    width: 100%;
    justify-content: flex-end;
  }
}

.content-area-video {
  max-width: 100%;
  min-height: calc(100vh - 64px - 120px);
  overflow-x: auto;
}

/* 视频报告：与 toolbar 同宽，内部 2 列网格 */
.video-report-body {
  --vr-grid-gap: 32px;
  --transcript-footprint: 420px;
  --teach-summary-footprint: 652px;
  --wh-chart-footprint: 280px;
  --volume-chart-footprint: 320px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.video-report-body .report-section-panel {
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  box-sizing: border-box;
}

.video-report-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--vr-grid-gap);
  width: 100%;
  align-items: start;
}

/* 仅左列有内容时占满整宽 */
.video-report-grid:has(> .video-report-col:only-child) {
  grid-template-columns: 1fr;
}

.video-report-col {
  display: flex;
  flex-direction: column;
  gap: var(--vr-grid-gap);
  min-width: 0;
}

.video-report-col > .report-card {
  margin-bottom: 0;
  min-width: 0;
}

.video-report-col > .video-card .video-wrapper {
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 9;
  max-width: none;
  box-sizing: border-box;
}

.video-report-col > .radar-card {
  display: flex;
  flex-direction: column;
}

.video-report-col > .report-card:not(.video-card) {
  display: flex;
  flex-direction: column;
}

.video-report-col > .radar-card .radar-wrap {
  width: 100%;
  max-width: 100%;
  flex: 1 1 auto;
}

.video-report-col > .radar-card .radar-svg {
  width: 100%;
  height: auto;
  aspect-ratio: 1 / 1;
}

.loading-container,
.error-container { text-align: center; padding: 48px 24px; color: #666; }

.retry-btn {
  display: inline-block;
  margin-top: 12px;
  padding: 8px 16px;
  background: #C5D9FF;
  border-radius: 8px;
  color: #333;
  text-decoration: none;
  font-size: 14px;
}
.retry-btn:hover { background: #b0caff; }

.status-banner {
  margin-bottom: 24px;
}
.status-banner-inner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: #fff8e6;
  border: 1px solid #f0d675;
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.status-banner-icon { font-size: 24px; line-height: 1; }
.status-banner-text { flex: 1; }
.status-banner-text strong { font-size: 15px; color: #333; }
.status-banner-desc {
  margin: 8px 0 0 0;
  font-size: 14px;
  color: #666;
  line-height: 1.5;
}
.status-banner-warn .status-banner-inner {
  background: #fff5e6;
  border-color: #e8b84d;
}

.video-section { margin-bottom: 32px; }
.section-title { font-size: 18px; font-weight: 700; color: #333; margin: 0 0 12px 0; }
.video-wrapper {
  background: #000;
  border-radius: 20px;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  margin-bottom: 12px;
}
.video-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #666;
  gap: 12px;
}
.video-placeholder p { margin: 0; font-size: 14px; }
.video-player { width: 100%; height: 100%; object-fit: contain; }
.video-player-wrap { width: 100%; height: 100%; position: relative; }
.video-loading,
.video-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #ddd;
  background: rgba(0, 0, 0, 0.35);
  z-index: 1;
  padding: 12px;
  text-align: center;
}
.video-meta {
  font-size: 14px;
  color: #666;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.video-volume-block {
  margin-top: 12px;
  width: 100%;
}

.video-sync-timeline {
  margin-bottom: 10px;
  width: 100%;
  padding: 0 16px;
  box-sizing: border-box;
}

.video-sync-track {
  position: relative;
  height: 6px;
  border-radius: 999px;
  background: rgba(217, 217, 217, 0.55);
  overflow: visible;
}

.video-sync-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #86aaf2 0%, #1358e4 100%);
  transition: width 0.1s linear;
}

.video-sync-cursor {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 14px;
  margin-left: -1px;
  background: #1358e4;
  border-radius: 1px;
  pointer-events: none;
  box-shadow: 0 0 8px rgba(19, 88, 228, 0.35);
  transition: left 0.06s ease-out;
}

.video-sync-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  padding: 0 2px;
  font-size: 12px;
  color: #888;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
}

.report-section { margin-top: 8px; }

.video-report-body .report-section {
  flex: 1 1 auto;
  width: 100%;
  max-width: 100%;
  margin: 0;
  overflow: visible;
  padding: 0;
  box-sizing: border-box;
  background: transparent;
}

.video-report-body .report-section .report-section-heading {
  margin: 0 0 12px 0;
}

.report-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  box-sizing: border-box;
}

/* 除视频卡片外：四周 24px 内边距 + 标题栏分割线 + 内容区间距 */
.report-card:not(.video-card) {
  --report-card-pad: 24px;
  --report-card-section-gap: 40px;
  --report-card-header-stroke: rgba(0, 0, 0, 0.05);
  padding: var(--report-card-pad);
  display: flex;
  flex-direction: column;
  gap: 0;
}

.report-card:not(.video-card) .report-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: 52px;
  margin: 0;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--report-card-header-stroke);
  box-sizing: border-box;
  flex-shrink: 0;
}

.report-card:not(.video-card) .report-card-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #333;
  text-align: left;
  flex: 1;
  min-width: 0;
  line-height: 1.35;
}

.report-card:not(.video-card) .report-card-header-extra {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
  min-width: 0;
}

.report-card-score {
  font-size: 15px;
  font-weight: 600;
  color: #1358e4;
  white-space: nowrap;
}

.question-type-stats {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-type-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.question-type-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f0f4ff;
  color: #1358e4;
  font-size: 13px;
  line-height: 1.4;
}

.ideology-item + .ideology-item {
  padding-top: 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.ideology-item-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.ideology-item-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.ideology-item-time {
  flex-shrink: 0;
  font-size: 13px;
  color: #888;
}

.report-card:not(.video-card) .report-card-body {
  display: flex;
  flex-direction: column;
  gap: var(--report-card-section-gap);
  min-width: 0;
  flex: 1 1 auto;
  padding: var(--report-card-pad) 0 0;
  box-sizing: border-box;
}

.report-card:not(.video-card) .report-card-body > * {
  margin-top: 0;
  margin-bottom: 0;
}

.report-card:not(.video-card) .report-card-body > .report-text + .report-text {
  margin-top: 0;
}

.report-subtitle { font-size: 15px; font-weight: 700; color: #333; margin: 0 0 8px 0; }
/* 数据缺失时的统一占位 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 120px;
  padding: 16px;
  color: #999;
  font-size: 14px;
  background: #fafbfd;
  border: 1px dashed #e6e8ef;
  border-radius: 10px;
  box-sizing: border-box;
}

.report-card:not(.video-card) .report-card-body > .empty-state {
  padding: 16px;
}
/* 词云卡的占位需要保持方形（与有数据时的方形画布一致） */
.empty-state-square {
  aspect-ratio: 1 / 1;
  width: 100%;
  min-height: 0;
}
/* 饼图卡的占位高度 = 饼图 + 图例的预期高度 */
.empty-state-chart {
  min-height: 240px;
}
.report-card > .empty-state,
.report-card-body > .empty-state {
  flex: 1 1 auto;
}
.report-text { font-size: 14px; color: #555; line-height: 1.6; margin: 0; }
.report-text + .report-text { margin-top: 8px; }
.transcript-list {
  /* 展开状态：自然流，不限高、不出滚动条，整段转写完整显示。 */
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.transcript-list.is-collapsed {
  /* 收起状态：限高并出内部滚动条，用户可以在小窗里滚动看完整内容，点「展开全部」后高度放开。 */
  max-height: 320px;
  overflow-y: auto;
  padding-right: 6px;
  position: relative;
}
.transcript-item {
  display: grid;
  grid-template-columns: minmax(200px, auto) 1fr;
  gap: 12px;
  align-items: start;
}
.transcript-time-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.transcript-time { font-size: 12px; color: #888; font-variant-numeric: tabular-nums; }
.transcript-seek-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(91, 141, 238, 0.12);
  color: #5b8dee;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, transform 0.05s;
}
.transcript-seek-btn:hover {
  background: rgba(91, 141, 238, 0.22);
  color: #3d7ae8;
}
.transcript-seek-btn:active {
  transform: scale(0.96);
}
.transcript-text { font-size: 14px; color: #444; line-height: 1.6; white-space: pre-wrap; }

/* 转写折叠相关样式 */
.transcript-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.transcript-toggle-btn {
  background: #f0f4ff;
  border: none;
  color: #5B8DEE;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: background-color 0.2s;
}
.transcript-toggle-btn:hover {
  background: #e0e8ff;
}
.toggle-icon {
  font-size: 10px;
  transition: transform 0.3s;
}
.toggle-icon.is-expanded {
  transform: rotate(180deg);
}
.transcript-fade {
  /* 改为内部滚动后不再需要底部渐隐提示：内容可见、可滚动，滚动条本身就起到了「下面还有更多」的指示作用。 */
  display: none;
}
.report-text-secondary { color: #666; font-size: 13px; }
.report-list { margin: 0.5em 0 0 1.25em; padding-left: 0; font-size: 14px; color: #555; line-height: 1.8; }
.report-dl { margin: 0; }
.report-dl dt { font-size: 13px; font-weight: 600; color: #444; margin-top: 10px; }
.report-dl dt:first-child { margin-top: 0; }
.report-dl dd { margin: 4px 0 0 0; padding-left: 0; }

.report-json {
  font-size: 13px;
  line-height: 1.6;
  color: #444;
  background: #fafafa;
  border-radius: 8px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

/* 雷达图 */
.radar-section { margin-bottom: 32px; }
.radar-card-body {
  align-items: center;
}
.radar-wrap {
  position: relative;
  width: 100%;
  max-width: 360px;
  margin: 0 auto;
}
.video-report-col > .radar-card .radar-wrap {
  max-width: 100%;
}

.radar-svg { width: 100%; height: auto; display: block; }

.radar-grid polygon {
  opacity: 0;
  animation: radar-grid-in 0.45s ease forwards;
}

@keyframes radar-grid-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.radar-axis-line {
  stroke: #ccc;
  stroke-width: 1;
  transition: stroke 0.2s ease, stroke-width 0.2s ease;
}

.radar-axis.is-hovered .radar-axis-line {
  stroke: #86aaf2;
  stroke-width: 2;
}

.radar-label {
  font-size: 12px;
  fill: #555;
  transition: fill 0.2s ease, font-weight 0.2s ease;
}

.radar-axis.is-hovered .radar-label {
  fill: #1358e4;
  font-weight: 600;
}

.radar-label-score {
  font-size: 11px;
  fill: #86aaf2;
  font-weight: 600;
  transition: fill 0.2s ease;
}

.radar-axis.is-hovered .radar-label-score {
  fill: #1358e4;
}

.radar-data-polygon {
  opacity: 0.35;
  transition: opacity 0.35s ease, stroke-width 0.25s ease;
}

.radar-data-polygon.is-ready {
  opacity: 1;
}

.radar-wrap:not(.is-animating) .radar-data-polygon.is-ready:hover {
  stroke-width: 2.5;
}

.radar-hit {
  fill: transparent;
  cursor: pointer;
}

.radar-vertex {
  fill: #5b8dee;
  stroke: #fff;
  stroke-width: 2;
  transition: fill 0.2s ease, r 0.2s ease;
  pointer-events: none;
}

.radar-vertex.is-active {
  fill: #1358e4;
}

.radar-vertex-score {
  font-size: 11px;
  font-weight: 700;
  fill: #1358e4;
  opacity: 0.85;
  transition: opacity 0.2s ease, font-size 0.2s ease;
  pointer-events: none;
}

.radar-vertex-score.is-active {
  opacity: 1;
  font-size: 12px;
}

.radar-tooltip {
  position: absolute;
  z-index: 2;
  transform: translate(-50%, calc(-100% - 14px));
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(197, 217, 255, 0.9);
  box-shadow: 0 6px 20px rgba(19, 88, 228, 0.15);
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.radar-tooltip-label {
  font-size: 12px;
  color: #555;
}

.radar-tooltip-score {
  font-size: 16px;
  font-weight: 700;
  color: #1358e4;
}

.radar-tooltip-fade-enter-active,
.radar-tooltip-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.radar-tooltip-fade-enter-from,
.radar-tooltip-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, calc(-100% - 10px));
}

.radar-tip { font-size: 12px; color: #999; margin: 0; text-align: center; }

/* 相关视频 */
.related-section { margin-top: 0; margin-bottom: 24px; }
.video-report-body .related-section {
  width: 100%;
  max-width: 100%;
  margin: 0;
  box-sizing: border-box;
}

.video-report-body .related-section .section-title {
  flex-shrink: 0;
}
.related-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 0 0 auto;
  overflow: visible;
  padding-right: 0;
}

.video-report-body .related-tip {
  flex-shrink: 0;
  margin-top: 8px;
  margin-bottom: 0;
}
.related-tab {
  flex: 0 0 auto;
  min-height: 162px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  text-decoration: none;
  color: inherit;
  padding: 12px 14px;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 10px;
  transition: box-shadow 0.2s;
}
.related-tab:hover {
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.12);
}
/* 封面 4:3：比例加在外层。由 flex 纵向 stretch 得到确定高度后，宽度按 4:3 推导；勿对子层再用 max-width:100% 否则会与父宽循环压成窄条 */
.related-tab-cover-wrap {
  flex: 0 0 auto;
  flex-shrink: 0;
  align-self: stretch;
  box-sizing: border-box;
  padding: 6px 0;
  /* 先占满卡片可用高度（再扣 padding），宽度随比例增长 */
  aspect-ratio: 4 / 3;
  width: auto;
  height: auto;
  min-height: calc(162px - 24px - 12px);
  /* 最低卡片高度下 4:3 对应宽度，避免部分浏览器不根据 stretch 高度推算主尺寸时变成窄条 */
  min-width: calc((162px - 24px - 12px) * 4 / 3);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 10px;
}
.related-tab-cover {
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  border-radius: inherit;
  background: rgba(184, 207, 254, 0.35);
  color: rgba(19, 88, 228, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
.related-tab-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  overflow: hidden;
}
.related-tab-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.related-tab-subtitle {
  font-size: 11px;
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 雷达 + 简评同一圆角底，左图右文、无分隔线 */
.related-tab-radar-summary {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  padding: 6px 8px;
  border-radius: 10px;
  background: rgba(184, 207, 254, 0.18);
  min-height: 0;
}
.related-tab-summary {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: #555;
  line-height: 1.45;
  margin: 0;
  display: -webkit-box;
  line-clamp: 3;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.related-tab-radar-summary .related-tab-radar {
  flex: 0 0 auto;
  width: 46px;
  height: 46px;
  border-radius: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}
.related-tab-radar-summary .related-tab-radar svg {
  width: 42px;
  height: 42px;
}

@media (max-width: 1100px) {
  .video-wrapper {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
  }
}
.related-tip { font-size: 12px; color: #999; margin: 12px 0 0 0; }

.mock-tip { display: none; }

.report-card:not(.video-card) .report-card-body > .report-list {
  margin-top: 0;
}

.report-card:not(.video-card) .teach-summary-list {
  gap: var(--report-card-section-gap);
}

.teach-summary-list {
  display: flex;
  flex-direction: column;
  gap: 40px;
}
.teach-summary-list.is-collapsed {
  /* 收起时限高 + 内部滚动。 */
  max-height: 480px;
  overflow-y: auto;
  padding-right: 6px;
  position: relative;
}

/* 教学环节时间线样式 */
.teach-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 0;
}
.teach-summary-text {
  font-size: 14px;
  color: #333;
  line-height: 1.7;
  margin: 0;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8faff 0%, #f0f4ff 100%);
  border-left: 3px solid #5B8DEE;
  border-radius: 0 8px 8px 0;
}
.teach-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.timeline-item {
  display: flex;
  gap: 16px;
  padding: 16px 0;
  position: relative;
}
.timeline-item:first-child {
  padding-top: 0;
}
.timeline-item:last-child {
  padding-bottom: 0;
}
.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 24px;
  position: relative;
}
.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #5B8DEE;
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px #5B8DEE;
  z-index: 1;
}
.timeline-line {
  position: absolute;
  top: 24px;
  bottom: -16px;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  background: linear-gradient(to bottom, #5B8DEE, #e0e7ff);
}
.timeline-item:last-child .timeline-line {
  display: none;
}
.timeline-content {
  flex: 1;
  background: #fafbfc;
  border-radius: 10px;
  padding: 14px 16px;
  border: 1px solid #f0f0f0;
  transition: box-shadow 0.2s;
}
.timeline-content:hover {
  box-shadow: 0 4px 12px rgba(91, 141, 238, 0.1);
}
.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.timeline-type {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  color: #5B8DEE;
  background: rgba(91, 141, 238, 0.1);
  padding: 4px 10px;
  border-radius: 16px;
}
.timeline-time {
  font-size: 12px;
  color: #888;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', Monaco, monospace;
}
.timeline-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.timeline-desc {
  font-size: 14px;
  color: #444;
  line-height: 1.6;
  margin: 0;
}
.timeline-keypoint {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
  padding: 8px 12px;
  background: #fff8e6;
  border-radius: 6px;
  font-size: 13px;
}
.keypoint-label {
  color: #d4a520;
  font-weight: 500;
  flex-shrink: 0;
}
.keypoint-text {
  color: #666;
}

/* 知识点树形结构样式 */
.knowledge-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.knowledge-node {
  position: relative;
}
.knowledge-node.is-root > .knowledge-node-content {
  background: linear-gradient(135deg, #f0f7ff 0%, #e8f0fe 100%);
  border-color: #5B8DEE;
}
.knowledge-node-content {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: #fafbfc;
  border: 1px solid #e8eaed;
  border-radius: 8px;
  transition: all 0.2s;
}
.knowledge-node-content:hover {
  background: #f5f7fa;
  border-color: #d0d7de;
}
.knowledge-node.is-leaf .knowledge-node-content {
  padding: 8px 14px;
  background: transparent;
  border: none;
}
.knowledge-node.is-leaf .knowledge-node-content:hover {
  background: #f8fafc;
}
.knowledge-node-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  position: relative;
}
.knowledge-node-icon {
  font-size: 14px;
  color: #5B8DEE;
  line-height: 1;
}
.knowledge-node.is-leaf .knowledge-node-icon {
  color: #84b1ff;
  font-size: 12px;
}
.knowledge-node-branch {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  height: calc(100% + 8px);
  background: linear-gradient(to bottom, #e0e7ff, transparent);
}
.knowledge-node:last-child .knowledge-node-branch {
  display: none;
}
.knowledge-node-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.knowledge-node-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  line-height: 1.5;
}
.knowledge-node.is-leaf .knowledge-node-title {
  font-size: 13px;
  color: #555;
  font-weight: normal;
}
.knowledge-node-time {
  font-size: 12px;
  color: #888;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', Monaco, monospace;
}
.knowledge-node-children {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-left: 30px;
  margin-top: 8px;
  padding-left: 12px;
  border-left: 2px solid #e0e7ff;
}
.knowledge-node.is-leaf .knowledge-node-children {
  display: none;
}

/* 知识图谱树形结构样式 */
.knowledge-graph-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.graph-node {
  position: relative;
}
.graph-node.is-root > .graph-node-content {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border-color: #3498db;
}
.graph-node-content {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: #fafbfc;
  border: 1px solid #e8eaed;
  border-radius: 8px;
  transition: all 0.2s;
}
.graph-node-content:hover {
  background: #f5f7fa;
  border-color: #d0d7de;
}
.graph-node.is-leaf .graph-node-content {
  padding: 10px 14px;
}
.graph-node-left {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
}
.graph-expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: rgba(91, 141, 238, 0.1);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}
.graph-expand-btn:hover {
  background: rgba(91, 141, 238, 0.2);
}
.expand-icon {
  font-size: 12px;
  color: #5B8DEE;
  transition: transform 0.2s;
}
.expand-icon.is-expanded {
  transform: rotate(90deg);
}
.graph-leaf-dot {
  font-size: 14px;
  color: #84b1ff;
  line-height: 1;
}
.graph-node-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.graph-node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.graph-node-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  line-height: 1.5;
  flex: 1;
}
.graph-node.is-root .graph-node-title {
  font-size: 15px;
  font-weight: 600;
  color: #2c3e50;
}
.graph-node.is-leaf .graph-node-title {
  font-size: 13px;
  color: #555;
  font-weight: normal;
}
.graph-node-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.graph-node-time {
  font-size: 12px;
  color: #888;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', Monaco, monospace;
}
.graph-details-btn {
  font-size: 12px;
  color: #5B8DEE;
  background: rgba(91, 141, 238, 0.1);
  border: none;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  transition: all 0.2s;
}
.graph-details-btn:hover {
  background: rgba(91, 141, 238, 0.2);
}
.graph-node-details {
  font-size: 13px;
  color: #666;
  line-height: 1.6;
  padding: 10px 12px;
  background: #fff8e6;
  border-radius: 6px;
  margin-top: 4px;
  border-left: 3px solid #f0d675;
}
.graph-node-children {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-left: 34px;
  margin-top: 8px;
  padding-left: 12px;
  border-left: 2px solid #e0e7ff;
}

/* 音量折线图样式 */
.volume-chart-container {
  margin-bottom: 16px;
}
.volume-chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.volume-chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.volume-chart-stats {
  font-size: 13px;
  color: #666;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
}
.volume-chart {
  background: #fafbfc;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e8eaed;
}

.volume-chart--interactive {
  position: relative;
  cursor: crosshair;
}

.volume-chart-container--under-video {
  margin-bottom: 0;
}

.volume-hover-line {
  stroke: #1358e4;
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
  opacity: 0.85;
  pointer-events: none;
}

.chart-point.is-active {
  fill: #1358e4;
}

.volume-chart-tooltip {
  position: absolute;
  z-index: 3;
  transform: translateX(-50%);
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(197, 217, 255, 0.9);
  box-shadow: 0 4px 14px rgba(19, 88, 228, 0.12);
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.volume-chart-tooltip-time {
  font-size: 12px;
  color: #555;
}

.volume-chart-tooltip-db {
  font-size: 14px;
  font-weight: 700;
  color: #1358e4;
}

.volume-chart-tooltip-hint {
  font-size: 11px;
  color: #86aaf2;
}

.volume-tooltip-fade-enter-active,
.volume-tooltip-fade-leave-active {
  transition: opacity 0.15s ease;
}

.volume-tooltip-fade-enter-from,
.volume-tooltip-fade-leave-to {
  opacity: 0;
}

.volume-moved-hint {
  margin: 0 0 8px;
}
.volume-chart-svg {
  width: 100%;
  height: 200px;
  overflow: visible;
}
.chart-point {
  transition: r 0.2s;
  cursor: pointer;
}
.chart-point:hover {
  r: 5;
}
.volume-chart-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 4px;
}
.axis-label {
  font-size: 12px;
  color: #888;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
}
.volume-chart-legend {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  justify-content: center;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #666;
}
.legend-line {
  display: inline-block;
  width: 20px;
  height: 3px;
  border-radius: 2px;
}

/* ---------- 文本分析 / 教学分析：卡片在列内纵向排列 ---------- */
.video-report-col > .transcript-card,
.video-report-col > .word-cloud-card {
  min-width: 0;
  width: 100%;
}

.video-report-col > .report-card:has(.report-card-body > .empty-state) {
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.video-report-col > .transcript-card > .report-card-body > .empty-state {
  min-height: var(--transcript-footprint);
}

.video-report-col > .transcript-card .transcript-list.is-collapsed {
  max-height: var(--transcript-footprint);
}

.video-report-col > .teach-summary-left {
  min-width: 0;
}

.video-report-col > .teach-summary-left:has(.report-card-body > .empty-state) {
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.video-report-col > .teach-summary-left > .report-card-body > .empty-state {
  min-height: var(--teach-summary-footprint);
}

.video-report-col > .teach-summary-left .teach-summary-list.is-collapsed {
  max-height: var(--teach-summary-footprint);
}

@media (max-width: 1100px) {
  .video-report-grid {
    grid-template-columns: 1fr;
  }
}

/* ---------- 知识点词云 ---------- */
.video-report-col > .word-cloud-card {
  align-self: stretch;
  width: 100%;
  min-width: 0;
}

.report-card:not(.video-card) .word-cloud-summary {
  margin: 0;
}

.word-cloud-summary {
  font-size: 13px;
  color: #555;
  line-height: 1.6;
}
.word-cloud-canvas-wrap {
  width: 100%;
  max-width: 100%;
  aspect-ratio: 1 / 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
.word-cloud-svg {
  width: 100%;
  height: 100%;
  max-width: 100%;
  display: block;
}
.word-cloud-text {
  font-family: inherit;
  user-select: none;
  transition: opacity 0.15s ease;
}
.word-cloud-text:hover {
  opacity: 0.75;
}

/* ---------- 五何互动环形图 ---------- */
.wh-card-layout {
  display: grid;
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
  column-gap: 14px;
  row-gap: 10px;
  align-items: center;
  width: 100%;
}
.wh-card-layout > .empty-state-chart {
  grid-column: 1 / -1;
  min-height: var(--wh-chart-footprint);
  width: 100%;
}
.wh-chart-wrap {
  width: 100%;
  max-width: 520px;
  margin: 0;
  grid-column: 1;
}
.teach-summary-right .wh-chart-wrap,
.video-report-col > .wh-card .wh-chart-wrap {
  max-width: 100%;
}
.wh-donut {
  width: 100%;
  height: auto;
  overflow: visible;
  display: block;
}
.wh-label-text {
  font-size: 13px;
  font-weight: 600;
  fill: #333;
}
.wh-label-pct {
  font-size: 11px;
  fill: #666;
}
.wh-legend {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  flex-wrap: nowrap;
  justify-content: center;
  align-items: flex-start;
  gap: 8px;
  margin-top: 0;
  min-width: 0;
}
.wh-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #444;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wh-legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}

.teach-expr-card > .report-card-body > .empty-state {
  min-height: var(--volume-chart-footprint);
}

/* ========== 移动端适配 ==========
   报告页的多个 2 列大网格在 1100px 时已经塌为单列，但 768px 以下的工具栏、
   按钮组和 SVG 容器还需要进一步收紧。 */
@media (max-width: 640px) {
  .report-content {
    padding: 12px;
  }
  .top-bar {
    padding: 12px 16px;
  }
  .content-area {
    padding: 0;
  }
  .right-section {
    flex-wrap: wrap;
    gap: 8px;
    width: 100%;
    justify-content: flex-start;
  }
  /* 报告内绝大多数 2 列网格都有 1100px 的塌缩规则；这里兜底强制 1 列，防止
     未覆盖到的特例（例如 minmax 在窄屏下塌成"挤死"） */
  .video-report-grid {
    grid-template-columns: 1fr !important;
  }
  /* SVG 图表容器自适应宽度 */
  svg {
    max-width: 100%;
    height: auto;
  }
}
</style>
