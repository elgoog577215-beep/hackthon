<template>
  <div class="admin-agents-view">
    <div class="admin-toolbar">
      <h2 class="admin-page-title">智能体管理</h2>
      <div class="admin-toolbar-actions">
        <button type="button" class="btn-secondary" @click="loadAgents" :disabled="loading">刷新</button>
        <button type="button" class="btn-primary" @click="openCreate">新建智能体</button>
      </div>
    </div>

    <p class="reorder-hint" v-if="agents.length > 1">提示：拖动行调整顺序，松开后自动保存</p>

    <div class="admin-agents-table-wrap" :class="{ 'is-reordering': reorderPending }">
      <table class="admin-agents-table" v-if="agents.length > 0">
        <thead>
          <tr>
            <th class="col-sort">排序</th>
            <th class="col-icon"></th>
            <th>标题</th>
            <th class="col-desc">描述</th>
            <th>标签</th>
            <th class="col-flag">热门</th>
            <th class="col-flag">上架</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(a, idx) in agents"
            :key="a.id"
            draggable="true"
            :class="{
              'is-dragging': draggingIndex === idx,
              'drag-over-above': dragOverIndex === idx && dragOverPosition === 'above' && draggingIndex !== idx,
              'drag-over-below': dragOverIndex === idx && dragOverPosition === 'below' && draggingIndex !== idx,
            }"
            @dragstart="onDragStart(idx, $event)"
            @dragover="onDragOver(idx, $event)"
            @dragleave="onDragLeave(idx)"
            @drop="onDrop(idx, $event)"
            @dragend="onDragEnd"
          >
            <td class="col-sort">
              <div class="sort-cell">
                <span class="drag-handle" aria-hidden="true">⋮⋮</span>
                <span class="sort-num">{{ a.sort_order }}</span>
              </div>
            </td>
            <td class="col-icon">
              <span class="agent-icon-cell" :style="{ backgroundColor: a.badge_bg }">
                <svg viewBox="0 0 24 24" :style="{ color: a.badge_fg }">
                  <path fill="currentColor" :d="a.icon_path" />
                </svg>
              </span>
            </td>
            <td class="col-title">{{ a.title }}</td>
            <td class="col-desc">
              <div class="agent-desc-cell" :title="a.description">{{ a.description }}</div>
            </td>
            <td>
              <span v-for="t in a.tags" :key="t" class="tag-chip">{{ t }}</span>
            </td>
            <td class="col-flag">
              <span :class="['flag-pill', a.popular ? 'flag-on' : 'flag-off']">{{ a.popular ? '是' : '否' }}</span>
            </td>
            <td class="col-flag">
              <label class="toggle">
                <input
                  type="checkbox"
                  :checked="a.enabled"
                  :disabled="togglingId === a.id"
                  @change="onToggle(a, ($event.target as HTMLInputElement).checked)"
                />
                <span class="toggle-slider"></span>
              </label>
            </td>
            <td class="col-actions">
              <button type="button" class="row-btn" @click="openEdit(a)">编辑</button>
              <button type="button" class="row-btn row-btn-danger" @click="askDelete(a)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty-state">加载中...</div>
      <div v-else-if="error" class="empty-state error">{{ error }}</div>
      <div v-else class="empty-state">暂无智能体，点击右上角「新建智能体」开始添加</div>
    </div>

    <AdminAgentEditModal
      v-model="modalOpen"
      :agent="editingAgent"
      @saved="onModalSaved"
    />

    <DeleteConfirmModal
      v-model="deleteOpen"
      title="删除智能体"
      entity-kind="智能体"
      :entity-name="pendingDelete?.title ?? ''"
      hint="此操作不可恢复。删除后首页广场将不再展示该卡片。"
      :pending="deletePending"
      :error="Boolean(deleteError)"
      :error-text="deleteError ?? ''"
      @cancel="closeDelete"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DeleteConfirmModal from '../../components/DeleteConfirmModal.vue'
import AdminAgentEditModal from './AdminAgentEditModal.vue'
import {
  fetchAdminAgents,
  operateAdminAgent,
  reorderAdminAgents,
  toggleAdminAgent,
} from '../../api/admin'
import { OperationEnum, type AdminAgentDetail } from '../../api/types'

const agents = ref<AdminAgentDetail[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const modalOpen = ref(false)
const editingAgent = ref<AdminAgentDetail | null>(null)

const togglingId = ref<string | null>(null)

const draggingIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)
const dragOverPosition = ref<'above' | 'below'>('above')
const reorderPending = ref(false)

const deleteOpen = ref(false)
const pendingDelete = ref<AdminAgentDetail | null>(null)
const deletePending = ref(false)
const deleteError = ref<string | null>(null)

async function loadAgents() {
  loading.value = true
  error.value = null
  try {
    agents.value = await fetchAdminAgents()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingAgent.value = null
  modalOpen.value = true
}

function openEdit(a: AdminAgentDetail) {
  editingAgent.value = a
  modalOpen.value = true
}

async function onModalSaved() {
  await loadAgents()
}

function onDragStart(idx: number, e: DragEvent) {
  draggingIndex.value = idx
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    // 让 Firefox 也能识别 drag
    e.dataTransfer.setData('text/plain', String(idx))
  }
}

function onDragOver(idx: number, e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  if (draggingIndex.value === null || draggingIndex.value === idx) {
    dragOverIndex.value = null
    return
  }
  const target = e.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const midY = rect.top + rect.height / 2
  dragOverIndex.value = idx
  dragOverPosition.value = e.clientY < midY ? 'above' : 'below'
}

function onDragLeave(idx: number) {
  if (dragOverIndex.value === idx) {
    dragOverIndex.value = null
  }
}

