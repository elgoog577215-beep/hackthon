<template>
  <Teleport to="body">
    <div class="course-dialog-layer" @keydown="keydown">
      <div class="course-dialog-backdrop" @click="close" />
      <section ref="panel" class="course-dialog-panel" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
        <header><h2 :id="titleId">{{ title }}</h2><button type="button" :disabled="busy" :aria-label="t('common.close')" @click="close"><X :size="17" /></button></header>
        <slot />
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
const props = defineProps<{ title: string; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
const titleId = useId()
const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
function close() { if (!props.busy) emit('close') }
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return }
  if (event.key !== 'Tab' || !panel.value) return
  const items = [...panel.value.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(item => !item.closest('[hidden]'))
  const first = items[0], last = items[items.length - 1]
  if (!first) { event.preventDefault(); panel.value.focus(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onMounted(async () => { await nextTick(); panel.value?.querySelector<HTMLElement>('input:not(:disabled),button:not(:disabled)')?.focus() })
onBeforeUnmount(() => { if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true }) })
</script>

<style scoped>
.course-dialog-layer{position:fixed;inset:0;z-index:2400;display:grid;place-items:center;padding:20px;box-sizing:border-box}.course-dialog-backdrop{position:absolute;inset:0;background:rgb(15 23 42/.3)}.course-dialog-panel{position:relative;width:min(520px,100%);max-height:calc(100vh - 40px);overflow:auto;border:1px solid var(--lz-border);border-radius:12px;color:var(--lz-text-primary);background:var(--lz-surface,#fff);box-shadow:0 20px 48px rgb(15 23 42/.16);outline:0}.course-dialog-panel>header{min-height:60px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid var(--lz-border)}h2{margin:0;font-size:18px;line-height:1.35}header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}header button:hover{background:var(--lz-fill)}button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
</style>
