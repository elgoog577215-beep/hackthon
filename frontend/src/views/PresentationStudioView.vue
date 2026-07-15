<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PresentationAiAside from '@/components/presentation/PresentationAiAside.vue'
import PresentationPreview from '@/components/presentation/PresentationPreview.vue'
import { usePresentationEvents } from '@/composables/usePresentationEvents'
import { presentationService, resolveInitialPresentationScope } from '@/services/presentations'
import { usePresentationStore } from '@/stores/presentation'
import type { PresentationTemplateId } from '@/types/presentation'

const route = useRoute()
const router = useRouter()
const store = usePresentationStore()
const events = usePresentationEvents()

const scopeType = ref<'chapter' | 'course'>(resolveInitialPresentationScope(
  route.query.nodeId || route.query.sectionId,
))
const templateId = ref<PresentationTemplateId>('lingzhi-classroom')
const purpose = ref<'teaching' | 'self_study'>('teaching')
const pageBudget = ref(8)
const requirements = ref('')
const mobileSurface = ref<'preview' | 'ai'>('preview')
const narrow = ref(false)
const sourceNotice = ref('')
const downloadMenuOpen = ref(false)
let media: MediaQueryList | null = null

const courseId = computed(() => String(route.params.courseId || store.deck?.course_id || ''))
const deckId = computed(() => String(route.params.deckId || ''))
const courseTitle = computed(() => String(route.query.courseTitle || store.deck?.title || '课程课件'))
const chapterTitle = computed(() => String(
  route.query.chapterTitle || (scopeType.value === 'course' ? '整门课程' : '当前章节'),
))
const previewRevisionId = computed(() => store.revision?.revision_id
  || `working:${store.activeGenerationId || store.deck?.active_generation_id || store.deck?.deck_id || 'draft'}`)
const canUndo = computed(() => Boolean(store.revision?.parent_revision_id))
const savedLabel = computed(() => store.error ? '草稿保存受阻' : store.generating ? '正在保存' : '草稿已保存')

function syncConfigFromDeck() {
  if (!store.deck) return
  scopeType.value = store.deck.scope.type
  templateId.value = store.deck.template_id
  purpose.value = store.deck.purpose
}

async function initialize() {
  sourceNotice.value = ''
  if (deckId.value) {
    await store.loadDeck(deckId.value)
    syncConfigFromDeck()
    if (store.activeGenerationId || store.deck?.active_generation_id) void events.reconnect()
    return
  }
  const existing = await store.listDecks(courseId.value)
  const latest = [...existing].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]
  if (latest && route.query.create !== '1') {
    await router.replace({
      path: `/course/${encodeURIComponent(courseId.value)}/deck/${encodeURIComponent(latest.deck_id)}`,
      query: route.query,
    })
    await store.loadDeck(latest.deck_id)
    syncConfigFromDeck()
    if (store.activeGenerationId || store.deck?.active_generation_id) void events.reconnect()
  }
}

async function startGeneration() {
  if (!courseId.value) return
  if (!store.deck) {
    const sectionIds = scopeType.value === 'chapter'
      ? [String(route.query.nodeId || route.query.sectionId || '')].filter(Boolean)
      : []
    const created = await store.createDeck(courseId.value, {
      title: `${courseTitle.value} · 课件`,
      scope: { type: scopeType.value, section_ids: sectionIds },
      purpose: purpose.value,
      template_id: templateId.value,
      page_budget: pageBudget.value,
      extra_requirements: requirements.value,
    })
    await router.replace({
      path: `/course/${encodeURIComponent(courseId.value)}/deck/${encodeURIComponent(created.deck_id)}`,
      query: route.query,
    })
  }
  await store.generate({ page_budget: pageBudget.value, extra_requirements: requirements.value })
}

function returnToCourse() {
  const nodeId = String(route.query.nodeId || '')
  void router.push(`/course/${encodeURIComponent(courseId.value)}/learn${nodeId ? `/${encodeURIComponent(nodeId)}` : ''}`)
}

