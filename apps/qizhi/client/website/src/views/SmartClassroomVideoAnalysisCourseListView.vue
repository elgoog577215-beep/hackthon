<template>
  <div class="sc-course-list-view core-app-page core-app-page--flow">
    <div class="toolbar">
      <div class="toolbar-left">
        <router-link to="/resource-analysis" class="back-btn" aria-label="返回">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18L9 12L15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </router-link>
        <h2 class="page-title">新建智云课堂视频分析</h2>
      </div>
    </div>

    <div class="content-area">
      <div class="panel-wrap">
        <div class="course-panel">
          <div class="panel-header-row">
            <div>
              <h3 class="panel-title">智云课堂视频导入</h3>
            </div>
          </div>

          <div class="search-bar" role="search" aria-label="智云课堂课程查询">
            <div class="search-grid">
              <div class="field">
                <div class="field-label">起始日期<span class="req-star" aria-hidden="true">*</span></div>
                <input
                  v-model="searchBeginDate"
                  type="date"
                  class="field-input"
                  :class="{ 'field-input--error': dateBeginInvalid }"
                  aria-required="true"
                  @change="onDateBeginChange"
                />
              </div>
              <div class="field">
                <div class="field-label">结束日期<span class="req-star" aria-hidden="true">*</span></div>
                <input
                  v-model="searchEndDate"
                  type="date"
                  class="field-input"
                  :class="{ 'field-input--error': dateEndInvalid }"
                  aria-required="true"
                  @change="onDateEndChange"
                />
              </div>
              <div class="field field--action">
                <div class="field-label" aria-hidden="true">&nbsp;</div>
                <button
                  type="button"
                  class="search-action"
                  :disabled="loading || importingSubId !== null"
                  @click="handleSearch"
                >
                  {{ loading ? '搜索中...' : '搜索' }}
                </button>
              </div>
            </div>
          </div>

          <div v-if="loading" class="loading-inline">加载中...</div>
          <div v-else-if="items.length === 0" class="empty-inline">暂无数据，请调整筛选条件后重试</div>

          <ul class="accordion-list" role="list">
            <li
              v-for="group in groupedCourses"
              :key="group.key"
              class="accordion-group"
            >
              <div
                class="accordion-group-header"
                :class="{ 'is-expanded': isGroupExpanded(group.key) }"
              >
                <button
                  type="button"
                  class="accordion-group-main"
                  :aria-expanded="isGroupExpanded(group.key)"
                  @click="toggleGroup(group.key)"
                >
                  <div class="accordion-group-left">
                    <div class="course-name">{{ group.courseName }}</div>
                    <div class="video-count">{{ group.items.length }} 个视频</div>
                  </div>
                </button>
                <button
                  type="button"
                  class="expand-btn icon-only"
                  :aria-expanded="isGroupExpanded(group.key)"
                  :aria-label="isGroupExpanded(group.key) ? '收起' : '展开'"
                  @click="toggleGroup(group.key)"
                >
                  <svg
                    class="expand-icon"
                    :class="{ 'is-expanded': isGroupExpanded(group.key) }"
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>

              <ul
                v-show="isGroupExpanded(group.key)"
                class="accordion-group-body"
                role="list"
              >
                <li
                  v-for="it in group.items"
                  :key="`${it.course_id}:${it.sub_id}`"
                  class="session-item"
                >
                  <div class="session-card">
                    <div class="session-left">
                      <div class="session-title">{{ it.sub_title || '未命名小节' }}</div>
                      <div class="session-meta">{{ [it.teacher_name, it.class_begin].filter(Boolean).join(' · ') }}</div>
                    </div>
                    <div class="session-right">
                      <div class="session-actions">
                        <button
                          type="button"
                          class="detail-btn"
                          :disabled="importingSubId !== null"
                          @click="handleImport(it)"
                        >
                          {{ importingSubId === it.sub_id ? `导入中${importingProgress != null ? `(${importingProgress.toFixed(0)}%)` : '...'}` : '导入' }}
                        </button>
                        <button
                          v-if="importingSubId === it.sub_id"
                          type="button"
                          class="cancel-btn"
                          @click="handleCancelImport"
                        >
                          取消
                        </button>
                      </div>
                      <div
                        v-if="importingSubId === it.sub_id"
                        class="import-progress-wrap"
                        role="status"
                        aria-live="polite"
                      >
                        <div class="import-progress-bar">
                          <div
                            class="import-progress-fill"
                            :style="{ width: `${Math.max(0, Math.min(100, importingProgress ?? 0))}%` }"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </li>
              </ul>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { cancelSmartClassroomImport, importSmartClassroomVideo, listSmartClassroomImportVideos } from '../api/video'

