<template>
  <div class="admin-audit-logs-view">
    <div class="admin-toolbar">
      <h2 class="admin-page-title">审计日志</h2>
      <div class="admin-toolbar-actions">
        <select v-model="filters.actor_type" class="filter-select" :title="'执行者类型'">
          <option :value="null">全部类型</option>
          <option value="admin">admin</option>
          <option value="user">user</option>
          <option value="agent">agent</option>
          <option value="system">system</option>
        </select>
        <input
          v-model.trim="filters.actor_id"
          type="text"
          class="filter-input filter-input-wide"
          placeholder="执行者 ID（学工号 / 服务名）"
        />
        <input
          v-model.trim="filters.action"
          list="audit-action-suggestions"
          type="text"
          class="filter-input filter-input-wide"
          placeholder="动作（agent.update / essay_check.delete...）"
        />
        <datalist id="audit-action-suggestions">
          <option value="agent.create" />
          <option value="agent.update" />
          <option value="agent.delete" />
          <option value="agent.toggle" />
          <option value="agent.reorder" />
          <option value="feedback.export" />
          <option value="user.export" />
          <option value="essay_check.submit" />
          <option value="essay_check.delete" />
          <option value="essay_check.export" />
        </datalist>
        <input
          v-model.trim="filters.target_type"
          type="text"
          class="filter-input"
          placeholder="目标类型"
        />
        <input
          v-model="filters.time_from"
          type="datetime-local"
          class="filter-input"
          :title="'起始时间'"
        />
        <input
          v-model="filters.time_to"
          type="datetime-local"
          class="filter-input"
          :title="'结束时间'"
        />
        <button type="button" class="btn-secondary" @click="resetAndLoad" :disabled="loading">查询</button>
        <button type="button" class="btn-secondary" @click="clearFilters" :disabled="loading">重置</button>
        <button type="button" class="btn-primary" @click="onExport" :disabled="exporting">
          {{ exporting ? '导出中...' : '导出 Excel' }}
        </button>
      </div>
    </div>

    <div class="audit-table-wrap">
      <table class="audit-table" v-if="logs.length > 0">
        <thead>
          <tr>
            <th class="col-time">时间</th>
            <th class="col-actor-type">类型</th>
            <th class="col-actor">执行者</th>
            <th class="col-action">动作</th>
            <th class="col-target">目标</th>
            <th class="col-result">结果</th>
            <th class="col-ip">IP</th>
            <th class="col-detail">详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td class="col-time mono">{{ log.create_time }}</td>
            <td class="col-actor-type">
              <span class="badge" :class="`badge-${log.actor_type}`">{{ log.actor_type }}</span>
            </td>
            <td class="col-actor">
              <div class="actor-label" :title="log.actor_id || ''">{{ log.actor_label || log.actor_id || '—' }}</div>
            </td>
            <td class="col-action mono">{{ log.action }}</td>
            <td class="col-target">
              <div v-if="log.target_type || log.target_id || log.target_label" class="target-cell">
                <span v-if="log.target_type" class="target-type">{{ log.target_type }}</span>
                <span class="target-label" :title="log.target_id || ''">{{ log.target_label || log.target_id || '' }}</span>
              </div>
              <span v-else class="muted">—</span>
            </td>
            <td class="col-result">
              <span
                v-if="log.result"
                class="badge"
                :class="`badge-result-${log.result}`"
              >{{ log.result }}</span>
              <span v-else class="muted">—</span>
            </td>
            <td class="col-ip mono">{{ log.request_ip || '—' }}</td>
            <td class="col-detail">
              <button type="button" class="link-btn" @click="openDetail(log)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty-state">加载中...</div>
      <div v-else-if="error" class="empty-state error">{{ error }}</div>
      <div v-else class="empty-state">暂无审计记录</div>

      <div class="audit-table-footer" v-if="logs.length > 0">
        <span class="audit-table-count">已加载 {{ logs.length }} 条</span>
        <button
          type="button"
          class="btn-secondary"
          v-if="hasMore"
          @click="loadMore"
          :disabled="loading"
        >
          {{ loading ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </div>

    <div v-if="detailLog" class="audit-modal-mask" @click.self="detailLog = null">
      <div class="audit-modal" role="dialog" aria-modal="true">
        <div class="audit-modal-header">
          <div>
            <div class="audit-modal-title">审计日志详情</div>
            <div class="audit-modal-subtitle mono">{{ detailLog.id }}</div>
          </div>
          <button type="button" class="audit-modal-close" @click="detailLog = null" aria-label="关闭">×</button>
        </div>
        <dl class="audit-modal-grid">
          <dt>时间</dt><dd class="mono">{{ detailLog.create_time }}</dd>
          <dt>执行者类型</dt><dd>{{ detailLog.actor_type }}</dd>
          <dt>执行者 ID</dt><dd class="mono">{{ detailLog.actor_id || '—' }}</dd>
          <dt>执行者标识</dt><dd>{{ detailLog.actor_label || '—' }}</dd>
          <dt>动作</dt><dd class="mono">{{ detailLog.action }}</dd>
          <dt>目标类型</dt><dd>{{ detailLog.target_type || '—' }}</dd>
          <dt>目标 ID</dt><dd class="mono">{{ detailLog.target_id || '—' }}</dd>
          <dt>目标标识</dt><dd>{{ detailLog.target_label || '—' }}</dd>
          <dt>结果</dt><dd>{{ detailLog.result || '—' }}</dd>
          <dt>请求 IP</dt><dd class="mono">{{ detailLog.request_ip || '—' }}</dd>
          <dt>User-Agent</dt><dd class="ua-cell">{{ detailLog.user_agent || '—' }}</dd>
        </dl>
        <div class="audit-modal-section">
          <div class="audit-modal-section-title">payload</div>
          <pre class="audit-modal-pre">{{ formatJson(detailLog.payload) }}</pre>
        </div>
        <div class="audit-modal-section">
          <div class="audit-modal-section-title">extra</div>
          <pre class="audit-modal-pre">{{ formatJson(detailLog.extra) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { exportAuditLogs, fetchAuditLogs, triggerBlobDownload } from '../../api/admin'
import type { AuditLogDetail, AuditLogListParams } from '../../api/types'

const PAGE_SIZE = 100

interface AuditFilters {
  actor_type: string | null
  actor_id: string
  action: string
  target_type: string
  time_from: string
  time_to: string
}

const filters = reactive<AuditFilters>({
  actor_type: null,
  actor_id: '',
  action: '',
  target_type: '',
  time_from: '',
  time_to: '',
})

const logs = ref<AuditLogDetail[]>([])
const loading = ref(false)
const exporting = ref(false)
const error = ref<string | null>(null)
const offset = ref(0)
const hasMore = ref(false)

const detailLog = ref<AuditLogDetail | null>(null)

function toIsoOrNull(value: string): string | null {
  if (!value) return null
  // <input type="datetime-local"> 给的是无时区字符串，按本地时间转 ISO（带本地时区偏移）
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

function currentQueryParams(append: boolean): AuditLogListParams {
  return {
    actor_type: filters.actor_type,
    actor_id: filters.actor_id || null,
    action: filters.action || null,
    target_type: filters.target_type || null,
    time_from: toIsoOrNull(filters.time_from),
    time_to: toIsoOrNull(filters.time_to),
    limit: PAGE_SIZE,
    offset: append ? offset.value : 0,
  }
}

async function loadLogs(append: boolean) {
  loading.value = true
  error.value = null
  try {
    const list = await fetchAuditLogs(currentQueryParams(append))
    if (append) {
      logs.value = [...logs.value, ...list]
    } else {
      logs.value = list
      offset.value = 0
    }
    offset.value += list.length
    hasMore.value = list.length === PAGE_SIZE
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function resetAndLoad() {
  offset.value = 0
  await loadLogs(false)
}

async function loadMore() {
  await loadLogs(true)
}

function clearFilters() {
  filters.actor_type = null
  filters.actor_id = ''
  filters.action = ''
  filters.target_type = ''
  filters.time_from = ''
  filters.time_to = ''
  resetAndLoad()
}

function openDetail(log: AuditLogDetail) {
  detailLog.value = log
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

async function onExport() {
  exporting.value = true
  try {
    const blob = await exportAuditLogs(currentQueryParams(false))
    const stamp = new Date()
      .toISOString()
      .replace(/[-:T]/g, '')
      .slice(0, 15)
    triggerBlobDownload(blob, `审计日志_${stamp}.xlsx`)
  } catch (e) {
    console.error('[Admin] 导出审计日志失败', e)
    alert(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  loadLogs(false)
})
</script>

<style scoped>
.admin-audit-logs-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.admin-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.admin-page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1a2540;
}

.admin-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-select,
.filter-input {
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #d8deea;
  font-size: 13px;
  color: #1a2540;
  background: #fff;
}

.filter-input {
  width: 140px;
}

.filter-input-wide {
  width: 220px;
}

.filter-select:focus,
.filter-input:focus {
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

.audit-table-wrap {
  background: #fff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
  overflow-x: auto;
}

.audit-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.audit-table thead th {
  background: #f5f7fb;
  color: #4b5670;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  white-space: nowrap;
}

.audit-table tbody td {
  padding: 10px 12px;
  color: #1a2540;
  border-bottom: 1px solid #f0f3f9;
  vertical-align: middle;
}

.col-time { width: 160px; white-space: nowrap; }
.col-actor-type { width: 80px; }
.col-actor { min-width: 160px; }
.col-action { width: 200px; white-space: nowrap; }
.col-target { min-width: 200px; }
.col-result { width: 90px; }
.col-ip { width: 130px; white-space: nowrap; }
.col-detail { width: 70px; }

.mono {
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  text-transform: lowercase;
  background: #e7eeff;
  color: #1f3c8b;
}

.badge-admin { background: #fce4d6; color: #b04a1a; }
.badge-user { background: #e7eeff; color: #1f3c8b; }
.badge-agent { background: #d6f0e0; color: #1f6a3a; }
.badge-system { background: #ece2ff; color: #5a3a99; }

.badge-result-success { background: #d6f0e0; color: #1f6a3a; }
.badge-result-failure { background: #fce4e4; color: #b03434; }
.badge-result-partial { background: #fff3cc; color: #8a6300; }

.actor-label {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 320px;
}

.target-type {
  flex-shrink: 0;
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: #f0f3f9;
  color: #4b5670;
}

.target-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  color: #8a93a6;
}

.link-btn {
  background: transparent;
  border: none;
  color: #2f4aa6;
  cursor: pointer;
  font-size: 13px;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}

.empty-state {
  padding: 48px 16px;
  text-align: center;
  color: #8a93a6;
  font-size: 14px;
}

.empty-state.error {
  color: #c62828;
}

.audit-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid #f0f3f9;
  margin-top: 8px;
}

.audit-table-count {
  font-size: 13px;
  color: #8a93a6;
}

/* ---------- 详情 modal ---------- */

.audit-modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 28, 58, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.audit-modal {
  background: #fff;
  border-radius: 16px;
  width: min(680px, 100%);
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  padding: 24px 28px;
  box-shadow: 0 18px 48px rgba(15, 28, 58, 0.25);
}

.audit-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.audit-modal-title {
  font-size: 18px;
  font-weight: 700;
  color: #1a2540;
}

.audit-modal-subtitle {
  font-size: 12px;
  color: #8a93a6;
  margin-top: 2px;
}

.audit-modal-close {
  background: transparent;
  border: none;
  font-size: 28px;
  line-height: 1;
  color: #8a93a6;
  cursor: pointer;
  padding: 0 4px;
}

.audit-modal-close:hover {
  color: #1a2540;
}

.audit-modal-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px 16px;
  margin: 0 0 20px 0;
}

.audit-modal-grid dt {
  font-size: 12px;
  color: #8a93a6;
  font-weight: 600;
}

.audit-modal-grid dd {
  font-size: 13px;
  color: #1a2540;
  margin: 0;
  word-break: break-all;
}

.ua-cell {
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
  font-size: 11px;
  line-height: 1.5;
}

.audit-modal-section {
  margin-top: 16px;
}

.audit-modal-section-title {
  font-size: 12px;
  color: #8a93a6;
  font-weight: 600;
  margin-bottom: 6px;
}

.audit-modal-pre {
  background: #f5f7fb;
  border: 1px solid #eef1f6;
  border-radius: 8px;
  padding: 12px;
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #1a2540;
  margin: 0;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