function download(format: 'html' | 'pptx') {
  if (!store.canDownload || !store.artifact) return
  window.open(presentationService.artifactUrl(store.artifact.artifact_id, format), '_blank', 'noopener')
  downloadMenuOpen.value = false
}

function viewSource() {
  const refs = store.selectedSlide?.source_refs
  if (!refs) return
  const sectionCount = refs.section_ids.length
  const blockCount = refs.block_ids.length
  sourceNotice.value = `本页来自 ${sectionCount} 个课程节点、${blockCount} 个内容块；课件修改不会覆盖课程正文。`
}

function onMediaChange(event: MediaQueryListEvent | MediaQueryList) {
  narrow.value = event.matches
}

watch(() => store.deck?.deck_id, syncConfigFromDeck)

onMounted(() => {
  media = window.matchMedia('(max-width: 1179px)')
  onMediaChange(media)
  media.addEventListener('change', onMediaChange)
  void initialize()
})

onBeforeUnmount(() => {
  media?.removeEventListener('change', onMediaChange)
  events.stop()
})
</script>

<template>
  <div class="studio-shell">
    <main class="presentation-workbench">
      <header class="studio-topbar">
        <button class="back-button" type="button" @click="returnToCourse">←　返回课程</button>
        <strong class="studio-title">{{ courseTitle }}</strong>
        <span class="saved-state" :class="{ warning: store.error }">◉ {{ savedLabel }}</span>
        <span v-if="store.deck?.source_outdated" class="source-version-warning">
          基于课程 {{ store.deck.source_ref.version_id }} · 当前 {{ store.deck.current_course_version_id }}
        </span>
        <span class="topbar-spacer" />
        <div class="download-wrap">
          <button class="download-button" type="button" :disabled="!store.canDownload" @click="download('pptx')">⇩　下载课件</button>
          <div v-if="downloadMenuOpen && store.canDownload" class="download-menu"><button type="button" @click="download('html')">打开 HTML 预览</button></div>
        </div>
        <button class="more-button" type="button" aria-label="更多导出选项" @click="downloadMenuOpen = !downloadMenuOpen">•••</button>
      </header>

      <nav class="studio-crumb" aria-label="课件位置">⌂　/　<b>课程</b>　/　{{ chapterTitle }}　/　<b>课件</b></nav>

      <div v-if="narrow" class="surface-switch" role="tablist" aria-label="工作台区域">
        <button type="button" :class="{ active: mobileSurface === 'preview' }" @click="mobileSurface = 'preview'">预览</button>
        <button type="button" :class="{ active: mobileSurface === 'ai' }" @click="mobileSurface = 'ai'">课件 AI</button>
      </div>

      <section class="studio-layout">
        <PresentationPreview
          v-show="!narrow || mobileSurface === 'preview'"
          :deck-id="store.deck?.deck_id || 'draft'"
          :revision-id="previewRevisionId"
          :revision-checksum="store.revisionChecksum || ''"
          :slides="store.orderedSlides"
          :selected-slide-id="store.selectedSlideId"
          :busy="store.generating"
          @select="store.selectedSlideId = $event"
          @measured="store.setRenderMeasurement"
        />
        <PresentationAiAside
          v-show="!narrow || mobileSurface === 'ai'"
          v-model:scope-type="scopeType"
          v-model:template-id="templateId"
          v-model:purpose="purpose"
          v-model:page-budget="pageBudget"
          v-model:requirements="requirements"
          :phase="store.phase"
          :selected-slide="store.selectedSlide"
          :proposal="store.proposal"
          :quality="store.quality"
          :error="store.error"
          :progress="store.generationProgress"
          :generating="store.generating"
          :proposing="store.proposing"
          :applying="store.applying"
          :finalizing="store.finalizing"
          :can-undo="canUndo"
          @generate="startGeneration"
          @prompt="store.requestProposal"
          @apply="store.applyProposal"
          @cancel-proposal="store.cancelProposal"
          @undo="store.undo"
          @finalize="store.finalize"
          @view-source="viewSource"
        />
      </section>
      <div v-if="sourceNotice" class="source-toast" role="status">{{ sourceNotice }}<button type="button" @click="sourceNotice = ''">知道了</button></div>
    </main>
  </div>
