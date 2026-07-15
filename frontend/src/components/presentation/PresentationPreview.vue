<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { PresentationPreviewMessage, PresentationRenderMeasurement, PresentationSlide } from '@/types/presentation'
import { presentationMeasurementRuntime } from './presentationPreviewMeasurement'

const props = defineProps<{
  deckId: string
  revisionId: string
  revisionChecksum: string
  slides: PresentationSlide[]
  selectedSlideId: string | null
  busy?: boolean
}>()

const emit = defineEmits<{
  select: [slideId: string]
  measured: [measurement: PresentationRenderMeasurement]
}>()

const frame = ref<HTMLIFrameElement | null>(null)
const previewShell = ref<HTMLElement | null>(null)
const showNotes = ref(false)

const currentIndex = computed(() => {
  const index = props.slides.findIndex(item => item.slide_id === props.selectedSlideId)
  return index >= 0 ? index : 0
})
const currentSlide = computed(() => props.slides[currentIndex.value] || null)

const escapeHtml = (value: unknown): string => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#039;')

const blockHtml = (slide: PresentationSlide): string => (slide.blocks || []).map((block) => {
  const heading = block.title ? `<h3>${escapeHtml(block.title)}</h3>` : ''
  const items = Array.isArray(block.items) ? block.items : []
  const metadata = block.metadata || {}
  if ((block.type === 'bullets' || block.type === 'exercise') && items.length) {
    return `<section class="block block-${block.type}">${heading}<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></section>`
  }
  if (block.type === 'code') {
    return `<section class="block block-code">${heading}<pre><code>${escapeHtml(block.content)}</code></pre></section>`
  }
  if (block.type === 'comparison') {
    const left = escapeHtml(metadata.left || block.content)
    const right = escapeHtml(metadata.right || '')
    return `<section class="block block-comparison">${heading}<div class="compare"><div>${left}</div><div>${right}</div></div></section>`
  }
  return `<section class="block block-${block.type}">${heading}<p>${escapeHtml(block.content)}</p></section>`
}).join('')

const slideInnerHtml = (slide: PresentationSlide, index: number, includeNotes = false): string => {
  if (slide.status === 'failed') {
    return '<div class="failed">这一页生成失败，已保留其他课件内容。请在右侧查看修复建议。</div>'
  }
  const notes = includeNotes && slide.speaker_notes
    ? `<aside class="speaker-notes">${escapeHtml(slide.speaker_notes)}</aside>`
    : ''
  return `<header><span class="eyebrow">${escapeHtml(slide.layout_id)}</span><h1>${escapeHtml(slide.title || '正在生成本页')}</h1><p>${escapeHtml(slide.subtitle || slide.key_message)}</p></header><div class="blocks">${blockHtml(slide)}</div><footer><span>${index + 1} / ${props.slides.length}</span><strong>灵知课件</strong></footer>${notes}${slide.status !== 'ready' ? '<div class="skeleton" aria-label="正在生成"></div>' : ''}`
}

