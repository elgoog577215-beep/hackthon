<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="kge-overlay" @click.self="handleCancel">
        <div class="kge-dialog">
          <div class="kge-header">
            <span class="kge-title">{{ isEdit ? '编辑关系' : '新建关系' }}</span>
            <button class="kge-close" @click="handleCancel"><el-icon><Close /></el-icon></button>
          </div>
          <div class="kge-body">
            <!-- 连线预览 -->
            <div v-if="sourceNode && targetNode" class="kge-edge-preview">
              <span class="kge-ep-node" :style="{ borderColor: getNodeColor(sourceNode) }">{{ sourceNode.label }}</span>
              <span class="kge-ep-arrow">→</span>
              <span class="kge-ep-node" :style="{ borderColor: getNodeColor(targetNode) }">{{ targetNode.label }}</span>
            </div>

            <div v-if="!isEdit" class="kge-field">
              <label class="kge-label">提示</label>
              <p class="kge-hint">在画布中依次点击源节点和目标节点来选择连线对象，或在下方手动选择。</p>
            </div>

            <div class="kge-field">
              <label class="kge-label">关系类型</label>
              <div class="kge-rel-grid">
                <button v-for="r in relationTypes" :key="r.value"
                  class="kge-rel-btn" :class="{ 'kge-rel-btn--active': form.relation === r.value }"
                  :style="form.relation === r.value ? { borderColor: r.color, background: r.color + '12' } : {}"
                  @click="form.relation = r.value">
                  <span class="kge-rel-dot" :style="{ background: r.color }"></span>
                  {{ r.label }}
                </button>
              </div>
            </div>

            <div class="kge-field">
              <label class="kge-label">权重 <span class="kge-weight-val">{{ form.weight }}</span></label>
              <div class="kge-slider-row">
                <span class="kge-slider-label">弱</span>
                <input type="range" v-model.number="form.weight" min="1" max="10" step="1" class="kge-slider" />
                <span class="kge-slider-label">强</span>
              </div>
            </div>

            <div class="kge-field">
              <label class="kge-label">自定义标签</label>
              <input v-model="form.label" class="kge-input" placeholder="可选，覆盖默认关系名..." maxlength="50" />
            </div>
          </div>
          <div class="kge-footer">
            <button class="kge-btn-cancel" @click="handleCancel">取消</button>
            <button class="kge-btn-confirm" @click="handleConfirm">
              {{ isEdit ? '保存' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { RELATION_TYPES, getNodeColor, type KGNode, type KGEdge } from '../../types/knowledge-graph'

const props = defineProps<{
  visible: boolean
  edge?: KGEdge | null
  sourceNode?: KGNode | null
  targetNode?: KGNode | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', data: { relation: string; weight: number; label?: string }): void
}>()

const isEdit = computed(() => !!props.edge)
const relationTypes = RELATION_TYPES

const form = ref({
  relation: 'related',
  weight: 5,
  label: '',
})

watch(() => props.visible, (show) => {
  if (show && props.edge) {
    form.value = {
      relation: props.edge.relation,
      weight: props.edge.weight ?? 5,
      label: props.edge.label || '',
    }
  } else if (show) {
    form.value = { relation: 'related', weight: 5, label: '' }
  }
})

const handleCancel = () => emit('close')
const handleConfirm = () => {
  emit('confirm', {
    relation: form.value.relation,
    weight: form.value.weight,
    label: form.value.label || undefined,
  })
}
</script>

<style scoped>
.kge-overlay { position: fixed; inset: 0; z-index: 200; background: rgba(15,23,42,0.4); backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; }
.kge-dialog { width: 440px; max-width: 90vw; background: #fff; border-radius: 14px; box-shadow: 0 16px 48px rgba(0,0,0,0.15); overflow: hidden; }
.kge-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #f1f5f9; }
.kge-title { font-size: 14px; font-weight: 700; color: #0f172a; }
.kge-close { width: 28px; height: 28px; border-radius: 6px; border: none; background: #f1f5f9; color: #64748b; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kge-close:hover { background: #fee2e2; color: #ef4444; }
.kge-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.kge-field { display: flex; flex-direction: column; gap: 5px; }
.kge-label { font-size: 12px; font-weight: 600; color: #475569; }
.kge-hint { font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.5; }
.kge-input { padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; color: #1e293b; background: #f8fafc; transition: all .2s; }
.kge-input:focus { outline: none; border-color: #6366f1; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.kge-edge-preview { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 12px; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0; }
.kge-ep-node { padding: 5px 12px; border-radius: 7px; border: 2px solid #e2e8f0; font-size: 12px; font-weight: 600; color: #1e293b; background: #fff; }
.kge-ep-arrow { font-size: 16px; color: #94a3b8; }
.kge-rel-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.kge-rel-btn { display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; border-radius: 7px; border: 1.5px solid #e2e8f0; background: #fff; font-size: 12px; color: #475569; cursor: pointer; transition: all .15s; }
.kge-rel-btn:hover { border-color: #cbd5e1; }
.kge-rel-btn--active { font-weight: 600; color: #1e293b; }
.kge-rel-dot { width: 8px; height: 8px; border-radius: 50%; }
.kge-weight-val { font-weight: 700; color: #6366f1; margin-left: 4px; }
.kge-slider-row { display: flex; align-items: center; gap: 8px; }
.kge-slider-label { font-size: 11px; color: #94a3b8; flex-shrink: 0; }
.kge-slider { flex: 1; height: 6px; -webkit-appearance: none; appearance: none; background: #e2e8f0; border-radius: 3px; outline: none; }
.kge-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 18px; height: 18px; border-radius: 50%; background: #6366f1; cursor: pointer; box-shadow: 0 2px 6px rgba(99,102,241,.3); }
.kge-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid #f1f5f9; }
.kge-btn-cancel { padding: 7px 16px; border-radius: 8px; border: 1px solid #e2e8f0; background: #fff; font-size: 13px; color: #64748b; cursor: pointer; transition: all .15s; }
.kge-btn-cancel:hover { background: #f8fafc; color: #1e293b; }
.kge-btn-confirm { padding: 7px 16px; border-radius: 8px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s; }
.kge-btn-confirm:hover { box-shadow: 0 3px 10px rgba(99,102,241,.3); }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
