<template>
  <Transition name="fade">
    <div v-if="visible" class="fixed inset-0 flex flex-col" style="z-index: 2200; background: rgba(255,255,255,0.12); backdrop-filter: blur(2px);">
      <!-- 工具栏 -->
      <div class="flex items-center gap-3 px-4 py-2.5 bg-white/95 border-b border-slate-200 shadow-sm flex-shrink-0">
        <span class="text-xs font-bold text-slate-500 mr-1">🎨 第 {{ questionIndex + 1 }} 题</span>
        <div class="w-px h-5 bg-slate-200" />
        <!-- 颜色选择 -->
        <div class="flex items-center gap-1.5">
          <button v-for="c in colors" :key="c" class="w-6 h-6 rounded-full border-2 transition-all"
            :style="{ backgroundColor: c }"
            :class="activeColor === c ? 'border-slate-800 scale-110 shadow-md' : 'border-slate-200 hover:border-slate-400'"
            @click="activeColor = c" />
        </div>
        <div class="w-px h-5 bg-slate-200" />
        <!-- 粗细选择 -->
        <div class="flex items-center gap-1">
          <button v-for="s in sizes" :key="s.value"
            class="px-2.5 py-1 text-xs rounded-md transition-all"
            :class="activeSize === s.value ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'"
            @click="activeSize = s.value">{{ s.label }}</button>
        </div>
        <div class="w-px h-5 bg-slate-200" />
        <!-- 工具切换 -->
        <div class="flex items-center gap-1">
          <button class="px-2.5 py-1 text-xs rounded-md transition-all flex items-center gap-1"
            :class="tool === 'pen' ? 'bg-primary-500 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'"
            @click="tool = 'pen'">✏️ 画笔</button>
          <button class="px-2.5 py-1 text-xs rounded-md transition-all flex items-center gap-1"
            :class="tool === 'eraser' ? 'bg-primary-500 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'"
            @click="tool = 'eraser'">🧹 橡皮</button>
        </div>
        <div class="w-px h-5 bg-slate-200" />
        <button class="px-2.5 py-1 text-xs rounded-md bg-red-50 text-red-500 hover:bg-red-100 transition-all" @click="clearCanvas">清空</button>
        <div class="flex-1" />
        <button class="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded hover:bg-slate-100" @click="closeOverlay">
          <el-icon :size="18"><Close /></el-icon>
        </button>
      </div>
      <!-- 画布 -->
      <canvas ref="canvasRef" class="flex-1 cursor-crosshair"
        :class="{ '!cursor-cell': tool === 'eraser' }"
        @mousedown="startDraw" @mousemove="draw" @mouseup="endDraw" @mouseleave="endDraw" />
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useDraftStore } from '../stores/draft'

const props = defineProps<{
  visible: boolean
  questionIndex: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const draftStore = useDraftStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const drawing = ref(false)
const tool = ref<'pen' | 'eraser'>('pen')
const activeColor = ref('#000000')
const activeSize = ref(3)

const colors = ['#000000', '#e53e3e', '#3182ce', '#38a169', '#dd6b20']
const sizes = [
  { label: '细', value: 2 },
  { label: '中', value: 4 },
  { label: '粗', value: 8 },
]

function getCtx() {
  return canvasRef.value?.getContext('2d') || null
}

function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width
  canvas.height = rect.height
}

function loadFromStore() {
  const canvas = canvasRef.value
  const ctx = getCtx()
  if (!canvas || !ctx) return
  const dataURL = draftStore.getDrawingDraft(props.questionIndex)
  if (dataURL) {
    const img = new Image()
    img.onload = () => { ctx.drawImage(img, 0, 0) }
    img.onerror = () => { /* 加载失败，显示空白画布 */ }
    img.src = dataURL
  }
}

function saveToStore() {
  const canvas = canvasRef.value
  if (!canvas) return
  try {
    draftStore.setDrawingDraft(props.questionIndex, canvas.toDataURL('image/png'))
  } catch { /* ignore */ }
}

function clearCanvas() {
  const canvas = canvasRef.value
  const ctx = getCtx()
  if (!canvas || !ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  saveToStore()
}

function startDraw(e: MouseEvent) {
  const ctx = getCtx()
  if (!ctx) return
  drawing.value = true
  const rect = canvasRef.value!.getBoundingClientRect()
  ctx.beginPath()
  ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top)
}

function draw(e: MouseEvent) {
  if (!drawing.value) return
  const ctx = getCtx()
  const canvas = canvasRef.value
  if (!ctx || !canvas) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  if (tool.value === 'eraser') {
    const r = activeSize.value * 3
    ctx.clearRect(x - r, y - r, r * 2, r * 2)
  } else {
    ctx.lineWidth = activeSize.value
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = activeColor.value
    ctx.lineTo(x, y)
    ctx.stroke()
  }
}

function endDraw() {
  if (drawing.value) {
    drawing.value = false
    saveToStore()
  }
}

function closeOverlay() {
  saveToStore()
  emit('update:visible', false)
}

watch(() => props.visible, async (val) => {
  if (val) {
    await nextTick()
    resizeCanvas()
    loadFromStore()
  }
})

watch(() => props.questionIndex, () => {
  if (!props.visible) return
  const ctx = getCtx()
  const canvas = canvasRef.value
  if (ctx && canvas) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    loadFromStore()
  }
})
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
