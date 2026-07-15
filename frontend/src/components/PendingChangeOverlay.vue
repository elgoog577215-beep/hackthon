<template>
  <div v-if="changeSets.length > 0" class="pending-change-overlay" data-testid="pending-change-overlay">
    <div v-for="cs in changeSets" :key="cs.id" class="pending-change-set">
      <div
        v-for="item in itemsForNode(cs)"
        :key="cs.id + '-' + item.target_node_id"
        class="pending-change-item"
        data-testid="pending-change-item"
      >
        <div class="pending-change-item__header">
          <span
            class="pending-change-badge"
            :class="{
              'pending-change-badge--from-kb': item.source === 'content_to_kb_link',
              'pending-change-badge--to-kb': item.source === 'kb_to_content_link',
            }"
          >{{ sourceLabel(item.source) }}</span>
          <span class="pending-change-op">{{ operationLabel(item.operation) }}</span>
          <span class="pending-change-scope">作用范围：{{ scopeLabel(cs.scope) }}</span>
        </div>

        <div class="pending-change-item__reason">{{ item.reason }}</div>

        <div class="pending-change-item__diff">
          <template v-if="!item.before">
            <div class="diff-block diff-block--after">
              <div class="diff-label">新增内容</div>
              <div class="diff-content">{{ item.after }}</div>
            </div>
          </template>
          <template v-else>
            <div class="diff-block diff-block--before">
              <div class="diff-label">修改前</div>
              <div class="diff-content">{{ item.before }}</div>
            </div>
            <div class="diff-block diff-block--after">
              <div class="diff-label">修改后</div>
              <div class="diff-content">{{ item.after }}</div>
            </div>
          </template>
        </div>

        <div class="pending-change-item__actions">
          <button
            type="button"
            class="pcb pcb--accept"
            data-testid="accept-btn"
            @click="handleAccept(cs, item)"
          >
            接受
          </button>
          <button
            type="button"
            class="pcb pcb--reject"
            data-testid="reject-btn"
            @click="openPrompt('reject', cs, item)"
          >
            拒绝
          </button>
          <button
            type="button"
            class="pcb pcb--regenerate"
            data-testid="regenerate-btn"
            @click="openPrompt('regenerate', cs, item)"
          >
            重新生成
          </button>
        </div>

        <div v-if="activePrompt && activePrompt.changeSetId === cs.id && activePrompt.targetNodeId === item.target_node_id" class="pending-change-item__prompt">
          <textarea
            v-model="promptText"
            class="pcb-textarea"
            data-testid="prompt-textarea"
            :placeholder="activePrompt.kind === 'reject' ? '（可选）填写拒绝理由' : '（可选）补充重新生成的说明'"
          ></textarea>
          <div class="pcb-prompt-actions">
            <button type="button" class="pcb pcb--confirm" data-testid="prompt-confirm-btn" @click="confirmPrompt">
              确认
            </button>
            <button type="button" class="pcb pcb--cancel" data-testid="prompt-cancel-btn" @click="cancelPrompt">
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePendingChangesStore } from '../stores/pendingChanges'
import type { ChangeItem, ChangeOperation, ChangeScope, CourseChangeSet } from '../types/adaptiveChange'

const props = withDefaults(
  defineProps<{
    nodeId: string
    /** 当前叠加层挂载的节点类型：课程节点（默认）或知识图谱节点 */
    nodeKind?: 'course_node' | 'kg_node'
  }>(),
  {
    nodeKind: 'course_node',
  }
)

const store = usePendingChangesStore()

/** 仅取影响当前 node 的变更集（作用域可控：其它节点的 item 不在此展示） */
const changeSets = computed<CourseChangeSet[]>(() =>
  props.nodeKind === 'kg_node' ? store.pendingForKgNode(props.nodeId) : store.pendingForNode(props.nodeId)
)

/** 一个变更集可能涉及多个节点，这里只渲染命中当前 node_id 的 change_items */
function itemsForNode(cs: CourseChangeSet): ChangeItem[] {
  return cs.change_items.filter(ci => ci.target_node_id === props.nodeId)
}

