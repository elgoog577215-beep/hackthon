<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div v-if="modelValue" class="app-dialog-overlay" @click.self="onOverlayClick">
      <div class="app-dialog-box" role="dialog" aria-modal="true" @click.stop>
        <h3 class="app-dialog-title">{{ title }}</h3>
        <div class="app-dialog-content">{{ message }}</div>
        <div v-if="error" class="app-dialog-error">{{ errorText }}</div>
        <div class="app-dialog-footer">
          <button
            v-if="!singleButton"
            type="button"
            class="app-dialog-btn app-dialog-btn--cancel"
            @click="emitCancel"
            :disabled="pending"
          >
            {{ cancelLabel }}
          </button>
          <button
            type="button"
            :class="[
              'app-dialog-btn',
              variant === 'danger' ? 'app-dialog-btn--danger' : 'app-dialog-btn--primary',
            ]"
            @click="emitConfirm"
            :disabled="pending"
          >
            {{ pending ? pendingLabel : confirmLabel }}
          </button>
        </div>
      </div>
    </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import '../assets/app-dialog.css'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    /** danger：红色主按钮（警告/不可逆）；info：深色主按钮（提示） */
    variant: 'danger' | 'info'
    title: string
    message: string
    singleButton?: boolean
    confirmLabel?: string
    cancelLabel?: string
    pending?: boolean
    error?: boolean
    errorText?: string
    pendingLabel?: string
  }>(),
  {
    singleButton: false,
    confirmLabel: '确认',
    cancelLabel: '取消',
    pending: false,
    error: false,
    errorText: '操作失败，请稍后重试',
    pendingLabel: '处理中...',
  }
)

const emit = defineEmits<{
  'update:modelValue': [boolean]
  cancel: []
  confirm: []
}>()

function emitCancel() {
  if (props.pending) return
  emit('update:modelValue', false)
  emit('cancel')
}

function emitConfirm() {
  if (props.pending) return
  emit('confirm')
}

function onOverlayClick() {
  if (props.singleButton) emitConfirm()
  else emitCancel()
}
</script>
