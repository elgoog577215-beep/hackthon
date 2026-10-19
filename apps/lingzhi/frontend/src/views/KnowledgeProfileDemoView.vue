<template>
  <main class="profile-demo" :class="{ 'has-detail': selected }">
  <CompanionFloatingWindow window-id="demo-companion-window" :visible="floating && chatOpen" :detail="Boolean(selected)" @close="closeFloating" />
    <header class="demo-top"><div class="demo-brand"><GitBranch :size="24" /><div><strong>{{ t('knowledgeProfile.demoTitle', '知识树 × 学生画像') }}</strong><span>{{ activeLocale === 'en' ? demo.title_en : demo.title }}</span></div></div><div class="demo-actions"><button type="button" @click="step = 0"><RotateCcw :size="15" />{{ t('knowledgeProfile.reset', '回到初始状态') }}</button><button type="button" @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'English' : '中文' }}</button></div></header>
    <details class="demo-replay" :open="!selected"><summary>{{ t('companionWorkspace.showReplay') }}<span>{{ t('companionWorkspace.demoLabel') }}</span></summary><section class="demo-controls"><div class="demo-label"><span>{{ t('knowledgeProfile.demoBadge', '交互演示') }}</span><p>{{ t('knowledgeProfile.demoNotice', '示例课程与证据，不读取或写入真实学生记录。选择一个步骤，查看同一套规则计算的变化。') }}</p></div><div class="demo-steps" :aria-label="t('knowledgeProfile.replay', '回放学习过程')"><button v-for="(item, index) in demo.cases" :key="index" type="button" :aria-pressed="step === index" @click="step = index"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ activeLocale === 'en' ? item.label_en : item.label }}</button></div><p class="demo-note" aria-live="polite"><Info :size="16" />{{ activeLocale === 'en' ? current.note_en : current.note }}</p></section></details>
    <div v-if="floating && chatOpen && selected" class="floating-tree-background" aria-hidden="true"><KnowledgeMasteryTree :profile="profile" :course-title="activeLocale === 'en' ? demo.title_en : demo.title" /></div>
    <div class="demo-workspace" :class="{ 'chat-visible': chatOpen, 'has-selection': selected, floating }">
      <aside v-if="selected" class="demo-navigation" data-companion-obstacle><button class="back-tree" @click="profileRef?.closePoint()"><ArrowLeft :size="16" />{{ t('companionWorkspace.backTree') }}</button><h2>{{ activeLocale === 'en' ? demo.title_en : demo.title }}</h2><div v-for="branch in profile.branches" :key="branch.id" class="demo-nav-group"><h3>{{ branch.name }}</h3><button v-for="point in profile.nodes.filter(n => n.parent_id === branch.id)" :key="point.knowledge_id" :class="{ active:selected?.knowledge_id === point.knowledge_id }" @click="profileRef?.openPoint(point.knowledge_id)">{{ point.name }}</button></div><button class="notes-link" @click="sheet = 'notes'"><NotebookPen :size="16" />{{ t('companionWorkspace.notes') }} · {{ notes.length }}</button></aside>
      <div class="demo-surface" data-companion-obstacle><Teleport to="#demo-companion-window-detail" :disabled="!floating || !chatOpen || !selected"><KnowledgeMasteryProfile ref="profileRef" can-read :learning-content="learningContent" :practice-ids="['demo-k7']" @practice="openPractice" :profile="profile" :course-title="activeLocale === 'en' ? demo.title_en : demo.title" @select="selectPoint" @ask="chatOpen = true" @evidence="discussEvidence" @lecture="openLecture" /></Teleport></div>
      <aside v-show="chatOpen" class="demo-chat-slot" :class="{ floating }"><Teleport to="#demo-companion-window-chat" :disabled="!floating || !chatOpen"><CompanionConversationDemo ref="chatRef" :point="selected" :floating="floating" @mode="floating = !floating" @close="closeChat" @lecture="openLecture" @practice="openPractice" @note="saveNote" /></Teleport></aside>
    </div>
    <dialog ref="sheetRef" class="demo-resource-sheet" @close="sheet = ''" @click="event => { if(event.target === sheetRef) closeSheet() }"><header><h2>{{ sheet === 'notes' ? t('companionWorkspace.notes') : sheet === 'practice' ? t('companionWorkspace.demoPractice') : t('companionWorkspace.demoLecture') }}</h2><button :aria-label="t('companionWorkspace.close')" @click="closeSheet"><X :size="20" /></button></header><template v-if="sheet === 'notes'"><article v-for="(note,index) in notes" :key="index"><h3>{{ note.point }}</h3><p>{{ note.text }}</p></article><p v-if="!notes.length">{{ t('companionWorkspace.noNotes') }}</p></template><template v-else-if="sheet === 'practice'"><p>{{ t('companionWorkspace.question') }}</p><button class="practice-choice" @click="feedback = 'correct'">{{ t('companionWorkspace.passOption') }}</button><button class="practice-choice" @click="feedback = 'incorrect'">{{ t('companionWorkspace.failOption') }}</button><p v-if="feedback" role="status">{{ t(`companionWorkspace.${feedback}`) }}</p></template><template v-else><h3>{{ resourcePoint?.name }}</h3><p>{{ resourcePoint?.statement }}</p><p v-if="resourcePoint?.knowledge_id === 'demo-k7'">{{ t('companionWorkspace.lectureBody') }}</p></template></dialog>
  </main>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowLeft, GitBranch, Info, NotebookPen, RotateCcw, X } from 'lucide-vue-next'
