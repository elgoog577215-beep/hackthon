<template>
  <div class="smart-bar" :class="{ expanded: isExpanded }">
    <!-- 收起状态 -->
    <div class="bar-collapsed" v-if="!isExpanded">
      <div class="status-section">
        <div class="location-badge">
          <el-icon class="location-icon"><Location /></el-icon>
          <span class="location-text">{{ currentLocation }}</span>
        </div>
        <div class="divider-vertical"></div>
        <div class="asset-badges">
          <button class="asset-badge notes" @click="expandAndShow('notes')">
            <el-icon><Notebook /></el-icon>
            <span class="badge-value">{{ notesCount }}</span>
            <span class="badge-label">笔记</span>
          </button>
          <button class="asset-badge wrong" @click="expandAndShow('wrongAnswers')">
            <el-icon><CircleClose /></el-icon>
            <span class="badge-value">{{ wrongAnswersCount }}</span>
            <span class="badge-label">错题</span>
          </button>
        </div>
      </div>
      <div class="actions-section">
        <div class="quick-actions">
          <button class="action-btn primary" @click="$emit('startQuiz')">
            <el-icon><EditPen /></el-icon>
            <span>出题</span>
          </button>
          <button class="action-btn" @click="$emit('summarize')">
            <el-icon><Document /></el-icon>
            <span>总结</span>
          </button>
          <button class="action-btn" @click="expandAndShow('stats')">
            <el-icon><DataLine /></el-icon>
            <span>统计</span>
          </button>
        </div>
        <button class="expand-trigger" @click="toggleExpand">
          <el-icon><ArrowUp /></el-icon>
        </button>
      </div>
    </div>

    <!-- 展开状态 -->
    <div class="bar-expanded" v-else>
      <div class="expanded-header">
        <div class="header-title">
          <div class="title-icon">
            <el-icon><Operation /></el-icon>
          </div>
          <span>智能助手工具栏</span>
        </div>
        <button class="collapse-trigger" @click="toggleExpand">
          <el-icon><ArrowDown /></el-icon>
          <span>收起</span>
        </button>
      </div>
      
      <div class="expanded-body">
        <!-- 左侧：知识资产 -->
        <div class="assets-panel">
          <!-- 笔记本 -->
          <div class="asset-card notes-card">
            <div class="card-header">
              <div class="card-icon notes">
                <el-icon><Notebook /></el-icon>
              </div>
              <div class="card-title">
                <span class="title-text">笔记本</span>
                <span class="title-count">{{ notesCount }}条</span>
              </div>
            </div>
            <div class="card-content">
              <div 
                v-for="note in recentNotes" 
                :key="note.id" 
                class="note-entry"
                @click="$emit('locateNote', note)"
              >
                <div class="entry-dot"></div>
                <span class="entry-text">{{ note.title || note.content?.slice(0, 35) }}</span>
                <button class="entry-action">定位</button>
              </div>
              <div v-if="notesCount === 0" class="empty-state">
                <el-icon><DocumentAdd /></el-icon>
                <span>暂无笔记，选中正文可添加批注</span>
              </div>
            </div>
            <button class="card-action" @click="$emit('viewAllNotes')">
              <span>查看全部笔记</span>
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <!-- 错题本 -->
          <div class="asset-card wrong-card">
            <div class="card-header">
              <div class="card-icon wrong">
                <el-icon><CircleClose /></el-icon>
              </div>
              <div class="card-title">
                <span class="title-text">错题本</span>
                <span class="title-count">{{ wrongAnswersCount }}道</span>
              </div>
            </div>
            <div class="card-content">
              <div 
                v-for="item in recentWrongAnswers" 
                :key="item.id" 
                class="wrong-entry"
              >
                <div class="entry-dot wrong"></div>
                <span class="entry-text">{{ item.question?.slice(0, 35) }}...</span>
                <button class="entry-action retry" @click="$emit('retryWrong', item)">重做</button>
              </div>
              <div v-if="wrongAnswersCount === 0" class="empty-state success">
                <el-icon><CircleCheck /></el-icon>
                <span>暂无错题，继续保持！</span>
              </div>
            </div>
            <div class="card-actions-row">
              <button class="card-action half" @click="$emit('viewAllWrongAnswers')">
                <span>查看全部</span>
              </button>
              <button class="card-action half primary" @click="$emit('retryAllWrong')" v-if="wrongAnswersCount > 0">
                <span>全部重做</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 右侧：快捷操作 -->
        <div class="actions-panel">
          <div class="panel-title">
            <el-icon><TrendCharts /></el-icon>
            <span>快捷操作</span>
          </div>
          <div class="action-grid">
            <button class="action-card" @click="$emit('startQuiz')">
              <div class="action-icon-wrapper quiz">
                <el-icon><EditPen /></el-icon>
              </div>
              <div class="action-info">
                <span class="action-name">出题测验</span>
                <span class="action-desc">基于当前内容出题</span>
              </div>
            </button>
            <button class="action-card" @click="$emit('summarize')">
              <div class="action-icon-wrapper summary">
                <el-icon><Document /></el-icon>
              </div>
              <div class="action-info">
                <span class="action-name">一键总结</span>
                <span class="action-desc">总结当前章节要点</span>
              </div>
            </button>
            <button class="action-card" @click="$emit('showStats')">
              <div class="action-icon-wrapper stats">
                <el-icon><DataLine /></el-icon>
              </div>
              <div class="action-info">
                <span class="action-name">学习统计</span>
                <span class="action-desc">查看学习数据</span>
              </div>
            </button>
            <button class="action-card" @click="$emit('showGraph')">
              <div class="action-icon-wrapper graph">
                <el-icon><Share /></el-icon>
              </div>
              <div class="action-info">
                <span class="action-name">知识图谱</span>
                <span class="action-desc">查看知识点关系</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { 
  Location, Notebook, CircleClose, EditPen, Document, 
  DataLine, ArrowUp, ArrowDown, Operation, Share, 
  TrendCharts, DocumentAdd, CircleCheck, ArrowRight
} from '@element-plus/icons-vue'
import { useCourseStore } from '../stores/course'

