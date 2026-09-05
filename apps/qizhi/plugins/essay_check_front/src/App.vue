<template>
  <div class="app-header">
    <h1> 浙江大学本科毕业论文检查系统（Beta测试版）</h1>
  </div>
  <div class="main">
    <div class="search-bar">
      <el-input v-model="taskId" placeholder="输入任务ID" clearable style="width: 400px" size="large"
                @keyup.enter="fetchTask" />
      <el-button type="primary" size="large" @click="fetchTask" :loading="loading">查询</el-button>
      <el-button size="large" @click="autoRefresh = !autoRefresh" :type="autoRefresh ? 'success' : ''">
        {{ autoRefresh ? '✅' : '⏸' }} 自动刷新
      </el-button>
    </div>

    <template v-if="task">
      <div class="task-info">
        <div class="header">
          <h2>任务信息</h2>
          <el-tag :type="statusType(task.status)" size="large">{{ task.status }}</el-tag>
        </div>

        <el-descriptions :column="3" border size="default" style="margin-bottom: 20px">
          <el-descriptions-item label="文件名">{{ task.filename }}</el-descriptions-item>
          <el-descriptions-item label="总页数">{{ task.total_pages }}</el-descriptions-item>
          <el-descriptions-item label="当前阶段">{{ task.current_stage }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ task.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ task.updated_at }}</el-descriptions-item>
          <el-descriptions-item label="Task ID">{{ task.task_id }}</el-descriptions-item>
        </el-descriptions>

        <div class="stat-row">
          <div class="stat-card total">
            <div class="value">{{ task.progress.total_pages }}</div>
            <div class="label">总页数</div>
          </div>
          <div class="stat-card done">
            <div class="value">{{ task.progress.completed_pages }}</div>
            <div class="label">已完成</div>
          </div>
          <div class="stat-card fail">
            <div class="value">{{ task.progress.failed_pages }}</div>
            <div class="label">失败</div>
          </div>
          <div class="stat-card pending">
            <div class="value">{{ task.progress.pending_pages }}</div>
            <div class="label">处理中</div>
          </div>
        </div>

        <el-progress :percentage="task.progress.percentage" :stroke-width="16" :color="'#67c23a'" striped />
        <div class="progress-text">处理进度：{{ task.progress.percentage }}%</div>
      </div>

      <div class="report-section" v-if="report">
        <h3>审查报告</h3>
        <span class="score-badge" :class="'score-' + report.overall_score">{{ report.overall_score }}</span>
        <p style="margin-bottom: 16px; color: #606266; font-size: 14px; line-height: 1.6;">{{ report.summary }}</p>

        <el-collapse v-model="activeDomains">
          <el-collapse-item v-for="(domain, idx) in report.check_domains" :key="idx" :title="domain.domain" :name="idx">
            <div v-for="(cp, i) in domain.check_points" :key="i" class="check-item" style="border-top: 1px solid #f0f0f0;">
              <span class="icon">{{ cp.passed ? '✅' : '❌' }}</span>
              <div>
                <div class="name">{{ cp.name }}</div>
                <div class="detail" v-if="cp.detail">{{ cp.detail }}</div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <div v-if="report.reference_issues && report.reference_issues.length" style="margin-top: 20px;">
          <h3 style="color: #f56c6c;">⚠️ 参考文献问题</h3>
          <ul style="margin-top: 8px; padding-left: 20px; color: #606266; font-size: 13px; line-height: 1.8;">
            <li v-for="(issue, i) in report.reference_issues" :key="i">{{ issue }}</li>
          </ul>
        </div>

        <div v-if="report.recommendations && report.recommendations.length" style="margin-top: 20px;">
          <h3 style="color: #409eff;">💡 修改建议</h3>
          <ul style="margin-top: 8px; padding-left: 20px; color: #606266; font-size: 13px; line-height: 1.8;">
            <li v-for="(rec, i) in report.recommendations" :key="i">{{ rec }}</li>
          </ul>
        </div>
      </div>

      <!-- Inline Page Viewer -->
      <div class="page-viewer-section" v-loading="viewerLoading">
        <div class="viewer-toolbar">
          <h3>页面检查</h3>
          <div class="viewer-controls">
            <el-button @click="goPrev" :disabled="currentViewIndex <= 0" circle>
              <el-icon><ArrowLeft /></el-icon>
            </el-button>
            <div class="viewer-jump">
              <span>第</span>
              <el-input-number v-model="currentViewPage" :min="1" :max="totalPages" size="small"
                               controls-position="right" style="width: 80px"
                               @change="jumpToPage" />
              <span>/ {{ totalPages }} 页</span>
            </div>
            <el-button @click="goNext" :disabled="currentViewIndex >= totalPages - 1" circle>
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
          <div class="viewer-filter">
            <el-checkbox v-model="viewOnlyFailed" @change="onViewFilterChange">只看检查不通过</el-checkbox>
          </div>
        </div>

        <div class="viewer-layout">
          <!-- Left: image -->
          <div class="viewer-image-pane">
            <img v-if="currentImageUrl" :src="currentImageUrl" :alt="`第 ${currentViewPage} 页`" />
            <div v-else class="viewer-image-placeholder">
              <el-icon class="loading-icon"><Loading /></el-icon>
              <span>加载中...</span>
            </div>
            <div class="viewer-page-label">
              <el-tag :type="statusType(currentPageData?.status)" size="small">{{ currentPageData?.status }}</el-tag>
              <span class="page-type">{{ pageTypeLabel(currentPageData?.page_type) || '未知' }}</span>
            </div>
          </div>

          <!-- Right: check results -->
          <div class="viewer-results-pane">
            <div class="results-header">
              <h4>检查结果</h4>
              <span class="results-count">{{ displayedResults.length }} 项</span>
            </div>
            <div class="results-list">
              <div v-for="(cp, i) in displayedResults" :key="i"
                   class="result-item" :class="cp.passed ? 'passed' : 'failed'">
                <span class="result-icon">{{ cp.passed ? '✅' : '❌' }}</span>
                <div class="result-body">
                  <div class="result-name">{{ cp.check_point || cp.name }}</div>
                  <div class="result-detail" v-if="cp.detail">{{ cp.detail }}</div>
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

    <div v-else class="empty-state">
      <p style="font-size: 48px;">🔍</p>
      <p>请输入任务ID查询状态</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, onMounted, h } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Loading } from '@element-plus/icons-vue'

