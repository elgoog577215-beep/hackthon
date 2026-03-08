<template>
  <div class="smart-bar">
    <!-- 主工具栏 -->
    <div class="bar-main">
      <!-- Reading Location -->
      <div class="location-section" v-if="currentLocation">
        <div class="location-badge">
          <el-icon class="text-slate-400" :size="14"><Location /></el-icon>
          <span class="location-text">{{ currentLocation }}</span>
        </div>
      </div>
      <div v-else class="location-section"></div>

      <div class="actions-section">
        <!-- 笔记 -->
        <div class="action-wrapper" ref="notesRef">
          <button class="action-btn" @click="togglePanel('notes')">
            <el-icon><Notebook /></el-icon>
            <span class="btn-label">笔记</span>
            <span v-if="(notesCount ?? 0) > 0" class="btn-badge">{{ notesCount }}</span>
          </button>
          <Transition name="popup">
            <div v-if="activePanel === 'notes'" class="popup-panel notes-panel">
              <div class="panel-header">
                <span class="panel-title">笔记本</span>
                <span class="panel-count">{{ notesCount ?? 0 }} 条</span>
              </div>
              <div class="panel-content">
                <div v-for="note in recentNotes" :key="note.id" class="list-item" @click="handleNoteClick(note)">
                  <div class="item-dot"></div>
                  <span class="item-text">{{ note.title || note.content?.slice(0, 40) }}</span>
                </div>
                <div v-if="(notesCount ?? 0) === 0" class="empty-tip">
                  <span>暂无笔记，选中文本可添加</span>
                </div>
              </div>
              <button v-if="(notesCount ?? 0) > 0" class="panel-footer" @click="$emit('viewAllNotes')">
                查看全部笔记
              </button>
            </div>
          </Transition>
        </div>

        <!-- 错题 -->
        <button class="action-btn" @click="$emit('showWrongAnswers')">
          <el-icon><DocumentDelete /></el-icon>
          <span class="btn-label">错题</span>
          <span v-if="(wrongCount ?? 0) > 0" class="btn-badge error">{{ wrongCount }}</span>
        </button>

        <div class="divider"></div>

        <!-- 出题 -->
        <button class="action-btn primary" @click="$emit('startQuiz')">
          <el-icon><EditPen /></el-icon>
          <span class="btn-label">出题</span>
        </button>

        <!-- 统计 -->
        <button class="action-btn" @click="$emit('showStats')">
          <el-icon><DataLine /></el-icon>
          <span class="btn-label">统计</span>
        </button>

        <!-- 知识图谱 -->
        <button class="action-btn" @click="$emit('showGraph')">
          <el-icon><Share /></el-icon>
          <span class="btn-label">图谱</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Notebook, EditPen, DataLine, Share, Location, DocumentDelete } from '@element-plus/icons-vue'

const props = defineProps<{
  notesCount?: number
  wrongCount?: number
  notes?: any[]
  currentLocation?: string
}>()

const emit = defineEmits<{
  (e: 'startQuiz'): void
  (e: 'showStats'): void
  (e: 'showWrongAnswers'): void
  (e: 'showGraph'): void
  (e: 'viewAllNotes'): void
  (e: 'locateNote', note: any): void
}>()

const activePanel = ref<string | null>(null)
const notesRef = ref<HTMLElement | null>(null)

const recentNotes = computed(() => (props.notes || []).slice(0, 5))

function togglePanel(panel: string) {
  activePanel.value = activePanel.value === panel ? null : panel
}

function handleNoteClick(note: any) {
  emit('locateNote', note)
  activePanel.value = null
}

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (
    notesRef.value?.contains(target)
  ) {
    return
  }
  activePanel.value = null
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.smart-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  z-index: 100;
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-bottom: none;
}

.bar-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  height: 56px;
}

.location-section {
  display: flex;
  align-items: center;
  min-width: 0;
  flex-shrink: 1;
}

.location-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f1f5f9;
  border-radius: 8px;
  max-width: 240px;
}

.location-text {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-section {
  display: flex;
  align-items: center;
}

.location-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

.location-icon {
  color: #6366f1;
  font-size: 14px;
}

.location-text {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions-section {
  display: flex;
  align-items: center;
  gap: 6px;
}

.action-wrapper {
  position: relative;
}

.action-btn {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
  color: #0f172a;
}

.action-btn.primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  color: white;
}

.action-btn.primary:hover {
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.btn-label {
  font-size: 13px;
}

.btn-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #6366f1;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-badge.error {
  background: #ef4444;
}

.divider {
  width: 1px;
  height: 24px;
  background: #e2e8f0;
  margin: 0 6px;
}

/* Popup Panel */
.popup-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  width: 280px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
  border: 1px solid #e2e8f0;
  overflow: hidden;
  z-index: 200;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.panel-count {
  font-size: 12px;
  color: #64748b;
}

.panel-content {
  max-height: 240px;
  overflow-y: auto;
  padding: 8px;
}

.list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.list-item:hover {
  background: #f1f5f9;
}

.item-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6366f1;
  flex-shrink: 0;
}

.item-dot.wrong {
  background: #ef4444;
}

.item-text {
  flex: 1;
  font-size: 13px;
  color: #475569;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-action {
  padding: 4px 10px;
  background: #fef2f2;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  color: #ef4444;
  cursor: pointer;
  transition: all 0.2s ease;
}

.item-action:hover {
  background: #ef4444;
  color: white;
}

.empty-tip {
  padding: 24px 16px;
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
}

.empty-tip.success {
  color: #10b981;
}

.panel-footer {
  width: 100%;
  padding: 12px;
  background: #f8fafc;
  border: none;
  border-top: 1px solid #e2e8f0;
  font-size: 13px;
  font-weight: 500;
  color: #6366f1;
  cursor: pointer;
  transition: all 0.2s ease;
}

.panel-footer:hover {
  background: #f1f5f9;
}

.panel-footer-row {
  display: flex;
  gap: 8px;
  padding: 8px;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
}

.footer-btn {
  flex: 1;
  padding: 10px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
}

.footer-btn:hover {
  background: #f1f5f9;
}

.footer-btn.primary {
  background: #6366f1;
  border-color: #6366f1;
  color: white;
}

.footer-btn.primary:hover {
  background: #4f46e5;
}

/* Transitions */
.popup-enter-active,
.popup-leave-active {
  transition: all 0.2s ease;
}

.popup-enter-from,
.popup-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* Responsive */
@media (max-width: 768px) {
  .bar-main {
    padding: 8px 12px;
  }

  .location-text {
    max-width: 100px;
  }

  .btn-label {
    display: none;
  }

  .action-btn {
    padding: 8px 10px;
  }

  .popup-panel {
    width: 260px;
  }
}
</style>