const frameDocument = computed(() => {
  const slide = currentSlide.value
  if (!slide) return ''
  const messageBase = JSON.stringify({
    version: 'presentation-preview/v1',
    deck_id: props.deckId,
    revision_id: props.revisionId,
    revision_checksum: props.revisionChecksum,
    slide_id: slide.slide_id,
  }).replace(/</g, '\\u003c')
  const measurementSlides = props.slides.map((item, index) => (
    `<section class="slide measure-slide layout-${escapeHtml(item.layout_id)}" data-measure-slide data-slide-id="${escapeHtml(item.slide_id)}" aria-hidden="true">${slideInnerHtml(item, index)}</section>`
  )).join('')
  const measurementRuntime = presentationMeasurementRuntime().replace(/<\/script/gi, '<\\/script')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    :root{--ink:#1e293b;--muted:#64748b;--line:#e6e8ee;--paper:#fffefa;--brand:#6366f1;--brand-soft:#eef2ff}
    *{box-sizing:border-box}html,body{width:100%;height:100%;margin:0}body{display:grid;place-items:center;overflow:hidden;background:#f7f8fa;color:var(--ink);font-family:"Noto Serif SC","Microsoft YaHei",serif}
    .slide{position:relative;display:flex;flex-direction:column;width:100%;height:100%;overflow:hidden;padding:6.4% 6.2% 5.2%;background:var(--paper)}
    .slide:before{position:absolute;inset:0 0 auto;height:6px;background:var(--brand);content:""}.eyebrow{color:var(--brand);font:700 11px/1.2 system-ui,sans-serif;letter-spacing:.12em}
    h1{margin:.4rem 0 .7rem;font-size:clamp(25px,4vw,47px);line-height:1.16;letter-spacing:.015em}header>p{margin:0;color:#475569;font-size:clamp(13px,1.65vw,20px);line-height:1.55}
    .blocks{min-height:0;flex:1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:center;gap:3.2%;margin-top:4%}.block{min-width:0;padding:4%;border:1px solid var(--line);border-radius:10px;background:#fafbff}.block h3{margin:0 0 .7em;font-size:clamp(14px,1.5vw,20px)}.block p,.block li{color:#475569;font-size:clamp(12px,1.18vw,17px);line-height:1.65}.block ul{margin:0;padding-left:1.2em}.block-code{background:#fafbff}pre{margin:0;white-space:pre-wrap;color:#334155;font:clamp(11px,1.12vw,16px)/1.7 ui-monospace,SFMono-Regular,Consolas,monospace}.compare{display:grid;grid-template-columns:1fr 1fr;gap:1px;overflow:hidden;border:1px solid #e8e8ec;border-radius:7px;background:#e8e8ec}.compare>div{padding:10px;background:#fff7f5;color:#a33}.compare>div+div{background:#f3fbf7;color:#176c4e}.layout-L01,.layout-L03{justify-content:center}.layout-L01 .blocks,.layout-L03 .blocks{display:none}.layout-L07 .blocks,.layout-L08 .blocks{grid-template-columns:1.1fr .9fr}
    footer{display:flex;justify-content:space-between;margin-top:2.5%;color:#94a3b8;font:12px/1.2 system-ui,sans-serif}footer strong{color:var(--brand)}.speaker-notes{position:absolute;right:5%;bottom:8%;max-width:36%;padding:8px 11px;color:var(--brand);background:rgba(255,254,250,.92);font-weight:700;line-height:1.55;transform:rotate(-2deg)}
    .failed{margin:auto;padding:20px;border:1px solid #fecaca;border-radius:10px;color:#b91c1c;background:#fef2f2}.skeleton{position:absolute;inset:0;background:linear-gradient(110deg,#f8fafc 30%,#eef2ff 45%,#f8fafc 60%);background-size:220% 100%;animation:shimmer 1.4s infinite}@keyframes shimmer{to{background-position-x:-220%}}
    .measurement-rack{position:fixed;inset:0;pointer-events:none}.measure-slide{position:absolute;top:0;left:-200vw;width:100%;height:100%;opacity:0;contain:layout style}
  </style></head><body><main class="slide layout-${escapeHtml(slide.layout_id)}" data-slide-id="${escapeHtml(slide.slide_id)}">
    ${slideInnerHtml(slide, currentIndex.value, showNotes.value)}
  </main><div class="measurement-rack" aria-hidden="true">${measurementSlides}</div><script>${measurementRuntime};const base=${messageBase};const send=(type,payload={})=>parent.postMessage({...base,type,payload},'*');document.querySelector('main.slide')?.addEventListener('click',()=>send('slide:selected'));send('preview:ready');Promise.resolve(document.fonts?.ready).then(()=>{const pages=[...document.querySelectorAll('[data-measure-slide]')];const measurement=aggregatePresentationMeasurements(pages);send('render:measured',measurement)})<\/script></body></html>`
})

function selectAt(index: number) {
  const slide = props.slides[Math.max(0, Math.min(props.slides.length - 1, index))]
  if (slide) emit('select', slide.slide_id)
}

function onPreviewMessage(event: MessageEvent) {
  if (!frame.value?.contentWindow || event.source !== frame.value.contentWindow) return
  if (event.origin !== 'null') return
  const message = event.data as Partial<PresentationPreviewMessage> | null
  if (!message || message.version !== 'presentation-preview/v1') return
  if (
    message.deck_id !== props.deckId
    || message.revision_id !== props.revisionId
    || message.revision_checksum !== props.revisionChecksum
  ) return
  if (message.type === 'slide:selected' && message.slide_id && props.slides.some(item => item.slide_id === message.slide_id)) {
    emit('select', message.slide_id)
  }
  if (message.type === 'render:measured' && message.payload && typeof message.payload === 'object') {
    const overflow = message.payload.overflow
    const collision = message.payload.collision
    const slideCount = message.payload.slide_count
    const overflowSlideIds = message.payload.overflow_slide_ids
    const collisionSlideIds = message.payload.collision_slide_ids
    const knownSlideIds = new Set(props.slides.map(item => item.slide_id))
    const validSlideIds = (value: unknown): value is string[] => (
      Array.isArray(value)
      && value.every(item => typeof item === 'string' && knownSlideIds.has(item))
    )
    if (
      typeof overflow !== 'boolean'
      || typeof collision !== 'boolean'
      || typeof slideCount !== 'number'
      || !Number.isInteger(slideCount)
      || slideCount !== props.slides.length
      || !validSlideIds(overflowSlideIds)
      || !validSlideIds(collisionSlideIds)
      || (overflow !== (overflowSlideIds.length > 0))
      || (collision !== (collisionSlideIds.length > 0))
    ) return
    emit('measured', {
      revision_id: props.revisionId,
      revision_checksum: props.revisionChecksum,
      overflow,
      collision,
      slide_count: Number(slideCount),
      overflow_slide_ids: [...new Set(overflowSlideIds)],
      collision_slide_ids: [...new Set(collisionSlideIds)],
    })
  }
}

async function enterFullscreen() {
  await previewShell.value?.requestFullscreen?.()
}

onMounted(() => window.addEventListener('message', onPreviewMessage))
onBeforeUnmount(() => window.removeEventListener('message', onPreviewMessage))
</script>

<template>
  <article ref="previewShell" class="presentation-preview" aria-label="课件预览">
    <div class="preview-toolbar">
      <button class="page-button" type="button" aria-label="上一页" :disabled="currentIndex <= 0" @click="selectAt(currentIndex - 1)">‹</button>
      <strong class="page-count">{{ slides.length ? currentIndex + 1 : 0 }} / {{ slides.length }}</strong>
      <button class="page-button" type="button" aria-label="下一页" :disabled="currentIndex >= slides.length - 1" @click="selectAt(currentIndex + 1)">›</button>
      <span class="toolbar-spacer" />
      <span v-if="busy" class="generation-note">● 正在生成</span>
      <button class="quiet-button" type="button" @click="enterFullscreen">⛶　全屏</button>
      <button class="quiet-button" type="button" :aria-pressed="showNotes" @click="showNotes = !showNotes">▤　{{ showNotes ? '隐藏备注' : '显示备注' }}</button>
    </div>

    <div v-if="!currentSlide" class="preview-empty">
      <div class="empty-mark">◇</div>
      <h2>在这里看到课件的每一页</h2>
      <p>先在右侧选择课件依据和模板，页序完成后内容会逐页出现。</p>
    </div>
    <div v-else class="frame-stage">
      <iframe
        ref="frame"
        :key="`${revisionId}:${revisionChecksum}:${currentSlide.slide_id}:${showNotes}`"
        class="slide-frame"
        :title="`第 ${currentIndex + 1} 页课件预览`"
        :srcdoc="frameDocument"
        sandbox="allow-scripts"
      />
    </div>
  </article>
</template>

<style scoped>
.presentation-preview{min-width:0;min-height:0;display:grid;grid-template-rows:54px minmax(0,1fr);overflow:hidden;border:1px solid #e2e8f0;border-radius:13px;background:#fbfcfd}.preview-toolbar{display:flex;align-items:center;gap:8px;padding:0 16px;border-bottom:1px solid #e2e8f0;background:#fff}.page-button{width:32px;height:32px;border:1px solid #dfe3eb;border-radius:7px;color:#475569;background:#fff;font-size:20px}.page-button:disabled{color:#cbd5e1;cursor:not-allowed}.page-count{padding:5px 12px;border:1px solid #dfe3eb;border-radius:7px;color:#334155;background:#fff}.toolbar-spacer{flex:1}.quiet-button{border:0;padding:7px;color:#64748b;background:transparent}.quiet-button:hover{color:#4f46e5;background:#f8fafc}.generation-note{color:#4f46e5;font-size:12px}.frame-stage{min-height:0;padding:28px;background:#f8fafc}.slide-frame{display:block;width:100%;height:100%;border:1px solid #e6e2da;background:#fffefa;box-shadow:0 13px 24px rgba(15,23,42,.1)}.preview-empty{display:grid;align-content:center;justify-items:center;padding:40px;text-align:center}.empty-mark{width:56px;height:56px;display:grid;place-items:center;margin-bottom:14px;border:1px solid #c7d2fe;border-radius:50%;color:#6366f1;background:#eef2ff;font-size:26px}.preview-empty h2{margin:0 0 8px;color:#1e293b;font-size:20px}.preview-empty p{max-width:420px;margin:0;color:#64748b;line-height:1.7}@media(max-width:700px){.preview-toolbar{padding:0 10px}.quiet-button{font-size:0}.quiet-button::first-letter{font-size:14px}.frame-stage{padding:12px}}
</style>
