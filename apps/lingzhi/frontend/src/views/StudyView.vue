<template>
  <div class="study-space">
    <header class="study-header">
      <div v-if="materialId" class="study-course-context"><button type="button" :aria-label="t('workspaceUi.backToCourses')" @click="goLibrary"><ArrowLeft :size="18" /></button><button v-if="!directoryOpen" type="button" :aria-label="c('showDirectory')" @click="directoryOpen = true"><PanelLeftOpen :size="18" /></button><BookOpen :size="19" /><h1>{{ material?.title }}</h1></div>
      <StudentBrand v-else />
      <nav v-if="user && !materialId" class="study-surface-navigation" :aria-label="t('studentWorkspace.space')">
        <button type="button" :aria-current="!materialId && !creating ? 'page' : undefined" :class="{ active: !materialId && !creating }" @click="openStudySection('home')"><BookOpen :size="16" />{{ t('workspaceUi.myCourses') }}</button>
      </nav>
      <div class="study-header-actions">
        <template v-if="materialId">
          <button v-if="material?.revisions[0]?.sections.length" @click="exportHandout"><Download :size="17" />{{ c('export') }}</button>
          <details class="study-reading-settings" @keydown.esc="closeReadingSettings">
            <summary><Settings2 :size="17" />{{ c('readingSettings') }}</summary>
            <div class="study-reading-settings-panel">
              <label>{{ c('fontSize') }} · {{ readingFontSize }}<input v-model.number="readingFontSize" type="range" min="16" max="22" :aria-label="c('fontSize')" /></label>
              <div role="group" :aria-label="c('readingSettings')"><button v-for="font in (['serif', 'sans'] as const)" :key="font" type="button" :aria-pressed="readingFont === font" @click="readingFont = font">{{ c(font === 'serif' ? 'serifFont' : 'sansFont') }}</button></div>
            </div>
          </details>
        </template>
        <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'English' : '中文' }}</button>
        <RouterLink v-if="!user" to="/courses">{{ c('teacher') }}</RouterLink>
        <span v-if="user && !developmentMode" class="study-user"><UserRound :size="17" />{{ user.username }}</span>
        <button v-if="user && !developmentMode" @click="logout">{{ c('logout') }}</button>
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
      <aside v-if="(materialId && directoryOpen) || creating" class="study-navigation">
        <button v-if="creating" type="button" class="study-back" @click="goLibrary"><ArrowLeft :size="17" />{{ t('workspaceUi.backToCourses') }}</button>
        <template v-if="materialId">
          <header class="study-directory-heading"><BookOpen :size="18" /><strong>{{ t('workspaceUi.directory') }}</strong><button type="button" :aria-label="c('hideDirectory')" @click="directoryOpen = false"><PanelLeftClose :size="17" /></button></header>
          <ElInput v-model="chapterQuery" class="study-chapter-search" size="large" type="search" clearable :placeholder="c('searchChapters')" :aria-label="c('searchChapters')"><template #prefix><Search :size="16" /></template></ElInput>
          <nav class="study-chapter-list" :aria-label="t('workspaceUi.directory')">
            <button v-for="section in filteredReadingSections" :key="section.id" type="button" :class="{ active: activeChapter === section.id }" :aria-current="activeChapter === section.id ? 'location' : undefined" @click="navigateChapter(section.id)"><span class="study-chapter-number">{{ String(section.number).padStart(2, '0') }}</span><span>{{ section.title }}</span></button>
          </nav>
          <p v-if="!filteredReadingSections.length" class="study-nav-hint">{{ readingSections.length ? c('noChapterMatches') : t('workspaceUi.noContents') }}</p>
        </template>
        <template v-else>
          <header class="study-directory-heading"><Plus :size="18" /><strong>{{ c('create') }}</strong></header>
          <nav class="study-create-steps" :aria-label="c('create')"><a href="#study-create-sources">{{ c('sourceHeading') }}</a><a href="#study-create-purpose">{{ c('purposeHeading') }}</a><a href="#study-create-settings">{{ c('settingsHeading') }}</a></nav>
        </template>
      </aside>

      <ColumnResizeHandle v-if="(materialId && directoryOpen) || creating" v-bind="leftColumnHandle" />
      <section v-if="!materialId" class="study-main-scroll">
        <StudentLearningHome v-if="!creating" ref="authorizedCourses" :key="user.id" :class="{ 'study-library': route.query.view === 'materials' }" :user-id="user.id" :materials="library" :initial-filter="route.query.view === 'courses' ? 'teacher' : route.query.view === 'materials' ? 'owned' : 'all'" @create="startNew" @source="createFromCourse" @filter="setCourseFilter" />
        <form v-else class="study-create" @submit.prevent="generate">
          <div class="study-page-heading"><div><span class="study-eyebrow">CREATE YOUR HANDOUT</span><h1>{{ c('create') }}</h1><p>{{ c('intro') }}</p></div></div>
          <section id="study-create-sources" class="study-form-section"><h2>{{ c('sourceHeading') }}</h2><p>{{ c('sourceHint') }}</p>
            <div class="study-source-actions"><input ref="sourceFileInput" class="study-upload-input" type="file" accept=".pdf,.pptx,.docx,.md,.txt" :disabled="sourceBusy || busy" multiple @change="uploadFiles" /><button type="button" class="study-upload" :disabled="sourceBusy || busy" @click="sourceFileInput?.click()"><Upload :size="19" />{{ sourceBusy ? c('busy') : c('upload') }}</button><button type="button" class="study-paste-toggle" :disabled="sourceBusy || busy" :aria-expanded="pasting" @click="pasting = !pasting"><ClipboardPaste :size="18" />{{ c('paste') }}</button><span>{{ c('uploadHint') }}</span></div>
            <div v-if="pasting" class="study-paste"><label>{{ c('sourceTitle') }}<ElInput v-model="sourceTitle" maxlength="160" /></label><label>{{ c('sourceContent') }}<ElInput v-model="sourceText" type="textarea" :rows="8" maxlength="120000" /></label><button type="button" :disabled="sourceBusy || !sourceTitle.trim() || !sourceText.trim()" @click="addText">{{ sourceBusy ? c('busy') : c('addSource') }}</button></div>
            <p v-if="!sources.length && !pasting" class="study-source-empty">{{ c('emptySources') }}</p>
            <div v-for="source in sources" :key="source.id" class="study-source"><div class="source-name"><FileText :size="18" /><strong>{{ source.filename }}</strong><span>{{ source.sections.length }} · {{ c('sourceRanges') }}</span></div><p v-if="!source.sections.length" class="source-warning">{{ source.error || c('sourceFailed') }}</p><p v-for="warning in source.warnings" :key="warning" class="source-warning">{{ warning }}</p><label v-for="section in source.sections" :key="section.id" class="source-selection"><input v-model="selectedRanges" type="checkbox" :value="`${source.id}:${section.id}`" :disabled="!section.characters || (selectedRanges.length >= 6 && !selectedRanges.includes(`${source.id}:${section.id}`))" /><span>{{ section.title }}</span><small>{{ section.characters.toLocaleString() }}</small></label></div>
            <p class="study-range-hint">{{ c('rangeLimit') }}</p>
            <div v-if="hasInvalidRanges && !busy" class="study-range-recovery" role="status"><span>{{ c('invalidRanges') }}</span><button type="button" @click="removeInvalidRanges">{{ c('removeInvalidRanges') }}</button></div>
          </section>
          <section id="study-create-purpose" class="study-form-section"><h2>{{ c('purposeHeading') }}</h2><div class="study-purpose-options"><button v-for="purpose in purposes" :key="purpose" type="button" :class="{ selected: form.purpose === purpose }" :aria-pressed="form.purpose === purpose" @click="form.purpose = purpose"><Target v-if="purpose === 'exam_prep'" :size="25" /><BookOpen v-else :size="25" /><strong>{{ c(purpose) }}</strong><span>{{ c(purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</span><Check v-if="form.purpose === purpose" class="purpose-check" :size="19" /></button></div></section>
          <section id="study-create-settings" class="study-form-section"><h2>{{ c('settingsHeading') }}</h2><label>{{ c('title') }}<ElInput v-model="form.title" required maxlength="160" :placeholder="c('titlePlaceholder')" /></label><div class="study-settings-row"><label>{{ c('level') }}<select v-model="form.level" :aria-label="c('level')"><option v-for="level in levels" :key="level" :value="level">{{ c(level) }}</option></select></label><label>{{ c('time') }}<input v-model.number="form.time_minutes" type="number" min="10" max="600" required /></label></div><label>{{ c('requirements') }}<ElInput v-model="form.requirements" type="textarea" :rows="3" maxlength="2000" :placeholder="c(form.purpose === 'exam_prep' ? 'examRequirementsPlaceholder' : 'requirementsPlaceholder')" /></label></section>
          <div class="study-generate-bar"><div><strong>{{ selectedRanges.length }} / 6 · {{ c('scope') }}</strong><p>{{ c('personalCourseHint') }}</p><p v-if="generationIssue && !busy && !sourceBusy" id="study-generation-issue" class="study-generation-issue" role="status">{{ c(generationIssue) }}</p></div><button class="study-primary" :aria-describedby="generationIssue ? 'study-generation-issue' : undefined" :disabled="busy || sourceBusy || !canGenerate">{{ busy ? c('busy') : c('generate') }}<ArrowRight :size="19" /></button></div>
        </form>
      </section>

      <template v-else>
        <div class="study-reading-workspace">
          <div class="study-reading-body">
            <div class="study-reading-pane">
              <div v-if="selectedPassage" class="study-selection-actions"><span>{{ c('selectedQuote') }} · {{ selectedPassage.block_title || selectedPassage.section_title }}</span><button @pointerdown.prevent @click="openTool('assistant')">{{ c('askSelection') }}</button><button @click="selectedPassage = null">{{ c('clearQuote') }}</button></div>
              <div v-if="material" ref="readingTarget" class="study-document-scroll" @scroll="followChapter" @pointerup="selectPassage" @keyup="selectPassage">
                <article class="study-handout" :style="readingStyle">
                  <div v-if="materialStatus !== 'completed'" class="study-progress" role="status"><span>{{ ['failed', 'paused'].includes(materialStatus) ? c('interrupted') : c('generatingHint') }}</span><progress v-if="isGenerating" :value="material.task?.progress || 0" max="100" /><button v-if="['failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c('continue') }}</button></div>

                  <section v-for="section in material.revisions[0]?.sections || []" :id="sectionAnchor(section.id)" :data-section-id="section.id" :key="section.id" class="study-handout-section"><div class="study-section-kicker">{{ section.source.filename }}</div><h2>{{ section.title }}</h2><div v-for="block in section.blocks" :id="blockAnchor(block.block_id)" :data-block-id="block.block_id" :key="block.block_id"><HandoutContentBlock :content-type="block.content_type" :label="block.type_label" :title="block.title" :answer-to="block.answer_to" :streaming="!section.complete"><MarkdownRenderer :content="block.content" :node-id="block.block_id" /></HandoutContentBlock></div><div v-if="section.fragment" class="study-draft"><span>{{ c('draft') }}</span><MarkdownRenderer :content="section.fragment" /></div></section>
                  <p v-if="materialStatus === 'completed'" class="study-end"><Check :size="17" />{{ c('finishReading') }}</p>
                </article>
              </div>
            </div>
            <ColumnResizeHandle v-if="material && toolsOpen" v-bind="rightColumnHandle" />
            <aside v-if="material" v-show="toolsOpen" class="study-reading-tools">
              <header class="study-tool-heading"><strong>{{ c(toolTab) }}</strong><ElButton text circle :aria-label="t('common.close')" @click="closeTool"><X :size="18" /></ElButton></header>
              <PersonalHandoutAssistant v-if="toolTab === 'assistant' && material.revisions[0]" :key="`${user.id}:${material.id}:${material.revisions[0].id}`" :owner-id="user.id" :material-id="material.id" :revision-id="material.revisions[0].id" :context="assistantContext" @clear-quote="selectedPassage = null" @session-expired="showError" />
              <div v-else-if="toolTab === 'note'" class="study-note"><p>{{ c('noteHint') }}</p><ElInput v-model="noteText" class="study-note-editor" type="textarea" :rows="16" resize="none" :placeholder="c('notePlaceholder')" :aria-label="c('note')" /><footer class="study-note-footer"><div class="study-note-status" role="status">{{ noteDirty ? c('noteUnsaved') : noteSaved ? c('noteSaved') : '' }}</div><ElButton type="primary" :disabled="busy || !noteDirty" @click="saveNote">{{ c('saveNote') }}</ElButton></footer></div>
              <div v-else-if="toolTab === 'sources'" class="study-source-list"><article v-for="source in selectedSourceScopes" :key="source.node_id"><FileText :size="18" /><strong>{{ source.filename }}</strong><p>{{ source.title }}</p><button :disabled="busy" @click="downloadSource(source.asset_id, source.filename)">{{ c('downloadSource') }}</button></article></div>
              <HandoutConceptMap v-else-if="conceptSections.some(section => section.nodes.length)" :sections="conceptSections" :target="readingTarget" :origin-label="c('conceptOrigin')" />
              <p v-else class="study-note">{{ c('preparingConcepts') }}</p>
            </aside>
          </div>
          <LearningDock v-if="material" toolbar placement="bottom" :location="assistantContext.section_title || material.title">
            <template #tools>
              <button v-for="tab in toolTabs" :key="tab" :data-tool="tab" type="button" class="learning-dock__domain" :class="{ 'is-active': toolsOpen && toolTab === tab }" :aria-pressed="toolsOpen && toolTab === tab" @click="toggleTool(tab)"><component :is="toolIcons[tab]" :size="17" />{{ c(tab) }}</button>
            </template>
          </LearningDock>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElButton, ElInput } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, BookOpen, Check, ClipboardPaste, Download, FileText, Plus, Target, Upload, UserRound, X, NotebookPen, Network, Sparkles, PanelLeftClose, PanelLeftOpen, Search, Settings2 } from 'lucide-vue-next'
import LearningDock from '../components/LearningDock.vue'
import HandoutContentBlock from '../components/HandoutContentBlock.vue'
import HandoutConceptMap from '../components/HandoutConceptMap.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import PersonalHandoutAssistant from '../components/PersonalHandoutAssistant.vue'
import { studyApi, studySession, StudyApiError, type StudyMaterial, type StudyPurpose, type StudySource, type StudySummary, type StudyUser } from '../api/study'
import { activeLocale, setLocale, t } from '../shared/i18n'
import StudentBrand from '../components/StudentBrand.vue'
import { studyCopy as c, type StudyCopyKey } from '../shared/study-copy'
import StudentLearningHome from '../components/StudentLearningHome.vue'
import { setStudyIdentity } from '../utils/study-identity'
import { buildHandoutConceptSections } from '../utils/handout-concepts'
import { clearQizhiAccessToken, isQizhiAuthRequired, redirectToQizhiLogin } from '../utils/http'
import ColumnResizeHandle from '../components/ColumnResizeHandle.vue'
import { useResizableColumns } from '../composables/useResizableColumns'

const router = useRouter(), route = useRoute()
const developmentMode = ref(false)
const user = ref<StudyUser | null>(null), localLoginEnabled = ref(false), qizhiAuth = isQizhiAuthRequired()
const username = ref(''), password = ref(''), registerMode = ref(false), busy = ref(false), sourceBusy = ref(false), error = ref('')
const library = ref<StudySummary[]>([]), sources = ref<StudySource[]>([]), material = ref<StudyMaterial | null>(null)
const creating = ref(false), pasting = ref(false), sourceTitle = ref(''), sourceText = ref(''), selectedRanges = ref<string[]>([])
const form = reactive({ title: '', purpose: 'systematic' as StudyPurpose, level: 'beginner', time_minutes: 60, requirements: '' })
const purposes: StudyPurpose[] = ['systematic', 'exam_prep'], levels = ['beginner', 'intermediate', 'advanced'] as const
const sourceFileInput = ref<HTMLInputElement | null>(null)
const availableRanges = computed(() => new Set(sources.value.flatMap(source => source.sections.filter(section => section.characters > 0).map(section => `${source.id}:${section.id}`))))
const hasInvalidRanges = computed(() => new Set(selectedRanges.value).size !== selectedRanges.value.length || selectedRanges.value.some(range => !availableRanges.value.has(range)))
const generationIssue = computed<StudyCopyKey | ''>(() => {
  if (hasInvalidRanges.value) return 'invalidRanges'
  if (!selectedRanges.value.length) return 'rangeRequired'
  if (selectedRanges.value.length > 6) return 'tooManyRanges'
  if (!form.title.trim()) return 'titleRequired'
  if (!Number.isInteger(form.time_minutes) || form.time_minutes < 10 || form.time_minutes > 600) return 'timeInvalid'
  return ''
})
const canGenerate = computed(() => !generationIssue.value)
function removeInvalidRanges() { selectedRanges.value = [...new Set(selectedRanges.value.filter(range => availableRanges.value.has(range)))] }
const toolTabs = ['note', 'assistant', 'concepts', 'sources'] as const
type StudyTool = typeof toolTabs[number]
const toolTab = ref<StudyTool>('assistant'), toolsOpen = ref(false)
const toolIcons = { assistant: Sparkles, note: NotebookPen, concepts: Network, sources: FileText }
function toolPreferenceKey() { return `lingzhi-study-tools:${user.value?.id}:${materialId.value}` }
function rememberTool() {
  try { sessionStorage.setItem(toolPreferenceKey(), JSON.stringify({ tab: toolTab.value, open: toolsOpen.value })) } catch { /* Optional layout preference. */ }
}
function openTool(tab: StudyTool) { toolTab.value = tab; toolsOpen.value = true; rememberTool() }
function closeTool() { toolsOpen.value = false; rememberTool() }
function toggleTool(tab: StudyTool) { if (toolsOpen.value && toolTab.value === tab) closeTool(); else openTool(tab) }
function restoreTool() {
  toolTab.value = 'assistant'; toolsOpen.value = false
  try {
    const stored = JSON.parse(sessionStorage.getItem(toolPreferenceKey()) || 'null')
    if (stored && toolTabs.includes(stored.tab)) { toolTab.value = stored.tab; toolsOpen.value = stored.open === true }
  } catch { /* A damaged preference never blocks reading. */ }
}
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
  if (visible) {
    activeChapter.value = visible.dataset.sectionId || ''
    try { sessionStorage.setItem(readingPositionKey(), activeChapter.value) } catch { /* Reading remains available without browser storage. */ }
  }
}
function readingPositionKey() { return `lingzhi-study-position:${user.value?.id}:${materialId.value}:${material.value?.revisions[0]?.id}` }
function navigateChapter(id: string) {
  const target = document.getElementById(sectionAnchor(id))
  if (!target || !readingTarget.value?.contains(target)) return
  const root = readingTarget.value
  root.scrollTo({ top: root.scrollTop + target.getBoundingClientRect().top - root.getBoundingClientRect().top - 24, behavior: 'instant' })
  activeChapter.value = id
  try { sessionStorage.setItem(readingPositionKey(), id) } catch { /* Optional UI position. */ }
}
function selectPassage() {
  const selection = window.getSelection(), root = readingTarget.value
  if (!selection || !root || selection.isCollapsed || !selection.rangeCount) return
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return
  const start = range.startContainer.nodeType === 1 ? range.startContainer as Element : range.startContainer.parentElement
  const end = range.endContainer.nodeType === 1 ? range.endContainer as Element : range.endContainer.parentElement
  const sid = start?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId
  if (!sid || sid !== end?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId) return
  const section = material.value?.revisions[0]?.sections.find(s => s.id === sid)
  const bid = start?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId
  const block = bid === end?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId ? section?.blocks.find(b => b.block_id === bid) : null
  const quote = selection.toString().trim()
  if (!section || !quote || quote.length > 3000) return
  selectedPassage.value = { section_id: sid, section_title: section.title, block_id: block?.block_id || '', block_title: block?.title || '', quote }
}
const readingTarget = ref<HTMLElement | null>(null), noteText = ref(''), savedNote = ref(''), noteSaved = ref(false)
const noteDirty = computed(() => noteText.value !== savedNote.value)
const materialId = computed(() => String(route.params.materialId || ''))
const studyLayoutRoot = ref<HTMLElement | null>(null)
const directoryOpen = ref(true), chapterQuery = ref('')
const readingFontSize = ref(18), readingFont = ref<'serif' | 'sans'>('serif')
const readingStyle = computed(() => ({
  '--study-reading-size': `${readingFontSize.value}px`,
  '--study-reading-font': readingFont.value === 'serif' ? 'var(--handout-serif)' : 'var(--handout-sans)',
}))
function closeReadingSettings(event: KeyboardEvent) {
  const details = event.currentTarget as HTMLDetailsElement
  details.open = false
  details.querySelector('summary')?.focus()
}
watch(materialId, () => { chapterQuery.value = ''; directoryOpen.value = true })
const { layoutStyle: columnLayoutStyle, leftHandle: leftColumnHandle, rightHandle: rightColumnHandle } = useResizableColumns(studyLayoutRoot, {
  storageKey: 'lingzhi:personal-study:columns', left: 244, right: 350, leftMin: 170, rightMin: 280,
  leftVisible: () => Boolean((materialId.value && directoryOpen.value) || creating.value),
  rightVisible: () => Boolean(materialId.value && material.value && toolsOpen.value),
})
const materialStatus = computed(() => material.value?.task?.status || material.value?.status || 'pending')
const isGenerating = computed(() => ['pending', 'running'].includes(materialStatus.value))
const sectionAnchor = (id: string) => `study-${materialId.value}-${id}`
const blockAnchor = (id: string) => `study-${materialId.value}-${id}`
const readingSections = computed(() => (material.value?.revisions[0]?.sections || []).map(section => ({ id: section.id, title: section.title, anchor: sectionAnchor(section.id), blocks: section.blocks.map(block => ({ id: block.block_id, title: block.title, anchor: blockAnchor(block.block_id), content: block.content, knowledge: block.knowledge_names })) })))
const filteredReadingSections = computed(() => {
  const query = chapterQuery.value.trim().toLocaleLowerCase()
  return readingSections.value.map((section, index) => ({ ...section, number: index + 1 }))
    .filter(section => section.title.toLocaleLowerCase().includes(query))
})
const conceptSections = computed(() => buildHandoutConceptSections(material.value?.plans || [], readingSections.value))
const selectedSourceScopes = computed(() => material.value?.sources || (material.value?.revisions[0]?.sections || []).map(section => ({ node_id: section.id, title: section.title, ...section.source })))
let timer: ReturnType<typeof setTimeout> | undefined, requestId = crypto.randomUUID(), submittedFingerprint = '', disposed = false, epoch = 0, actionSequence = 0, librarySequence = 0
const draftKey = () => `lingzhi-study-draft:${user.value?.id || ''}`
const noteKey = () => `lingzhi-study-note:${user.value?.id}:${materialId.value}:${material.value?.revisions[0]?.id}`

