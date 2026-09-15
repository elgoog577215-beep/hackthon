<template>
  <div class="admin-dashboard">
    <div class="admin-toolbar">
      <h2 class="admin-page-title">数据驾驶舱</h2>
      <div class="admin-as-of" v-if="stats?.as_of">数据时间：{{ stats.as_of }}</div>
    </div>

    <section class="dashboard-stats" aria-label="核心指标">
      <div class="stat-card" v-for="card in statCards" :key="card.key">
        <div class="stat-card-label" :title="card.tooltip">{{ card.label }}</div>
        <div class="stat-card-value">
          <template v-if="statsLoading">—</template>
          <template v-else>{{ formatNumber(card.value) }}</template>
        </div>
        <div class="stat-card-hint">{{ card.hint }}</div>
      </div>
    </section>

    <section class="usage-section" aria-label="用户行为与任务转化">
      <div class="usage-toolbar">
        <h3 class="usage-title">用户行为与任务转化</h3>
        <span class="stat-card-hint">与下方统计共用最近 {{ usageDays }} 天范围</span>
      </div>
      <div class="dashboard-stats behavior-stats">
        <div class="stat-card" v-for="card in behaviorCards" :key="card.key">
          <div class="stat-card-label" :title="card.tooltip">{{ card.label }}</div>
          <div class="stat-card-value">
            <template v-if="behaviorLoading">—</template>
            <template v-else>{{ card.value }}</template>
          </div>
          <div class="stat-card-hint">{{ card.hint }}</div>
        </div>
      </div>
    </section>

    <section class="usage-section" aria-label="功能使用统计">
      <div class="usage-toolbar">
        <h3 class="usage-title">功能使用排序</h3>
        <select v-model.number="usageDays" class="usage-range-select" @change="loadUsage">
          <option :value="1">今天</option>
          <option :value="7">近 7 天</option>
          <option :value="30">近 30 天</option>
        </select>
      </div>
      <div class="usage-grid">
        <div class="usage-card">
          <div class="usage-card-title">常驻 + 智能体（按操作次数）</div>
          <div v-if="usageLoading" class="usage-status">加载中...</div>
          <BarChart v-else :data="featureChartData" />
        </div>
        <div class="usage-card">
          <div class="usage-card-title">智能体使用 Top 10</div>
          <div v-if="usageLoading" class="usage-status">加载中...</div>
          <BarChart v-else :data="agentChartData" />
        </div>
      </div>
    </section>

    <section class="user-list-section" aria-label="用户明细">
      <div class="user-list-toolbar">
        <h3 class="user-list-title">用户明细</h3>
        <div class="user-list-actions">
          <input
            v-model="keyword"
            type="text"
            class="user-list-search"
            placeholder="搜索 姓名 / 学工号 / 学院 / 手机号 / 邮箱"
            @keydown.enter="resetAndLoad"
          />
          <button type="button" class="btn-secondary" @click="resetAndLoad" :disabled="usersLoading">查询</button>
          <button type="button" class="btn-primary" @click="onExport" :disabled="exporting">
            {{ exporting ? '导出中...' : '导出 Excel' }}
          </button>
        </div>
      </div>

      <div class="user-table-wrap">
        <table class="user-table" v-if="users.length > 0">
          <thead>
            <tr>
              <th>姓名</th>
              <th>学工号</th>
              <th>学院</th>
              <th>手机号</th>
              <th>邮箱</th>
              <th>注册时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.name || '—' }}</td>
              <td>{{ u.zju_id || '—' }}</td>
              <td>{{ u.department || '—' }}</td>
              <td>{{ u.phone || '—' }}</td>
              <td>{{ u.email || '—' }}</td>
              <td>{{ u.create_time || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="usersLoading" class="user-table-status">加载中...</div>
        <div v-else-if="usersError" class="user-table-status error">{{ usersError }}</div>
        <div v-else class="user-table-status">暂无用户数据</div>

        <div class="user-table-footer" v-if="users.length > 0">
          <span class="user-table-count">已加载 {{ users.length }} 条</span>
          <button
            type="button"
            class="btn-secondary"
            v-if="hasMore"
            @click="loadMore"
            :disabled="usersLoading"
          >
            {{ usersLoading ? '加载中...' : '加载更多' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BarChart from '../../components/charts/BarChart.vue'
import type { BarChartItem } from '../../components/charts/BarChart.vue'
import {
  exportAdminUsers,
  fetchAdminUsers,
  fetchAgentUsage,
  fetchBehaviorMetrics,
  fetchDashboardStats,
  fetchFeatureUsage,
  triggerBlobDownload,
} from '../../api/admin'
import type {
  AdminUserDetail,
  AgentUsageItem,
  BehaviorMetrics,
  DashboardStats,
  FeatureUsageItem,
} from '../../api/types'

const PAGE_SIZE = 100

const stats = ref<DashboardStats | null>(null)
const statsLoading = ref(false)
const behavior = ref<BehaviorMetrics | null>(null)
const behaviorLoading = ref(false)

const users = ref<AdminUserDetail[]>([])
const usersLoading = ref(false)
const usersError = ref<string | null>(null)
const keyword = ref('')
const offset = ref(0)
const hasMore = ref(false)

const exporting = ref(false)

const usageDays = ref(7)
const usageLoading = ref(false)
const featureUsage = ref<FeatureUsageItem[]>([])
const agentUsage = ref<AgentUsageItem[]>([])

const featureChartData = computed<BarChartItem[]>(() =>
  featureUsage.value.map((it) => ({
    label: it.pending ? `${it.label}（待上线）` : it.label,
    value: it.count,
  })),
)

const agentChartData = computed<BarChartItem[]>(() =>
  agentUsage.value.map((it) => ({
    label: it.title,
    value: it.count,
  })),
)

const behaviorCards = computed(() => {
  const value = behavior.value
  const scroll75 = value?.scroll_reach['75'] ?? 0
  const scroll75Rate = value?.page_views ? scroll75 / value.page_views * 100 : 0
  return [
    { key: 'pv', label: '页面浏览量', value: formatNumber(value?.page_views ?? 0), hint: '全站路由进入次数', tooltip: '按 page_view 事件统计，不包含 URL 查询参数' },
    { key: 'uv', label: '访问用户', value: formatNumber(value?.unique_visitors ?? 0), hint: '登录与匿名访问者去重', tooltip: '登录用户按 user_id，匿名用户按 anonymous_id 去重' },
    { key: 'engagement', label: '平均活跃停留', value: `${value?.average_engaged_seconds ?? 0} 秒`, hint: '排除隐藏标签页时间', tooltip: '基于页面可见期间的低频心跳与离开汇总' },
    { key: 'bounce', label: '跳出率', value: `${value?.bounce_rate ?? 0}%`, hint: '单页且活跃少于 10 秒', tooltip: '单页面、低参与会话 / 全部会话' },
    { key: 'completion', label: '任务完成率', value: `${value?.task_completion_rate ?? 0}%`, hint: `${value?.task_succeeded ?? 0}/${value?.task_started ?? 0} 个任务`, tooltip: '成功 workflow_id / 已开始 workflow_id' },
    { key: 'failure', label: '任务失败率', value: `${value?.task_failure_rate ?? 0}%`, hint: `${value?.task_failed ?? 0} 个失败任务`, tooltip: '失败 workflow_id / 已开始 workflow_id；取消单独记录，不计失败' },
    { key: 'cancelled', label: '任务取消率', value: `${value?.task_cancellation_rate ?? 0}%`, hint: `${value?.task_cancelled ?? 0} 个取消任务`, tooltip: '断开或主动取消的 workflow_id / 已开始 workflow_id' },
    { key: 'unfinished', label: '未结束任务', value: formatNumber(value?.unfinished_tasks ?? 0), hint: value?.latest_event_at ? `最新事件 ${value.latest_event_at}` : '暂未收到事件', tooltip: '已开始但尚无成功、失败或取消终态的任务' },
    { key: 'scroll75', label: '滚动到 75%', value: `${scroll75Rate.toFixed(1)}%`, hint: `${scroll75} 个页面实例`, tooltip: '达到 75% 深度的页面实例 / 页面浏览量' },
  ]
})

const statCards = computed(() => [
  {
    key: 'total',
    label: '累计用户',
    value: stats.value?.total_users ?? 0,
    hint: '截至当前的累计注册用户数',
    tooltip: '所有曾通过统一身份认证登录过本应用的用户',
  },
  {
    key: 'dau',
    label: '日活',
    value: stats.value?.dau ?? 0,
    hint: '当日有功能使用记录的用户数',
    tooltip: '当日（Asia/Shanghai 00:00 起）在 user_operation_logs 留下任意一条记录的去重用户数（含资源生成 / 视频分析 / 我的课程访问 / 智能体点击 / 智能对话 等）',
  },
  {
    key: 'wau',
    label: '周活',
    value: stats.value?.wau ?? 0,
    hint: '本周（周一起）有功能使用记录的用户数',
    tooltip: '本周（周一 00:00 起）在 user_operation_logs 留下任意一条记录的去重用户数',
  },
])

function formatNumber(value: number): string {
  return value.toLocaleString('zh-CN')
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await fetchDashboardStats()
  } catch (e) {
    console.error('[Admin] 加载指标失败', e)
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function loadUsage() {
  usageLoading.value = true
  behaviorLoading.value = true
  try {
    const [features, agents, behaviorResult] = await Promise.all([
      fetchFeatureUsage(usageDays.value),
      fetchAgentUsage(usageDays.value, 10),
      fetchBehaviorMetrics(usageDays.value),
    ])
    featureUsage.value = features
    agentUsage.value = agents
    behavior.value = behaviorResult
  } catch (e) {
    console.error('[Admin] 加载使用数据失败', e)
    featureUsage.value = []
    agentUsage.value = []
    behavior.value = null
  } finally {
    usageLoading.value = false
    behaviorLoading.value = false
  }
}

async function loadUsers(append: boolean) {
  usersLoading.value = true
  usersError.value = null
  try {
    const list = await fetchAdminUsers({
      keyword: keyword.value || null,
      limit: PAGE_SIZE,
      offset: append ? offset.value : 0,
    })
    if (append) {
      users.value = [...users.value, ...list]
    } else {
      users.value = list
      offset.value = 0
    }
    offset.value += list.length
    hasMore.value = list.length === PAGE_SIZE
  } catch (e) {
    usersError.value = e instanceof Error ? e.message : '加载用户失败'
  } finally {
    usersLoading.value = false
  }
}

async function resetAndLoad() {
  offset.value = 0
  await loadUsers(false)
}

async function loadMore() {
  await loadUsers(true)
}

async function onExport() {
  exporting.value = true
  try {
    const blob = await exportAdminUsers(keyword.value || null)
    const date = new Date().toISOString().slice(0, 10)
    triggerBlobDownload(blob, `用户明细_${date}.xlsx`)
  } catch (e) {
    console.error('[Admin] 导出用户失败', e)
    alert(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadStats(), loadUsers(false), loadUsage()])
})
</script>

<style scoped>
.admin-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.admin-toolbar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.admin-page-title {
  font-size: 22px;
  font-weight: 700;
  color: #1a2540;
  margin: 0;
}

.admin-as-of {
  color: #8a93a6;
  font-size: 13px;
}

.dashboard-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  background: #ffffff;
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 140px;
}

.stat-card-label {
  font-size: 14px;
  color: #4b5670;
  font-weight: 600;
}

.stat-card-value {
  font-size: 48px;
  font-weight: 700;
  color: #1a2540;
  line-height: 1.1;
  letter-spacing: -0.01em;
}

.stat-card-hint {
  font-size: 12px;
  color: #8a93a6;
}

.usage-section {
  background: #ffffff;
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
}

.usage-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.usage-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1a2540;
}

.usage-range-select {
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #d8deea;
  font-size: 13px;
  color: #1a2540;
  background: #fff;
}

.usage-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.usage-card {
  border: 1px solid #eef1f6;
  border-radius: 12px;
  padding: 16px 20px;
  background: #fcfdff;
}

.usage-card-title {
  font-size: 13px;
  color: #4b5670;
  font-weight: 600;
  margin-bottom: 12px;
}

.usage-status {
  padding: 24px;
  text-align: center;
  color: #8a93a6;
  font-size: 13px;
}

.user-list-section {
  background: #ffffff;
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
}

.user-list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.user-list-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1a2540;
}

.user-list-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.user-list-search {
  width: 280px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid #d8deea;
  padding: 0 12px;
  font-size: 14px;
  color: #1a2540;
  background: #fff;
}

.user-list-search:focus {
  outline: none;
  border-color: #4467d9;
}

.btn-primary,
.btn-secondary {
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 14px;
  border: none;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.btn-primary {
  background: #2f4aa6;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #243a85;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f0f4fb;
  color: #1f3c8b;
}

.btn-secondary:hover:not(:disabled) {
  background: #dde6f8;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.user-table-wrap {
  overflow-x: auto;
}

.user-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}

.user-table thead th {
  background: #f5f7fb;
  color: #4b5670;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
}

.user-table tbody td {
  padding: 12px;
  color: #1a2540;
  border-bottom: 1px solid #f0f3f9;
}

.user-table tbody tr:hover td {
  background: #fafbfe;
}

.user-table-status {
  padding: 24px;
  text-align: center;
  color: #8a93a6;
  font-size: 14px;
}

.user-table-status.error {
  color: #c62828;
}

.user-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid #f0f3f9;
  margin-top: 8px;
}

.user-table-count {
  font-size: 13px;
  color: #8a93a6;
}

@media (max-width: 960px) {
  .dashboard-stats {
    grid-template-columns: 1fr;
  }
  .usage-grid {
    grid-template-columns: 1fr;
  }
  .user-list-search {
    width: 100%;
  }
}
</style>
