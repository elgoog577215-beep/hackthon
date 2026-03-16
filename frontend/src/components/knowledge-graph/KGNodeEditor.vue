<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="kge-overlay" @click.self="handleCancel">
        <div class="kge-dialog">
          <div class="kge-header">
            <span class="kge-title">{{ isEdit ? '编辑节点' : '新建节点' }}</span>
            <button class="kge-close" @click="handleCancel"><el-icon><Close /></el-icon></button>
          </div>
          <div class="kge-body">
            <div class="kge-field">
              <label class="kge-label">名称 <span class="kge-req">*</span></label>
              <input v-model="form.label" class="kge-input" placeholder="输入概念名称..." maxlength="100" ref="labelInput" />
            </div>
            <div class="kge-field">
              <label class="kge-label">类型</label>
              <div class="kge-type-grid">
                <button v-for="t in nodeTypes" :key="t.value"
                  class="kge-type-btn" :class="{ 'kge-type-btn--active': form.type === t.value }"
                  :style="form.type === t.value ? { borderColor: t.color, background: t.color + '12' } : {}"
                  @click="form.type = t.value">
                  <span class="kge-type-dot" :style="{ background: t.color }"></span>
                  {{ t.label }}
                </button>
              </div>
            </div>
            <div class="kge-field">
              <label class="kge-label">描述</label>
              <textarea v-model="form.description" class="kge-textarea" placeholder="简要描述..." rows="3" maxlength="500"></textarea>
            </div>
            <div class="kge-field">
              <label class="kge-label">自定义颜色</label>
              <div class="kge-color-row">
                <input type="color" v-model="colorPick" class="kge-color-picker" />
                <button v-if="form.color" class="kge-color-clear" @click="form.color = undefined">清除</button>
                <span class="kge-color-hint">{{ form.color || '使用类型默认色' }}</span>
              </div>
            </div>
          </div>
          <div class="kge-footer">
            <button class="kge-btn-cancel" @click="handleCancel">取消</button>
            <button class="kge-btn-confirm" :disabled="!form.label.trim()" @click="handleConfirm">
              {{ isEdit ? '保存' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { NODE_TYPES, type KGNode, type KGNodeType } from '../../types/knowledge-graph'

const props = defineProps<{
  visible: boolean
  node?: KGNode | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', data: { label: string; type: KGNodeType; description: string; color?: string }): void
}>()

const isEdit = computed(() => !!props.node)
const labelInput = ref<HTMLInputElement>()
const nodeTypes = NODE_TYPES.filter(t => t.value !== 'root')

const form = ref({
  label: '',
  type: 'custom' as KGNodeType,
  description: '',
  color: undefined as string | undefined,
})

const colorPick = computed({
  get: () => form.value.color || '#8b5cf6',
  set: (v: string) => { form.value.color = v },
})

watch(() => props.visible, (show) => {
  if (show) {
    if (props.node) {
      form.value = {
        label: props.node.label,
        type: props.node.type,
        description: props.node.description || '',
        color: props.node.color,
      }
    } else {
      form.value = { label: '', type: 'custom', description: '', color: undefined }
    }
    nextTick(() => labelInput.value?.focus())
  }
})

const handleCancel = () => emit('close')
const handleConfirm = () => {
  if (!form.value.label.trim()) return
  emit('confirm', { ...form.value })
}
</script>

<style scoped>
.kge-overlay { position: fixed; inset: 0; z-index: 200; background: rgba(15,23,42,0.4); backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; }
.kge-dialog { width: 420px; max-width: 90vw; background: #fff; border-radius: 14px; box-shadow: 0 16px 48px rgba(0,0,0,0.15); overflow: hidden; }
.kge-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #f1f5f9; }
.kge-title { font-size: 14px; font-weight: 700; color: #0f172a; }
.kge-close { width: 28px; height: 28px; border-radius: 6px; border: none; background: #f1f5f9; color: #64748b; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kge-close:hover { background: #fee2e2; color: #ef4444; }
.kge-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.kge-field { display: flex; flex-direction: column; gap: 5px; }
.kge-label { font-size: 12px; font-weight: 600; color: #475569; }
.kge-req { color: #ef4444; }
.kge-input { padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; color: #1e293b; background: #f8fafc; transition: all .2s; }
.kge-input:focus { outline: none; border-color: #6366f1; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.kge-textarea { padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; color: #1e293b; background: #f8fafc; resize: vertical; font-family: inherit; transition: all .2s; }
.kge-textarea:focus { outline: none; border-color: #6366f1; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.kge-type-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.kge-type-btn { display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; border-radius: 7px; border: 1.5px solid #e2e8f0; background: #fff; font-size: 12px; color: #475569; cursor: pointer; transition: all .15s; }
.kge-type-btn:hover { border-color: #cbd5e1; }
.kge-type-btn--active { font-weight: 600; color: #1e293b; }
.kge-type-dot { width: 8px; height: 8px; border-radius: 50%; }
.kge-color-row { display: flex; align-items: center; gap: 8px; }
.kge-color-picker { width: 32px; height: 32px; border: 1px solid #e2e8f0; border-radius: 6px; cursor: pointer; padding: 2px; }
.kge-color-clear { font-size: 11px; color: #64748b; background: #f1f5f9; border: none; border-radius: 5px; padding: 3px 8px; cursor: pointer; }
.kge-color-clear:hover { background: #e2e8f0; }
.kge-color-hint { font-size: 11px; color: #94a3b8; }
.kge-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid #f1f5f9; }
.kge-btn-cancel { padding: 7px 16px; border-radius: 8px; border: 1px solid #e2e8f0; background: #fff; font-size: 13px; color: #64748b; cursor: pointer; transition: all .15s; }
.kge-btn-cancel:hover { background: #f8fafc; color: #1e293b; }
.kge-btn-confirm { padding: 7px 16px; border-radius: 8px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s; }
.kge-btn-confirm:hover:not(:disabled) { box-shadow: 0 3px 10px rgba(99,102,241,.3); }
.kge-btn-confirm:disabled { opacity: .45; cursor: not-allowed; }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