function showError(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : c('requestFailure')
  if (cause instanceof StudyApiError && cause.status === 401) { persistDraft(); epoch++; user.value = null; clearPrivateUi(); clearTimeout(timer) }
}
function clearPrivateUi() { librarySequence++; material.value = null; library.value = []; sources.value = []; selectedRanges.value = []; sourceText.value = ''; sourceTitle.value = ''; noteText.value = ''; savedNote.value = ''; creating.value = false; pasting.value = false; sourceBusy.value = false; selectedPassage.value = null; activeChapter.value = ''; Object.assign(form, { title: '', purpose: 'systematic', level: 'beginner', time_minutes: 60, requirements: '' }) }
const sameOwner = (owner: string | undefined) => !disposed && user.value?.id === owner
async function action(operation: () => Promise<void>) { const owner = user.value?.id, sequence = ++actionSequence; busy.value = true; error.value = ''; try { await operation() } catch (cause) { if (!disposed && (!owner || sameOwner(owner))) showError(cause) } finally { if (sequence === actionSequence) busy.value = false } }
function persistDraft() { if (user.value) sessionStorage.setItem(draftKey(), JSON.stringify({ form, selectedRanges: selectedRanges.value, sourceTitle: sourceTitle.value, sourceText: sourceText.value, requestId, submittedFingerprint })) }
function restoreDraft() { try { const draft = JSON.parse(sessionStorage.getItem(draftKey()) || '{}'); Object.assign(form, draft.form || {}); selectedRanges.value = draft.selectedRanges || []; sourceTitle.value = draft.sourceTitle || ''; sourceText.value = draft.sourceText || ''; requestId = draft.requestId || crypto.randomUUID(); submittedFingerprint = draft.submittedFingerprint || '' } catch { /* An invalid UI draft does not affect saved materials. */ } }
watch([form, selectedRanges, sourceTitle, sourceText], persistDraft, { deep: true })
watch(noteText, () => { if (material.value && user.value) sessionStorage.setItem(noteKey(), noteText.value) })

