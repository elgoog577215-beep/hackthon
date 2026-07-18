<template>
  <footer
    ref="dockRoot"
    class="learning-dock"
    :class="{ 'has-resume': resumeActionLabel }"
    :aria-label="t('learningDock.title', '学习工具')"
    @keydown="handleKeydown"
  >
    <div class="learning-dock__location" :title="location">
      <MapPin :size="14" />
      <span>{{ t('learningDock.location', '当前位置') }}</span>
      <strong>{{ location }}</strong>
    </div>

    <div v-if="resumeActionLabel" class="learning-dock__resume">
      <button
        type="button"
        :disabled="resumeActionBusy || !resumeActionAvailable"
        :title="resumeActionLabel"
        @click="emit('resume')"
      >
        <LoaderCircle v-if="resumeActionBusy" :size="15" class="learning-dock__spin" />
        <ArrowRight v-else :size="15" />
        <span>{{ resumeActionLabel }}</span>
      </button>
    </div>

    <nav class="learning-dock__actions" :aria-label="t('learningDock.primaryNavigation', '学习辅助导航')">
      <Transition name="learning-dock-tray">
        <section
          v-if="toolsOpen"
          id="learning-tool-menu"
          class="learning-dock__tray"
          role="menu"
          :aria-label="t('learningDock.learningMenuTitle', '学习工具')"
          data-tool-menu="learning"
        >
          <header>
            <span class="learning-dock__tray-icon">
              <NotebookTabs :size="18" />
            </span>
            <span>
              <strong>{{ t('learningDock.learningMenuTitle', '学习工具') }}</strong>
              <small>{{ t('learningDock.learningMenuHelp', '学习记录与学习概况') }}</small>
            </span>
          </header>

          <div class="learning-dock__tool-list">
            <button type="button" role="menuitem" data-tool-item="records" @click="selectTool('records')">
              <span class="learning-dock__item-icon"><NotebookTabs :size="18" /></span>
              <span class="learning-dock__item-copy">
                <strong>{{ t('learningDock.records', '学习记录') }}</strong>
                <small>{{ t('learningDock.recordsDescription', '查看笔记、问答和待复习内容') }}</small>
              </span>
              <span v-if="recordCount" class="learning-dock__item-meta is-count">{{ recordCount }} {{ t('learningDock.recordUnit', '条') }}</span>
              <ChevronRight :size="17" />
            </button>
            <button type="button" role="menuitem" data-tool-item="stats" @click="selectTool('stats')">
              <span class="learning-dock__item-icon"><ChartNoAxesCombined :size="18" /></span>
              <span class="learning-dock__item-copy">
                <strong>{{ t('learningDock.stats', '学习概况') }}</strong>
                <small>{{ t('learningDock.statsDescription', '查看阅读、掌握与学习证据') }}</small>
              </span>
              <ChevronRight :size="17" />
            </button>
          </div>
        </section>
      </Transition>

      <button
        ref="learningTrigger"
        type="button"
        class="learning-dock__domain"
        data-domain="learning"
        :class="{ 'is-active': toolsOpen || activeDomain === 'learning' }"
        aria-haspopup="menu"
        :aria-expanded="toolsOpen"
        aria-controls="learning-tool-menu"
        :title="t('learningDock.learningGroupHint', '展开学习记录和学习概况')"
        @click="toggleTools"
      >
        <NotebookTabs :size="16" />
        <span>{{ t('learningDock.learningGroup', '学习工具 · 2') }}</span>
        <ChevronUp v-if="toolsOpen" class="learning-dock__chevron" :size="14" />
        <ChevronDown v-else class="learning-dock__chevron" :size="14" />
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="knowledge-library"
        :class="{ 'is-active': activeDomain === 'knowledge-library' && !toolsOpen }"
        :aria-current="activeDomain === 'knowledge-library' ? 'page' : undefined"
        :title="t('learningDock.knowledgeLibraryHint', '查看学科知识与本课覆盖')"
        @click="openKnowledgeLibrary"
      >
        <Library :size="16" />
        <span>{{ t('learningDock.knowledgeLibrary', '知识库') }}</span>
      </button>
      <button
        type="button"
        class="learning-dock__domain"
        data-domain="assistant"
        :class="{ 'is-active': activeDomain === 'assistant' && !toolsOpen }"
        :aria-current="activeDomain === 'assistant' ? 'page' : undefined"
        :title="t('learningDock.assistantHint', '在当前页面打开 AI 老师')"
        @click="openAssistant"
      >
        <MessageSquareText :size="16" />
        <span>{{ t('learningDock.assistant', '智能助教') }}</span>
      </button>
    </nav>
  </footer>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowRight,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Library,
  LoaderCircle,
  MapPin,
  MessageSquareText,
  NotebookTabs,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