// Touch icons so TS doesn't complain
void h(ArrowLeft); void h(ArrowRight); void h(Loading)

const API_BASE = '/api/v1'

const taskId = ref('')
const task = ref(null)
const report = ref(null)
const loading = ref(false)
const autoRefresh = ref(false)
const activeDomains = ref([])
let timer = null

// Viewer state
const currentViewPage = ref(1)
const currentImageUrl = ref('')
const viewOnlyFailed = ref(false)
const viewerLoading = ref(false)

const statusType = (s) => {
  const map = {
    uploaded: '', processing: 'warning', summarizing: 'warning',
    completed: 'success', failed: 'danger', pending: 'info',
    classifying: 'warning', classified: '', checking: 'warning'
  }
  return map[s] || ''
}

const pageTypeLabel = (t) => {
  const map = {
    cover: '封面', commitment: '承诺书', abstract_cn: '中文摘要',
    abstract_en: '英文摘要', toc: '目录', body: '正文',
    conclusion: '结论', references: '参考文献', appendix: '附录',
    task_sheet: '任务书', assessment_form: '考核表',
    expert_review: '专家评阅', defense_record: '答辩记录', unknown: '未知'
  }
  return map[t]
}

// All pages data (flat list by page_number)
const pagesMap = computed(() => {
  const m = {}
  for (const p of pages.value) m[p.page_number] = p
  return m
})

const totalPages = computed(() => task.value?.total_pages || 0)

// Current page data
const currentPageData = computed(() => {
  return pagesMap.value[currentViewPage.value] || null
})

const hasFailedChecks = (page) => {
  if (!page || !page.check_results || !page.check_results.length) return false
  return page.check_results.some(cp => !cp.passed)
}

// Visible pages: filtered by "only failed" checkbox
const visiblePages = computed(() => {
  const pages = []
  for (let i = 1; i <= totalPages.value; i++) {
    const page = pagesMap.value[i]
    if (page) {
      if (!viewOnlyFailed.value || hasFailedChecks(page)) {
        pages.push(i)
      }
    }
  }
  return pages
})

const currentViewIndex = computed(() => {
  return visiblePages.value.indexOf(currentViewPage.value)
})

const displayedResults = computed(() => {
  const page = currentPageData.value
  if (!page || !page.check_results) return []
  if (viewOnlyFailed.value) return page.check_results.filter(cp => !cp.passed)
  return page.check_results
})

// Fetch all pages once when task is loaded
const pages = ref([])

const fetchTask = async () => {
  if (!taskId.value) return
  loading.value = true
  report.value = null
  try {
    const res = await fetch(`${API_BASE}/tasks/${taskId.value}`)
    if (!res.ok) { ElMessage.error('任务不存在或查询失败'); return }
    task.value = await res.json()

    if (task.value.status === 'completed') {
      try {
        const rRes = await fetch(`${API_BASE}/tasks/${taskId.value}/result`)
        if (rRes.ok) report.value = await rRes.json()
      } catch {}
    }

    // Fetch all pages at once
    try {
      const pRes = await fetch(`${API_BASE}/tasks/${taskId.value}/pages?page=1&page_size=1000`)
      if (pRes.ok) {
        const data = await pRes.json()
        pages.value = data.pages
        currentViewPage.value = 1
        loadCurrentImage()
      }
    } catch {}
  } catch {
    ElMessage.error('网络错误，请检查后端是否运行')
  } finally {
    loading.value = false
  }
}

const loadCurrentImage = () => {
  const page = pagesMap.value[currentViewPage.value]
  currentImageUrl.value = page?.image_url || ''
}

const goToPage = (num) => {
  if (num < 1 || num > totalPages.value) return
  currentViewPage.value = num
  loadCurrentImage()
}