import KnowledgeMasteryTree from '../components/KnowledgeMasteryTree.vue'
import CompanionFloatingWindow from '../components/CompanionFloatingWindow.vue'
import KnowledgeMasteryProfile from '../components/KnowledgeMasteryProfile.vue'
import CompanionConversationDemo from '../components/CompanionConversationDemo.vue'
import demo from '../demo/knowledge-profile.json'
import { demoLearningContent } from '../demo/knowledge-learning-content'
import type { KnowledgeProfile, KnowledgeProfileNode } from '../types/knowledge-profile'
import { activeLocale, setLocale, t } from '../shared/i18n'
const step = ref(demo.cases.length - 1)
const current = computed(() => demo.cases[step.value]!)
const profile = computed(() => current.value.profile as KnowledgeProfile)
const learningContent = computed(() => demoLearningContent(activeLocale.value))
const selected = ref<KnowledgeProfileNode|null>(null)
const profileRef = ref<InstanceType<typeof KnowledgeMasteryProfile>|null>(null)
const chatRef = ref<InstanceType<typeof CompanionConversationDemo>|null>(null)
const chatOpen = ref(false)
const floating = ref(false)
const notes = ref<Array<{point:string;text:string}>>([])
const sheet = ref('')
const sheetRef = ref<HTMLDialogElement|null>(null)
const resourcePoint = ref<KnowledgeProfileNode|null>(null)
const feedback = ref('')
function selectPoint(point:KnowledgeProfileNode|null) { selected.value = point; if(point) { chatOpen.value = true; floating.value = true } else floating.value = false }
function closeChat() { chatOpen.value = false; floating.value = false }
function closeFloating() { closeChat(); profileRef.value?.closePoint() }
function discussEvidence(point:KnowledgeProfileNode,evidence:KnowledgeProfileNode['evidence'][number]) { chatOpen.value = true; chatRef.value?.discuss(point,evidence) }
function openLecture(point:KnowledgeProfileNode) { resourcePoint.value = point; sheet.value = 'lecture' }
function openPractice(point:KnowledgeProfileNode) { resourcePoint.value = point; feedback.value = ''; sheet.value = point.knowledge_id === 'demo-k7' ? 'practice' : 'lecture' }
function saveNote(text:string, point:KnowledgeProfileNode) { notes.value.push({text,point:point.name}) }
function closeSheet() { sheetRef.value?.close(); sheet.value = '' }
watch(sheet, async value => { if(value) { await nextTick(); sheetRef.value?.showModal() } })
watch(profile, value => { if(selected.value) selected.value = value.nodes.find(n => n.knowledge_id === selected.value?.knowledge_id) || null })
onMounted(() => { const id = new URLSearchParams(window.location.search).get('point'); if(id && profile.value.nodes.some(n => n.knowledge_id === id)) void profileRef.value?.openPoint(id) })
</script>
<style scoped>
.profile-demo { height:100%; min-height:0; box-sizing:border-box; padding:24px 32px 40px; background:linear-gradient(130deg,#f5f3fb,#f5f7fb); color:#373047; overflow:auto; }
.demo-top { max-width:1240px; margin:0 auto 22px; display:flex; justify-content:space-between; align-items:center; gap:20px; }.demo-brand { display:flex; gap:13px; align-items:center; color:#7660b2; }.demo-brand div { display:flex; flex-direction:column; gap:5px; }.demo-brand strong { color:#493b61; font-size:20px; }.demo-brand span { color:#97869e; font-size:13px; }
.demo-actions { display:flex; gap:8px; }.demo-actions button { display:flex; align-items:center; gap:7px; padding:8px 12px; border:1px solid #ded5e9; border-radius:8px; background:#fff; color:#786386; font-size:13px; cursor:pointer; }
.demo-controls { max-width:1240px; margin:auto; padding:16px 20px; background:#eeebf7; border:1px solid #e0d9ed; border-radius:14px; }.demo-label { display:flex; align-items:center; gap:12px; }.demo-label>span { color:#785ca6; background:#fff; border-radius:5px; padding:4px 8px; font-size:11px; flex:none; }.demo-label p { margin:0; color:#85768e; font-size:13px; line-height:1.7; }
.demo-steps { display:flex; flex-wrap:wrap; gap:6px; margin-top:14px; }.demo-steps button { display:flex; align-items:center; gap:6px; padding:8px 10px; border:1px solid #ded5ea; border-radius:8px; color:#84718f; background:#f8f6fc; font-size:12px; cursor:pointer; }.demo-steps button span { opacity:.55; font-size:10px; }.demo-steps button[aria-pressed=true] { border-color:#8b6dc3; color:#fff; background:#8b6dc3; }
.demo-note { display:flex; gap:8px; align-items:flex-start; margin:14px 0 0; font-size:13px; line-height:1.7; color:#7b678c; }.demo-note svg { flex:none; margin-top:3px; }.demo-surface { max-width:1240px; margin:20px auto 0; background:#fff; border:1px solid #e5dfec; border-radius:18px; box-shadow:0 8px 35px #614b8708; }
button:focus-visible { outline:2px solid #7858a5; outline-offset:3px; }
@media(max-width:900px) { .profile-demo { padding:18px 14px; }.demo-top { gap:10px; }.demo-brand strong { font-size:17px; } }
</style>

<style scoped>
.profile-demo { padding:18px 22px 24px; }.demo-top { max-width:none; margin-bottom:16px; }.demo-replay { margin:0 auto 14px; max-width:1440px; }.demo-replay summary { display:flex; align-items:center; gap:18px; color:#77638f; font-size:13px; cursor:pointer; padding:8px 2px; }.demo-replay summary span { margin-left:auto; color:#9c8aaa; font-size:12px; }.demo-controls { max-width:none; }.demo-workspace { display:grid; grid-template-columns:minmax(0,1fr); gap:12px; max-width:1600px; margin:auto; align-items:start; }.demo-workspace.has-selection { grid-template-columns:210px minmax(0,1fr); }.demo-workspace.chat-visible { grid-template-columns:minmax(0,1fr) 390px; }.demo-workspace.has-selection.chat-visible { grid-template-columns:210px minmax(0,1fr) 390px; }.demo-surface { width:100%; margin:0; min-width:0; overflow:hidden; }.demo-navigation { border:1px solid #e5dfec; border-radius:18px; background:#fff; padding:20px 12px; min-height:calc(100vh - 146px); }.demo-navigation h2 { font-size:19px; padding:0 7px; margin:20px 0; line-height:1.5; color:#342850; }.demo-navigation h3 { font-size:14px; margin:18px 7px 8px; color:#66507e; }.demo-navigation button { background:none; border:0; cursor:pointer; text-align:left; font:inherit; color:#88759d; }.demo-nav-group>button { display:block; width:100%; padding:10px 9px 10px 17px; border-radius:9px; font-size:13px; line-height:1.65; }.demo-nav-group>button.active { color:#7750bd; background:#f0eafa; }.back-tree,.notes-link { display:flex; align-items:center; gap:7px; font-size:13px!important; padding:5px; }.notes-link { margin-top:20px; }
.demo-chat-slot { position:sticky; top:0; height:calc(100vh - 146px); min-height:600px; border:1px solid #e4dcee; border-radius:18px; overflow:hidden; }.demo-chat-slot.floating { height:calc(100vh - 172px); margin-top:14px; box-shadow:0 15px 40px #65477622; border-color:#d6c7ea; }.demo-workspace.floating { gap:20px; }
.demo-resource-sheet { position:fixed; inset:0; margin:auto; max-width:600px; width:calc(100vw - 48px); max-height:80vh; overflow:auto; border:1px solid #ddd0ef; background:#fff; border-radius:18px; padding:24px; color:#5c4673; box-shadow:0 25px 70px #2c17443d; }.demo-resource-sheet::backdrop { background:#27173c55; backdrop-filter:blur(3px); }.demo-resource-sheet header { display:flex; align-items:center; justify-content:space-between; gap:20px; }.demo-resource-sheet h2 { font-size:20px; }.demo-resource-sheet header button { border:0; background:none; color:#80669a; cursor:pointer; }.demo-resource-sheet p { white-space:pre-wrap; line-height:1.85; font-size:15px; margin:16px 0; }.practice-choice { display:block; padding:12px; margin:10px 0; width:100%; border:1px solid #e4d7f0; background:#f7f3fd; border-radius:9px; color:#76579c; text-align:left; cursor:pointer; }
@media(max-width:1250px) { .demo-workspace.has-selection.chat-visible { grid-template-columns:175px minmax(0,1fr) 350px; }.profile-demo { padding:16px 12px; }.demo-navigation { padding:14px 8px; } }
@media(max-width:1000px) { .demo-workspace.has-selection.chat-visible,.demo-workspace.has-selection { grid-template-columns:minmax(0,1fr); }.demo-navigation { display:none; }.demo-chat-slot { position:relative; height:650px; }.demo-workspace.chat-visible { grid-template-columns:minmax(0,1fr); } }
</style>

<style scoped>
.demo-workspace.floating { display:none; }
.floating-tree-background { padding:28px; border:1px solid #e5dcef; border-radius:18px; background:#fff; }
</style>