async function loadLibrary() {
  const owner = user.value?.id, sequence = ++librarySequence
  const current = () => sameOwner(owner) && sequence === librarySequence
  // One unavailable list must not hide the other list or an already saved handout.
  const results = await Promise.allSettled([
    studyApi.list().then(result => { if (current()) library.value = result }),
    studyApi.sources().then(result => { if (current()) sources.value = result }),
  ])
  const failure = results.find(result => result.status === 'rejected')
  if (current() && failure?.status === 'rejected') showError(failure.reason)
}
async function connect() {
  const config = await studyApi.config(); localLoginEnabled.value = config.local_login_enabled; developmentMode.value = config.development_identity === true
  if (!studySession.get() && !qizhiAuth && !developmentMode.value) return
  try { user.value = await studyApi.me(); setStudyIdentity(user.value); restoreDraft(); creating.value = !materialId.value && route.query.create === '1'; await Promise.all([loadLibrary(), openMaterial()]) }
  catch (cause) { showError(cause) }
}
async function authenticate() { if (busy.value) return; await action(async () => { const result = await studyApi.login(username.value, password.value, registerMode.value); studySession.set(result.token); setStudyIdentity(result.user); password.value = ''; epoch++; user.value = result.user; restoreDraft(); creating.value = !materialId.value && route.query.create === '1'; await Promise.all([loadLibrary(), openMaterial()]); const returnTo = String(route.query.returnTo || ''); if (returnTo.startsWith('/course/') && !returnTo.startsWith('//')) await router.push(returnTo); else creating.value = !materialId.value && route.query.create === '1' }) }
async function logout() { persistDraft(); await action(async () => { await studyApi.logout(); epoch++; studySession.clear(); if (qizhiAuth) clearQizhiAccessToken(); clearTimeout(timer); user.value = null; clearPrivateUi(); await router.push('/study') }) }
const authorizedCourses = ref<InstanceType<typeof StudentLearningHome> | null>(null)
function reconnect() { void action(async () => { if (!user.value) await connect(); else { await Promise.all([loadLibrary(), authorizedCourses.value?.reload()]); await openMaterial() } }) }
async function openStudySection(view: 'home' | 'courses' | 'materials') { creating.value = false; await router.push({ path: '/study', query: view === 'home' ? {} : { view } }); await action(loadLibrary) }
async function goLibrary() { await openStudySection('home') }
async function setCourseFilter(value: 'all' | 'teacher' | 'owned') { await router.replace({ path: '/study', query: value === 'all' ? {} : { view: value === 'teacher' ? 'courses' : 'materials' } }) }
async function startNew(purpose?: StudyPurpose) { if (!user.value) return; persistDraft(); await router.push('/study?create=1'); creating.value = true; if (purpose) form.purpose = purpose }
async function createFromCourse(source: StudySource) { const owner = user.value?.id; await startNew(); if (sameOwner(owner)) { sources.value = sources.value.filter(item => item.id !== source.id); selectedRanges.value = []; form.title = ''; rememberSource(source) } }
function rememberSource(source: StudySource) {
  sources.value = [source, ...sources.value.filter(existing => existing.id !== source.id)]
  if (!source.sections.length) { error.value = source.error || c('sourceFailed'); return }
  if (!form.title) form.title = source.filename.replace(/\.[^.]+$/, '')
}
async function addText() { if (sourceBusy.value || busy.value || !user.value) return; const owner = user.value?.id; sourceBusy.value = true; error.value = ''; try { const source = await studyApi.addText(sourceTitle.value.trim(), sourceText.value); if (!sameOwner(owner)) return; rememberSource(source); sourceText.value = ''; sourceTitle.value = ''; pasting.value = false } catch (cause) { if (sameOwner(owner)) showError(cause) } finally { if (sameOwner(owner)) sourceBusy.value = false } }
async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  if (sourceBusy.value || busy.value || !user.value || !files.length) return
  const oversized = files.find(file => file.size > 20 * 1024 * 1024)
  if (oversized) { error.value = `${oversized.name}: ${c('sourceTooLarge')}`; input.value = ''; return }
  const owner = user.value?.id
  sourceBusy.value = true; error.value = ''
  try { for (const file of files) { const source = await studyApi.upload(file); if (!sameOwner(owner)) return; rememberSource(source) } } catch (cause) { if (sameOwner(owner)) showError(cause) } finally { if (sameOwner(owner)) sourceBusy.value = false; input.value = '' }
}
async function generate() {
  if (busy.value || sourceBusy.value) return
  if (generationIssue.value) { error.value = c(generationIssue.value); return }
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
  const retainedRevision = material.value?.id === id ? material.value.revisions[0]?.id : undefined
  if (!retainedRevision) {
    material.value = null; noteText.value = ''; savedNote.value = ''; noteSaved.value = false
    activeChapter.value = ''; selectedPassage.value = null; restoreTool()
  }
  if (!id || !user.value) return
  async function refresh(first = false) {
    try {
      const result = await studyApi.get(id)
      if (disposed || current !== epoch || materialId.value !== id || !user.value) return
      material.value = result
      if (first && !retainedRevision) {
        await nextTick()
        if (disposed || current !== epoch || materialId.value !== id) return
        let saved = ''
        try { saved = sessionStorage.getItem(readingPositionKey()) || '' } catch { /* Optional UI position. */ }
        if (saved && readingSections.value.some(section => section.id === saved)) navigateChapter(saved)
        else activeChapter.value = readingSections.value[0]?.id || ''
      }
      if (first && retainedRevision !== result.revisions[0]?.id) { savedNote.value = result.notes[result.revisions[0]!.id]?.content || ''; noteText.value = sessionStorage.getItem(noteKey()) ?? savedNote.value }
      const summary = library.value.find(item => item.id === id)
      if (summary) summary.status = materialStatus.value
      if (isGenerating.value) timer = setTimeout(() => { void refresh() }, 1500)
    } catch (cause) { if (current === epoch) showError(cause) }
  }
  await refresh(true)
}
watch(materialId, () => { creating.value = route.query.create === '1' && !materialId.value; void openMaterial() })
watch(() => route.query.create, value => { creating.value = value === '1' && !materialId.value && Boolean(user.value) })
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
.study-space {
  height: 100%; min-height: 0; display: flex; flex-direction: column;
  padding: 10px; gap: 10px; box-sizing: border-box;
  --study-ui-font: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  color: var(--lz-text); background: transparent;
  font: 15px/1.6 var(--study-ui-font);
}
.study-space button, .study-space input, .study-space textarea, .study-space select { font: inherit; }
.study-space button, .study-space a { transition: background .15s, color .15s; }
.study-space button:where(:not(.el-button)) {
  cursor: pointer; min-height: 36px; border: 1px solid var(--lz-action-border);
  border-radius: 8px; background: #fff; color: var(--lz-text-secondary);
  padding: 8px 12px; display: inline-flex; justify-content: center; align-items: center; gap: 8px;
}
.study-space button:where(:not(.el-button)):hover:not(:disabled) { background: var(--lz-brand-soft); color: var(--lz-brand-strong); }
.study-space button:where(:not(.el-button)):disabled { cursor: default; opacity: .55; }
.study-space :is(button:where(:not(.el-button)), a, select, summary, input[type=range]):focus-visible { outline: 2px solid var(--lz-action-focus); outline-offset: 3px; }
.study-space a { text-decoration: none; color: inherit; }
.study-space .study-primary { background: var(--lz-action-primary-bg); color: var(--lz-action-primary-text); font-weight: 600; border-color: var(--lz-action-primary-border); }
.study-space .study-primary:hover:not(:disabled) { background: var(--lz-action-primary-hover); color: var(--lz-action-primary-text); }
.study-header {
  min-height: 60px; flex: none; box-sizing: border-box; display: flex; align-items: center;
  justify-content: space-between; padding: 8px 20px; gap: 20px;
  border: 1px solid rgba(255, 255, 255, .88); border-radius: 18px;
  background: linear-gradient(135deg, rgba(255, 255, 255, .96), rgba(250, 250, 255, .91));
  box-shadow: 0 8px 26px rgba(79, 70, 229, .08), inset 0 1px 0 rgba(255, 255, 255, .96);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.study-header-actions { display: flex; align-items: center; flex: none; gap: 10px; }
.study-header-actions button, .study-course-context > button { border: 0; background: transparent; padding: 6px 8px; white-space: nowrap; }
.study-user { display: flex; align-items: center; gap: 7px; color: #7c8496; }
.study-surface-navigation { display: flex; flex: 1; align-items: center; justify-content: center; }
.study-surface-navigation button { border: 1px solid #dbe2ee; background: #f8fafc; padding: 6px 14px; font-weight: 600; }
.study-surface-navigation button.active { background: white; color: var(--lz-brand-strong); box-shadow: 0 2px 7px rgba(51, 65, 85, .09); }
.study-course-context { display: flex; align-items: center; gap: 10px; min-width: 0; }
.study-course-context h1 { margin: 0; font-size: 18px; font-weight: 650; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.study-course-context > svg { flex: none; color: var(--lz-brand); }
.study-reading-settings { position: relative; }
.study-reading-settings summary { display: flex; align-items: center; gap: 8px; padding: 6px 8px; cursor: pointer; list-style: none; white-space: nowrap; }
.study-reading-settings summary::-webkit-details-marker { display: none; }
.study-reading-settings-panel { position: absolute; right: 0; top: calc(100% + 14px); z-index: 30; width: 240px; padding: 20px; background: white; border: 1px solid #dbe2ee; border-radius: 12px; box-shadow: 0 8px 26px rgba(79, 70, 229, .08); }
.study-reading-settings-panel label { display: grid; gap: 12px; margin-bottom: 12px; }
.study-reading-settings-panel input { width: 100%; accent-color: var(--lz-brand); }
.study-reading-settings-panel [role=group] { display: flex; gap: 8px; }
.study-reading-settings-panel button[aria-pressed=true] { background: var(--lz-brand-soft); color: var(--lz-brand-strong); }
.study-eyebrow { font-size: 15px; color: #7b6ca4; font-weight: 650; letter-spacing: .09em; }
.study-error { flex: none; padding: 10px 28px; background: #fff1f1; color: #a14253; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.study-error button { padding: 5px 12px; color: inherit; }
.study-workspace { flex: 1; min-height: 0; min-width: 0; display: flex; overflow: hidden; border-radius: 16px; }
.study-workspace.is-library { background: #f5f6f8; }
.study-navigation { box-sizing: border-box; width: var(--column-left-width); flex: none; min-width: 0; padding: 12px; display: flex; flex-direction: column; border: 1px solid #e3e8f2; border-radius: 16px; background: rgba(255, 255, 255, .94); overflow: auto; overflow-wrap: anywhere; }
.study-directory-heading { display: flex; align-items: center; gap: 9px; min-height: 40px; padding: 4px 6px 12px; color: var(--lz-text-strong); }
.study-directory-heading > svg { color: var(--lz-brand-strong); }
.study-directory-heading button { margin-left: auto; padding: 4px; border: 0; background: transparent; }
.study-chapter-search { flex: none; margin-bottom: 20px; }

.study-chapter-list { display: grid; gap: 4px; }
.study-chapter-list button { justify-content: flex-start; align-items: start; width: 100%; border: 0; border-radius: 8px; background: transparent; text-align: start; line-height: 1.65; padding: 10px; }
.study-chapter-list button.active { background: #eef2ff; color: var(--lz-brand-strong); }
.study-chapter-number { flex: none; color: var(--lz-text-muted); font-size: 15px; }
.study-nav-hint { color: #8890a1; padding: 0 10px; font-size: 15px; }
.study-create-steps { display: grid; gap: 8px; padding: 6px 14px; }
.study-create-steps a { padding: 10px 0; color: var(--lz-text-secondary); }
.study-create-steps a:hover { color: var(--lz-brand-strong); }
.study-main-scroll { flex: 1; min-width: 0; overflow: auto; }
.study-reading-workspace { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; border-radius: 16px; overflow: hidden; background: white; }
.study-reading-body { display: flex; flex: 1; min-width: 0; min-height: 0; }
.study-reading-pane { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: white; }
.study-selection-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 8px 20px; background: #eef2ff; color: var(--lz-brand-strong); font: 15px/1.6 var(--handout-sans); }
.study-selection-actions span { flex: 1; }
.study-selection-actions button { padding: 4px 8px; }
.study-document-scroll { min-height: 0; flex: 1; overflow: auto; scroll-behavior: smooth; }
.study-handout { box-sizing: border-box; max-width: 890px; margin: auto; min-width: 0; padding: 35px 54px 64px; color: #303440; font: var(--study-reading-size, 18px)/1.95 var(--study-reading-font, var(--handout-serif)); }
.study-handout :deep(.handout-block) { font-size: var(--study-reading-size, 18px); font-family: var(--study-reading-font, var(--handout-serif)); }
.study-handout-section { scroll-margin-top: 24px; }
.study-handout-section + .study-handout-section { padding-top: 32px; margin-top: 48px; border-top: 1px solid #ededf2; }
.study-section-kicker { font: 15px/1.6 var(--handout-sans); color: #9096a5; }
.study-handout-section h2 { font: 650 27px/1.5 var(--study-ui-font); margin: 10px 0 28px; letter-spacing: -.02em; }
.study-handout-section > div[id] { min-width: 0; scroll-margin-top: 24px; }
.study-progress { border: 1px solid #dcd4ed; background: #faf7ff; padding: 17px 20px; font: 15px/1.8 var(--handout-sans); margin-bottom: 24px; display: flex; flex-direction: column; gap: 12px; }
.study-progress progress { width: 100%; height: 5px; accent-color: #8066c6; }
.study-progress button { align-self: flex-start; }
.study-draft { border-top: 1px dashed #d3d8e6; padding: 15px 0; }
.study-draft > span { font: 15px/1.6 var(--handout-sans); color: #8792a5; }
.study-end { display: flex; gap: 9px; justify-content: center; align-items: center; color: #8698a0; font: 15px/1.8 var(--handout-sans); padding-top: 30px; border-top: 1px solid #e3e8ee; margin-top: 35px; }
.study-reading-tools { box-sizing: border-box; width: var(--column-right-width); flex: none; display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: auto; background: white; border-left: 1px solid #e3e8f2; }
.study-reading-tools:has(.personal-assistant) { overflow: hidden; }
.study-tool-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 18px; border-bottom: 1px solid #e3e8f2; flex: none; }
.study-note { padding: 20px; display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 16px; }
.study-note > p { color: var(--lz-text-muted); font-size: 15px; margin: 0; }
.study-note-editor { flex: 1; min-height: 100px; }
.study-note-editor :deep(.el-textarea__inner) { height: 100%; }

.study-note-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex: none; padding-top: 12px; border-top: 1px solid #efedf4; }
.study-note-status { color: var(--lz-text-muted); font-size: 15px; }
.study-note-footer button { flex: none; }
.study-space :deep(.el-button + .el-button) { margin-left: 0; }
.study-source-list { padding: 20px; }
.study-source-list article { padding: 16px 0; border-bottom: 1px solid #e3e8f2; }
.study-source-list strong { font-size: 15px; display: block; margin: 8px 0; overflow-wrap: anywhere; }
.study-source-list p { font-size: 15px; color: #7e899b; margin: 7px 0; }
.study-reading-tools :deep(.handout-concept-map) { position: static; border: 0; max-height: none; overflow: visible; }
.study-reading-tools :deep(.concept-eyebrow) { font-size: 15px; }
.study-reading-workspace .learning-dock { font-family: var(--study-ui-font); }
.study-reading-workspace .learning-dock :deep(button) { font-family: inherit; font-weight: 600; border-color: transparent; background: transparent; padding: 7px 10px; }
.study-reading-workspace .learning-dock :deep(button.is-active), .study-reading-workspace .learning-dock :deep(button:hover) { background: var(--lz-brand-soft); color: var(--lz-brand-strong); }
@media (max-width: 1200px) { .study-handout { padding: 32px 34px 60px; } .study-header { padding: 8px 14px; gap: 12px; } .study-header-actions { gap: 4px; } }
@media (max-width: 1100px) { .study-header-actions .study-user { display: none; } }

.study-login-page { flex: 1; overflow: auto; display: grid; grid-template-columns: minmax(0,570px) 410px; justify-content: center; align-items: center; gap: 90px; padding: 45px; }
.login-story h1 { font-size: 40px; line-height: 1.3; letter-spacing: -.02em; margin: 15px 0 20px; }
.login-story>p { font-size: 18px; color: #748399; margin-bottom: 35px; }
.login-purpose { display: flex; gap: 18px; margin-top: 25px; padding: 20px 0; border-top: 1px solid #dfe3f0; }
.login-purpose svg { color: #7662bd; margin-top: 7px; flex: none; }
.login-purpose h3 { font-size: 18px; margin: 0 0 6px; }
.login-purpose p { margin: 0; color: #718096; }
.study-login-card { padding: 36px; background: white; border: 1px solid #e2e5ef; border-radius: 22px; box-shadow: 0 16px 50px #58688910; }
.study-login-card h2 { font-size: 25px; margin: 12px 0; }
.study-login-card>p { color: #7b889c; margin-bottom: 25px; }
.study-login-card .study-primary { width: 100%; margin-top: 14px; }
.study-login-card .study-text-button { display: flex; margin: 17px auto 0; border: 0; color: #6551c7; }
.study-page-heading { display: flex; align-items: center; justify-content: space-between; gap: 25px; margin-bottom: 34px; }
.study-page-heading h1 { font-size: 30px; margin: 8px 0 10px; }
.study-page-heading p { color: #7a889c; margin: 0; }
.study-form-section { background: #fff; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-surface); padding: 26px 28px; margin: 22px 0; }
.study-form-section h2 { font-size: 20px; margin: 0 0 10px; }
.study-form-section>p { margin: 0 0 22px; color: #7b879b; }
.study-space :is(.study-create, .study-login-card) label:not(.source-selection):not(.study-upload) { display: flex; flex-direction: column; gap: 9px; margin-bottom: 18px; font-weight: 550; }
.study-space :is(.study-create, .study-login-card) input:not([type=checkbox]):not([type=file]),.study-space :is(.study-create, .study-login-card) textarea,.study-space :is(.study-create, .study-login-card) select { width: 100%; min-width: 0; border: 1px solid #d7deeb; border-radius: 9px; background: #fcfdff; padding: 11px 13px; color: #33455f; box-sizing: border-box; }
.study-source-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 22px; }
.study-upload { position: relative; display: flex; align-items: center; gap: 9px; border: 1px solid #c9c0eb; background: #f7f4ff; color: #6952b5; padding: 9px 14px; border-radius: 10px; cursor: pointer; }
.study-upload input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.study-source-actions>span { font-size: 15px; color: #8a94a6; }
.study-paste { padding: 20px; background: #f7f8fc; border-radius: 12px; margin-bottom: 20px; }
.study-source { padding: 16px 0; border-top: 1px solid #e7e9f1; }
.source-name { display: flex; align-items: center; gap: 9px; color: #576783; margin-bottom: 13px; flex-wrap: wrap; }
.source-name>span { margin-left: auto; font-size: 15px; color: #8591a2; }
.source-selection { display: flex; align-items: center; gap: 12px; padding: 9px 10px; margin: 2px 0; border-radius: 8px; background: #fafbfe; cursor: pointer; }
.source-selection input { width: 17px; height: 17px; accent-color: #755fc0; }
.source-selection small { margin-left: auto; color: #8a95a5; font-size: 15px; }
.source-warning { color: #a47548; font-size: 15px; }
.study-purpose-options { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 20px; }
.study-purpose-options button { position: relative; display: flex; flex-direction: column; align-items: flex-start; text-align: left; padding: 21px; border: 1px solid #e1e5ef; background: #fcfcff; gap: 12px; align-content: start; border-radius: var(--lz-radius-control); }
.study-purpose-options button.selected { border-color: var(--lz-brand); background: var(--lz-brand-soft); }
.study-purpose-options strong { font-size: 18px; color: #3c4260; }
.study-purpose-options span { color: #7d849c; font-size: 15px; font-weight: 400; }
.purpose-check { position: absolute; right: 18px; top: 23px; color: #7761bc; }
.study-settings-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.study-generate-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; color: #8190a3; flex-wrap: wrap; gap: 16px; }
.study-upload-input { display: none; }
.study-create { width: 100%; max-width: 980px; margin: 0 auto; padding: 28px; box-sizing: border-box; }
.study-create .study-page-heading p { max-width: 740px; color: var(--lz-text-secondary); font-size: 15px; line-height: 1.7; margin: 10px 0 0; }
.study-purpose-options button > span { font-size: 15px; line-height: 1.7; color: var(--lz-text-secondary); }
.study-range-recovery { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--lz-text-secondary); font-size: 15px; }
.study-generation-issue { color: var(--lz-brand-strong) !important; }
.study-range-hint { color: var(--lz-text-secondary); font-size: 15px; margin-top: 14px; }
.study-generate-bar > div { flex: 1; min-width: 220px; color: var(--lz-text); font-size: 15px; }
.study-generate-bar p { margin: 6px 0 0; font-size: 15px; line-height: 1.6; color: var(--lz-text-secondary); }
.study-generate-bar button { flex: none; }
.study-create-steps { display: grid; gap: 8px; padding: 6px 14px; }
.study-create-steps a { padding: 10px 0; color: var(--lz-text-secondary); text-decoration: none; font-size: 15px; line-height: 1.6; }
.study-create-steps a:hover { color: var(--lz-brand-strong); }
@media(max-width:1200px) { .study-login-page { gap:40px; } }
@media(max-width:980px) { .study-login-page { grid-template-columns:minmax(0,1fr) 350px; gap:30px; padding:30px; } .login-story h1 { font-size:31px; } .study-purpose-options { gap:12px; } }
</style>
