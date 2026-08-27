<template>
  <div class="teacher-document-command-bar lesson-document-toolbar" role="toolbar" :aria-label="label">
    <div class="teacher-document-command-bar__editing">
      <button
        type="button"
        :disabled="disabled || !editing || !canUndo"
        title="撤销"
        aria-label="撤销"
        @click="emit('undo')"
      ><Undo2 :size="16" /></button>
      <button
        type="button"
        :disabled="disabled || !editing || !canRedo"
        title="重做"
        aria-label="重做"
        @click="emit('redo')"
      ><Redo2 :size="16" /></button>
      <i aria-hidden="true" />
      <button
        type="button"
        :class="{ active: historyOpen }"
        :disabled="disabled"
        :aria-expanded="historyOpen"
        @click="emit('history')"
      >
        <History :size="16" />
        <span>历史版本</span>
        <small v-if="historyCount">{{ historyCount }}</small>
      </button>
      <span class="teacher-document-command-bar__status" :data-tone="statusTone" role="status">
        <LoaderCircle v-if="statusTone === 'busy'" :size="14" class="spin" />
        <CircleAlert v-else-if="statusTone === 'warning'" :size="14" />
        <CircleCheck v-else :size="14" />
        {{ statusLabel }}
      </span>
    </div>
    <div class="teacher-document-command-bar__actions lesson-toolbar-actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleAlert, CircleCheck, History, LoaderCircle, Redo2, Undo2 } from 'lucide-vue-next'

withDefaults(defineProps<{
  label: string
  editing?: boolean
  canUndo?: boolean
  canRedo?: boolean
  disabled?: boolean
  historyOpen?: boolean
  historyCount?: number
  statusLabel?: string
  statusTone?: 'normal' | 'busy' | 'warning'
}>(), {
  editing: false,
  canUndo: false,
  canRedo: false,
  disabled: false,
  historyOpen: false,
  historyCount: 0,
  statusLabel: '已保存',
  statusTone: 'normal',
})

const emit = defineEmits<{
  (event: 'undo'): void
  (event: 'redo'): void
  (event: 'history'): void
}>()
</script>

<style scoped>
.teacher-document-command-bar{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border:1px solid #e0e6ef;border-width:1px 1px 0;background:#fff}.teacher-document-command-bar__editing,.teacher-document-command-bar__actions{min-width:0;display:flex;align-items:center;gap:3px}.teacher-document-command-bar button{min-height:34px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:11.5px;font-weight:750;cursor:pointer}.teacher-document-command-bar button:hover:not(:disabled),.teacher-document-command-bar button.active{color:#3730a3;background:#f0f1f8}.teacher-document-command-bar button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.teacher-document-command-bar button:disabled{opacity:.38;cursor:not-allowed}.teacher-document-command-bar button small{min-width:18px;padding:1px 5px;border-radius:999px;color:#5b57e8;background:#e9e9ff;font-size:9px}.teacher-document-command-bar__editing>i{width:1px;height:22px;margin:0 4px;background:#e1e5ec}.teacher-document-command-bar__status{display:inline-flex;align-items:center;gap:6px;margin-left:7px;color:#687386;font-size:11px;white-space:nowrap}.teacher-document-command-bar__status[data-tone="warning"]{color:#a15c13}.teacher-document-command-bar__status[data-tone="busy"]{color:#4f46c8}.teacher-document-command-bar__actions :deep(button){min-height:34px;display:flex;align-items:center;justify-content:center;gap:6px;padding:0 9px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:11.5px;font-weight:750;cursor:pointer}.teacher-document-command-bar__actions :deep(button:hover:not(:disabled)){color:#3730a3;background:#f0f1f8}.teacher-document-command-bar__actions :deep(button:disabled){opacity:.48;cursor:not-allowed}.teacher-document-command-bar__actions :deep(.primary-action){margin-left:3px;border-color:#d7ddea;color:#3730a3;background:#fff}.teacher-document-command-bar__actions :deep(.primary-action:hover:not(:disabled)){border-color:#c6cbe0;background:#f7f7ff}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.teacher-document-command-bar{padding-inline:12px}.teacher-document-command-bar button span,.teacher-document-command-bar__status{display:none}}
</style>