const props = defineProps<{
  notesCount?: number
  wrongAnswersCount?: number
  notes?: any[]
  wrongAnswers?: any[]
}>()

const emit = defineEmits<{
  (e: 'startQuiz'): void
  (e: 'summarize'): void
  (e: 'showStats'): void
  (e: 'showGraph'): void
  (e: 'viewAllNotes'): void
  (e: 'viewAllWrongAnswers'): void
  (e: 'retryWrong', item: any): void
  (e: 'retryAllWrong'): void
  (e: 'locateNote', note: any): void
}>()

const courseStore = useCourseStore()
const isExpanded = ref(false)
const activeTab = ref('notes')

const currentLocation = computed(() => {
  const course = courseStore.currentCourse?.title || '未选择课程'
  const node = courseStore.currentNode?.node_name || ''
  return node ? `${course} · ${node}` : course
})

const recentNotes = computed(() => {
  return (props.notes || []).slice(0, 3)
})

const recentWrongAnswers = computed(() => {
  return (props.wrongAnswers || []).slice(0, 3)
})

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function expandAndShow(tab: string) {
  activeTab.value = tab
  isExpanded.value = true
}
</script>

<style scoped>
.smart-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--color-surface, #ffffff);
  z-index: 100;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.08), 0 -2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid var(--color-border-light, #f1f5f9);
  border-bottom: none;
}

/* ========== 收起状态 ========== */
.bar-collapsed {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  height: 56px;
}

.status-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.location-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid var(--color-border, #e2e8f0);
}