const router = useRouter()
const error = ref<string | null>(null)
/** 仅当前正在导入的那条 sub_id 显示「导入中...」，其余卡片保持文案不变 */
const importingSubId = ref<string | null>(null)
const importingProgress = ref<number | null>(null)
/** 当前导入请求的中断控制器；用户点击「取消」时 abort，立即停止 SSE 连接 */
const importAbortController = ref<AbortController | null>(null)
/** 当前导入任务标识；用于向后端发送「取消导入」信号（避免后端继续下载并落库） */
const currentImportId = ref<string | null>(null)

/** 生成导入任务标识；不依赖 crypto.randomUUID（HTTP 非安全上下文下不可用） */
function genImportId(): string {
  return `imp_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

const loading = ref(false)
const items = ref<Array<{
  course_id: string
  sub_id: string
  course_name: string
  sub_title: string
  teacher_name: string
  class_begin: string
  campus_name?: string
  room_name?: string
  class_over?: string
  thumb?: string
}>>([])

const expandedGroupKeys = ref<Set<string>>(new Set())

type ImportListItem = (typeof items.value)[number]

const groupedCourses = computed(() => {
  const map = new Map<string, { courseName: string; items: ImportListItem[] }>()
  for (const it of items.value) {
    const courseName = (it.course_name || '').trim() || '未命名课程'
    const key = (it.course_id || '').trim() || courseName
    const entry = map.get(key) ?? { courseName, items: [] }
    entry.items.push(it)
    map.set(key, entry)
  }
  return Array.from(map.entries())
    .map(([key, { courseName, items: list }]) => ({
      courseName,
      key,
      items: [...list].sort((a, b) => String(b.class_begin || '').localeCompare(String(a.class_begin || ''))),
    }))
    .sort((a, b) => a.courseName.localeCompare(b.courseName, 'zh-CN'))
})

function isGroupExpanded(key: string): boolean {
  return expandedGroupKeys.value.has(key)
}

function toggleGroup(key: string) {
  const next = new Set(expandedGroupKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedGroupKeys.value = next
}

const searchBeginDate = ref('')
const searchEndDate = ref('')

/** 未通过必填校验时，对应日期输入框红框提示 */
const dateBeginInvalid = ref(false)
const dateEndInvalid = ref(false)

function onDateBeginChange() {
  dateBeginInvalid.value = false
  if (
    error.value === '起始日期不能晚于结束日期'
  ) {
    error.value = null
  }
}

function onDateEndChange() {
  dateEndInvalid.value = false
  if (
    error.value === '起始日期不能晚于结束日期'
  ) {
    error.value = null
  }
}

function formatYmd(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function resolveDefaultDateRange(): { begin: string; end: string } {
  const endDate = new Date()
  const beginDate = new Date(endDate)
  beginDate.setDate(beginDate.getDate() - 14)
  return { begin: formatYmd(beginDate), end: formatYmd(endDate) }
}

onMounted(() => {
  // 初始化：默认查询前两周～今天，并立即拉取一次列表
  const def = resolveDefaultDateRange()
  searchBeginDate.value = def.begin
  searchEndDate.value = def.end
  void handleSearch()
})

async function handleSearch() {
  if (loading.value) return
  error.value = null
  dateBeginInvalid.value = false
  dateEndInvalid.value = false

  let begin = searchBeginDate.value.trim()
  let end = searchEndDate.value.trim()

  // 用户未填完整日期范围时：默认“两周前～今天”，并回填到输入框
  if (!begin || !end) {
    const def = resolveDefaultDateRange()
    begin = def.begin
    end = def.end
    searchBeginDate.value = begin
    searchEndDate.value = end
  }

  if (begin > end) {
    dateBeginInvalid.value = true
    dateEndInvalid.value = true
    error.value = '起始日期不能晚于结束日期'
    return
  }

  loading.value = true
  try {
    const rows = await listSmartClassroomImportVideos({
      search_begin_date: begin,
      search_end_date: end,
    })
    expandedGroupKeys.value = new Set()
    items.value = rows.map((row) => ({
      course_id: String(row.course_id ?? ''),
      sub_id: String(row.sub_id ?? ''),
      course_name: row.course_name ?? '',
      sub_title: String(row.sub_title ?? '').trim(),
      teacher_name: row.teacher_name ?? '',
      class_begin: row.class_begin ?? '',
      campus_name: row.campus_name,
      room_name: row.room_name,
      class_over: row.class_over,
      thumb: row.thumb,
    }))
  } catch (e) {
    // 上线环境不在页面直接展示报错，保留 console 便于排查
    console.error('[SmartClassroom] 查询课程失败', e)
    error.value = null
    items.value = []
  } finally {
    loading.value = false
  }
}

async function handleImport(it: { course_id: string; sub_id: string }) {
  if (importingSubId.value !== null) return
  importingSubId.value = it.sub_id
  importingProgress.value = null
  error.value = null
  const controller = new AbortController()
  importAbortController.value = controller
  const importId = genImportId()
  currentImportId.value = importId
  let navigated = false
  try {
    const videoId = await importSmartClassroomVideo(
      { course_id: it.course_id, sub_id: it.sub_id },
      {
        onProgress(progress) {
          importingProgress.value = progress
        },
        onEnd(id) {
          // 接收到 end 后立即跳转到新版报告详情页；分析改为在详情页手动触发
          navigated = true
          router.push(`/resource-analysis/report-new/${encodeURIComponent(id)}`)
        },
      },
      { signal: controller.signal, importId },
    )
    if (!navigated) {
      router.push(`/resource-analysis/report-new/${encodeURIComponent(videoId)}`)
    }
  } catch (e) {
    // 用户主动取消（AbortError）属于正常操作，不记为失败
    const isAbort = e instanceof DOMException && e.name === 'AbortError'
    if (!isAbort) {
      // 上线环境不在页面直接展示报错，保留 console 便于排查
      console.error('[SmartClassroom] 导入视频失败', e)
    }
    error.value = null
  } finally {
    importingSubId.value = null
    importingProgress.value = null
    importAbortController.value = null
    currentImportId.value = null
  }
}

/**
 * 取消正在进行的智云课堂视频导入。
 * 先通知后端写取消标记（best-effort，避免后端继续下载并落库），再 abort 前端 SSE
 * 连接以立即复位 UI；状态在 handleImport 的 finally 中复位。
 */
function handleCancelImport() {
  const importId = currentImportId.value
  if (importId) void cancelSmartClassroomImport(importId)
  importAbortController.value?.abort()
}

// 进入页面会用默认日期范围自动搜索一次；用户可改条件后再次点击「搜索」。
</script>

<style scoped>
/* 页面壳层与顶栏/内容区边距见 assets/core-page-layout.css（与「我的资源」一致） */

.sc-course-list-view.core-app-page .page-title {
  font-size: 20px;
  font-weight: 600;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: #333;
  text-decoration: none;
  transition: color 0.2s;
  border-radius: 4px;
  flex-shrink: 0;
}
.back-btn:hover {
  color: #c5d9ff;
}

.loading-container,
.error-container {
  text-align: center;
  padding: 48px 24px;
  color: #666;
}
.retry-btn {
  margin-top: 12px;
  padding: 8px 16px;
  background: #c5d9ff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.panel-wrap {
  width: 100%;
}

.course-panel {
  width: 100%;
  max-width: none;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 20px 22px 24px;
  box-sizing: border-box;
}

.panel-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.search-bar {
  width: 100%;
  max-width: 100%;
  margin-bottom: 14px;
  box-sizing: border-box;
}

/* 与标题区、列表同宽；列用 minmax(0, fr) 防止子项最小宽度把整行撑出面板 */
.search-grid {
  width: 100%;
  max-width: 100%;
  display: grid;
  grid-template-columns:
    minmax(0, 1fr)
    minmax(0, 1fr)
    auto;
  gap: 8px;
  align-items: end;
  box-sizing: border-box;
}

.field {
  min-width: 0;
}

.field--wide {
  min-width: 0;
}

.field--action {
  justify-self: end;
}

.field-label {
  font-size: 12px;
  font-weight: 400;
  color: #8a8f9c;
  margin: 0 0 6px 6px;
  text-align: left;
  user-select: none;
  white-space: nowrap;
}

.req-star {
  color: #c62828;
  margin-left: 2px;
  font-weight: 600;
}

.field-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid #e6e8ef;
  background: #fafbfd;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.35;
  color: #333;
  outline: none;
  box-sizing: border-box;
}

.field-input:focus {
  border-color: rgba(19, 88, 228, 0.35);
  background: #fff;
}

.field-input--error {
  border-color: #c62828 !important;
  background: #fff5f5;
}

.search-action {
  height: 40px;
  padding: 0 16px;
  border-radius: 999px;
  border: none;
  background: rgba(19, 88, 228, 0.65);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: filter 0.2s;
}

.search-action:hover:not(:disabled) {
  filter: brightness(1.05);
}

.search-action:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-inline {
  padding: 10px 0 14px;
  color: #666;
  font-size: 13px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #333;
}

.panel-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #888;
}

.error-inline {
  margin: 8px 0 12px;
  color: #c62828;
  font-size: 13px;
}

.empty-inline {
  text-align: center;
  padding: 28px 12px;
  color: #888;
  font-size: 14px;
}

.accordion-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}


.accordion-group {
  width: 100%;
  border-radius: 12px;
  border: 1px solid #e8ecf4;
  background: rgba(208, 224, 255, 0.22);
  overflow: hidden;
  box-sizing: border-box;
}

.accordion-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 52px;
  padding: 4px 6px 4px 4px;
  box-sizing: border-box;
}

.accordion-group-header.is-expanded {
  background: #fff;
  border-bottom: 1px solid #e8ecf4;
}

.accordion-group-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
}

.accordion-group-left {
  min-width: 0;
}

.expand-icon {
  transition: transform 0.2s ease;
}

.expand-icon.is-expanded {
  transform: rotate(180deg);
}

.accordion-group-body {
  list-style: none;
  margin: 0;
  padding: 8px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fff;
}

.session-item {
  list-style: none;
}

.session-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #e8ecf4;
  background: #fafbfd;
}

.session-left {
  flex: 1 1 auto;
  min-width: 0;
}

.session-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  line-height: 1.4;
}

.session-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}

.session-right {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.accordion-item {
  width: 100%;
}

.accordion-card {
  width: 100%;
  border-radius: 12px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color 0.2s, box-shadow 0.2s, border-color 0.2s;
  background: rgba(208, 224, 255, 0.3);
  box-sizing: border-box;
}

.accordion-item.expanded .accordion-card {
  background: #fff;
  border-color: #e8ecf4;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}

.accordion-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 10px 14px 10px 16px;
}

.accordion-item.expanded .accordion-inner {
  align-items: flex-start;
  padding-top: 12px;
  padding-bottom: 12px;
}

.accordion-left {
  flex: 1 1 auto;
  min-width: 0;
  text-align: left;
}

.course-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
}

.video-count {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 400;
  color: #888;
  line-height: 1.4;
}

.accordion-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-only {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #555;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}
.icon-only:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #333;
}

.detail-btn {
  padding: 8px 14px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  cursor: pointer;
  white-space: nowrap;
  background: rgba(19, 88, 228, 0.65);
  transition: background-color 0.2s, filter 0.2s;
}
.detail-btn:hover {
  filter: brightness(1.05);
}

.cancel-btn {
  padding: 8px 14px;
  border: 1px solid #e3c0c0;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: #c62828;
  cursor: pointer;
  white-space: nowrap;
  background: #fff;
  transition: background-color 0.2s, border-color 0.2s;
}
.cancel-btn:hover {
  background: #fdecec;
  border-color: #c62828;
}

/* 测试按钮：轻量样式（白底描边胶囊），与主按钮区分开。 */
.detail-btn.demo-btn {
  background: #ffffff;
  color: #1358e4;
  border: 1px solid #C5D9FF;
  border-radius: 20px;
  padding: 8px 16px;
  align-self: flex-start;
}
.detail-btn.demo-btn:hover {
  filter: none;
  background: #f8f9ff;
  border-color: #1358e4;
}

.import-progress-wrap {
  margin-top: 8px;
  width: 210px;
}

.import-progress-bar {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #e8eef9;
  overflow: hidden;
}

.import-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #6f9cff 0%, #1358e4 100%);
  transition: width 0.2s ease;
}


@media (max-width: 960px) {
  .search-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .field--action {
    grid-column: 1 / -1;
    justify-self: stretch;
  }
  .search-action {
    width: 100%;
  }
}

@media (max-width: 768px) {
  .sc-course-list-view.core-app-page .page-title {
    font-size: 18px;
  }

  .panel-header-row {
    flex-direction: column;
    align-items: stretch;
  }
  .search-grid {
    grid-template-columns: 1fr;
  }
  .field--action {
    justify-self: stretch;
  }
  .field-input { border-radius: 12px; }
  .search-action { width: 100%; border-radius: 12px; }
}

@media (max-width: 480px) {
  .sc-course-list-view.core-app-page .page-title {
    font-size: 16px;
  }
}
</style>