const goPrev = () => {
  const idx = currentViewIndex.value
  if (idx > 0) goToPage(visiblePages.value[idx - 1])
}

const goNext = () => {
  const idx = currentViewIndex.value
  if (idx < visiblePages.value.length - 1) goToPage(visiblePages.value[idx + 1])
}

const jumpToPage = (val) => {
  if (val) goToPage(val)
}

const onViewFilterChange = () => {
  // If current page is hidden by filter, jump to first visible
  if (viewOnlyFailed.value && !hasFailedChecks(currentPageData.value)) {
    const next = visiblePages.value[0]
    if (next) goToPage(next)
  }
}

watch(autoRefresh, (val) => {
  if (val) {
    timer = setInterval(() => { if (taskId.value) fetchTask() }, 3000)
  } else {
    clearInterval(timer)
  }
})

onUnmounted(() => { clearInterval(timer) })

// Keyboard navigation
onMounted(() => {
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') goPrev()
    if (e.key === 'ArrowRight') goNext()
  })
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; min-height: 100vh; }
.app-header { background: #fff; padding: 20px 32px; box-shadow: 0 1px 4px rgba(0,0,0,.08); display: flex; align-items: center; gap: 16px; }
.app-header h1 { font-size: 20px; color: #303133; }
.main { max-width: 1400px; margin: 24px auto; padding: 0 20px; }
.search-bar { background: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); display: flex; gap: 12px; align-items: flex-end; }
.task-info { background: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); margin-top: 20px; }
.task-info .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.task-info .header h2 { font-size: 16px; color: #303133; }
.stat-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { flex: 1; background: #f5f7fa; border-radius: 6px; padding: 16px; text-align: center; }
.stat-card .value { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.stat-card .label { font-size: 12px; color: #909399; }
.stat-card.total .value { color: #409eff; }
.stat-card.done .value { color: #67c23a; }
.stat-card.fail .value { color: #f56c6c; }
.stat-card.pending .value { color: #e6a23c; }
.progress-text { font-size: 14px; color: #606266; margin-bottom: 16px; }
.report-section { background: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); margin-top: 20px; }
.report-section h3 { font-size: 16px; margin-bottom: 16px; color: #303133; }
.score-badge { display: inline-block; padding: 4px 16px; border-radius: 4px; font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.score-合格 { background: #f0f9eb; color: #67c23a; }
.score-需修改 { background: #fdf6ec; color: #e6a23c; }
.score-不合格 { background: #fef0f0; color: #f56c6c; }
.check-item { padding: 10px 16px; border-top: 1px solid #ebeef5; display: flex; gap: 12px; align-items: flex-start; }
.check-item .icon { flex-shrink: 0; margin-top: 2px; }
.check-item .name { font-size: 13px; color: #606266; font-weight: 500; }
.check-item .detail { font-size: 12px; color: #909399; margin-top: 4px; }
.empty-state { text-align: center; padding: 60px 20px; color: #909399; }

/* Page Viewer */
.page-viewer-section { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.06); margin-top: 20px; overflow: hidden; }
.viewer-toolbar { display: flex; align-items: center; gap: 16px; padding: 16px 24px; border-bottom: 1px solid #ebeef5; }
.viewer-toolbar h3 { font-size: 16px; color: #303133; margin: 0; }
.viewer-controls { display: flex; align-items: center; gap: 8px; }
.viewer-jump { display: flex; align-items: center; gap: 4px; color: #606266; font-size: 13px; }
.viewer-filter { margin-left: auto; }

.viewer-layout { display: flex; height: 75vh; }
.viewer-image-pane { width: 60%; background: #1a1a2e; display: flex; align-items: center; justify-content: center; position: relative; overflow: auto; }
.viewer-image-pane img { max-width: 100%; max-height: 100%; object-fit: contain; }
.viewer-image-placeholder { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #888; gap: 12px; }
.viewer-image-placeholder .loading-icon { font-size: 32px; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.viewer-page-label { position: absolute; bottom: 0; left: 0; right: 0; display: flex; align-items: center; gap: 8px; padding: 8px 16px; background: rgba(0,0,0,0.6); color: #ccc; font-size: 13px; }

.viewer-results-pane { width: 40%; display: flex; flex-direction: column; border-left: 1px solid #ebeef5; }
.results-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid #eee; }
.results-header h4 { font-size: 15px; color: #303133; }
.results-count { font-size: 13px; color: #909399; }

.results-list { flex: 1; overflow-y: auto; padding: 0; }
.result-item { display: flex; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }
.result-item.passed { background: #f0f9eb; }
.result-item.failed { background: #fef0f0; }
.result-icon { font-size: 16px; flex-shrink: 0; margin-top: 2px; }
.result-body { flex: 1; }
.result-name { font-size: 14px; font-weight: 500; color: #303133; margin-bottom: 4px; }
.result-detail { font-size: 12px; color: #606266; line-height: 1.6; }
.no-results { text-align: center; padding: 40px 20px; color: #909399; font-size: 14px; }
</style>
