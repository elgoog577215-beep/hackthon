<template>
  <div class="inline-annotation-layer">
    <button
      v-for="marker in markers"
      :key="marker.note.id"
      type="button"
      class="inline-record-marker"
      :style="{ left: `${marker.left}px`, top: `${marker.top}px` }"
      :title="t('inlineRecords.open', '查看此处的学习记录')"
      :aria-label="t('inlineRecords.open', '查看此处的学习记录')"
      @click.stop="emit('open', { note: marker.note, x: marker.viewportX, y: marker.viewportY })"
    >
      <NotebookTabs :size="13" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NotebookTabs } from 'lucide-vue-next'
import type { Note } from '@/stores/types'
import { t } from '@/shared/i18n'

const props = defineProps<{ notes: Note[]; rootId?: string }>()
const emit = defineEmits<{ open: [payload: { note: Note; x: number; y: number }] }>()
const markers = ref<Array<{ note: Note; left: number; top: number; viewportX: number; viewportY: number }>>([])
let refreshTimer: ReturnType<typeof setTimeout> | null = null

function refresh() {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(async () => {
    await nextTick()
    const root = document.getElementById(props.rootId || 'content-scroll-container')
    if (!root) return
    const rootRect = root.getBoundingClientRect()
    markers.value = props.notes.flatMap(note => {
      if (!note.highlightId) return []
      const elements = [...document.querySelectorAll<HTMLElement>(`[id^="${CSS.escape(note.highlightId)}"]`)]
      const target = elements[elements.length - 1]
      if (!target) return []
      const rect = target.getBoundingClientRect()
      return [{
        note,
        left: Math.max(6, rect.right - rootRect.left + root.scrollLeft + 3),
        top: Math.max(6, rect.bottom - rootRect.top + root.scrollTop - 18),
        viewportX: rect.right + 8,
        viewportY: rect.bottom,
      }]
    })
  }, 0)
}

watch(() => props.notes.map(note => `${note.id}:${note.quote}:${note.syncState}`).join('|'), refresh)
onMounted(() => {
  const root = document.getElementById(props.rootId || 'content-scroll-container')
  root?.addEventListener('scroll', refresh, { passive: true })
  window.addEventListener('resize', refresh)
  refresh()
})
onBeforeUnmount(() => {
  if (refreshTimer) clearTimeout(refreshTimer)
  const root = document.getElementById(props.rootId || 'content-scroll-container')
  root?.removeEventListener('scroll', refresh)
  window.removeEventListener('resize', refresh)
})

defineExpose({ refresh })
</script>

<style scoped>
.inline-annotation-layer { position:absolute; inset:0; z-index:8; pointer-events:none; }
.inline-record-marker { position:absolute; width:24px; height:24px; display:grid; place-items:center; padding:0; border:1px solid rgba(245,158,11,.22); border-radius:50%; color:#b45309; background:rgba(255,251,235,.92); box-shadow:0 3px 9px rgba(120,53,15,.12); pointer-events:auto; cursor:pointer; transform:translateY(-1px); transition:color .16s ease,background .16s ease,transform .16s ease; }
.inline-record-marker:hover { color:#92400e; background:#fef3c7; transform:translateY(-2px); }
</style>
