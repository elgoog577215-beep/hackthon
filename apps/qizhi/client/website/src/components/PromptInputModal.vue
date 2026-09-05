<template>
  <Teleport to="body">
    <div v-if="modelValue" class="pim-overlay" @click.self="emitCancel">
      <div class="pim-box" role="dialog" aria-modal="true">
        <div class="pim-header">
          <h3>{{ title }}</h3>
          <button type="button" class="pim-close" @click="emitCancel" :disabled="pending">&times;</button>
        </div>
        <div class="pim-body">
          <label v-if="label" class="pim-label">{{ label }}</label>
          <textarea
            v-if="multiline"
            v-model="localValue"
            class="pim-input pim-textarea"
            :rows="rows"
            :placeholder="placeholder"
            :disabled="pending"
          />
          <template v-else>
            <input
              v-model="localValue"
              class="pim-input"
              :type="inputType"
              :min="showRange ? rangeMin : undefined"
              :max="showRange ? rangeMax : undefined"
              step="1"
              :placeholder="placeholder"
              :disabled="pending"
              @keydown.enter.prevent="onEnterConfirm"
              @blur="onNumberBlur"
            />
            <div v-if="showRange" class="range-control pim-range-control">
              <input
                type="range"
                class="range-slider"
                :min="rangeMin"
                :max="rangeMax"
                step="1"
                :value="rangeValue"
                :style="{ '--range-ratio': rangeRatio }"
                :disabled="pending"
                aria-label="滑动调节数值"
                @input="onRangeInput"
              />
              <div class="range-ticks">
                <span>{{ rangeMin }}</span>
                <span>{{ rangeMax }}</span>
              </div>
            </div>
          </template>
          <div v-if="error" class="pim-error">{{ errorText }}</div>
          <div class="pim-footer">
            <button type="button" class="pim-btn-secondary" @click="emitCancel" :disabled="pending">取消</button>
            <button type="button" class="pim-btn-primary" @click="emitSubmit" :disabled="pending">
              {{ pending ? pendingLabel : confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    label?: string
    initialValue?: string
    placeholder?: string
    /** text | number */
    inputType?: 'text' | 'number'
    multiline?: boolean
    rows?: number
    pending?: boolean
    error?: boolean
    errorText?: string
    confirmLabel?: string
    pendingLabel?: string
    /** 数字输入时展示横向滑动条（与大纲表单 range-slider 同款） */
    showRange?: boolean
    rangeMin?: number
    rangeMax?: number
  }>(),
  {
    label: '',
    initialValue: '',
    placeholder: '',
    inputType: 'text',
    multiline: false,
    rows: 4,
    pending: false,
    error: false,
    errorText: '',
    confirmLabel: '确定',
    pendingLabel: '保存中...',
    showRange: false,
    rangeMin: 0,
    rangeMax: 128,
  }
)

const emit = defineEmits<{
  'update:modelValue': [boolean]
  cancel: []
  submit: [value: string]
}>()

const localValue = ref(props.initialValue)

const rangeValue = computed(() => {
  const n = parseInt(String(localValue.value).trim(), 10)
  if (Number.isNaN(n)) return props.rangeMin
  return Math.min(props.rangeMax, Math.max(props.rangeMin, Math.round(n)))
})

const rangeRatio = computed(() => {
  const span = props.rangeMax - props.rangeMin
  if (span <= 0) return 0
  return (rangeValue.value - props.rangeMin) / span
})

function onRangeInput(e: Event) {
  localValue.value = String((e.target as HTMLInputElement).value)
}

function onNumberBlur() {
  if (!props.showRange) return
  const n = parseInt(String(localValue.value).trim(), 10)
  if (Number.isNaN(n)) {
    localValue.value = String(props.rangeMin)
    return
  }
  localValue.value = String(Math.min(props.rangeMax, Math.max(props.rangeMin, Math.round(n))))
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) localValue.value = props.initialValue ?? ''
  }
)

watch(
  () => props.initialValue,
  (v) => {
    if (props.modelValue) localValue.value = v ?? ''
  }
)

function emitCancel() {
  if (props.pending) return
  emit('update:modelValue', false)
  emit('cancel')
}

function emitSubmit() {
  if (props.pending) return
  emit('submit', localValue.value)
}

function onEnterConfirm() {
  if (props.multiline) return
  emitSubmit()
}
</script>

<style scoped>
.pim-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal-overlay, 1200);
}

.pim-box {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  width: 90%;
  max-width: 440px;
  max-height: 90vh;
  overflow: auto;
}

.pim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}

.pim-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.pim-close {
  background: none;
  border: none;
  font-size: 24px;
  line-height: 1;
  color: #666;
  cursor: pointer;
  padding: 0 4px;
}

.pim-close:hover:not(:disabled) {
  color: #333;
}

.pim-body {
  padding: 20px;
}

.pim-label {
  display: block;
  font-size: 14px;
  color: #333;
  margin-bottom: 8px;
}

.pim-input {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  box-sizing: border-box;
  font-family: inherit;
  color: #333;
  transition: border-color 0.2s;
}

.pim-input:focus {
  outline: none;
  border-color: #c5d9ff;
}

.pim-range-control {
  margin-top: 12px;
}

.pim-textarea {
  resize: vertical;
  min-height: 96px;
  border-radius: 20px;
}

.pim-error {
  font-size: 13px;
  color: #d32f2f;
  margin-top: 10px;
}

.pim-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
}

.pim-btn-secondary {
  padding: 8px 16px;
  font-size: 14px;
  color: #333;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.pim-btn-secondary:hover:not(:disabled) {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
}

.pim-btn-primary {
  padding: 8px 16px;
  font-size: 14px;
  color: #333;
  background-color: #fff;
  border: 1px solid #c5d9ff;
  border-radius: 20px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.pim-btn-primary:hover:not(:disabled) {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
}

.pim-btn-primary:disabled,
.pim-btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