async function onDrop(idx: number, e: DragEvent) {
  e.preventDefault()
  const src = draggingIndex.value
  const pos = dragOverPosition.value
  resetDragState()
  if (src === null || src === idx) return

  const next = [...agents.value]
  const [moved] = next.splice(src, 1)
  if (!moved) return
  let insertAt = idx
  if (pos === 'below') insertAt = idx + 1
  if (src < insertAt) insertAt--
  next.splice(insertAt, 0, moved)
  // 顺序无变化则不发请求
  if (next.every((a, i) => a.id === agents.value[i]?.id)) return

  const snapshot = agents.value
  agents.value = next // 乐观更新
  reorderPending.value = true
  try {
    await reorderAdminAgents({ id_list: next.map((a) => a.id) })
    await loadAgents() // 拉新的 sort_order
  } catch (err) {
    agents.value = snapshot // 失败回滚
    alert(err instanceof Error ? err.message : '排序保存失败')
  } finally {
    reorderPending.value = false
  }
}

function onDragEnd() {
  resetDragState()
}

function resetDragState() {
  draggingIndex.value = null
  dragOverIndex.value = null
}

async function onToggle(a: AdminAgentDetail, enabled: boolean) {
  togglingId.value = a.id
  const original = a.enabled
  try {
    await toggleAdminAgent({ id: a.id, enabled })
    a.enabled = enabled
  } catch (e) {
    a.enabled = original
    alert(e instanceof Error ? e.message : '切换失败')
  } finally {
    togglingId.value = null
  }
}

function askDelete(a: AdminAgentDetail) {
  pendingDelete.value = a
  deleteError.value = null
  deleteOpen.value = true
}

function closeDelete() {
  if (deletePending.value) return
  deleteOpen.value = false
  pendingDelete.value = null
}

async function confirmDelete() {
  if (!pendingDelete.value) return
  deletePending.value = true
  deleteError.value = null
  try {
    await operateAdminAgent({ operation: OperationEnum.DELETE, id: pendingDelete.value.id })
    deleteOpen.value = false
    pendingDelete.value = null
    await loadAgents()
  } catch (e) {
    deleteError.value = e instanceof Error ? e.message : '删除失败'
  } finally {
    deletePending.value = false
  }
}

onMounted(() => {
  loadAgents()
})
</script>

<style scoped>
.admin-agents-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.admin-toolbar {
  display: flex;
  align-items: center;
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

.btn-secondary {
  background: #f0f4fb;
  color: #1f3c8b;
}

.btn-secondary:hover:not(:disabled) {
  background: #dde6f8;
}

.admin-agents-table-wrap {
  background: #ffffff;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(15, 28, 58, 0.05);
  overflow-x: auto;
}

.admin-agents-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}

.admin-agents-table thead th {
  background: #f5f7fb;
  color: #4b5670;
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid #e6eaf2;
  white-space: nowrap;
}

.admin-agents-table tbody td {
  padding: 12px;
  color: #1a2540;
  border-bottom: 1px solid #f0f3f9;
  vertical-align: middle;
}

.reorder-hint {
  margin: -8px 0 0;
  color: #8a93a6;
  font-size: 12px;
}

.col-sort {
  width: 84px;
  text-align: center;
}

.sort-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-start;
  padding-left: 4px;
}

.drag-handle {
  color: #b3bbcb;
  cursor: grab;
  font-size: 16px;
  line-height: 1;
  letter-spacing: -2px;
  user-select: none;
}

.admin-agents-table tbody tr:active .drag-handle {
  cursor: grabbing;
}

.sort-num {
  font-weight: 600;
  color: #1a2540;
  min-width: 24px;
  text-align: right;
}

.admin-agents-table tbody tr {
  cursor: grab;
}

.admin-agents-table tbody tr.is-dragging {
  opacity: 0.4;
  cursor: grabbing;
}

.admin-agents-table tbody tr.drag-over-above td {
  box-shadow: inset 0 2px 0 0 #4467d9;
}

.admin-agents-table tbody tr.drag-over-below td {
  box-shadow: inset 0 -2px 0 0 #4467d9;
}

.admin-agents-table-wrap.is-reordering {
  opacity: 0.7;
  pointer-events: none;
}

.col-icon {
  width: 56px;
}

.col-title {
  font-weight: 600;
  white-space: nowrap;
}

.col-desc {
  max-width: 280px;
}

.agent-desc-cell {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #4b5670;
}

.col-flag {
  width: 88px;
  text-align: center;
}

.col-actions {
  width: 140px;
  white-space: nowrap;
}

.agent-icon-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
}

.agent-icon-cell svg {
  width: 22px;
  height: 22px;
}

.tag-chip {
  display: inline-block;
  margin-right: 4px;
  padding: 2px 8px;
  background: #f0f4fb;
  color: #1f3c8b;
  border-radius: 999px;
  font-size: 12px;
}

.flag-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.flag-on {
  background: #e6fff6;
  color: #0a7c5a;
}

.flag-off {
  background: #f0f3f9;
  color: #8a93a6;
}

.toggle {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  background: #d8deea;
  border-radius: 999px;
  transition: background 0.2s ease;
  cursor: pointer;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  top: 2px;
  left: 2px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s ease;
}

.toggle input:checked + .toggle-slider {
  background: #2f4aa6;
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(18px);
}

.toggle input:disabled + .toggle-slider {
  opacity: 0.6;
  cursor: not-allowed;
}

.row-btn {
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid #d8deea;
  background: #fff;
  color: #1f3c8b;
  cursor: pointer;
  font-size: 12px;
  margin-right: 6px;
}

.row-btn:hover {
  background: #f0f4fb;
}

.row-btn-danger {
  color: #c62828;
  border-color: #f5c6c6;
}

.row-btn-danger:hover {
  background: #fdecec;
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
</style>