.location-icon {
  color: var(--color-primary-500, #6366f1);
  font-size: 14px;
}

.location-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary, #475569);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.divider-vertical {
  width: 1px;
  height: 24px;
  background: var(--color-border, #e2e8f0);
}

.asset-badges {
  display: flex;
  gap: 8px;
}

.asset-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.asset-badge:hover {
  background: var(--color-primary-50, #eef2ff);
  border-color: var(--color-primary-200, #c7d2fe);
}

.asset-badge.notes .el-icon {
  color: var(--color-primary-500, #6366f1);
}

.asset-badge.wrong .el-icon {
  color: var(--color-error, #ef4444);
}

.badge-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.badge-label {
  font-size: 12px;
  color: var(--color-text-tertiary, #64748b);
}

.actions-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.quick-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  color: var(--color-text-secondary, #475569);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--color-surface-hover, #f1f5f9);
  border-color: var(--color-slate-300, #cbd5e1);
  color: var(--color-text-primary, #0f172a);
}

.action-btn.primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  color: white;
}

.action-btn.primary:hover {
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.expand-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  color: var(--color-text-tertiary, #64748b);
  cursor: pointer;
  transition: all 0.2s ease;
}

.expand-trigger:hover {
  background: var(--color-primary-50, #eef2ff);
  border-color: var(--color-primary-200, #c7d2fe);
  color: var(--color-primary-500, #6366f1);
}

/* ========== 展开状态 ========== */
.smart-bar.expanded {
  height: 340px;
}

.bar-expanded {
  padding: 16px 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.expanded-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border-light, #f1f5f9);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-radius: 10px;
  color: white;
  font-size: 16px;
}

.header-title span {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.collapse-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  color: var(--color-text-secondary, #475569);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.collapse-trigger:hover {
  background: var(--color-surface-hover, #f1f5f9);
}

.expanded-body {
  display: flex;
  gap: 20px;
  flex: 1;
  overflow: hidden;
}

/* ========== 资产面板 ========== */
.assets-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.asset-card {
  background: var(--color-surface-subtle, #f8fafc);
  border-radius: 14px;
  padding: 14px;
  border: 1px solid var(--color-border-light, #f1f5f9);
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.card-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 14px;
}

.card-icon.notes {
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  color: var(--color-primary-500, #6366f1);
}

.card-icon.wrong {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: var(--color-error, #ef4444);
}

.card-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.title-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.title-count {
  font-size: 12px;
  color: var(--color-text-tertiary, #64748b);
}

.card-content {
  flex: 1;
  overflow-y: auto;
}

.note-entry,
.wrong-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--color-surface, #ffffff);
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.note-entry:hover,
.wrong-entry:hover {
  background: var(--color-primary-50, #eef2ff);
}

.entry-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary-400, #818cf8);
  flex-shrink: 0;
}

.entry-dot.wrong {
  background: var(--color-error, #ef4444);
}

.entry-text {
  flex: 1;
  font-size: 12px;
  color: var(--color-text-secondary, #475569);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-action {
  padding: 4px 10px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary, #64748b);
  cursor: pointer;
  transition: all 0.2s ease;
}

.entry-action:hover {
  background: var(--color-primary-50, #eef2ff);
  border-color: var(--color-primary-200, #c7d2fe);
  color: var(--color-primary-500, #6366f1);
}

.entry-action.retry {
  background: var(--color-error-light, #fee2e2);
  border-color: transparent;
  color: var(--color-error, #ef4444);
}

.entry-action.retry:hover {
  background: var(--color-error, #ef4444);
  color: white;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--color-text-muted, #94a3b8);
  font-size: 12px;
}

.empty-state .el-icon {
  font-size: 24px;
  opacity: 0.5;
}

.empty-state.success {
  color: var(--color-success, #10b981);
}

.card-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 10px;
  margin-top: 10px;
  background: var(--color-surface, #ffffff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary, #475569);
  cursor: pointer;
  transition: all 0.2s ease;
}

.card-action:hover {
  background: var(--color-primary-50, #eef2ff);
  border-color: var(--color-primary-200, #c7d2fe);
  color: var(--color-primary-500, #6366f1);
}

.card-action.primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  color: white;
}

.card-action.primary:hover {
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.card-actions-row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.card-action.half {
  flex: 1;
  margin-top: 0;
}

/* ========== 操作面板 ========== */
.actions-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.panel-title .el-icon {
  color: var(--color-primary-500, #6366f1);
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  flex: 1;
}

.action-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px 16px;
  background: var(--color-surface-subtle, #f8fafc);
  border: 1px solid var(--color-border-light, #f1f5f9);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.25s ease;
}

.action-card:hover {
  background: var(--color-surface, #ffffff);
  border-color: var(--color-primary-200, #c7d2fe);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.12);
  transform: translateY(-2px);
}

.action-icon-wrapper {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  font-size: 22px;
}

.action-icon-wrapper.quiz {
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  color: var(--color-primary-500, #6366f1);
}

.action-icon-wrapper.summary {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  color: #d97706;
}

.action-icon-wrapper.stats {
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
  color: var(--color-success, #10b981);
}

.action-icon-wrapper.graph {
  background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
  color: var(--color-accent-500, #a855f7);
}

.action-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.action-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #0f172a);
}

.action-desc {
  font-size: 11px;
  color: var(--color-text-muted, #94a3b8);
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .bar-collapsed {
    padding: 8px 12px;
    height: 52px;
  }

  .location-text {
    max-width: 100px;
  }

  .badge-label {
    display: none;
  }

  .action-btn span {
    display: none;
  }

  .action-btn {
    padding: 8px 10px;
  }

  .expanded-body {
    flex-direction: column;
  }

  .action-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }

  .action-card {
    padding: 12px 8px;
  }

  .action-icon-wrapper {
    width: 40px;
    height: 40px;
    font-size: 18px;
  }

  .action-desc {
    display: none;
  }
}
</style>
