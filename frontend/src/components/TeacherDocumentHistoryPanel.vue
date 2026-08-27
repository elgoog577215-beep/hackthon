<template>
  <section class="teacher-history-panel" aria-label="历史版本">
    <header>
      <div>
        <History :size="17" />
        <strong>{{ title }}</strong>
      </div>
      <span>恢复会生成一个新版本，不会删除现有内容</span>
      <button type="button" aria-label="关闭历史版本" @click="emit('close')"><X :size="16" /></button>
    </header>
    <ol v-if="items.length">
      <li v-for="item in items" :key="item.id" :class="{ current: item.current }">
        <div class="teacher-history-panel__rail"><i /><span /></div>
        <div class="teacher-history-panel__content">
          <strong>{{ item.title }}</strong>
          <span>{{ item.time }}<template v-if="item.actor"> · {{ item.actor }}</template></span>
          <small v-if="item.detail">{{ item.detail }}</small>
        </div>
        <em v-if="item.current">当前版本</em>
        <button
          v-else
          type="button"
          :disabled="Boolean(restoringId) || restoreDisabled"
          :title="restoreDisabled ? '请先完成或取消当前编辑' : ''"
          @click="emit('restore', item.id)"
        >
          <LoaderCircle v-if="restoringId === item.id" :size="14" class="spin" />
          <RotateCcw v-else :size="14" />
          {{ restoringId === item.id ? '正在恢复…' : '恢复此版本' }}
        </button>
      </li>
    </ol>
    <p v-else>还没有可恢复的历史版本。完成一次保存后，版本会保留在这里。</p>
  </section>
</template>

<script setup lang="ts">
import { History, LoaderCircle, RotateCcw, X } from 'lucide-vue-next'

export interface TeacherDocumentHistoryItem {
  id: string
  title: string
  time: string
  actor?: string
  detail?: string
  current?: boolean
}

defineProps<{
  title: string
  items: TeacherDocumentHistoryItem[]
  restoringId?: string
  restoreDisabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'restore', id: string): void
}>()
</script>

<style scoped>
.teacher-history-panel{border:1px solid #e0e6ef;border-top-color:#edf0f5;background:#fbfcfe}.teacher-history-panel>header{min-height:48px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;padding:0 20px;border-bottom:1px solid #e5e9f0}.teacher-history-panel>header div{display:flex;align-items:center;gap:8px;color:#454ca8}.teacher-history-panel>header strong{color:#29334a;font-size:12px}.teacher-history-panel>header span{color:#7a8699;font-size:10.5px}.teacher-history-panel>header button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:7px;color:#687386;background:transparent;cursor:pointer}.teacher-history-panel>header button:hover{color:#3730a3;background:#f0f1f8}.teacher-history-panel ol{max-height:270px;overflow:auto;margin:0;padding:5px 20px 9px;list-style:none}.teacher-history-panel li{min-height:58px;display:grid;grid-template-columns:16px minmax(0,1fr) auto;align-items:center;gap:10px;position:relative}.teacher-history-panel__rail{height:100%;display:grid;grid-template-rows:1fr 1fr;justify-items:center}.teacher-history-panel__rail i{align-self:end;width:7px;height:7px;border:2px solid #a5aec0;border-radius:50%;background:#fff;z-index:1}.teacher-history-panel__rail span{width:1px;height:100%;background:#dfe4ec}.teacher-history-panel li:first-child .teacher-history-panel__rail i{border-color:#5b57e8}.teacher-history-panel li:last-child .teacher-history-panel__rail span{display:none}.teacher-history-panel__content{min-width:0;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:2px 9px}.teacher-history-panel__content strong{color:#334155;font-size:11.5px}.teacher-history-panel__content span{overflow:hidden;color:#7a8699;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.teacher-history-panel__content small{grid-column:1/-1;color:#667085;font-size:10px}.teacher-history-panel li>em{padding:3px 7px;border-radius:999px;color:#35765b;background:#eaf7ef;font-size:9.5px;font-style:normal;font-weight:750}.teacher-history-panel li>button{min-height:31px;display:flex;align-items:center;gap:6px;padding:0 9px;border:1px solid #d9dee7;border-radius:7px;color:#4f55a9;background:#fff;font-size:10.5px;font-weight:750;cursor:pointer}.teacher-history-panel li>button:hover:not(:disabled){border-color:#bfc4e8;background:#f7f7ff}.teacher-history-panel li>button:disabled{opacity:.55;cursor:not-allowed}.teacher-history-panel>p{margin:0;padding:24px;color:#7a8699;font-size:11px;text-align:center}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
