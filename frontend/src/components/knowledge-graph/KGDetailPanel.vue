<template>
  <Transition name="slide-in">
    <div v-if="node" class="kgd-panel" @click.stop>
      <div class="kgd-head">
        <span class="kgd-badge" :style="{ background: accent + '18', color: accent }">
          {{ getNodeTypeLabel(node.type) }}
        </span>
        <div class="kgd-head-actions">
          <button class="kgd-icon-btn" title="编辑" @click.stop="$emit('editNode', node)">
            <el-icon :size="12"><Edit /></el-icon>
          </button>
          <button class="kgd-icon-btn kgd-icon-btn--danger" title="删除" @click.stop="$emit('deleteNode', node)">
            <el-icon :size="12"><Delete /></el-icon>
          </button>
          <button class="kgd-close" @click.stop="$emit('close')"><el-icon><Close /></el-icon></button>
        </div>
      </div>

      <h3 class="kgd-title">{{ node.label }}</h3>
      <p v-if="node.description" class="kgd-desc">{{ node.description }}</p>

      <div class="kgd-meta">
        <span v-if="node.created_by === 'user'" class="kgd-tag kgd-tag--user">手动创建</span>
        <span v-else class="kgd-tag kgd-tag--ai">AI 生成</span>
      </div>

      <!-- 相关概念 -->
      <div v-if="relatedNodes.length" class="kgd-section">
        <div class="kgd-sec-title">相关概念</div>
        <button v-for="r in relatedNodes" :key="r.node.id" class="kgd-rel-item" @click.stop="$emit('selectNode', r.node)">
          <span class="kgd-rel-dot" :style="{ background: getNodeColor(r.node) }"></span>
          <span class="kgd-rel-name">{{ r.node.label }}</span>
          <span class="kgd-rel-tag">{{ getRelationLabel(r.relation) }}</span>
          <span v-if="r.weight !== 5" class="kgd-rel-weight">{{ r.weight }}</span>
        </button>
      </div>

      <!-- 相关笔记 -->
      <div v-if="notes.length" class="kgd-section">
        <button class="kgd-sec-toggle" @click.stop="showNotes = !showNotes">
          <span>📝</span>
          <span class="kgd-sec-label">相关笔记</span>
          <span class="kgd-sec-count">{{ notes.length }}</span>
          <span class="kgd-sec-arrow" :class="{ 'kgd-sec-arrow--open': showNotes }">›</span>
        </button>
        <div v-if="showNotes" class="kgd-sec-body">
          <div v-for="note in notes" :key="note.id" class="kgd-note-item" @click.stop="$emit('navigateToNode', note.nodeId)">
            <span class="kgd-note-bar" :style="{ background: note.color || '#6366f1' }"></span>
            <div class="kgd-note-content">
              <p v-if="note.quote" class="kgd-note-quote">{{ note.quote.slice(0, 40) }}{{ note.quote.length > 40 ? '...' : '' }}</p>
              <p class="kgd-note-text">{{ note.content.slice(0, 50) }}{{ note.content.length > 50 ? '...' : '' }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 相关错题 -->
      <div v-if="wrongAnswers.length" class="kgd-section">
        <button class="kgd-sec-toggle" @click.stop="showWrong = !showWrong">
          <span>❌</span>
          <span class="kgd-sec-label">相关错题</span>
          <span class="kgd-sec-count">{{ wrongAnswers.length }}</span>
          <span class="kgd-sec-arrow" :class="{ 'kgd-sec-arrow--open': showWrong }">›</span>
        </button>
        <div v-if="showWrong" class="kgd-sec-body">
          <div v-for="(w, i) in wrongAnswers" :key="w.question + w.nodeId" class="kgd-wrong-item">
            <button class="kgd-wrong-head" @click.stop="expandedWrong = expandedWrong === i ? -1 : i">
              <span class="kgd-wrong-num">{{ i + 1 }}</span>
              <span class="kgd-wrong-q">{{ w.question.slice(0, 36) }}{{ w.question.length > 36 ? '...' : '' }}</span>
            </button>
            <div v-if="expandedWrong === i" class="kgd-wrong-body">
              <div class="kgd-wrong-opt kgd-wrong-opt--wrong">✗ {{ w.options[w.userIndex] }}</div>
              <div class="kgd-wrong-opt kgd-wrong-opt--right">✓ {{ w.options[w.correctIndex] }}</div>
              <p v-if="w.explanation" class="kgd-wrong-exp">{{ w.explanation.slice(0, 80) }}...</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 前往学习 -->
      <div v-if="node.chapter_id" class="kgd-foot">
        <button class="kgd-btn-primary" @click.stop="$emit('navigateToNode', node.chapter_id)">
          <el-icon><Position /></el-icon> 前往学习
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Close, Edit, Delete, Position } from '@element-plus/icons-vue'
import { getNodeColor, getNodeTypeLabel, getRelationLabel, type KGNode } from '../../types/knowledge-graph'

const props = defineProps<{
  node: KGNode | null
  relatedNodes: { node: KGNode; relation: string; weight: number }[]
  notes: any[]
  wrongAnswers: any[]
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'selectNode', node: KGNode): void
  (e: 'editNode', node: KGNode): void
  (e: 'deleteNode', node: KGNode): void
  (e: 'navigateToNode', nodeId: string): void
}>()