type ToolItem = 'records' | 'stats'

const props = withDefaults(defineProps<{
  location: string
  activeDomain?: 'course' | 'learning' | 'knowledge-library' | 'assistant'
  recordCount?: number
  resumeActionLabel?: string
  resumeActionAvailable?: boolean
  resumeActionBusy?: boolean
}>(), {
  activeDomain: 'course',
  recordCount: 0,
  resumeActionLabel: '',
  resumeActionAvailable: true,
  resumeActionBusy: false,
})

const emit = defineEmits<{
  (event: 'records' | 'stats' | 'knowledge-library' | 'ai' | 'resume'): void
}>()

const dockRoot = ref<HTMLElement | null>(null)
const learningTrigger = ref<HTMLButtonElement | null>(null)
const toolsOpen = ref(false)

function toggleTools() {
  toolsOpen.value = !toolsOpen.value
}

function closeMenu(restoreFocus = false) {
  if (!toolsOpen.value) return
  toolsOpen.value = false
  if (restoreFocus) void nextTick(() => learningTrigger.value?.focus())
}

function selectTool(tool: ToolItem) {
  closeMenu()
  emit(tool)
}

function openKnowledgeLibrary() {
  closeMenu()
  emit('knowledge-library')
}

function openAssistant() {
  closeMenu()
  emit('ai')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !toolsOpen.value) return
  event.preventDefault()
  event.stopPropagation()
  closeMenu(true)
}

function handleOutsidePointer(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node) || dockRoot.value?.contains(target)) return
  closeMenu()
}

watch(() => props.activeDomain, domain => {
  if (domain !== 'learning') closeMenu()
})