</template>

<style scoped>
.studio-shell{height:100vh;height:100dvh;min-height:0;overflow:hidden;padding:16px;color:#1e293b;background:radial-gradient(circle at 9% 4%,#fffdf7 0,transparent 33%),#f6f7f9;font:14px/1.5 "Noto Serif SC","Microsoft YaHei",serif}.presentation-workbench{height:calc(100vh - 32px);height:calc(100dvh - 32px);min-height:0;display:grid;grid-template-rows:68px 42px minmax(0,1fr);overflow:hidden;border:1px solid #dfe3e9;border-radius:16px;background:#fffefa;box-shadow:0 18px 50px rgba(15,23,42,.1)}.studio-topbar{display:flex;align-items:center;gap:22px;padding:0 22px;border-bottom:1px solid #e2e8f0}.back-button,.more-button{border:0;color:#475569;background:transparent}.studio-title{font-size:20px;letter-spacing:.02em}.saved-state{color:#059669;font-size:12px}.saved-state.warning{color:#b45309}.source-version-warning{padding:3px 7px;border:1px solid #fed7aa;border-radius:999px;color:#b45309;background:#fffbeb;font-size:11px}.topbar-spacer{flex:1}.download-wrap{position:relative}.download-button{border:1px solid #d8dce4;border-radius:8px;padding:8px 13px;color:#4f46e5;background:#fff}.download-button:disabled{color:#94a3b8;background:#f8fafc}.download-menu{position:absolute;z-index:10;top:calc(100% + 6px);right:0;width:170px;padding:5px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;box-shadow:0 12px 30px rgba(15,23,42,.12)}.download-menu button{width:100%;border:0;padding:8px;color:#475569;background:transparent;text-align:left}.more-button{font-size:24px}.studio-crumb{display:flex;align-items:center;padding:0 26px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:12px}.studio-crumb b{color:#334155}.studio-layout{min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:20px;overflow:hidden;padding:20px}.surface-switch{display:none}.source-toast{position:fixed;z-index:20;right:34px;bottom:28px;max-width:460px;padding:12px 14px;border-radius:9px;color:#fff;background:#1e293b;box-shadow:0 12px 30px rgba(15,23,42,.2)}.source-toast button{margin-left:12px;border:0;color:#c7d2fe;background:transparent;font-weight:700}@media(max-width:1179px){.presentation-workbench{grid-template-rows:68px 42px 44px minmax(0,1fr)}.surface-switch{display:grid;grid-template-columns:1fr 1fr;padding:5px 20px 0;border-bottom:1px solid #e2e8f0;background:#fff}.surface-switch button{border:0;border-bottom:2px solid transparent;color:#64748b;background:transparent}.surface-switch button.active{border-bottom-color:#6366f1;color:#4f46e5;font-weight:700}.studio-layout{grid-template-columns:minmax(0,1fr)}.studio-layout>*{min-height:0}.studio-layout :deep(.presentation-ai-aside){height:100%;max-height:100%;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}}@media(max-width:700px){.studio-shell{height:100vh;height:100dvh;min-height:0;overflow:hidden;padding:0}.presentation-workbench{height:100vh;height:100dvh;min-height:0;border:0;border-radius:0}.studio-topbar{gap:9px;padding:0 12px}.studio-title{max-width:33vw;overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.saved-state,.source-version-warning{display:none}.back-button{font-size:12px}.download-button{padding:7px;font-size:0}.download-button::first-letter{font-size:14px}.studio-crumb{padding:0 14px}.studio-layout{padding:10px}.source-toast{right:12px;bottom:12px;left:12px}}
</style>
