<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="method-overlay"
      @click.self="handleClose"
    >
      <div
        class="method-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysis-method-title"
        @click.stop
      >
        <div class="modal-header">
          <h3 id="analysis-method-title">选择分析方式</h3>
          <button
            type="button"
            class="modal-close"
            :disabled="pending"
            aria-label="关闭"
            @click="handleClose"
          >
            &times;
          </button>
        </div>

        <div class="modal-body">
          <p class="modal-description">请选择视频分析方式：</p>

          <div class="options-list">
            <button
              v-for="opt in options"
              :key="opt.id"
              type="button"
              class="option-card"
              :class="{ selected: selected === opt.id }"
              :disabled="pending"
              @click="selected = opt.id"
            >
              <span class="option-icon" aria-hidden="true">{{ opt.icon }}</span>
              <span class="option-text">
                <span class="option-title">{{ opt.title }}</span>
                <span class="option-desc">{{ opt.desc }}</span>
              </span>
              <span class="option-radio" :class="{ on: selected === opt.id }" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="modal-footer">
          <button
            type="button"
            class="footer-btn ghost"
            :disabled="pending"
            @click="handleClose"
          >
            取消
          </button>
          <button
            type="button"
            class="footer-btn primary"
            :disabled="pending"
            @click="handleConfirm"
          >
            {{ pending ? '启动中...' : '开始分析' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { AnalysisMode } from '../api/video'

const props = defineProps<{
  visible: boolean
  pending?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', mode: AnalysisMode): void
}>()

const options: Array<{ id: AnalysisMode; icon: string; title: string; desc: string }> = [
  {
    id: 'cloud',
    icon: '☁️',
    title: '云端分析',
    desc: '上传至云端进行分析，需等待平台处理',
  },
  {
    id: 'local',
    icon: '💻',
    title: '本地分析',
    desc: '使用本地模型直接分析视频，不依赖第三方平台',
  },
]

const selected = ref<AnalysisMode>('cloud')

// 每次打开时重置为默认选项
watch(
  () => props.visible,
  (v) => {
    if (v) selected.value = 'cloud'
  },
)

function handleClose() {
  if (props.pending) return
  emit('close')
}

function handleConfirm() {
  if (props.pending) return
  emit('select', selected.value)
}
</script>

<style scoped>
.method-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal-overlay, 1200);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  box-sizing: border-box;
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.method-modal {
  position: relative;
  background: #fff;
  border-radius: 12px;
  width: min(480px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: #666;
  padding: 0 4px;
}

.modal-close:hover:not(:disabled) {
  color: #333;
}

.modal-close:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
}

.modal-description {
  margin: 0 0 16px;
  font-size: 14px;
  color: #666;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1.5px solid #e3e6ee;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.option-card:hover:not(:disabled) {
  border-color: #b9c3f0;
  background: #f7f9ff;
}

.option-card.selected {
  border-color: #3d51e3;
  background: #f0f4ff;
  box-shadow: 0 0 0 3px rgba(61, 81, 227, 0.12);
}

.option-card:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.option-icon {
  font-size: 22px;
  flex-shrink: 0;
}

.option-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1 1 auto;
  min-width: 0;
}

.option-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2430;
}

.option-desc {
  font-size: 12.5px;
  color: #6b7280;
  line-height: 1.45;
}

.option-radio {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid #c4cad8;
  position: relative;
}

.option-radio.on {
  border-color: #3d51e3;
}

.option-radio.on::after {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  background: #3d51e3;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid #eee;
  flex-shrink: 0;
}

.footer-btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #d9dce5;
  background: #fff;
  color: #333;
  transition: all 0.15s;
}

.footer-btn.ghost:hover:not(:disabled) {
  background: #f5f6fa;
}

.footer-btn.primary {
  background: #3d51e3;
  border-color: #3d51e3;
  color: #fff;
}

.footer-btn.primary:hover:not(:disabled) {
  background: #3343c4;
  border-color: #3343c4;
}

.footer-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
