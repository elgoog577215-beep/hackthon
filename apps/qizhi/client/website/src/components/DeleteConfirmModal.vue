<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div v-if="modelValue" class="app-dialog-overlay" @click.self="onOverlayClick">
      <div class="app-dialog-box" role="dialog" aria-modal="true" :aria-labelledby="titleId" @click.stop>
        <h3 :id="titleId" class="app-dialog-title">{{ title }}</h3>
        <div v-if="bodyText.trim()" class="app-dialog-content">
          {{ bodyText }}
        </div>
        <div v-else class="app-dialog-content">
          确定要删除{{ entityKind }}「{{ entityName }}」吗？{{ hint }}
        </div>
        <div v-if="error" class="app-dialog-error">{{ errorText }}</div>
        <div class="app-dialog-footer">
          <button type="button" class="app-dialog-btn app-dialog-btn--cancel" @click="emitCancel" :disabled="pending">
            取消
          </button>
          <button
            type="button"
            class="app-dialog-btn app-dialog-btn--danger"
            @click="emitConfirm"
            :disabled="pending || (!useCustomBody && !entityName)"
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
import { computed } from 'vue'
import '../assets/app-dialog.css'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    /** 文案中的类型词，如「课程」「资源」 */
    entityKind: string
    entityName: string
    /** 若填写则整段作为正文，不再使用「确定要删除某「名」」模板（用于长说明） */
    bodyText?: string
    pending?: boolean
    /** 是否显示错误提示 */
    error?: boolean
    errorText?: string
    /** 确认按钮文案 */
    confirmLabel?: string
    pendingLabel?: string
    /** 「此操作不可恢复。」前的补充，默认与课程删除一致 */
    hint?: string
  }>(),
  {
    bodyText: '',
    pending: false,
    error: false,
    errorText: '操作失败，请稍后重试',
    confirmLabel: '删除',
    pendingLabel: '删除中...',
    hint: '此操作不可恢复。',
  }
)

const useCustomBody = computed(() => Boolean(props.bodyText?.trim()))

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  cancel: []
  confirm: []
}>()

const titleId = computed(() => `delete-confirm-title-${Math.random().toString(36).slice(2, 9)}`)

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
  emitCancel()
}
</script>
