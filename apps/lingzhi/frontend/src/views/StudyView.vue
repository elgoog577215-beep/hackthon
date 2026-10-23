<template>
  <div class="study-space">
    <header class="study-header glass-panel-elevated">
      <RouterLink to="/study" class="study-brand"><img src="/qizhi-favicon.svg" alt="启智" /><span><strong>启智</strong><small>{{ c('brand') }}</small></span></RouterLink>
      <nav v-if="user && !materialId && !creating" class="study-surface-navigation" :aria-label="t('studentWorkspace.space')">
        <button :class="{ active: !['courses','materials'].includes(String(route.query.view || '')) }" @click="openStudySection('home')">{{ t('studentWorkspace.home') }}</button>
        <button :class="{ active: route.query.view === 'courses' }" @click="openStudySection('courses')">{{ c('authorizedCourses') }}</button>
        <button :class="{ active: route.query.view === 'materials' }" @click="goLibrary">{{ c('library') }}</button>
        <button data-testid="student-create-handout" @click="startNew()"><Plus :size="16" />{{ c('create') }}</button>
      </nav>
      <div class="study-header-actions">
        <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'English' : '中文' }}</button>
        <RouterLink v-if="!user" to="/courses">{{ c('teacher') }}</RouterLink>
        <span v-if="user" class="study-user"><UserRound :size="17" />{{ user.username }}</span>
        <button v-if="user" @click="logout">{{ c('logout') }}</button>
      </div>
    </header>
    <div v-if="error" class="study-error" role="alert">{{ error }}<button @click="reconnect">{{ c('retry') }}</button></div>

    <main v-if="!user" class="study-login-page">
      <div class="login-story"><span class="study-eyebrow">PERSONAL LEARNING</span><h1>{{ c('welcome') }}</h1><p>{{ c('intro') }}</p><div class="login-purpose"><BookOpen :size="28" /><div><h3>{{ c('systematic') }}</h3><p>{{ c('understandingHint') }}</p></div></div><div class="login-purpose"><Target :size="28" /><div><h3>{{ c('exam_prep') }}</h3><p>{{ c('examHint') }}</p></div></div></div>
      <form v-if="localLoginEnabled" class="study-login-card" @submit.prevent="authenticate">
        <span class="study-eyebrow">{{ c('localAccount') }}</span><h2>{{ c(registerMode ? 'register' : 'login') }}</h2><p>{{ c('loginIntro') }}</p>
        <label>{{ c('username') }}<input v-model="username" autocomplete="username" required minlength="3" maxlength="40" pattern="[A-Za-z0-9_.\-]+" /></label>
        <label>{{ c('password') }}<input v-model="password" type="password" :autocomplete="registerMode ? 'new-password' : 'current-password'" required minlength="8" maxlength="128" :placeholder="c('passwordHint')" /></label>
        <button class="study-primary" :disabled="busy">{{ busy ? c('busy') : c(registerMode ? 'register' : 'login') }}<ArrowRight :size="18" /></button>
        <button type="button" class="study-text-button" @click="registerMode = !registerMode">{{ c(registerMode ? 'login' : 'register') }}</button>
      </form>
      <div v-else class="study-login-card"><h2>{{ c('login') }}</h2><p>{{ c('disabledLogin') }}</p><button v-if="qizhiAuth" class="study-primary" @click="redirectToQizhiLogin">{{ c('unifiedLogin') }}</button></div>
    </main>

    <div v-else ref="studyLayoutRoot" class="study-workspace" :class="{ 'is-reading': !!materialId, 'is-library': !materialId && !creating }" :style="columnLayoutStyle">
      <aside v-if="materialId || creating" class="study-navigation">
        <span class="study-eyebrow">{{ t('studentWorkspace.space') }}</span>
        <button :class="{ active: !materialId && !creating && !['courses','materials'].includes(String(route.query.view || '')) }" @click="openStudySection('home')"><BookOpen :size="19" />{{ t('studentWorkspace.home') }}</button>
        <button :class="{ active: !materialId && !creating && route.query.view === 'materials' }" @click="goLibrary"><LibraryBig :size="19" />{{ c('library') }}</button>
        <button data-testid="student-create-handout" :class="{ active: creating }" @click="startNew()"><Plus :size="19" />{{ c('create') }}</button>
        <button :class="{ active: !materialId && !creating && route.query.view === 'courses' }" @click="openStudySection('courses')"><GraduationCap :size="19" />{{ c('authorizedCourses') }}</button>
        <div class="recent-materials"><RouterLink v-for="item in library" :key="item.id" :to="`/study/${item.id}`" :class="{ active: materialId === item.id }"><span class="material-dot" :class="item.purpose" /><span>{{ item.title }}<small>{{ c(item.purpose) }}</small></span></RouterLink></div>
        <p class="study-nav-hint"><LockKeyhole :size="16" />{{ c('savedHint') }}</p>
      </aside>

      <ColumnResizeHandle v-if="materialId || creating" v-bind="leftColumnHandle" />
      <section v-if="!materialId" class="study-main-scroll">
        <StudentCourseLibrary v-if="!creating && route.query.view === 'courses'" ref="authorizedCourses" :key="user.id" :user-id="user.id" @source="createFromCourse" />
        <StudentLearningHome v-else-if="!creating && route.query.view !== 'materials'" :user-id="user.id" :materials="library" @create="startNew" @source="createFromCourse" />
        <div v-else-if="!creating" class="study-library">
          <div class="study-page-heading"><div><span class="study-eyebrow">MY MATERIALS</span><h1>{{ c('library') }}</h1><p>{{ c('intro') }}</p></div><button class="study-primary" @click="startNew()"><Plus :size="18" />{{ c('create') }}</button></div>
          <div v-if="library.length" class="study-material-grid"><RouterLink v-for="item in library" :key="item.id" :to="`/study/${item.id}`" class="study-material-card"><span class="material-mode" :class="item.purpose"><Target v-if="item.purpose === 'exam_prep'" :size="18" /><BookOpen v-else :size="18" />{{ c(item.purpose) }}</span><h2>{{ item.title }}</h2><p>{{ c(item.purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</p><footer><span class="study-status" :class="item.status">{{ statusLabel(item.status) }}</span><ArrowUpRight :size="22" /></footer></RouterLink></div>
          <div v-else class="study-empty"><div class="empty-books"><BookOpen :size="46" /></div><h2>{{ c('emptyLibrary') }}</h2><p>{{ c('emptyHint') }}</p><button class="study-primary" @click="startNew()">{{ c('create') }}<ArrowRight :size="18" /></button></div>
        </div>
        <form v-else class="study-create" @submit.prevent="generate">
          <div class="study-page-heading"><div><span class="study-eyebrow">CREATE YOUR HANDOUT</span><h1>{{ c('create') }}</h1><p>{{ c('intro') }}</p></div></div>
          <section class="study-form-section"><h2>{{ c('sourceHeading') }}</h2><p>{{ c('sourceHint') }}</p>
            <div class="study-source-actions"><label class="study-upload"><Upload :size="19" />{{ sourceBusy ? c('busy') : c('upload') }}<input type="file" accept=".pdf,.pptx,.docx,.md,.txt" :disabled="sourceBusy" multiple @change="uploadFiles" /></label><button type="button" @click="pasting = !pasting"><ClipboardPaste :size="18" />{{ c('paste') }}</button><span>{{ c('uploadHint') }}</span></div>
            <div v-if="pasting" class="study-paste"><label>{{ c('sourceTitle') }}<input v-model="sourceTitle" maxlength="160" /></label><label>{{ c('sourceContent') }}<textarea v-model="sourceText" rows="8" maxlength="120000" /></label><button type="button" :disabled="sourceBusy || !sourceTitle.trim() || !sourceText.trim()" @click="addText">{{ sourceBusy ? c('busy') : c('addSource') }}</button></div>
            <p v-if="!sources.length && !pasting" class="study-source-empty">{{ c('emptySources') }}</p>
            <div v-for="source in sources" :key="source.id" class="study-source"><div class="source-name"><FileText :size="18" /><strong>{{ source.filename }}</strong><span>{{ source.sections.length }} · {{ c('scope') }}</span></div><p v-if="!source.sections.length" class="source-warning">{{ source.error || c('sourceFailed') }}</p><p v-for="warning in source.warnings" :key="warning" class="source-warning">{{ warning }}</p><label v-for="section in source.sections" :key="section.id" class="source-selection"><input v-model="selectedRanges" type="checkbox" :value="`${source.id}:${section.id}`" :disabled="!section.characters" /><span>{{ section.title }}</span><small>{{ section.characters.toLocaleString() }}</small></label></div>
          </section>
          <section class="study-form-section"><h2>{{ c('purposeHeading') }}</h2><div class="study-purpose-options"><button v-for="purpose in purposes" :key="purpose" type="button" :class="{ selected: form.purpose === purpose }" :aria-pressed="form.purpose === purpose" @click="form.purpose = purpose"><Target v-if="purpose === 'exam_prep'" :size="25" /><BookOpen v-else :size="25" /><strong>{{ c(purpose) }}</strong><span>{{ c(purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</span><Check v-if="form.purpose === purpose" class="purpose-check" :size="19" /></button></div></section>
          <section class="study-form-section"><h2>{{ c('settingsHeading') }}</h2><label>{{ c('title') }}<input v-model="form.title" required maxlength="160" :placeholder="c('titlePlaceholder')" /></label><div class="study-settings-row"><label>{{ c('level') }}<select v-model="form.level" :aria-label="c('level')"><option v-for="level in levels" :key="level" :value="level">{{ c(level) }}</option></select></label><label>{{ c('time') }}<input v-model.number="form.time_minutes" type="number" min="10" max="600" required /></label></div><label>{{ c('requirements') }}<textarea v-model="form.requirements" rows="3" maxlength="2000" :placeholder="c('requirementsPlaceholder')" /></label></section>
          <div class="study-generate-bar"><span>{{ selectedRanges.length }} · {{ c('scope') }}</span><button class="study-primary" :disabled="busy || sourceBusy || !selectedRanges.length">{{ busy ? c('busy') : c('generate') }}<ArrowRight :size="19" /></button></div>
        </form>
      </section>

      <template v-else>
        <div class="study-reading-pane">
          <div class="study-reading-toolbar"><CompanionPlanPanel :material-id="materialId" @navigate="navigatePersonalPlan" @navigate-course="openSourceMainline" /><button @click="goLibrary"><ArrowLeft :size="17" />{{ c('back') }}</button><span v-if="material" class="study-status" :class="materialStatus">{{ statusLabel(materialStatus) }}</span><button v-if="material?.revisions[0]?.sections.length" @click="exportHandout"><Download :size="17" />{{ c('export') }}</button><button v-if="inlineCompanion" type="button" @click="readingCompanionAnchor = null; toolTab = 'note'">{{ c('note') }}</button></div>
          <div v-if="selectedPassage" class="study-selection-actions"><span>{{ c('selectedQuote') }} · {{ selectedPassage.block_title || selectedPassage.section_title }}</span><button @pointerdown.prevent @click="openPassageHelp()">{{ c('askSelection') }}</button><button @click="selectedPassage = null">{{ c('clearQuote') }}</button></div>
          <div v-if="material" ref="readingTarget" class="study-document-scroll" @scroll="followChapter" @pointerup="selectPassage" @keyup="selectPassage">
            <article class="study-handout">
              <header class="study-handout-cover"><span class="study-eyebrow">{{ c(material.purpose) }}</span><h1>{{ material.title }}</h1><p>{{ c(material.purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</p><div class="handout-rule" /></header>
              <div v-if="materialStatus !== 'completed'" class="study-progress" role="status"><span>{{ ['failed', 'paused'].includes(materialStatus) ? c('interrupted') : c('generatingHint') }}</span><progress v-if="isGenerating" :value="material.task?.progress || 0" max="100" /><button v-if="['failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c('continue') }}</button></div>
              <HandoutTableOfContents v-if="readingSections.length" :entries="readingSections.map(section => ({ id: section.anchor, title: section.title }))" collapsible />
              <section v-for="section in material.revisions[0]?.sections || []" :id="sectionAnchor(section.id)" :data-section-id="section.id" :key="section.id" class="study-handout-section"><div class="study-section-kicker">{{ section.source.filename }}</div><h2>{{ section.title }}</h2><div v-for="block in section.blocks" :id="blockAnchor(block.block_id)" :data-block-id="block.block_id" :key="block.block_id"><HandoutContentBlock :content-type="block.content_type" :label="block.type_label" :title="block.title" :answer-to="block.answer_to" :streaming="!section.complete"><MarkdownRenderer :content="block.content" :node-id="block.block_id" /></HandoutContentBlock><button type="button" class="personal-block-help" data-testid="personal-block-help" @click="openBlockHelp(section.id, block.block_id)">{{ t('readingCompanion.title') }}</button><div data-study-companion-anchor :data-study-node-id="section.id" :data-study-block-id="block.block_id"></div></div><div v-if="section.fragment" class="study-draft"><span>{{ c('draft') }}</span><MarkdownRenderer :content="section.fragment" /></div></section>
              <p v-if="materialStatus === 'completed'" class="study-end"><Check :size="17" />{{ c('finishReading') }}</p>
            </article>
          </div>
        </div>
        <ColumnResizeHandle v-if="material && (!inlineCompanion || toolTab !== 'assistant')" v-bind="rightColumnHandle" />
        <aside v-if="material" v-show="!inlineCompanion || toolTab !== 'assistant'" class="study-reading-tools">
          <div class="study-tool-tabs"><button v-for="tab in toolTabs" :key="tab" :class="{ active: toolTab === tab }" @click="toolTab = tab">{{ c(tab) }}</button></div>
          <ReadingCompanionSurface v-if="material.revisions[0]" :anchor="readingCompanionAnchor" :visible="toolTab === 'assistant'" @presentation-change="inlineCompanion = $event"><PersonalHandoutAssistant :key="`${user.id}:${material.id}:${material.revisions[0].id}`" :owner-id="user.id" :material-id="material.id" :revision-id="material.revisions[0].id" :context="assistantContext" @clear-quote="selectedPassage = null" @session-expired="showError" /></ReadingCompanionSurface>
          <div v-if="toolTab === 'note'" class="study-note"><h3>{{ c('note') }}</h3><p>{{ c('noteHint') }}</p><textarea v-model="noteText" rows="16" :placeholder="c('notePlaceholder')" :aria-label="c('note')" /><div class="study-note-status" role="status">{{ noteDirty ? c('noteUnsaved') : noteSaved ? c('noteSaved') : '' }}</div><button class="study-primary" :disabled="busy || !noteDirty" @click="saveNote">{{ c('saveNote') }}</button></div>
          <div v-else-if="toolTab === 'sources'" class="study-source-list"><h3>{{ c('sources') }}</h3><article v-for="source in selectedSourceScopes" :key="source.node_id"><FileText :size="18" /><strong>{{ source.filename }}</strong><p>{{ source.title }}</p><code>{{ source.source_sha256.slice(0, 12) }}</code><button :disabled="busy" @click="downloadSource(source.asset_id, source.filename)">{{ c('downloadSource') }}</button></article></div>
          <HandoutConceptMap v-else-if="toolTab === 'concepts' && conceptSections.some(section => section.nodes.length)" :sections="conceptSections" :target="readingTarget" :origin-label="c('conceptOrigin')" />
          <p v-else-if="toolTab !== 'assistant'" class="study-note">{{ c('preparingConcepts') }}</p>
        </aside>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, ClipboardPaste, Download, FileText, GraduationCap, LibraryBig, LockKeyhole, Plus, Target, Upload, UserRound } from 'lucide-vue-next'
import HandoutContentBlock from '../components/HandoutContentBlock.vue'
import HandoutTableOfContents from '../components/HandoutTableOfContents.vue'
import HandoutConceptMap from '../components/HandoutConceptMap.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import PersonalHandoutAssistant from '../components/PersonalHandoutAssistant.vue'
import ReadingCompanionSurface from '../components/ReadingCompanionSurface.vue'
import CompanionPlanPanel from '../components/CompanionPlanPanel.vue'
import { studyApi, studySession, StudyApiError, type StudyMaterial, type StudyPurpose, type StudySource, type StudySummary, type StudyUser } from '../api/study'
import { activeLocale, setLocale, t } from '../shared/i18n'
import { studyCopy as c, type StudyCopyKey } from '../shared/study-copy'
import StudentCourseLibrary from '../components/StudentCourseLibrary.vue'
import StudentLearningHome from '../components/StudentLearningHome.vue'
import { setStudyIdentity } from '../utils/study-identity'
import { buildHandoutConceptSections } from '../utils/handout-concepts'
import { clearQizhiAccessToken, isQizhiAuthRequired, redirectToQizhiLogin } from '../utils/http'
import ColumnResizeHandle from '../components/ColumnResizeHandle.vue'
import { useResizableColumns } from '../composables/useResizableColumns'

const router = useRouter(), route = useRoute()
const user = ref<StudyUser | null>(null), localLoginEnabled = ref(false), qizhiAuth = isQizhiAuthRequired()
const username = ref(''), password = ref(''), registerMode = ref(false), busy = ref(false), sourceBusy = ref(false), error = ref('')
const library = ref<StudySummary[]>([]), sources = ref<StudySource[]>([]), material = ref<StudyMaterial | null>(null)
const creating = ref(false), pasting = ref(false), sourceTitle = ref(''), sourceText = ref(''), selectedRanges = ref<string[]>([])
const form = reactive({ title: '', purpose: 'systematic' as StudyPurpose, level: 'beginner', time_minutes: 60, requirements: '' })
const purposes: StudyPurpose[] = ['systematic', 'exam_prep'], levels = ['beginner', 'intermediate', 'advanced'] as const
const toolTabs = ['assistant', 'note', 'concepts', 'sources'] as const, toolTab = ref<typeof toolTabs[number]>('assistant')
const activeChapter = ref(''), selectedPassage = ref<{ section_id: string; section_title: string; block_id: string; block_title: string; quote: string } | null>(null)
const assistantContext = computed(() => {
  if (selectedPassage.value) return selectedPassage.value
  const section = material.value?.revisions[0]?.sections.find(s => s.id === activeChapter.value) || material.value?.revisions[0]?.sections[0]
  return { section_id: section?.id || '', section_title: section?.title || '', block_id: '', block_title: '', quote: '' }
})
function followChapter() {
  const root = readingTarget.value; if (!root) return
  const boundary = root.getBoundingClientRect().top + 100
  const chapters = Array.from(root.querySelectorAll<HTMLElement>('[data-section-id]'))
  const visible = chapters.filter(node => node.getBoundingClientRect().top <= boundary).at(-1) || chapters[0]
  if (visible) activeChapter.value = visible.dataset.sectionId || ''
}
function selectPassage() {
  const selection = window.getSelection(), root = readingTarget.value
  if (!selection || !root || selection.isCollapsed || !selection.rangeCount) return
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return
  const start = range.startContainer.nodeType === 1 ? range.startContainer as Element : range.startContainer.parentElement
  const end = range.endContainer.nodeType === 1 ? range.endContainer as Element : range.endContainer.parentElement
  if (start?.closest('.reading-companion-surface, .personal-block-help') || end?.closest('.reading-companion-surface, .personal-block-help')) return
  const sid = start?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId
  if (!sid || sid !== end?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId) return
  const section = material.value?.revisions[0]?.sections.find(s => s.id === sid)
  const bid = start?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId
  const block = bid === end?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId ? section?.blocks.find(b => b.block_id === bid) : null
  const fragment = range.cloneContents()
  fragment.querySelectorAll('[data-study-companion-anchor], .personal-block-help').forEach(element => element.remove())
  const quote = fragment.textContent?.trim() || ''
  if (!section || !quote || quote.length > 3000) return
  selectedPassage.value = { section_id: sid, section_title: section.title, block_id: block?.block_id || '', block_title: block?.title || '', quote }
}
function openPassageHelp() {
  toolTab.value = 'assistant'
  const passage = selectedPassage.value
  readingCompanionAnchor.value = passage?.block_id ? Array.from(readingTarget.value?.querySelectorAll<HTMLElement>('[data-study-companion-anchor]') || [])
    .find(element => element.dataset.studyNodeId === passage.section_id && element.dataset.studyBlockId === passage.block_id) || null : null
}
function openSourceMainline(courseId:string){void router.push({name:'learning',params:{courseId},query:{returnTo:route.fullPath}})}
function navigatePersonalPlan(id:string){document.getElementById(sectionAnchor(id))?.scrollIntoView({block:'start'})}
function openBlockHelp(sectionId: string, blockId: string) {
  const section = material.value?.revisions[0]?.sections.find(item => item.id === sectionId)
  const block = section?.blocks.find(item => item.block_id === blockId)
  if (!section || !block) return
  selectedPassage.value = { section_id: section.id, section_title: section.title, block_id: block.block_id, block_title: block.title, quote: block.content.slice(0, 3000) }
  openPassageHelp()
}
const readingTarget = ref<HTMLElement | null>(null), noteText = ref(''), savedNote = ref(''), noteSaved = ref(false)
const noteDirty = computed(() => noteText.value !== savedNote.value)
const readingCompanionAnchor = ref<HTMLElement | null>(null), inlineCompanion = ref(false)
const materialId = computed(() => String(route.params.materialId || ''))
const studyLayoutRoot = ref<HTMLElement | null>(null)
const { layoutStyle: columnLayoutStyle, leftHandle: leftColumnHandle, rightHandle: rightColumnHandle } = useResizableColumns(studyLayoutRoot, {
  storageKey: 'lingzhi:personal-study:columns', left: 240, right: 360, leftMin: 170, rightMin: 280,
  leftVisible: () => Boolean(materialId.value || creating.value),
  rightVisible: () => Boolean(materialId.value && material.value && (!inlineCompanion.value || toolTab.value !== 'assistant')),
})
const materialStatus = computed(() => material.value?.task?.status || material.value?.status || 'pending')
const isGenerating = computed(() => ['pending', 'running'].includes(materialStatus.value))
const sectionAnchor = (id: string) => `study-${materialId.value}-${id}`
const blockAnchor = (id: string) => `study-${materialId.value}-${id}`
const readingSections = computed(() => (material.value?.revisions[0]?.sections || []).map(section => ({ id: section.id, title: section.title, anchor: sectionAnchor(section.id), blocks: section.blocks.map(block => ({ id: block.block_id, title: block.title, anchor: blockAnchor(block.block_id), content: block.content, knowledge: block.knowledge_names })) })))
const conceptSections = computed(() => buildHandoutConceptSections(material.value?.plans || [], readingSections.value))
const selectedSourceScopes = computed(() => material.value?.sources || (material.value?.revisions[0]?.sections || []).map(section => ({ node_id: section.id, title: section.title, ...section.source })))
const statusLabel = (status: string) => c((['pending', 'running', 'completed', 'failed', 'paused'].includes(status) ? status : 'draft') as StudyCopyKey)
let timer: ReturnType<typeof setTimeout> | undefined, requestId = crypto.randomUUID(), submittedFingerprint = '', disposed = false, epoch = 0, actionSequence = 0
const draftKey = () => `lingzhi-study-draft:${user.value?.id || ''}`
const noteKey = () => `lingzhi-study-note:${user.value?.id}:${materialId.value}:${material.value?.revisions[0]?.id}`

function showError(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : c('requestFailure')
  if (cause instanceof StudyApiError && cause.status === 401) { persistDraft(); epoch++; user.value = null; clearPrivateUi(); clearTimeout(timer) }
}
function clearPrivateUi() { readingCompanionAnchor.value = null; material.value = null; library.value = []; sources.value = []; selectedRanges.value = []; sourceText.value = ''; sourceTitle.value = ''; noteText.value = ''; savedNote.value = ''; creating.value = false; pasting.value = false; sourceBusy.value = false; selectedPassage.value = null; activeChapter.value = ''; Object.assign(form, { title: '', purpose: 'systematic', level: 'beginner', time_minutes: 60, requirements: '' }) }
const sameOwner = (owner: string | undefined) => !disposed && user.value?.id === owner
async function action(operation: () => Promise<void>) { const owner = user.value?.id, sequence = ++actionSequence; busy.value = true; error.value = ''; try { await operation() } catch (cause) { if (!disposed && (!owner || sameOwner(owner))) showError(cause) } finally { if (sequence === actionSequence) busy.value = false } }
function persistDraft() { if (user.value) sessionStorage.setItem(draftKey(), JSON.stringify({ form, selectedRanges: selectedRanges.value, sourceTitle: sourceTitle.value, sourceText: sourceText.value, requestId, submittedFingerprint })) }
function restoreDraft() { try { const draft = JSON.parse(sessionStorage.getItem(draftKey()) || '{}'); Object.assign(form, draft.form || {}); selectedRanges.value = draft.selectedRanges || []; sourceTitle.value = draft.sourceTitle || ''; sourceText.value = draft.sourceText || ''; requestId = draft.requestId || crypto.randomUUID(); submittedFingerprint = draft.submittedFingerprint || '' } catch { /* An invalid UI draft does not affect saved materials. */ } }
watch([form, selectedRanges, sourceTitle, sourceText], persistDraft, { deep: true })
watch(noteText, () => { if (material.value && user.value) sessionStorage.setItem(noteKey(), noteText.value) })

async function loadLibrary() { const current = epoch; const result = await Promise.all([studyApi.list(), studyApi.sources()]); if (current !== epoch || !user.value) return; [library.value, sources.value] = result }
async function connect() {
  const config = await studyApi.config(); localLoginEnabled.value = config.local_login_enabled
  if (!studySession.get() && !qizhiAuth) return
  try { user.value = await studyApi.me(); setStudyIdentity(user.value); restoreDraft(); await loadLibrary(); await openMaterial() }
  catch (cause) { showError(cause) }
}
async function authenticate() { if (busy.value) return; await action(async () => { const result = await studyApi.login(username.value, password.value, registerMode.value); studySession.set(result.token); setStudyIdentity(result.user); password.value = ''; epoch++; user.value = result.user; restoreDraft(); await loadLibrary(); const returnTo = String(route.query.returnTo || ''); if (returnTo.startsWith('/course/') && !returnTo.startsWith('//')) await router.push(returnTo); else await openMaterial() }) }
async function logout() { persistDraft(); await action(async () => { await studyApi.logout(); epoch++; studySession.clear(); if (qizhiAuth) clearQizhiAccessToken(); clearTimeout(timer); user.value = null; clearPrivateUi(); await router.push('/study') }) }
const authorizedCourses = ref<InstanceType<typeof StudentCourseLibrary> | null>(null)
function reconnect() { void action(async () => { if (!user.value) await connect(); else { await Promise.all([loadLibrary(), authorizedCourses.value?.reload()]); await openMaterial() } }) }
async function openStudySection(view: 'home' | 'courses' | 'materials') { creating.value = false; await router.push({ path: '/study', query: view === 'home' ? {} : { view } }); await action(loadLibrary) }
async function goLibrary() { await openStudySection('materials') }
async function startNew(purpose?: StudyPurpose) { await router.push('/study'); creating.value = true; if (purpose) form.purpose = purpose; await action(loadLibrary) }
async function createFromCourse(source: StudySource) { const owner = user.value?.id; await startNew(); if (sameOwner(owner)) { sources.value = sources.value.filter(item => item.id !== source.id); selectedRanges.value = []; form.title = ''; rememberSource(source) } }
function rememberSource(source: StudySource) {
  sources.value.unshift(source)
  if (!source.sections.length) { error.value = source.error || c('sourceFailed'); return }
  selectedRanges.value.push(...source.sections.slice(0, 3).filter(section => section.characters).map(section => `${source.id}:${section.id}`))
  if (!form.title) form.title = source.filename.replace(/\.[^.]+$/, '')
}
async function addText() { const owner = user.value?.id; sourceBusy.value = true; error.value = ''; try { const source = await studyApi.addText(sourceTitle.value.trim(), sourceText.value); if (!sameOwner(owner)) return; rememberSource(source); sourceText.value = ''; sourceTitle.value = ''; pasting.value = false } catch (cause) { if (sameOwner(owner)) showError(cause) } finally { if (sameOwner(owner)) sourceBusy.value = false } }
async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  const owner = user.value?.id
  sourceBusy.value = true; error.value = ''
  try { for (const file of files) { const source = await studyApi.upload(file); if (!sameOwner(owner)) return; rememberSource(source) } } catch (cause) { if (sameOwner(owner)) showError(cause) } finally { if (sameOwner(owner)) sourceBusy.value = false; input.value = '' }
}
async function generate() {
  if (busy.value) return
  if (!form.title.trim() || !selectedRanges.value.length || selectedRanges.value.length > 6) { error.value = c('scopeRequired'); return }
  await action(async () => {
    const owner = user.value?.id
    const payload = { ...form, title: form.title.trim(), language: activeLocale.value, selections: selectedRanges.value.map(range => { const [asset_id, section_id] = range.split(':'); return { asset_id: asset_id!, section_id: section_id! } }) }
    const fingerprint = JSON.stringify(payload)
    if (submittedFingerprint && submittedFingerprint !== fingerprint) requestId = crypto.randomUUID()
    submittedFingerprint = fingerprint; persistDraft()
    const result = await studyApi.generate({ ...payload, request_id: requestId })
    if (!sameOwner(owner)) return
    requestId = crypto.randomUUID(); submittedFingerprint = ''; persistDraft(); creating.value = false; await router.push(`/study/${result.id}`); await loadLibrary()
  })
}
async function openMaterial() {
  clearTimeout(timer); const id = materialId.value, current = ++epoch
  readingCompanionAnchor.value = null
  material.value = null; noteText.value = ''; savedNote.value = ''; noteSaved.value = false
  activeChapter.value = ''; selectedPassage.value = null; toolTab.value = 'assistant'
  if (!id || !user.value) return
  async function refresh(first = false) {
    try {
      const result = await studyApi.get(id)
      if (disposed || current !== epoch || materialId.value !== id || !user.value) return
      material.value = result
      if (first) { savedNote.value = result.notes[result.revisions[0]!.id]?.content || ''; noteText.value = sessionStorage.getItem(noteKey()) ?? savedNote.value }
      const summary = library.value.find(item => item.id === id)
      if (summary) summary.status = materialStatus.value
      if (isGenerating.value) timer = setTimeout(() => { void refresh() }, 1500)
    } catch (cause) { if (current === epoch) showError(cause) }
  }
  await refresh(true)
}
watch(materialId, () => { creating.value = false; void openMaterial() })
async function resume() { await action(async () => { const owner = user.value?.id, id = materialId.value; await studyApi.resume(id); if (sameOwner(owner) && materialId.value === id) await openMaterial() }) }
async function saveNote() { await action(async () => { const owner = user.value?.id, id = materialId.value, revision = material.value!.revisions[0]!.id, content = noteText.value; await studyApi.note(id, revision, content); if (sameOwner(owner) && id === materialId.value) { savedNote.value = content; noteSaved.value = true } }) }
function download(blob: Blob, filename: string) { const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) }
async function exportHandout() { await action(async () => { const owner = user.value?.id, title = material.value!.title, blob = await studyApi.export(materialId.value); if (sameOwner(owner)) download(blob, `${title}.md`) }) }
async function downloadSource(id: string, filename: string) { await action(async () => { const owner = user.value?.id, blob = await studyApi.downloadSource(id); if (sameOwner(owner)) download(blob, filename) }) }
onBeforeRouteLeave(() => { persistDraft() })
onMounted(() => { void action(connect) })
onBeforeUnmount(() => { disposed = true; epoch++; clearTimeout(timer); persistDraft() })
</script>

<style scoped>
.study-selection-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 20px;background:#eeeafa;color:#6b59a2;font:15px/1.6 var(--handout-sans)}.study-selection-actions span{flex:1}.study-selection-actions button{padding:4px 8px}
.study-reading-tools{display:flex;flex-direction:column;min-height:0}.study-tool-tabs{flex:none}.study-reading-tools:has(.personal-assistant){overflow:hidden;width:360px}.study-reading-tools:has(.personal-assistant) .study-tool-tabs{padding-inline:5px;gap:0}
@media(max-width:1200px){.study-reading-tools:has(.personal-assistant){width:320px}}
.study-space{height:100%;min-height:0;display:flex;flex-direction:column;color:#263449;background:#f5f6fc;font:15px/1.6 var(--lz-font-sans,Inter,"Microsoft YaHei",sans-serif)}
.study-space button,.study-space input,.study-space textarea,.study-space select{font:inherit}.study-space button,.study-space a{transition:background .15s,color .15s}.study-space button{cursor:pointer;border:1px solid #dbe0ed;border-radius:10px;background:white;color:#43536d;padding:9px 14px;display:inline-flex;justify-content:center;align-items:center;gap:8px}.study-space button:hover{background:#eeedf9;color:#5145a4}.study-space button:disabled{cursor:default;opacity:.55}.study-space :is(button,a,input,textarea,select):focus-visible{outline:3px solid #9385ed;outline-offset:3px}.study-space a{text-decoration:none;color:inherit}.study-space .study-primary{background:var(--lz-action-bg);border-color:var(--lz-action-border);color:var(--lz-action-text);font-weight:650;padding:12px 20px;box-shadow:var(--lz-action-shadow);border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius)}.study-space .study-primary:hover{background:var(--lz-action-bg);color:var(--lz-action-text)}
.study-header{height:82px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 30px;background:#ffffffed;border-bottom:1px solid #e4e7f0;gap:20px}.study-brand{display:flex;align-items:center;gap:12px}.brand-symbol{width:46px;height:46px;display:grid;place-items:center;background:#eee9fb;color:#6551c7;border-radius:15px}.study-brand strong{font-size:20px;display:block}.study-brand small{font-size:15px;color:#8190a4}.study-header-actions{display:flex;align-items:center;gap:18px}.study-header-actions button{border:0;background:transparent;padding:7px}.study-user{display:flex;align-items:center;gap:7px;color:#647187}.study-eyebrow{font-size:15px;color:#7b6ca4;font-weight:650;letter-spacing:.09em}.study-error{flex:none;padding:10px 28px;background:#fff1f1;color:#a14253;display:flex;align-items:center;justify-content:space-between;gap:16px}.study-error button{padding:5px 12px;color:inherit}
.study-login-page{flex:1;overflow:auto;display:grid;grid-template-columns:minmax(0,570px) 410px;justify-content:center;align-items:center;gap:90px;padding:45px}.login-story h1{font-size:40px;line-height:1.3;letter-spacing:-.02em;margin:15px 0 20px}.login-story>p{font-size:18px;color:#748399;margin-bottom:35px}.login-purpose{display:flex;gap:18px;margin-top:25px;padding:20px 0;border-top:1px solid #dfe3f0}.login-purpose svg{color:#7662bd;margin-top:7px;flex:none}.login-purpose h3{font-size:18px;margin:0 0 6px}.login-purpose p{margin:0;color:#718096}.study-login-card{padding:36px;background:white;border:1px solid #e2e5ef;border-radius:22px;box-shadow:0 16px 50px #58688910}.study-login-card h2{font-size:25px;margin:12px 0}.study-login-card>p{color:#7b889c;margin-bottom:25px}.study-login-card .study-primary{width:100%;margin-top:14px}.study-login-card .study-text-button{display:flex;margin:17px auto 0;border:0;color:#6551c7}
.study-workspace{flex:1;min-height:0;display:flex}.study-navigation{width:240px;flex:none;padding:28px 18px;display:flex;flex-direction:column;border-right:1px solid #e2e5ef;background:#fbfcff;overflow:auto}.study-navigation>.study-eyebrow{padding:0 11px;margin-bottom:25px;font-size:15px;letter-spacing:.02em}.study-navigation>button{justify-content:flex-start;border:0;background:transparent;margin-bottom:8px;padding:12px;color:#69778b}.study-navigation>button.active{color:#6651bd;background:#eeeafb;font-weight:650}.recent-materials{display:flex;flex-direction:column;gap:5px;margin-top:27px;border-top:1px solid #e6e8f1;padding-top:19px}.recent-materials a{display:flex;gap:10px;padding:11px;border-radius:10px;overflow-wrap:anywhere}.recent-materials a:hover,.recent-materials a.active{background:#f0edf9}.recent-materials small{display:block;font-size:15px;color:#8390a2;margin-top:4px}.material-dot{margin-top:9px;width:7px;height:7px;flex:none;border-radius:50%;background:#7e6db8}.material-dot.exam_prep{background:#4682b2}.study-nav-hint{display:flex;align-items:flex-start;gap:9px;margin-top:auto;padding:35px 10px 0;color:#8a94a5;font-size:15px}.study-nav-hint svg{flex:none;margin-top:5px}
.study-main-scroll{flex:1;min-width:0;overflow:auto}.study-library,.study-create{max-width:1080px;margin:auto;padding:42px 48px 60px}.study-page-heading{display:flex;align-items:center;justify-content:space-between;gap:25px;margin-bottom:34px}.study-page-heading h1{font-size:30px;margin:8px 0 10px}.study-page-heading p{color:#7a889c;margin:0}.study-material-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:22px}.study-material-card{background:white;border:1px solid #e0e5f0;border-radius:17px;padding:26px;box-shadow:0 5px 14px #4a597106;min-height:250px;display:flex;flex-direction:column}.study-material-card:hover{border-color:#baafe7;box-shadow:0 8px 25px #6551c711}.material-mode{display:flex;align-items:center;gap:8px;color:#7660b4;font-weight:600}.material-mode.exam_prep{color:#3e7f9d}.study-material-card h2{font-size:22px;margin:22px 0 10px}.study-material-card>p{color:#7a889c;margin:0 0 28px}.study-material-card footer{display:flex;justify-content:space-between;align-items:center;margin-top:auto;color:#8675b2}.study-status{color:#778299;display:inline-flex;align-items:center;gap:8px;font-size:15px}.study-status:before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor}.study-status.completed{color:#278061}.study-status.running{color:#7057b7}.study-status.failed,.study-status.paused{color:#a87540}.study-empty{text-align:center;padding:70px 20px;border:1px dashed #d5d9eb;border-radius:20px;background:#fafbff}.empty-books{color:#8d7bbc;background:#eeeafb;width:95px;height:95px;border-radius:24px;display:grid;place-items:center;margin:auto}.study-empty h2{margin:24px 0 12px;font-size:25px}.study-empty p{color:#7a889c;max-width:500px;margin:0 auto 26px}
.study-form-section{background:white;border:1px solid #e3e6ef;border-radius:16px;padding:26px 28px;margin:22px 0}.study-form-section h2{font-size:20px;margin:0 0 10px}.study-form-section>p{margin:0 0 22px;color:#7b879b}.study-space label:not(.source-selection):not(.study-upload){display:flex;flex-direction:column;gap:9px;margin-bottom:18px;font-weight:550}.study-space input:not([type=checkbox]):not([type=file]),.study-space textarea,.study-space select{width:100%;min-width:0;border:1px solid #d7deeb;border-radius:9px;background:#fcfdff;padding:11px 13px;color:#33455f;box-sizing:border-box}.study-space textarea{resize:vertical}.study-source-actions{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin-bottom:22px}.study-upload{position:relative;display:flex;align-items:center;gap:9px;border:1px solid #c9c0eb;background:#f7f4ff;color:#6952b5;padding:9px 14px;border-radius:10px;cursor:pointer}.study-upload input{position:absolute;width:1px;height:1px;opacity:0}.study-source-actions>span{font-size:15px;color:#8a94a6}.study-paste{padding:20px;background:#f7f8fc;border-radius:12px;margin-bottom:20px}.study-source{padding:16px 0;border-top:1px solid #e7e9f1}.source-name{display:flex;align-items:center;gap:9px;color:#576783;margin-bottom:13px;flex-wrap:wrap}.source-name>span{margin-left:auto;font-size:15px;color:#8591a2}.source-selection{display:flex;align-items:center;gap:12px;padding:9px 10px;margin:2px 0;border-radius:8px;background:#fafbfe;cursor:pointer}.source-selection input{width:17px;height:17px;accent-color:#755fc0}.source-selection small{margin-left:auto;color:#8a95a5;font-size:15px}.source-warning{color:#a47548;font-size:15px}.study-purpose-options{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:20px}.study-purpose-options button{position:relative;display:flex;flex-direction:column;align-items:flex-start;text-align:left;padding:21px;border:1px solid #e1e5ef;background:#fcfcff;gap:12px}.study-purpose-options button.selected{border-color:#8d7ad0;background:#f5f1ff}.study-purpose-options strong{font-size:18px;color:#3c4260}.study-purpose-options span{color:#7d849c;font-size:15px;font-weight:400}.purpose-check{position:absolute;right:18px;top:23px;color:#7761bc}.study-settings-row{display:grid;grid-template-columns:1fr 1fr;gap:20px}.study-generate-bar{display:flex;justify-content:space-between;align-items:center;padding:10px 0;color:#8190a3}
.study-reading-pane{flex:1;min-width:0;min-height:0;display:flex;flex-direction:column;background:#f3f4f9}.study-reading-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex:none;padding:13px 20px;background:white;border-bottom:1px solid #e4e7f0}.study-reading-toolbar button{border:0;font-size:15px;background:transparent;padding:5px 9px}.study-document-scroll{min-height:0;overflow:auto;scroll-behavior:smooth;padding:32px 32px 70px}.study-handout{max-width:950px;margin:auto;min-width:0;background:white;border:1px solid #e0e5ef;box-shadow:0 6px 25px #49567105;padding:40px 45px;color:#272e3d;font:18px/1.95 var(--handout-serif)}.study-handout-cover h1{font:700 32px/1.45 var(--handout-serif);margin:12px 0 16px}.study-handout-cover p{font:15px/1.8 var(--handout-sans);color:#7a879a;margin:0}.handout-rule{height:1px;background:#dce2ec;margin:26px 0}.study-section-kicker{font:15px/1.6 var(--handout-sans);color:#8c96a7;margin-top:30px}.study-handout-section{scroll-margin-top:25px}.study-handout-section h2{font:700 25px/1.6 var(--handout-serif);margin:8px 0 20px}.study-handout-section>div[id]{min-width:0;scroll-margin-top:25px}.study-progress{border:1px solid #dcd4ed;background:#faf7ff;padding:17px 20px;font:15px/1.8 var(--handout-sans);margin-bottom:24px;display:flex;flex-direction:column;gap:12px}.study-progress progress{width:100%;height:5px;accent-color:#8066c6}.study-progress button{align-self:flex-start}.study-draft{border-top:1px dashed #d3d8e6;padding:15px 0}.study-draft>span{font:15px/1.6 var(--handout-sans);color:#8792a5}.study-end{display:flex;gap:9px;justify-content:center;align-items:center;color:#8698a0;font:15px/1.8 var(--handout-sans);padding-top:30px;border-top:1px solid #e3e8ee;margin-top:35px}.study-reading-tools{width:300px;flex:none;overflow:auto;background:#fcfdff;border-left:1px solid #dfe4ef}.study-tool-tabs{display:flex;justify-content:space-around;gap:3px;padding:18px 10px;border-bottom:1px solid #e4e8f0}.study-tool-tabs button{padding:7px 6px;border:0;font-size:15px;color:#7e8899;background:transparent}.study-tool-tabs button.active{color:#715ab3;background:#efebfa}.study-note,.study-source-list{padding:23px}.study-note h3,.study-source-list h3{font-size:18px;margin:0 0 12px}.study-note>p{color:#8c97a8;font-size:15px;margin:0 0 22px}.study-note textarea{font-size:15px;line-height:1.9;min-height:290px}.study-note .study-primary{width:100%}.study-note-status{font-size:15px;color:#7d909b;min-height:27px;margin:10px 0}.study-source-list article{border:1px solid #dce2ed;border-radius:10px;background:white;padding:15px;margin-top:16px}.study-source-list strong{font-size:15px;display:block;margin:8px 0;overflow-wrap:anywhere}.study-source-list p{font-size:15px;color:#7e899b;margin:7px 0}.study-source-list code{font-size:15px;color:#9ba4b4}.study-reading-tools :deep(.handout-concept-map){position:static;border:0;max-height:none;overflow:visible}.study-reading-tools :deep(.concept-eyebrow){font-size:15px}
@media(max-width:1200px){.study-navigation{width:190px;padding:25px 12px}.study-reading-tools{width:270px}.study-library,.study-create{padding:35px 30px}.study-document-scroll{padding:24px 18px 60px}.study-handout{padding:30px 25px}.study-login-page{gap:45px}.study-brand small{display:none}}
@media(max-width:980px){.study-navigation{width:165px}.study-header{padding:0 20px}.study-header-actions{gap:10px}.study-reading-tools{width:235px}.study-user{max-width:180px;overflow:hidden}.study-login-page{grid-template-columns:minmax(0,1fr) 350px;gap:30px;padding:30px}.login-story h1{font-size:31px}.study-purpose-options{gap:12px}.study-reading-toolbar{flex-wrap:wrap}.study-handout{padding:25px 18px}}
.study-workspace{min-width:0;overflow:hidden}
.study-workspace>.study-navigation{box-sizing:border-box;width:var(--column-left-width);min-width:0;overflow-wrap:anywhere}
.study-workspace>.study-reading-tools{box-sizing:border-box;width:var(--column-right-width);min-width:0}
.study-workspace>.study-reading-tools .study-tool-tabs{flex-wrap:wrap}
</style>

<style scoped>
.study-space { padding: 10px; gap: 10px; box-sizing: border-box; background: transparent; }
.study-header { min-height: 60px; height: auto; padding: 8px 20px; border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: rgba(255,255,255,.82); }
.study-brand { flex: none; gap: 10px; }
.study-brand > img { width: 34px; height: 34px; }
.study-brand strong { color: #312e81; }
.study-brand small { font-size: 15px; }
.study-surface-navigation { display: flex; flex: 1; align-items: center; justify-content: center; gap: 4px; flex-wrap: wrap; }
.study-surface-navigation button { padding: 7px 10px; border: 0; background: transparent; white-space: nowrap; }
.study-surface-navigation button.active { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.study-header-actions { flex: none; gap: 10px; }
.study-workspace { gap: 8px; }
.study-workspace.is-library .study-main-scroll { border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: rgba(255,255,255,.76); box-shadow: var(--lz-shadow-panel); }
@media(max-width:1100px) { .study-header-actions .study-user { display: none; } }
</style>
