<template>
  <button
    v-if="selection.visible"
    ref="actionButton"
    type="button"
    class="text-selection-ai-action"
    :style="{ left: `${selection.x}px`, top: `${selection.y}px` }"
    :aria-label="label"
    @pointerdown.prevent
    @click="invoke"
  >
    <Sparkles :size="13" />
    {{ label }}
  </button>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Sparkles } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  container: HTMLElement | null
  disabled?: boolean
  label?: string
}>(), {
  disabled: false,
  label: 'AI 修改',
})

const emit = defineEmits<{
  invoke: [payload: { text: string }]
}>()

const actionButton = ref<HTMLButtonElement | null>(null)
const selection = reactive({ visible: false, x: 0, y: 0, text: '' })

function clear() {
  selection.visible = false
  selection.text = ''
}

function selectionElement(node: Node | null) {
  return node instanceof Element ? node : node?.parentElement || null
}

function capture(event: MouseEvent) {
  if (props.disabled || !props.container || actionButton.value?.contains(event.target as Node)) return
  const selected = window.getSelection()
  const text = selected?.toString().replace(/\s+/g, ' ').trim() || ''
  if (!selected || selected.rangeCount === 0 || text.length < 2) {
    clear()
    return
  }
  const range = selected.getRangeAt(0)
  const start = selectionElement(range.startContainer)
  const end = selectionElement(range.endContainer)
  if (!start || !end || !props.container.contains(start) || !props.container.contains(end)) {
    clear()
    return
  }
  const rect = range.getBoundingClientRect()
  const containerRect = props.container.getBoundingClientRect()
  const x = rect.left - containerRect.left + props.container.scrollLeft + rect.width / 2
  const y = rect.top - containerRect.top + props.container.scrollTop - 10
  selection.text = text.slice(0, 1200)
  selection.x = Math.max(58, Math.min(props.container.clientWidth - 58, x))
  selection.y = Math.max(34, y)
  selection.visible = true
}

function invoke() {
  if (!selection.text) return
  emit('invoke', { text: selection.text })
  clear()
  window.getSelection()?.removeAllRanges()
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (actionButton.value?.contains(event.target as Node)) return
  if (!props.container?.contains(event.target as Node)) clear()
}

onMounted(() => {
  document.addEventListener('mouseup', capture)
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mouseup', capture)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})

watch(() => props.disabled, disabled => { if (disabled) clear() })
</script>

<style scoped>
.text-selection-ai-action{
  position:absolute;
  z-index:18;
  min-height:30px;
  display:flex;
  align-items:center;
  gap:5px;
  padding:0 9px;
  border:1px solid #c7c9ef;
  border-radius:7px;
  color:#fff;
  background:#514bdc;
  box-shadow:0 8px 20px rgba(55,48,163,.2);
  font-size:11px;
  font-weight:750;
  cursor:pointer;
  transform:translate(-50%,-100%);
}
.text-selection-ai-action:hover{background:#4338ca}
.text-selection-ai-action:focus-visible{outline:2px solid #818cf8;outline-offset:2px}
@media(prefers-reduced-motion:reduce){.text-selection-ai-action{transition:none}}
</style>