onMounted(() => document.addEventListener('pointerdown', handleOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', handleOutsidePointer))
</script>

<style scoped>
.learning-dock { position:relative; min-width:0; min-height:58px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:14px; overflow:visible; padding:8px 12px 8px 16px; border-top:1px solid rgba(224,231,255,.94); background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(248,250,255,.99)); box-shadow:0 -8px 24px rgba(79,70,229,.05); }
.learning-dock__location { min-width:0; display:grid; grid-template-columns:14px auto minmax(0,1fr); align-items:center; gap:7px; color:var(--lz-text-muted); }
.learning-dock__location svg { color:#818cf8; }
.learning-dock__location span { font-size:10px; white-space:nowrap; }
.learning-dock__location strong { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-secondary); font-size:11px; font-weight:650; }
.learning-dock__resume { min-width:0; flex:0 1 auto; display:flex; align-items:center; }
.learning-dock__resume > button { min-width:0; color:#fff; border-color:#15803d; background:#15803d; box-shadow:0 4px 10px rgba(21,128,61,.16); }
.learning-dock__resume > button:hover:not(:disabled) { color:#fff; border-color:#166534; background:#166534; }
.learning-dock__resume > button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.learning-dock__spin { animation:learning-dock-spin .8s linear infinite; }
.learning-dock__actions { position:relative; flex:0 0 auto; display:flex; align-items:center; gap:6px; }
.learning-dock button { position:relative; min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border:1px solid transparent; border-radius:10px; color:var(--lz-text-secondary); background:transparent; font-size:11px; font-weight:680; cursor:pointer; transition:background .16s ease,border-color .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease; }
.learning-dock button:hover:not(:disabled) { color:var(--lz-brand-strong); border-color:#dfe4ff; background:#f5f7ff; }
.learning-dock button:focus-visible { outline:3px solid rgba(99,102,241,.26); outline-offset:2px; }
.learning-dock button:disabled { color:#a9b4c8; cursor:not-allowed; }
.learning-dock__domain.is-active { color:var(--lz-brand-strong); border-color:#cfd6ff; background:linear-gradient(180deg,#f8f7ff,#eef0ff); box-shadow:0 3px 10px rgba(79,70,229,.1); }
.learning-dock__chevron { margin-left:1px; color:#94a3b8; }
.learning-dock__domain.is-active .learning-dock__chevron { color:#6366f1; }
.learning-dock__tray { --pointer-right:245px; position:absolute; right:0; bottom:calc(100% + 18px); z-index:80; width:min(440px,calc(100vw - 32px)); overflow:visible; padding:16px; border:1px solid rgba(203,213,225,.9); border-radius:16px; color:var(--lz-text); background:rgba(255,255,255,.985); box-shadow:0 20px 54px rgba(15,23,42,.16),0 4px 14px rgba(79,70,229,.08); }
.learning-dock__tray::after { content:""; position:absolute; right:var(--pointer-right); bottom:-8px; width:14px; height:14px; transform:rotate(45deg); border-right:1px solid rgba(203,213,225,.9); border-bottom:1px solid rgba(203,213,225,.9); background:#fff; }
.learning-dock__tray header { display:grid; grid-template-columns:38px minmax(0,1fr); align-items:center; gap:10px; padding:0 2px 12px; }
.learning-dock__tray header > span:last-child { min-width:0; display:flex; flex-direction:column; gap:3px; }
.learning-dock__tray header strong { color:var(--lz-text-strong); font-size:15px; line-height:1.3; }
.learning-dock__tray header small { color:var(--lz-text-muted); font-size:11px; line-height:1.4; }
.learning-dock__tray-icon,.learning-dock__item-icon { display:grid; place-items:center; color:#5b5ce2; background:#f1f2ff; }
.learning-dock__tray-icon { width:38px; height:38px; border-radius:11px; }
.learning-dock__tool-list { overflow:hidden; border-top:1px solid #e8ebf4; }
.learning-dock__tool-list > button { width:100%; min-height:66px; display:grid; grid-template-columns:38px minmax(0,1fr) auto 18px; justify-content:stretch; gap:11px; padding:10px 4px; border:0; border-bottom:1px solid #edf0f6; border-radius:0; text-align:left; background:transparent; }
.learning-dock__tool-list > button:last-child { border-bottom:0; }
.learning-dock__tool-list > button:hover:not(:disabled) { transform:none; border-color:#edf0f6; background:#f8f9ff; }
.learning-dock__item-icon { width:38px; height:38px; border-radius:10px; }
.learning-dock__item-copy { min-width:0; display:flex; flex-direction:column; gap:4px; }
.learning-dock__item-copy strong { color:var(--lz-text-strong); font-size:13px; line-height:1.3; }
.learning-dock__item-copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-muted); font-size:10px; font-weight:500; line-height:1.4; }
.learning-dock__item-meta { min-width:48px; padding:4px 8px; border-radius:999px; color:#4f46e5; background:#eef0ff; font-size:10px; font-weight:700; text-align:center; }
.learning-dock__tool-list > button > svg { color:#94a3b8; }
.learning-dock-tray-enter-active,.learning-dock-tray-leave-active { transition:opacity .16s ease,transform .16s ease; transform-origin:bottom right; }
.learning-dock-tray-enter-from,.learning-dock-tray-leave-to { opacity:0; transform:translateY(8px) scale(.985); }
@container (max-width:760px) {
  .learning-dock__location span { display:none; }
  .learning-dock__location strong { max-width:140px; }
  .learning-dock__resume > button { width:38px; padding:0; }
  .learning-dock__resume > button span { display:none; }
  .learning-dock__domain { padding-inline:10px; }
}
@keyframes learning-dock-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .learning-dock { position:fixed; left:0; right:0; bottom:0; z-index:120; min-height:calc(58px + env(safe-area-inset-bottom,0px)); padding:4px 6px env(safe-area-inset-bottom,0px); }
  .learning-dock__location,.learning-dock__resume { display:none; }
  .learning-dock__actions { width:100%; display:grid; grid-template-columns:1fr 1fr .9fr; gap:3px; }
  .learning-dock__domain { min-width:0; min-height:50px; flex-direction:column; gap:2px; padding:3px 2px; border-radius:9px; font-size:9px; line-height:1.1; }
  .learning-dock__chevron { position:absolute; top:7px; right:7px; width:11px; height:11px; }
  .learning-dock__tray { position:fixed; left:8px; right:8px; bottom:calc(66px + env(safe-area-inset-bottom,0px)); width:auto; max-height:min(70vh,330px); overflow-y:auto; padding:14px; border-radius:16px; }
  .learning-dock__tray::after { display:none; }
  .learning-dock__tool-list > button { min-height:64px; grid-template-columns:38px minmax(0,1fr) auto 18px; }
  .learning-dock__item-copy small { white-space:normal; }
}
@media (prefers-reduced-motion:reduce) {
  .learning-dock button,.learning-dock-tray-enter-active,.learning-dock-tray-leave-active { transition:none; }
}
</style>
