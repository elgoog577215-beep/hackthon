<template>
  <div class="teacher-document-command-bar-row">
    <div v-if="showStatus || $slots.context" class="teacher-document-command-bar__context">
      <slot name="context" />
      <span v-if="showStatus" class="teacher-document-command-bar__status" :data-tone="statusTone" role="status">
        <LoaderCircle v-if="statusTone === 'busy'" :size="15" class="spin" />
        <CircleAlert v-else-if="statusTone === 'warning'" :size="15" />
        <CircleCheck v-else :size="15" />
        {{ statusLabel }}
      </span>
    </div>
    <div class="teacher-document-command-bar lesson-document-toolbar" role="toolbar" :aria-label="label">
      <div class="teacher-document-command-bar__editing">
        <template v-if="editing">
          <button
            type="button"
            :disabled="disabled || !canUndo"
            title="撤销"
            aria-label="撤销"
            @click="emit('undo')"
          ><Undo2 :size="16" /></button>
          <button
            type="button"
            :disabled="disabled || !canRedo"
            title="重做"
            aria-label="重做"
            @click="emit('redo')"
          ><Redo2 :size="16" /></button>
          <i aria-hidden="true" />
        </template>
        <button
          v-if="showHistory"
          class="history-action"
          type="button"
          :class="{ active: historyOpen }"
          :disabled="disabled"
          title="历史版本"
          aria-label="历史版本"
          :aria-expanded="historyOpen"
          @click="emit('history')"
        >
          <History :size="16" />
          <small v-if="historyCount">{{ historyCount }}</small>
        </button>
      </div>
      <div class="teacher-document-command-bar__actions lesson-toolbar-actions">
        <slot />
      </div>
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
  showHistory?: boolean
  showStatus?: boolean
  statusLabel?: string
  statusTone?: 'normal' | 'busy' | 'warning'
}>(), {
  editing: false,
  canUndo: false,
  canRedo: false,
  disabled: false,
  historyOpen: false,
  historyCount: 0,
  showHistory: true,
  showStatus: true,
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
.teacher-document-command-bar-row{position:sticky;z-index:9;top:12px;width:calc(100% - 40px);min-height:44px;display:flex;align-items:center;justify-content:space-between;gap:14px;margin:12px 20px 10px}
.teacher-document-command-bar{width:max-content;max-width:100%;min-height:44px;display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:4px;border:1px solid #e1e5ec;border-radius:14px;color:#526077;background:#fff;box-shadow:0 8px 22px rgba(30,41,59,.1)}
.teacher-document-command-bar__context{min-width:0;display:flex;align-items:center;gap:12px;white-space:nowrap}
.teacher-document-command-bar__editing,.teacher-document-command-bar__actions{min-width:0;display:flex;align-items:center;gap:3px;white-space:nowrap}
.teacher-document-command-bar button{min-height:34px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 9px;border:1px solid transparent;border-radius:9px;color:#526077;background:transparent;font-size:15px;font-weight:750;cursor:pointer}
.teacher-document-command-bar button:hover:not(:disabled),.teacher-document-command-bar button.active{color:#3730a3;background:#f1f2f8}
.teacher-document-command-bar button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.teacher-document-command-bar button:disabled{opacity:.38;cursor:not-allowed}
.teacher-document-command-bar button small{position:absolute;top:0;right:0;min-width:16px;padding:0 4px;border-radius:999px;color:#4338ca;background:#e9e9ff;font-size:15px;line-height:16px}
.teacher-document-command-bar__editing>i{width:1px;height:20px;margin:0 2px;background:#e1e5ec}
.teacher-document-command-bar .history-action{position:relative;width:34px;padding:0}
.teacher-document-command-bar__status{display:inline-flex;align-items:center;gap:5px;color:#687386;font-size:15px;white-space:nowrap}
.teacher-document-command-bar__status svg{color:#159174}
.teacher-document-command-bar__status[data-tone="warning"]{color:#a15c13}
.teacher-document-command-bar__status[data-tone="warning"] svg{color:#b56a18}
.teacher-document-command-bar__status[data-tone="busy"]{color:#4f46c8}
.teacher-document-command-bar__status[data-tone="busy"] svg{color:#5b57d9}
.teacher-document-command-bar__actions :deep(button){min-height:34px;display:flex;align-items:center;justify-content:center;gap:6px;padding:0 10px;border:1px solid transparent;border-radius:9px;color:#526077;background:transparent;font-size:15px;font-weight:750;cursor:pointer}
.teacher-document-command-bar__actions :deep(button:hover:not(:disabled)){color:#3730a3;background:#f1f2f8}
.teacher-document-command-bar__actions :deep(button:focus-visible){outline:2px solid #5b57e8;outline-offset:2px}
.teacher-document-command-bar__actions :deep(button:disabled){opacity:.48;cursor:not-allowed}
.teacher-document-command-bar__actions :deep(.primary-action){margin-left:2px;border-color:#454ca8;color:#fff;background:#454ca8}
.teacher-document-command-bar__actions :deep(.primary-action:hover:not(:disabled)){border-color:#373b91;color:#fff;background:#373b91}
.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.teacher-document-command-bar-row{width:calc(100% - 24px);gap:10px;margin-inline:12px}.teacher-document-command-bar__context{gap:8px}}
</style>