/** 变更来源角标文案 */
function sourceLabel(source: ChangeItem['source']): string {
  if (source === 'content_to_kb_link') return '来自知识库联动'
  if (source === 'kb_to_content_link') return '联动至知识库'
  return 'AI 生成'
}

const operationLabels: Record<ChangeOperation, string> = {
  insert: '新增',
  update: '修改',
  delete: '删除',
  reorder: '移动',
}
function operationLabel(op: ChangeOperation): string {
  return operationLabels[op] || op
}

const scopeLabels: Record<ChangeScope, string> = {
  block: '当前内容块',
  section: '当前小节',
  sections: '多个小节',
  chapters: '多个章节',
  book: '全书',
}
function scopeLabel(scope: ChangeScope): string {
  return scopeLabels[scope] || scope
}

type PromptKind = 'reject' | 'regenerate'
const activePrompt = ref<{ kind: PromptKind; changeSetId: string; targetNodeId: string } | null>(null)
const promptText = ref('')

function openPrompt(kind: PromptKind, cs: CourseChangeSet, item: ChangeItem) {
  activePrompt.value = { kind, changeSetId: cs.id, targetNodeId: item.target_node_id }
  promptText.value = ''
}

function cancelPrompt() {
  activePrompt.value = null
  promptText.value = ''
}

/** 接受：仅对当前 node_id 生效，不影响该 change_set 中其它节点的 item（作用域可控的核心实现点） */
function handleAccept(cs: CourseChangeSet, item: ChangeItem) {
  store.acceptChangeSet(cs.id, [item.target_node_id])
}

function confirmPrompt() {
  if (!activePrompt.value) return
  const { kind, changeSetId, targetNodeId } = activePrompt.value
  if (kind === 'reject') {
    store.rejectChangeSet(changeSetId, promptText.value || undefined, [targetNodeId])
  } else {
    store.regenerateChangeSet(changeSetId, promptText.value || undefined)
  }
  cancelPrompt()
}
</script>

<style scoped>
.pending-change-overlay {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.pending-change-item {
  border-left: 3px solid #f5c451;
  background: #fffbea;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.pending-change-item__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.4rem;
  font-size: 0.75rem;
}

.pending-change-badge {
  background: #7c3aed;
  color: #fff;
  border-radius: 9999px;
  padding: 0.05rem 0.6rem;
  font-weight: 600;
  font-size: 0.7rem;
}

.pending-change-badge--from-kb {
  background: #0891b2;
}

.pending-change-badge--to-kb {
  background: #059669;
}

.pending-change-op {
  background: #fef3c7;
  color: #92400e;
  border-radius: 0.375rem;
  padding: 0.05rem 0.5rem;
  font-weight: 600;
}

.pending-change-scope {
  color: #6b7280;
}

.pending-change-item__reason {
  font-size: 0.85rem;
  color: #4b5563;
  margin-bottom: 0.5rem;
}

.pending-change-item__diff {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 0.6rem;
}

.diff-block {
  border-radius: 0.375rem;
  padding: 0.4rem 0.6rem;
  font-size: 0.85rem;
  white-space: pre-wrap;
}

.diff-block--before {
  background: #fef2f2;
  color: #991b1b;
  text-decoration: line-through;
  text-decoration-color: #f3a5a5;
}

.diff-block--after {
  background: #ecfdf5;
  color: #065f46;
}

.diff-label {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 0.15rem;
}

.pending-change-item__actions {
  display: flex;
  gap: 0.5rem;
}

.pcb {
  border: none;
  border-radius: 0.375rem;
  padding: 0.3rem 0.75rem;
  font-size: 0.8rem;
  cursor: pointer;
  font-weight: 600;
}

.pcb--accept { background: #10b981; color: #fff; }
.pcb--reject { background: #ef4444; color: #fff; }
.pcb--regenerate { background: #3b82f6; color: #fff; }
.pcb--confirm { background: #1f2937; color: #fff; }
.pcb--cancel { background: #e5e7eb; color: #374151; }

.pending-change-item__prompt {
  margin-top: 0.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.pcb-textarea {
  width: 100%;
  min-height: 2.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
  resize: vertical;
}

.pcb-prompt-actions {
  display: flex;
  gap: 0.5rem;
}
</style>