const showNotes = ref(false)
const showWrong = ref(false)
const expandedWrong = ref(-1)

const accent = ref('#6366f1')

watch(() => props.node, (n) => {
  if (n) accent.value = getNodeColor(n)
  showNotes.value = false
  showWrong.value = false
  expandedWrong.value = -1
})
</script>

<style scoped>
.kgd-panel { position: absolute; top: 16px; right: 16px; width: 250px; background: rgba(30,31,54,.95); border: 1px solid #2d2f4a; border-radius: 12px; padding: 14px; box-shadow: 0 4px 24px rgba(0,0,0,0.35); backdrop-filter: blur(12px); max-height: calc(100% - 32px); overflow-y: auto; z-index: 10; }
.kgd-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.kgd-badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 20px; }
.kgd-head-actions { display: flex; align-items: center; gap: 3px; }
.kgd-icon-btn { width: 24px; height: 24px; border-radius: 5px; border: none; background: #2d2f4a; color: #8b8fa3; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kgd-icon-btn:hover { background: #3d4167; color: #c4c9e2; }
.kgd-icon-btn--danger:hover { background: rgba(239,68,68,.15); color: #f87171; }
.kgd-close { width: 24px; height: 24px; border-radius: 6px; border: none; background: #2d2f4a; color: #8b8fa3; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.kgd-close:hover { background: rgba(239,68,68,.15); color: #f87171; }
.kgd-title { font-size: 14px; font-weight: 700; color: #c4c9e2; margin: 0 0 6px; }
.kgd-desc { font-size: 12px; color: #8b8fa3; line-height: 1.6; margin: 0 0 10px; }
.kgd-meta { margin-bottom: 10px; }
.kgd-tag { font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 600; }
.kgd-tag--user { background: rgba(99,102,241,.15); color: #a78bfa; }
.kgd-tag--ai { background: rgba(16,185,129,.12); color: #34d399; }
.kgd-section { margin-bottom: 10px; }
.kgd-sec-title { font-size: 11px; font-weight: 700; color: #6b7094; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.kgd-rel-item { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 7px; border-radius: 7px; border: none; background: none; cursor: pointer; text-align: left; transition: background .15s; }
.kgd-rel-item:hover { background: #2d2f4a; }
.kgd-rel-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
.kgd-rel-name { font-size: 12px; color: #c4c9e2; flex: 1; }
.kgd-rel-tag { font-size: 10px; color: #6b7094; }
.kgd-rel-weight { font-size: 9px; color: #a78bfa; background: rgba(99,102,241,.12); padding: 1px 5px; border-radius: 8px; font-weight: 700; }
.kgd-sec-toggle { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; border-radius: 7px; border: none; background: #232541; cursor: pointer; transition: background .15s; font-size: 12px; }
.kgd-sec-toggle:hover { background: #2d2f4a; }
.kgd-sec-label { font-size: 11px; font-weight: 600; color: #8b8fa3; flex: 1; text-align: left; }
.kgd-sec-count { font-size: 10px; color: #6b7094; background: #2d2f4a; padding: 1px 6px; border-radius: 10px; }
.kgd-sec-arrow { font-size: 14px; color: #6b7094; transition: transform .2s; display: inline-block; }
.kgd-sec-arrow--open { transform: rotate(90deg); }
.kgd-sec-body { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.kgd-note-item { display: flex; gap: 7px; padding: 5px 6px; border-radius: 6px; cursor: pointer; transition: background .15s; }
.kgd-note-item:hover { background: #2d2f4a; }
.kgd-note-bar { width: 3px; border-radius: 2px; flex-shrink: 0; align-self: stretch; }
.kgd-note-content { flex: 1; min-width: 0; }
.kgd-note-quote { font-size: 10px; color: #6b7094; margin: 0 0 2px; font-style: italic; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kgd-note-text { font-size: 11px; color: #8b8fa3; margin: 0; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kgd-wrong-item { border-radius: 6px; overflow: hidden; }
.kgd-wrong-head { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; border: none; background: none; cursor: pointer; transition: background .15s; text-align: left; }
.kgd-wrong-head:hover { background: rgba(239,68,68,.08); }
.kgd-wrong-num { width: 18px; height: 18px; border-radius: 50%; background: rgba(239,68,68,.15); color: #f87171; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kgd-wrong-q { font-size: 11px; color: #c4c9e2; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kgd-wrong-body { padding: 4px 6px 8px 30px; }
.kgd-wrong-opt { font-size: 11px; line-height: 1.6; }
.kgd-wrong-opt--wrong { color: #f87171; }
.kgd-wrong-opt--right { color: #34d399; }
.kgd-wrong-exp { font-size: 10px; color: #6b7094; margin: 4px 0 0; line-height: 1.5; }
.kgd-foot { border-top: 1px solid #2d2f4a; padding-top: 10px; }
.kgd-btn-primary { width: 100%; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 14px; border-radius: 9px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.kgd-btn-primary:hover { box-shadow: 0 3px 16px rgba(99,102,241,.4); }
.slide-in-enter-active, .slide-in-leave-active { transition: all .2s ease; }
.slide-in-enter-from, .slide-in-leave-to { opacity: 0; transform: translateX(16px); }
</style>
