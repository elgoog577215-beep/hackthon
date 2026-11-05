<template>
  <div class="study-space" :class="{ 'is-reading-page': !!materialId, 'is-creating-page': creating }">
    <ApplicationHeader surface="student" :show-brand="!materialId" :centered="!materialId && !creating" :library="!materialId" :compact-actions="!!materialId && mobileViewport">
      <template v-if="materialId" #context>
        <div class="study-course-context">
          <CourseWorkspaceHeaderAction :label="t('workspaceUi.backToCourses')" icon-only @click="goLibrary"><ArrowLeft :size="18" /></CourseWorkspaceHeaderAction>
          <CourseWorkspaceHeaderAction v-if="!directoryOpen" :label="c('showDirectory')" :icon-only="mobileViewport" :display-label="t('workspaceUi.directory')" @click="openDirectory"><PanelLeftOpen :size="18" /></CourseWorkspaceHeaderAction>
          <h1>{{ material?.title }}</h1>
        </div>
      </template>
      <template v-if="user && !materialId && !creating" #center>
        <UiSegmentedControl class="study-home-navigation" :model-value="creating ? '' : 'courses'" :options="[{ value: 'courses', label: t('workspaceUi.myCourses'), icon: BookOpen }]" :accessibility-label="t('studentWorkspace.space')" @update:model-value="openStudySection('home')" />
        <h1 class="study-home-mobile-title">{{ t('workspaceUi.myCourses') }}</h1>
      </template>
      <template #actions>
        <div class="study-header-actions">
          <template v-if="materialId">
            <CourseWorkspaceHeaderAction v-if="currentRevision?.sections.length" :label="c('export')" @click="exportHandout"><Download :size="17" /></CourseWorkspaceHeaderAction>
            <details class="study-reading-settings" @keydown.esc="closeReadingSettings">
              <summary><Settings2 :size="17" />{{ c('readingSettings') }}</summary>
              <div class="study-reading-settings-panel">
                <label>{{ c('fontSize') }} · {{ readingFontSize }}<input v-model.number="readingFontSize" type="range" min="16" max="22" :aria-label="c('fontSize')" /></label>
                <UiSegmentedControl :model-value="readingFont" :options="[{ value: 'serif', label: c('serifFont') }, { value: 'sans', label: c('sansFont') }]" :accessibility-label="c('readingSettings')" @update:model-value="setReadingFont" />
              </div>
            </details>
          </template>
          <CourseWorkspaceHeaderAction :label="activeLocale === 'zh' ? 'English' : '中文'" :display-label="activeLocale === 'zh' ? 'EN' : '中文'" @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')" />
          <span v-if="user && !developmentMode" class="study-user" :title="user.guest ? c('guestHint') : undefined"><UserRound :size="17" />{{ user.guest ? c('guestSpace') : user.username }}</span>
          <CourseWorkspaceHeaderAction v-if="user && !developmentMode && !user.guest" :label="c('logout')" @click="logout" />
        </div>
      </template>
    </ApplicationHeader>
    <div v-if="error" class="study-error" role="alert">{{ !user && (!authConfigLoaded || guestMode || developmentMode) ? c('connectionFailed') : error }}<button @click="reconnect">{{ c('retry') }}</button></div>

    <div v-if="!draftStorageAvailable" class="study-error" role="status">{{ c('draftStorageUnavailable') }}</div>

    <main v-if="!user && (connecting || guestMode || developmentMode || !authConfigLoaded)" class="study-login-page">
      <p v-if="!error" role="status">{{ c('openingSpace') }}</p>
    </main>
    <main v-else-if="!user" class="study-login-page">
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

    <div v-else ref="studyLayoutRoot" class="study-workspace" :class="{ 'is-reading': !!materialId, 'is-library': !materialId && !creating, 'is-tools-open': toolsOpen }" :style="columnLayoutStyle">
      <button v-if="materialId && directoryOpen" type="button" class="study-mobile-backdrop study-directory-backdrop" :aria-label="c('hideDirectory')" @click="closeDirectory" />
      <aside v-if="materialId && directoryOpen" class="study-navigation">
          <header class="study-directory-heading"><BookOpen :size="18" /><strong>{{ t('workspaceUi.directory') }}</strong><button type="button" :aria-label="c('hideDirectory')" @click="closeDirectory"><PanelLeftClose :size="17" /></button></header>
          <ElInput v-model="chapterQuery" class="study-chapter-search" size="large" type="search" clearable :placeholder="c('searchChapters')" :aria-label="c('searchChapters')"><template #prefix><Search :size="16" /></template></ElInput>
          <nav class="study-chapter-list" :aria-label="t('workspaceUi.directory')">
            <div v-for="section in filteredReadingSections" :key="section.id" class="study-chapter-entry">
              <div class="study-chapter-row" :class="{ 'is-current': activeChapter === section.id }">
                <button type="button" class="study-chapter-link" :aria-current="activeChapter === section.id ? 'location' : undefined" @click="selectChapter(section.id)"><span class="study-chapter-number">{{ String(section.number).padStart(2, '0') }}</span><span class="study-chapter-title">{{ section.title }}</span></button>
                <button v-if="section.blocks.length" type="button" class="study-chapter-toggle" :aria-label="`${activeLocale === 'zh' ? (sectionExpanded(section.id) ? '收起' : '展开') : (sectionExpanded(section.id) ? 'Collapse' : 'Expand')} ${section.title}`" :aria-expanded="sectionExpanded(section.id)" :aria-controls="`study-directory-${section.id}`" @click="toggleSection(section.id)"><ChevronRight :size="16" :class="{ 'is-open': sectionExpanded(section.id) }" /></button>
              </div>
              <div v-if="sectionExpanded(section.id)" :id="`study-directory-${section.id}`" class="study-block-list">
                <button v-for="block in section.blocks" :key="block.id" type="button" :class="{ active: activeBlock === block.id }" :aria-current="activeBlock === block.id ? 'location' : undefined" @click="jumpToAnchor(block.anchor)"><span v-if="block.presentation.label" class="study-block-tag" :style="block.presentation.style">{{ block.presentation.label }}</span><span>{{ block.title }}</span></button>
              </div>
            </div>
          </nav>
          <p v-if="!filteredReadingSections.length" class="study-nav-hint">{{ readingSections.length ? c('noChapterMatches') : t('workspaceUi.noContents') }}</p>
      </aside>

      <ColumnResizeHandle v-if="materialId && directoryOpen && !mobileViewport" v-bind="leftColumnHandle" />
      <section v-if="!materialId" class="study-main-scroll">
        <StudentLearningHome v-if="!creating" ref="authorizedCourses" :key="user.id" :class="{ 'study-library': route.query.view === 'materials' }" :user-id="user.id" :materials="library" :initial-filter="route.query.view === 'courses' ? 'teacher' : route.query.view === 'materials' ? 'owned' : 'all'" @create="startNew" @source="createFromCourse" @filter="setCourseFilter" />
        <form v-else class="study-create" @submit.prevent="generate">
          <div class="study-page-heading"><button type="button" class="study-create-back" :aria-label="t('workspaceUi.backToCourses')" @click="goLibrary"><ArrowLeft :size="18" /><span>{{ t('workspaceUi.backToCourses') }}</span></button><h1>{{ c('create') }}</h1></div>
          <section id="study-create-purpose" class="study-form-section"><h2>{{ c('purposeHeading') }}</h2><div class="study-purpose-options"><button v-for="purpose in purposes" :key="purpose" type="button" :class="{ selected: form.purpose === purpose }" :aria-pressed="form.purpose === purpose" @click="form.purpose = purpose"><Target v-if="purpose === 'exam_prep'" :size="25" /><BookOpen v-else :size="25" /><strong>{{ c(purpose) }}</strong><span>{{ c(purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</span><Check v-if="form.purpose === purpose" class="purpose-check" :size="19" /></button></div><p class="study-purpose-mobile-hint" aria-live="polite">{{ c(form.purpose === 'exam_prep' ? 'examHint' : 'understandingHint') }}</p></section>
          <section id="study-create-settings" class="study-form-section"><h2>{{ c('settingsHeading') }}</h2><label>{{ c('title') }}<ElInput v-model="form.title" required maxlength="160" :placeholder="c('titlePlaceholder')" /></label><label>{{ c('requirements') }}<ElInput v-model="form.requirements" type="textarea" :rows="3" maxlength="2000" :placeholder="c(form.purpose === 'exam_prep' ? 'examRequirementsPlaceholder' : 'requirementsPlaceholder')" /></label><div class="study-settings-row"><label>{{ c('level') }}<select v-model="form.level" :aria-label="c('level')"><option v-for="level in levels" :key="level" :value="level">{{ c(level) }}</option></select></label><label>{{ c('time') }}<input v-model.number="form.time_minutes" type="number" min="10" max="600" required /></label></div></section>
          <section id="study-create-sources" class="study-form-section"><h2>{{ c('materialsOptionalHeading') }}</h2><p>{{ c('materialsOptionalHint') }}</p>
            <div class="study-source-actions"><input ref="sourceFileInput" class="study-upload-input" type="file" :accept="STUDY_UPLOAD_ACCEPT" :disabled="sourceBusy || busy" multiple @change="uploadFiles" /><button type="button" class="study-upload" :disabled="sourceBusy || busy" @click="sourceFileInput?.click()"><Upload :size="19" />{{ sourceBusy ? c('busy') : c('upload') }}</button><button type="button" class="study-paste-toggle" :disabled="sourceBusy || busy" :aria-expanded="pasting" @click="pasting = !pasting"><ClipboardPaste :size="18" />{{ c('paste') }}</button><span>{{ c('uploadHint') }}</span></div>
            <div v-if="pasting" class="study-paste"><label>{{ c('sourceTitle') }}<ElInput v-model="sourceTitle" maxlength="160" /></label><label>{{ c('sourceContent') }}<ElInput v-model="sourceText" type="textarea" :rows="8" maxlength="120000" /></label><button type="button" :disabled="sourceBusy || !sourceTitle.trim() || !sourceText.trim()" @click="addText">{{ sourceBusy ? c('busy') : c('addSource') }}</button></div>
            <p v-if="!sources.length && !pasting" class="study-source-empty">{{ c('emptySources') }}</p>
            <div v-for="source in sources" :key="source.id" class="study-source"><div class="source-name"><FileText :size="18" /><strong>{{ source.filename }}</strong><span>{{ source.sections.length }} · {{ c('sourceRanges') }}</span></div><p v-if="!source.sections.length" class="source-warning">{{ source.error || c('sourceFailed') }}</p><p v-for="warning in source.warnings" :key="warning" class="source-warning">{{ warning }}</p><label v-for="section in source.sections" :key="section.id" class="source-selection"><input v-model="selectedRanges" type="checkbox" :value="`${source.id}:${section.id}`" :disabled="!section.characters" /><span>{{ section.title }}</span><small>{{ section.characters.toLocaleString() }}</small></label></div>

            <div v-if="hasInvalidRanges && !busy" class="study-range-recovery" role="status"><span>{{ c('invalidRanges') }}</span><button type="button" @click="removeInvalidRanges">{{ c('removeInvalidRanges') }}</button></div>
          </section>
          <div class="study-generate-bar"><div><strong>{{ selectedRanges.length ? `${selectedRanges.length} ${c('scope')}` : c('directReady') }}</strong><p v-if="generationIssue && !busy && !sourceBusy" id="study-generation-issue" class="study-generation-issue" role="status">{{ c(generationIssue) }}</p></div><button class="study-primary" :aria-describedby="generationIssue ? 'study-generation-issue' : undefined" :disabled="busy || sourceBusy || !canGenerate">{{ busy ? c('busy') : c('generate') }}<ArrowRight :size="19" /></button></div>
        </form>
      </section>

      <template v-else>
        <div class="study-reading-workspace">
          <div class="study-reading-body">
            <div class="study-reading-pane" :inert="mobileViewport && (toolsOpen || directoryOpen)">
              <div v-if="selectedPassage" class="study-selection-actions"><span>{{ c('selectedQuote') }} · {{ selectedPassage.block_title || selectedPassage.section_title }}</span><button @pointerdown.prevent @click="openTool('assistant')">{{ c('askSelection') }}</button><button @click="selectedPassage = null">{{ c('clearQuote') }}</button></div>
              <div v-if="material" ref="readingTarget" class="study-document-scroll" @scroll="followChapter" @toggle.capture="followChapter" @pointerup="selectPassage" @keyup="selectPassage">
                <article class="study-handout" :style="readingStyle">
                  <div v-if="materialStatus !== 'completed'" class="study-progress" role="status"><span>{{ ['failed', 'paused'].includes(materialStatus) ? c('interrupted') : c('running') }}</span><progress v-if="isGenerating" :value="material.task?.phase_progress ?? material.task?.progress ?? 0" max="100" /><button v-if="['failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c('continue') }}</button></div>
                  <HandoutReadingGuide compact v-if="currentRevision?.sections.length" :target="readingTarget" :title="material.title" />

                  <section v-for="section in currentRevision?.sections || []" :id="sectionAnchor(section.id)" :data-section-id="section.id" :key="section.id" class="study-handout-section"><div class="study-section-kicker">{{ section.source?.kind === 'ai_generated' ? c('directMode') : section.source?.filename || '' }}</div><h2>{{ section.title }}</h2><div v-for="block in section.blocks" :id="blockAnchor(block.block_id)" :data-block-id="block.block_id" :key="block.block_id"><HandoutContentBlock :content-type="block.content_type" :label="block.type_label" :title="block.title" :answer-to="block.answer_to" :streaming="!section.complete"><MarkdownRenderer :content="block.content" smooth-stream :animate-initial="newBlockIds.has(block.block_id)" :node-id="block.block_id" /></HandoutContentBlock></div><div v-if="section.fragment" class="study-draft"><span>{{ c('draft') }}</span><MarkdownRenderer :content="section.fragment" smooth-stream /></div></section>

                </article>
              </div>
            </div>
            <ColumnResizeHandle v-if="material && toolsOpen && !mobileViewport" v-bind="rightColumnHandle" />
            <button v-if="material && toolsOpen" type="button" class="study-mobile-backdrop study-tools-backdrop" :aria-label="t('common.close')" @click="closeTool" />
            <aside v-if="material" v-show="toolsOpen" class="study-reading-tools">
              <header class="study-tool-heading"><strong>{{ c(toolTab) }}</strong><ElButton text circle :aria-label="t('common.close')" @click="closeTool"><X :size="18" /></ElButton></header>
              <PersonalHandoutAssistant v-if="toolTab === 'assistant' && currentRevision" :key="`${user.id}:${material.id}:${currentRevision.id}`" :owner-id="user.id" :material-id="material.id" :revision-id="currentRevision.id" :context="assistantContext" @clear-quote="selectedPassage = null" @session-expired="showError" />
              <div v-else-if="toolTab === 'note'" class="study-note"><ElInput v-model="noteText" class="study-note-editor" type="textarea" :rows="16" resize="none" :placeholder="c('notePlaceholder')" :aria-label="c('note')" /><footer class="study-note-footer"><div class="study-note-status" role="status">{{ noteDirty ? c('noteUnsaved') : noteSaved ? c('noteSaved') : '' }}</div><ElButton type="primary" :disabled="busy || !noteDirty" @click="saveNote">{{ c('saveNote') }}</ElButton></footer></div>
              <div v-else-if="toolTab === 'sources'" class="study-source-list"><article v-for="source in selectedSourceScopes" :key="source.node_id"><FileText :size="18" /><strong>{{ source.filename }}</strong><p>{{ source.title }}</p><button :disabled="busy" @click="downloadSource(source.asset_id, source.filename)">{{ c('downloadSource') }}</button></article><p v-if="!selectedSourceScopes.length" class="study-note">{{ material.generation_mode === 'direct' ? c('aiGeneratedSourceHint') : c('emptySources') }}</p></div>
              <KeepAlive :key="`${user.id}:${material.id}:${currentRevision?.id}`" :max="1">
                <HandoutReferencePanel v-if="toolTab === 'reference'" :sections="currentRevision?.sections || []" :current-section="activeChapter" @jump="jumpToReference" />
              </KeepAlive>
              <div v-if="toolTab === 'concepts'">
                <div v-if="!conceptsReady" class="study-note" role="status">
                  <p>{{ isGenerating ? c('preparingConcepts') : c('missingConcepts') }}</p>
                  <ElButton v-if="!isGenerating && ['completed', 'failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c('completeConcepts') }}</ElButton>
                </div>
                <HandoutConceptMap v-if="conceptSections.some(section => section.nodes.length)" :sections="conceptSections" :target="readingTarget" :origin-label="c('conceptOrigin')" :navigate="jumpToAnchor" />
              </div>
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
import { captureReadingPosition, restoreReadingPosition } from '../utils/reading-position'
import { createUuid } from '../utils/client-id'
import { ElButton, ElInput } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, BookOpen, Check, ClipboardPaste, Download, FileText, Target, Upload, UserRound, X, NotebookPen, Network, MessageCircle, PanelLeftClose, PanelLeftOpen, Search, Settings2, Sigma, ChevronRight } from 'lucide-vue-next'
import { handoutPresentation } from '../utils/handout-content'
import LearningDock from '../components/LearningDock.vue'
import HandoutContentBlock from '../components/HandoutContentBlock.vue'
import HandoutReadingGuide from '../components/HandoutReadingGuide.vue'
import HandoutReferencePanel from '../components/HandoutReferencePanel.vue'
import HandoutConceptMap from '../components/HandoutConceptMap.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import PersonalHandoutAssistant from '../components/PersonalHandoutAssistant.vue'
import { studyApi, studySession, StudyApiError, STUDY_UPLOAD_ACCEPT, type StudyMaterial, type StudyPurpose, type StudySource, type StudySummary, type StudyUser } from '../api/study'
import { activeLocale, setLocale, t } from '../shared/i18n'
import ApplicationHeader from '../components/ApplicationHeader.vue'
import CourseWorkspaceHeaderAction from '../components/CourseWorkspaceHeaderAction.vue'
import UiSegmentedControl from '../components/UiSegmentedControl.vue'
import { studyCopy as c, type StudyCopyKey } from '../shared/study-copy'
import StudentLearningHome from '../components/StudentLearningHome.vue'
import { setStudyIdentity } from '../utils/study-identity'
import { buildHandoutConceptSections } from '../utils/handout-concepts'
import { clearQizhiAccessToken, isQizhiAuthRequired, redirectToQizhiLogin } from '../utils/http'
import ColumnResizeHandle from '../components/ColumnResizeHandle.vue'
import { useResizableColumns } from '../composables/useResizableColumns'

const router = useRouter(), route = useRoute()
const developmentMode = ref(false)
const guestMode = ref(false), connecting = ref(true), authConfigLoaded = ref(false)
const user = ref<StudyUser | null>(null), localLoginEnabled = ref(false), qizhiAuth = isQizhiAuthRequired()
const username = ref(''), password = ref(''), registerMode = ref(false), busy = ref(false), sourceBusy = ref(false), error = ref('')
const library = ref<StudySummary[]>([]), sources = ref<StudySource[]>([]), material = ref<StudyMaterial | null>(null)
const currentRevision = computed(() => material.value?.revisions.at(-1))
const draftStorageAvailable = ref(true)
const creating = ref(false), pasting = ref(false), sourceTitle = ref(''), sourceText = ref(''), selectedRanges = ref<string[]>([])
const form = reactive({ title: '', purpose: 'systematic' as StudyPurpose, level: 'beginner', time_minutes: 60, requirements: '' })
const purposes: StudyPurpose[] = ['systematic', 'exam_prep'], levels = ['beginner', 'intermediate', 'advanced'] as const
const sourceFileInput = ref<HTMLInputElement | null>(null)
const availableRanges = computed(() => new Set(sources.value.flatMap(source => source.sections.filter(section => section.characters > 0).map(section => `${source.id}:${section.id}`))))
const hasInvalidRanges = computed(() => new Set(selectedRanges.value).size !== selectedRanges.value.length || selectedRanges.value.some(range => !availableRanges.value.has(range)))
const generationIssue = computed<StudyCopyKey | ''>(() => {
  if (hasInvalidRanges.value) return 'invalidRanges'
  if (!form.title.trim()) return 'titleRequired'
  if (!Number.isInteger(form.time_minutes) || form.time_minutes < 10 || form.time_minutes > 600) return 'timeInvalid'
  return ''
})
const canGenerate = computed(() => !generationIssue.value)
function removeInvalidRanges() { selectedRanges.value = [...new Set(selectedRanges.value.filter(range => availableRanges.value.has(range)))] }
const toolTabs = ['note', 'assistant', 'reference', 'concepts', 'sources'] as const
type StudyTool = typeof toolTabs[number]
const toolTab = ref<StudyTool>('assistant'), toolsOpen = ref(false)
const toolIcons = { assistant: MessageCircle, note: NotebookPen, concepts: Network, sources: FileText, reference: Sigma }
function toolPreferenceKey() { return `lingzhi-study-tools:${user.value?.id}:${materialId.value}` }
function rememberTool() {
  try { sessionStorage.setItem(toolPreferenceKey(), JSON.stringify({ tab: toolTab.value, open: toolsOpen.value })) } catch { /* Optional layout preference. */ }
}
function openTool(tab: StudyTool) { mobileDirectoryOpen.value = false; toolTab.value = tab; toolsOpen.value = true; rememberTool() }
function closeTool() {
  const restoreFocus = studyLayoutRoot.value?.querySelector('.study-reading-tools')?.contains(document.activeElement)
  toolsOpen.value = false; rememberTool()
  if (restoreFocus && !navigating) void nextTick(() => studyLayoutRoot.value?.querySelector<HTMLButtonElement>(`[data-tool="${toolTab.value}"]`)?.focus())
}
function toggleTool(tab: StudyTool) { if (toolsOpen.value && toolTab.value === tab) closeTool(); else openTool(tab) }
function restoreTool() {
  toolTab.value = 'assistant'; toolsOpen.value = false
  try {
    const stored = JSON.parse(sessionStorage.getItem(toolPreferenceKey()) || 'null')
    if (stored && toolTabs.includes(stored.tab)) { toolTab.value = stored.tab; toolsOpen.value = stored.open === true && !mobileViewport.value }
  } catch { /* A damaged preference never blocks reading. */ }
}
const activeChapter = ref(''), activeBlock = ref(''), selectedPassage = ref<{ section_id: string; section_title: string; block_id: string; block_title: string; quote: string } | null>(null)
const assistantContext = computed(() => {
  if (selectedPassage.value) return selectedPassage.value
  const section = currentRevision.value?.sections.find(s => s.id === activeChapter.value) || currentRevision.value?.sections[0]
  return { section_id: section?.id || '', section_title: section?.title || '', block_id: '', block_title: '', quote: '' }
})
function readingPositionKey() { return `lingzhi-study-position:${user.value?.id}:${material.value?.id}:${currentRevision.value?.id}` }
let lastReadingPosition: { key: string; value: ReturnType<typeof captureReadingPosition> } | null = null
let reflowing = false, viewportSequence = 0
function followChapter() {
  const root = readingTarget.value
  if (!root || !currentRevision.value || reflowing) return
  const position = captureReadingPosition(root)
  lastReadingPosition = { key: readingPositionKey(), value: position }
  activeChapter.value = position.sectionId
  activeBlock.value = position.blockId
  try { sessionStorage.setItem(readingPositionKey(), JSON.stringify(position)) } catch { /* Reading works without storage. */ }
}
function restorePosition() {
  const root = readingTarget.value
  if (!root) return
  try {
    const saved = sessionStorage.getItem(readingPositionKey())
    if (saved) restoreReadingPosition(root, saved)
  } catch { /* Invalid or unavailable storage never prevents reading. */ }
  followChapter()
}
let navigating = false
async function jumpToAnchor(anchor: string) {
  navigating = true
  try {
    if (mobileViewport.value) { closeTool(); closeDirectory() }
    await nextTick()
    const root = readingTarget.value
    const target = Array.from(root?.querySelectorAll<HTMLElement>('[id]') || []).find(node => node.id === anchor)
    if (!root || !target) return
    if (target.dataset.blockId) target.querySelectorAll<HTMLDetailsElement>('details.handout-block--answer').forEach(details => { details.open = true })
    root.scrollTo({ top: root.scrollTop + target.getBoundingClientRect().top - root.getBoundingClientRect().top - 24, behavior: 'instant' })
    target.tabIndex = -1
    target.focus({ preventScroll: true })
    target.classList.remove('study-jump-target')
    void target.offsetWidth
    target.classList.add('study-jump-target')
    followChapter()
  } finally { navigating = false }
}
function jumpToReference(blockId: string) { return jumpToAnchor(blockAnchor(blockId)) }
function selectChapter(id: string) { expandedChapters.value[id] = true; return jumpToAnchor(sectionAnchor(id)) }
function selectPassage() {
  const selection = window.getSelection(), root = readingTarget.value
  if (!selection || !root || selection.isCollapsed || !selection.rangeCount) return
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return
  const start = range.startContainer.nodeType === 1 ? range.startContainer as Element : range.startContainer.parentElement
  const end = range.endContainer.nodeType === 1 ? range.endContainer as Element : range.endContainer.parentElement
  const sid = start?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId
  if (!sid || sid !== end?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId) return
  const section = currentRevision.value?.sections.find(s => s.id === sid)
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
const viewportWidth = ref(window.innerWidth)
const mobileViewport = computed(() => viewportWidth.value <= 760)
const compactViewport = computed(() => viewportWidth.value <= 1280)
const desktopDirectoryOpen = ref(true), mobileDirectoryOpen = ref(false), chapterQuery = ref('')
const expandedChapters = ref<Record<string, boolean>>({})
function sectionExpanded(id: string) { return expandedChapters.value[id] ?? (Boolean(chapterQuery.value.trim()) || activeChapter.value === id) }
watch(chapterQuery, () => { expandedChapters.value = {} })
function toggleSection(id: string) { expandedChapters.value[id] = !sectionExpanded(id) }
const directoryOpen = computed(() => mobileViewport.value ? mobileDirectoryOpen.value : desktopDirectoryOpen.value && !(compactViewport.value && toolsOpen.value))
function openDirectory() {
  if (compactViewport.value) closeTool()
  if (mobileViewport.value) mobileDirectoryOpen.value = true
  else desktopDirectoryOpen.value = true
  void nextTick(() => studyLayoutRoot.value?.querySelector<HTMLButtonElement>('.study-directory-heading button')?.focus())
}
function closeDirectory() {
  const restoreFocus = studyLayoutRoot.value?.querySelector('.study-navigation')?.contains(document.activeElement)
  if (mobileViewport.value) mobileDirectoryOpen.value = false
  else desktopDirectoryOpen.value = false
  if (restoreFocus && !navigating) void nextTick(() => studyLayoutRoot.value?.closest('.study-space')?.querySelector<HTMLButtonElement>('.study-course-context button:not(.is-icon-only)')?.focus())
}
async function updateViewport() {
  const root = readingTarget.value, sequence = ++viewportSequence, key = readingPositionKey()
  const position = lastReadingPosition?.key === readingPositionKey() ? lastReadingPosition.value : null
  reflowing = true
  const wasMobile = mobileViewport.value
  viewportWidth.value = window.innerWidth
  if (wasMobile !== mobileViewport.value) mobileDirectoryOpen.value = false
  await nextTick()
  if (sequence !== viewportSequence) return
  if (root && readingTarget.value === root && key === readingPositionKey() && position) restoreReadingPosition(root, JSON.stringify(position))
  reflowing = false
  followChapter()
}
function closePanels(event: KeyboardEvent) {
  if (event.key === 'Tab' && mobileViewport.value && directoryOpen.value) {
    const controls = Array.from(studyLayoutRoot.value?.querySelectorAll<HTMLElement>('.study-navigation button, .study-navigation input') || []).filter(node => node.getClientRects().length)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    return
  }
  if (event.key !== 'Escape') return
  if (mobileDirectoryOpen.value) closeDirectory()
  else if (toolsOpen.value) closeTool()
}
const readingFontSize = ref(18), readingFont = ref<'serif' | 'sans'>('serif')
const readingStyle = computed(() => ({
  '--study-reading-size': `${readingFontSize.value}px`,
  '--study-reading-font': readingFont.value === 'serif' ? 'var(--handout-serif)' : 'var(--handout-sans)',
}))
function setReadingFont(value: string) { if (value === 'serif' || value === 'sans') readingFont.value = value }
function closeReadingSettings(event: KeyboardEvent) {
  const details = event.currentTarget as HTMLDetailsElement
  details.open = false
  details.querySelector('summary')?.focus()
}
watch(materialId, () => { chapterQuery.value = ''; expandedChapters.value = {}; mobileDirectoryOpen.value = false })
watch(() => user.value?.id, owner => {
  readingFontSize.value = 18; readingFont.value = 'serif'
  if (!owner) return
  try {
    const saved = JSON.parse(localStorage.getItem(`lingzhi-study-reading:${owner}`) || 'null')
    if (saved && Number.isFinite(saved.size) && saved.size >= 16 && saved.size <= 22) readingFontSize.value = saved.size
    if (saved?.font === 'sans') readingFont.value = 'sans'
  } catch { /* Optional reading preference. */ }
})
watch([readingFontSize, readingFont], () => {
  if (!user.value) return
  try { localStorage.setItem(`lingzhi-study-reading:${user.value.id}`, JSON.stringify({ size: readingFontSize.value, font: readingFont.value })) } catch { /* Optional reading preference. */ }
})
// Preserve the visible passage when columns or typography reflow the document.
watch([directoryOpen, toolsOpen, readingFontSize, readingFont], async () => {
  const root = readingTarget.value
  if (!root || navigating || reflowing) return
  const position = captureReadingPosition(root), key = readingPositionKey()
  await nextTick()
  if (readingTarget.value === root && key === readingPositionKey() && !navigating && !reflowing) { restoreReadingPosition(root, JSON.stringify(position)); followChapter() }
})
const { layoutStyle: columnLayoutStyle, leftHandle: leftColumnHandle, rightHandle: rightColumnHandle } = useResizableColumns(studyLayoutRoot, {
  enabled: () => !mobileViewport.value, centerMin: 560,
  storageKey: 'lingzhi:personal-study:columns', left: 272, right: 350, leftMin: 230, rightMin: 280,
  leftVisible: () => Boolean(materialId.value && directoryOpen.value),
  rightVisible: () => Boolean(materialId.value && material.value && toolsOpen.value),
})
const materialStatus = computed(() => material.value?.task?.status || material.value?.status || 'pending')
const isGenerating = computed(() => ['pending', 'running'].includes(materialStatus.value))
const sectionAnchor = (id: string) => `study-${materialId.value}-${id}`
const blockAnchor = (id: string) => `study-${materialId.value}-${id}`
const readingSections = computed(() => (currentRevision.value?.sections || []).map(section => ({ id: section.id, title: section.title, anchor: sectionAnchor(section.id), blocks: section.blocks.map(block => ({ id: block.block_id, title: block.title, anchor: blockAnchor(block.block_id), content: block.content, presentation: handoutPresentation(block.content_type, activeLocale.value, block.type_label), knowledge: block.knowledge_names })) })))
const filteredReadingSections = computed(() => {
  const query = chapterQuery.value.trim().toLocaleLowerCase()
  return readingSections.value.map((section, index) => ({ ...section, number: index + 1 }))
    .filter(section => section.title.toLocaleLowerCase().includes(query) || section.blocks.some(block => (block.title + ' ' + block.presentation.label).toLocaleLowerCase().includes(query)))
})
const conceptSections = computed(() => buildHandoutConceptSections(material.value?.plans || [], readingSections.value))
const conceptsReady = computed(() => material.value?.concepts_complete ?? (conceptSections.value.length > 0 && conceptSections.value.every(section => section.nodes.length > 0)))
const selectedSourceScopes = computed(() => material.value?.sources || [])
let timer: ReturnType<typeof setTimeout> | undefined, requestId = createUuid(), submittedFingerprint = '', disposed = false, epoch = 0, actionSequence = 0, librarySequence = 0
const draftKey = () => `lingzhi-study-draft:${user.value?.id || ''}`
const noteKey = () => `lingzhi-study-note:${user.value?.id}:${material.value?.id}:${currentRevision.value?.id}`

function showError(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : c('requestFailure')
  if (cause instanceof StudyApiError && cause.status === 401) { persistDraft(); epoch++; user.value = null; clearPrivateUi(); clearTimeout(timer) }
}
function clearPrivateUi() { librarySequence++; material.value = null; library.value = []; sources.value = []; selectedRanges.value = []; sourceText.value = ''; sourceTitle.value = ''; noteText.value = ''; savedNote.value = ''; creating.value = false; pasting.value = false; sourceBusy.value = false; selectedPassage.value = null; activeChapter.value = ''; Object.assign(form, { title: '', purpose: 'systematic', level: 'beginner', time_minutes: 60, requirements: '' }) }
const sameOwner = (owner: string | undefined) => !disposed && user.value?.id === owner
async function action(operation: () => Promise<void>) { const owner = user.value?.id, sequence = ++actionSequence; busy.value = true; error.value = ''; try { await operation() } catch (cause) { if (!disposed && (!owner || sameOwner(owner))) showError(cause) } finally { if (sequence === actionSequence) busy.value = false } }
function saveBrowserDraft(key: string, value: string) {
  try { sessionStorage.setItem(key, value); draftStorageAvailable.value = true }
  catch { draftStorageAvailable.value = false }
}
function readBrowserDraft(key: string) {
  try { return sessionStorage.getItem(key) }
  catch { draftStorageAvailable.value = false; return null }
}
function persistDraft() { if (user.value) saveBrowserDraft(draftKey(), JSON.stringify({ form, selectedRanges: selectedRanges.value, sourceTitle: sourceTitle.value, sourceText: sourceText.value, requestId, submittedFingerprint })) }
function restoreDraft() { try { const draft = JSON.parse(readBrowserDraft(draftKey()) || '{}'); const savedForm = { ...(draft.form || {}) }; delete savedForm.generation_mode; Object.assign(form, savedForm); selectedRanges.value = draft.selectedRanges || []; sourceTitle.value = draft.sourceTitle || ''; sourceText.value = draft.sourceText || ''; requestId = draft.requestId || createUuid(); submittedFingerprint = draft.submittedFingerprint || '' } catch { /* An invalid UI draft does not affect saved materials. */ } }
watch([form, selectedRanges, sourceTitle, sourceText], persistDraft, { deep: true })
watch(noteText, () => { if (material.value && user.value) saveBrowserDraft(noteKey(), noteText.value) }, { flush: 'sync' })

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
  connecting.value = true
  authConfigLoaded.value = false
  try {
    const config = await studyApi.config()
    authConfigLoaded.value = true
    localLoginEnabled.value = config.local_login_enabled
    developmentMode.value = config.development_identity === true
    guestMode.value = config.guest_login_enabled === true && !qizhiAuth && !developmentMode.value
    if (guestMode.value) {
      const result = await studyApi.guest()
      studySession.set(result.token)
      user.value = result.user
    } else {
      if (!studySession.get() && !qizhiAuth && !developmentMode.value) return
      user.value = await studyApi.me()
    }
    setStudyIdentity(user.value); restoreDraft(); creating.value = !materialId.value && route.query.create === '1'
    await Promise.all([loadLibrary(), openMaterial()])
  } finally { connecting.value = false }
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
  const owner = user.value?.id
  sourceBusy.value = true; error.value = ''
  const failures: string[] = []
  try {
    for (const file of files) {
      try {
        const source = await studyApi.upload(file)
        if (!sameOwner(owner)) return
        rememberSource(source)
        if (!source.sections.length) failures.push(`${file.name}：${source.error || c('sourceFailed')}`)
      } catch (cause) {
        if (!sameOwner(owner)) return
        if (cause instanceof StudyApiError && cause.status === 401) { showError(cause); return }
        failures.push(`${file.name}：${cause instanceof Error ? cause.message : c('requestFailure')}`)
      }
    }
    if (sameOwner(owner) && failures.length) error.value = failures.join('；')
  } finally { if (sameOwner(owner)) sourceBusy.value = false; input.value = '' }
}
async function generate() {
  if (busy.value || sourceBusy.value) return
  if (generationIssue.value) { error.value = c(generationIssue.value); return }
  await action(async () => {
    const owner = user.value?.id
    const payload = { ...form, title: form.title.trim(), language: activeLocale.value, selections: selectedRanges.value.map(range => { const [asset_id, section_id] = range.split(':'); return { asset_id: asset_id!, section_id: section_id! } }) }
    const fingerprint = JSON.stringify(payload)
    if (submittedFingerprint && submittedFingerprint !== fingerprint) requestId = createUuid()
    submittedFingerprint = fingerprint; persistDraft()
    const result = await studyApi.generate({ ...payload, request_id: requestId })
    if (!sameOwner(owner)) return
    requestId = createUuid(); submittedFingerprint = ''; persistDraft(); creating.value = false; await router.push(`/study/${result.id}`); await loadLibrary()
  })
}
const newBlockIds = ref(new Set<string>())
async function openMaterial() {
  clearTimeout(timer); const id = materialId.value, current = ++epoch
  const retainedRevision = material.value?.id === id ? currentRevision.value?.id : undefined
  if (!retainedRevision) {
    newBlockIds.value.clear(); material.value = null; noteText.value = ''; savedNote.value = ''; noteSaved.value = false
    activeChapter.value = ''; selectedPassage.value = null; restoreTool()
  }
  if (!id || !user.value) return
  async function refresh(first = false) {
    try {
      const result = await studyApi.get(id)
      if (disposed || current !== epoch || materialId.value !== id || !user.value) return
      const previousRevision = currentRevision.value?.id
      const previousBlocks = new Set(currentRevision.value?.sections.flatMap(section => section.blocks.map(block => block.block_id)) || [])
      material.value = result
      if (previousRevision !== currentRevision.value?.id) newBlockIds.value.clear()
      else if (!first) for (const section of currentRevision.value?.sections || []) {
        for (const block of section.blocks) if (!previousBlocks.has(block.block_id)) newBlockIds.value.add(block.block_id)
      }
      if (first && !retainedRevision) {
        await nextTick()
        if (disposed || current !== epoch || materialId.value !== id) return
        restorePosition()
      }
      if (previousRevision !== currentRevision.value?.id && currentRevision.value) {
        selectedPassage.value = null
        if (!readingSections.value.some(section => section.id === activeChapter.value)) activeChapter.value = readingSections.value[0]?.id || ''
        const draft = readBrowserDraft(noteKey())
        savedNote.value = result.notes[currentRevision.value.id]?.content || ''
        noteText.value = draft ?? savedNote.value
        noteSaved.value = false
      }
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
async function saveNote() { await action(async () => { const owner = user.value?.id, id = materialId.value, revision = currentRevision.value!.id, content = noteText.value; await studyApi.note(id, revision, content); if (sameOwner(owner) && id === materialId.value && currentRevision.value?.id === revision) { savedNote.value = content; noteSaved.value = true } }) }
function download(blob: Blob, filename: string) { const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) }
async function exportHandout() { await action(async () => { const owner = user.value?.id, title = material.value!.title, blob = await studyApi.export(materialId.value); if (sameOwner(owner)) download(blob, `${title}.md`) }) }
async function downloadSource(id: string, filename: string) { await action(async () => { const owner = user.value?.id, blob = await studyApi.downloadSource(id); if (sameOwner(owner)) download(blob, filename) }) }
onBeforeRouteUpdate(() => { followChapter() })
onBeforeRouteLeave(() => { followChapter(); persistDraft() })
onMounted(() => { window.addEventListener('resize', updateViewport); window.addEventListener('keydown', closePanels); void action(connect) })
onBeforeUnmount(() => { followChapter(); window.removeEventListener('resize', updateViewport); window.removeEventListener('keydown', closePanels); disposed = true; epoch++; clearTimeout(timer); persistDraft() })
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
.study-space button.study-mobile-backdrop { display: none; }
.study-space button, .study-space a { transition: background .15s, color .15s; }
.study-space button:where(:not(.el-button, .workspace-header-action)) {
  cursor: pointer; min-height: 36px; border: 1px solid var(--lz-action-border);
  border-radius: 8px; background: #fff; color: var(--lz-text-secondary);
  padding: 8px 12px; display: inline-flex; justify-content: center; align-items: center; gap: 8px;
}
.study-space button:where(:not(.el-button, .workspace-header-action)):hover:not(:disabled) { background: var(--lz-brand-soft); color: var(--lz-brand-strong); }
.study-space button:where(:not(.el-button, .workspace-header-action)):disabled { cursor: default; opacity: .55; }
.study-space :is(button:where(:not(.el-button, .workspace-header-action)), a, select, summary, input[type=range]):focus-visible { outline: 2px solid var(--lz-action-focus); outline-offset: 3px; }
.study-space a { text-decoration: none; color: inherit; }
.study-space .study-primary { background: var(--lz-action-primary-bg); color: var(--lz-action-primary-text); font-weight: 600; border-color: var(--lz-action-primary-border); }
.study-space .study-primary:hover:not(:disabled) { background: var(--lz-action-primary-hover); color: var(--lz-action-primary-text); }
.study-header-actions { display: flex; align-items: center; flex: none; gap: 10px; }
.study-user { display: flex; align-items: center; gap: 7px; color: #7c8496; }
.study-course-context { display: flex; align-items: center; gap: 10px; min-width: 0; }
.study-course-context h1 { margin: 0; font-size: 18px; font-weight: 650; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.study-course-context > svg { flex: none; color: var(--lz-brand); }
.study-reading-settings { position: relative; }
.study-reading-settings summary { display: flex; align-items: center; gap: 8px; padding: 6px 8px; cursor: pointer; list-style: none; white-space: nowrap; }
.study-reading-settings summary::-webkit-details-marker { display: none; }
.study-reading-settings-panel { position: absolute; right: 0; top: calc(100% + 14px); z-index: 30; width: 240px; padding: 20px; background: white; border: 1px solid #dbe2ee; border-radius: 12px; box-shadow: 0 8px 26px rgba(79, 70, 229, .08); }
.study-reading-settings-panel label { display: grid; gap: 12px; margin-bottom: 12px; }
.study-reading-settings-panel input { width: 100%; accent-color: var(--lz-brand); }
.study-eyebrow { font-size: 15px; color: #7b6ca4; font-weight: 650; letter-spacing: .09em; }
.study-error { flex: none; padding: 10px 28px; background: #fff1f1; color: #a14253; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.study-error button { padding: 5px 12px; color: inherit; }
.study-workspace { flex: 1; min-height: 0; min-width: 0; display: flex; overflow: hidden; border-radius: 16px; }
.study-workspace.is-library { background: #f5f6f8; }
.study-navigation { box-sizing: border-box; width: var(--column-left-width); flex: none; min-width: 0; padding: 14px 10px 10px; display: flex; flex-direction: column; border: 1px solid #e4e7ef; border-radius: 12px; background: linear-gradient(180deg,#fff,#fafbfe); overflow: hidden; }
.study-directory-heading { display: flex; align-items: center; gap: 9px; min-height: 36px; padding: 0 8px 12px; color: #41495c; font-size: 15px; }
.study-directory-heading > svg { color: #7873ad; }
.study-directory-heading button { margin-left: auto; width: 34px; height: 34px; padding: 0; display: grid; place-items: center; border: 0; background: transparent; color: #9299a9; }
.study-chapter-search { flex: none; margin-bottom: 12px; }
.study-chapter-search :deep(.el-input__wrapper) { min-height: 38px; background: #f5f6fa; box-shadow: 0 0 0 1px #e7e9f0 inset; border-radius: 8px; }
.study-chapter-search :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #a39ace inset; background: white; }
.study-chapter-list { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: #d9dce8 transparent; padding: 2px; }
.study-chapter-entry { margin-bottom: 6px; }
.study-chapter-row { position: relative; display: flex; align-items: stretch; border-radius: 10px; transition: background .15s ease; }
.study-chapter-row:hover { background: #f2f3f9; }
.study-chapter-row.is-current { background: linear-gradient(105deg,#f7f7fd,#efedf9); }
.study-chapter-row.is-current::before { content: ''; position: absolute; left: 0; top: 16px; bottom: 16px; width: 3px; border-radius: 3px; background: #7b70bd; }
.study-space .study-chapter-link { flex: 1; min-width: 0; display: flex; align-items: center; justify-content: flex-start; gap: 10px; min-height: 58px; border: 0; padding: 10px 4px 10px 10px; background: transparent; text-align: left; }
.study-chapter-title { min-width: 0; font-size: 15px; font-weight: 600; line-height: 1.55; color: #495165; overflow-wrap: anywhere; }
.is-current .study-chapter-title { color: #574b9b; }
.study-chapter-number { flex: none; display: grid; place-items: center; width: 30px; height: 32px; border: 1px solid #e6e6f0; border-radius: 8px; background: #fff; color: #969bb1; font-size: 13px; font-weight: 550; font-variant-numeric: tabular-nums; }
.is-current .study-chapter-number { color: #fff; border-color: transparent; background: #7b70bd; box-shadow: 0 2px 5px #7561a51a; }
.study-space .study-chapter-toggle { display: grid; place-items: center; flex: none; width: 32px; min-height: 44px; padding: 0; border: 0; background: transparent; color: #9298a9; }
.study-chapter-toggle svg { transition: transform .15s ease; }
.study-chapter-toggle svg.is-open { transform: rotate(90deg); }
.study-block-tag { display:inline-block; vertical-align:1px; margin-right:6px; padding:0 4px; border-radius:3px; color:var(--handout-accent); background:var(--handout-tint); font-size:12px; font-weight:500; line-height:20px; }
.study-block-list { margin: 6px 5px 12px 25px; padding-left: 12px; border-left: 1px dashed #d8dcea; }
.study-space .study-block-list button { position: relative; display: block; width: 100%; min-height: 38px; border: 0; border-radius: 7px; padding: 8px 9px; background: transparent; text-align: left; color: #788196; font-size: 14px; font-weight: 400; line-height: 1.55; overflow-wrap: anywhere; }
.study-space .study-block-list button:hover { background: #f0f1f7; color: #4d5267; }
.study-space .study-block-list button.active { color: #6254a7; background: #efedf7; font-weight: 550; }
.study-nav-hint { color: #8890a1; padding: 0 10px; font-size: 15px; }
.study-main-scroll { flex: 1; min-width: 0; overflow: auto; }
.study-reading-workspace { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; border: 1px solid #e5e7ee; border-radius: 12px; overflow: hidden; background: white; }
.study-reading-body { display: flex; flex: 1; min-width: 0; min-height: 0; }
.study-reading-pane { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: white; }
.study-selection-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 8px 20px; background: #eef2ff; color: var(--lz-brand-strong); font: 15px/1.6 var(--handout-sans); }
.study-selection-actions span { flex: 1; }
.study-selection-actions button { padding: 4px 8px; }
.study-document-scroll { min-height: 0; flex: 1; overflow: auto; scroll-behavior: smooth; }
.study-handout :deep(.code-block-wrapper) { border-radius:8px; border:0; box-shadow:none; }
.study-handout :deep(.markdown-code-tools) { padding:6px 10px 0; }
.study-handout :deep(.markdown-code-tools .copy-btn) { min-height:28px; border-radius:5px; padding:3px 7px; font-size:13px; }
.study-handout :deep(pre) { padding:10px 14px 14px; border-radius:0; }
.study-handout { box-sizing: border-box; max-width: 890px; margin: auto; min-width: 0; padding: 28px clamp(24px, 3vw, 48px) 64px; color: #303440; font: var(--study-reading-size, 18px)/1.95 var(--study-reading-font, var(--handout-serif)); }
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
.study-reading-tools { box-sizing: border-box; width: var(--column-right-width); flex: none; display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: auto; background: white; border-left: 1px solid #e3e8f2; }
.study-reading-tools:has(.personal-assistant), .study-reading-tools:has(.handout-reference) { overflow: hidden; }
.study-tool-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 56px; box-sizing: border-box; padding: 10px 18px; border-bottom: 1px solid #e9ebf1; background: #fafbfe; flex: none; font-size: 15px; }
.study-note { padding: 20px; display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 16px; }
.study-note > p { color: var(--lz-text-muted); font-size: 15px; margin: 0; }
.study-note-editor { flex: 1; min-height: 100px; }
.study-note-editor :deep(.el-textarea__inner) { height: 100%; padding: 14px; line-height: 1.85; border-radius: 10px; box-shadow: 0 0 0 1px #e5e7ef inset; background: #fcfcfe; }

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
.study-jump-target { animation: study-jump 1.5s ease-out; outline: none; }
@keyframes study-jump { from { box-shadow: inset 3px 0 var(--lz-brand); background: var(--lz-brand-soft); } to { box-shadow: inset 3px 0 transparent; background: transparent; } }
@media (prefers-reduced-motion: reduce) { .study-jump-target { animation: none; outline: 2px solid var(--lz-brand-soft); } }
.study-space.is-reading-page { padding: 14px; gap: 12px; background: #f5f6fa; }
.is-reading-page :deep(.app-header), .is-creating-page :deep(.app-header) { min-height: 56px; border: 1px solid #e5e7ee; border-radius: 12px; background: #fff; box-shadow: none; backdrop-filter: none; }
.is-reading-page :deep(.workspace-header-action) { box-shadow: none; }
.study-reading-workspace .learning-dock.is-toolbar.is-bottom { min-height: 58px; background: #fcfcfe; border-color: #e9ebf2; box-shadow: none; padding: 8px 14px; }
.study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(.learning-dock__actions) { gap: 6px; }
.study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(button) { font-size: 15px; font-weight: 600; min-height: 40px; border-radius: 8px; }
@media (max-width: 1280px) { .study-reading-workspace .learning-dock :deep(.learning-dock__location) { display: none; } }
@media (max-width: 1200px) { .study-handout { padding: 32px 34px 60px; } .study-header-actions { gap: 4px; } }
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
.study-page-heading { display: flex; align-items: center; justify-content: flex-start; gap: 14px; margin-bottom: 34px; }
.study-page-heading h1 { font-size: 30px; margin: 0; }
.study-create-back { display: inline-flex; align-items: center; justify-content: center; flex: none; gap: 7px; min-height: 44px; padding: 0 8px; border: 0; border-radius: 9px; background: transparent; color: var(--lz-text-secondary); font-size: 15px; font-weight: 550; cursor: pointer; }
.study-create-back:hover { background: var(--lz-brand-soft); color: var(--lz-brand-strong); }
.study-page-heading p { color: #7a889c; margin: 0; }
.study-form-section { padding:26px 0 0; margin:26px 0; border:0; border-top:1px solid #e2e6ed; border-radius:0; background:transparent; }
#study-create-purpose { border-top:0; padding-top:0; }
.study-form-section h2 { font-size: 18px; font-weight:600; margin: 0 0 10px; }
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
.study-purpose-options button { position: relative; display: grid; grid-template-columns:25px minmax(0,1fr); align-items: center; text-align: left; padding:16px; border: 1px solid #e1e5ef; background: #fcfcff; gap: 12px; align-content: start; border-radius: var(--lz-radius-control); }
.study-purpose-options button.selected { border-color: var(--lz-brand); background: var(--lz-brand-soft); }
.study-purpose-options strong { padding-right:22px; font-size:16px; font-weight:600; color: #3c4260; }
.study-purpose-options span { color: #7d849c; font-size: 15px; font-weight: 400; }
.purpose-check { position: absolute; right: 18px; top: 23px; color: #7761bc; }
.study-settings-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.study-generate-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; color: #8190a3; flex-wrap: wrap; gap: 16px; }
.study-upload-input { display: none; }
.is-creating-page { background:#f8f9fc; }
.study-create :deep(.el-input__wrapper) { min-height:44px; box-sizing:border-box; border-radius:8px; }
.study-create :deep(.el-input__inner), .study-create :deep(.el-textarea__inner) { font-weight:400; font-size:15px; }
.study-create :deep(input::placeholder), .study-create :deep(textarea::placeholder) { color:#758095; }
.study-create { width: 100%; max-width: 980px; margin: 0 auto; padding: 28px; box-sizing: border-box; }
.study-create .study-page-heading p { max-width: 740px; color: var(--lz-text-secondary); font-size: 15px; line-height: 1.7; margin: 10px 0 0; }
.study-purpose-options button > span { grid-column:1 / -1; font-size:14px; line-height: 1.7; color: var(--lz-text-secondary); }
.study-purpose-mobile-hint { display: none; }
.study-range-recovery { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--lz-text-secondary); font-size: 15px; }
.study-generation-issue { color: var(--lz-brand-strong) !important; }
.study-range-hint { color: var(--lz-text-secondary); font-size: 15px; margin-top: 14px; }
.study-generate-bar > div { flex: 1; min-width: 220px; color: var(--lz-text); font-size: 15px; }
.study-generate-bar p { margin: 6px 0 0; font-size: 15px; line-height: 1.6; color: var(--lz-text-secondary); }
.study-generate-bar button { flex: none; }
@media(max-width:1200px) { .study-login-page { gap:40px; } }
@media(max-width:980px) { .study-login-page { grid-template-columns:minmax(0,1fr) 350px; gap:30px; padding:30px; } .login-story h1 { font-size:31px; } .study-purpose-options { gap:12px; } }

.study-home-navigation { --ui-segment-font-size: 15px; width: max-content; margin: 0 auto; }
.study-home-mobile-title { display: none; margin: 0; color: var(--lz-text-strong); font-size: 16px; font-weight: 650; line-height: 1.3; }

@media (max-width: 760px) {
  .study-space, .study-space.is-reading-page { padding: max(6px, env(safe-area-inset-top, 0px)) max(6px, env(safe-area-inset-right, 0px)) 0 max(6px, env(safe-area-inset-left, 0px)); gap: 7px; }
  .study-home-navigation { display: none; }
  .study-home-mobile-title { display: block; }
  .study-error { padding: 8px 12px; font-size: 14px; }
  .study-error button { min-height: 40px; }
  .study-space :deep(.app-header:has(.study-course-context)) { grid-template-columns: minmax(0,1fr) auto; min-height: 52px; gap: 4px; padding: 0 4px; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools) { grid-column: 2; }
  .study-course-context { gap: 2px; }
  .study-course-context h1 { flex: 1; min-width: 0; max-width: none; font-size: 15px; }
  .study-course-context :deep(.workspace-header-action) { min-height: 44px; padding-inline: 6px; }
  .study-header-actions { flex-wrap: wrap; justify-content: flex-start; gap: 8px; }
  .study-header-actions :deep(.workspace-header-action) { min-height: 44px; }
  .study-reading-settings summary { min-height: 44px; }
  .study-reading-settings-panel { position: static; width: 100%; padding: 12px 0; border: 0; box-shadow: none; box-sizing: border-box; }
  .study-reading-settings[open] { width: 100%; }
  .study-workspace { border-radius: 12px; }
  .study-workspace.is-reading { position: relative; overflow: hidden; }
  .study-space button.study-mobile-backdrop { display: block; position: fixed; inset: 0; z-index: 95; width: 100%; height: 100%; min-height: 0; padding: 0; border: 0; border-radius: 0; background: rgb(20 28 48 / 42%); cursor: default; }
  .study-space button.study-mobile-backdrop:hover { background: rgb(20 28 48 / 42%); }
  .study-navigation { position: fixed; z-index: 96; inset: max(8px, env(safe-area-inset-top)) 8px max(8px, env(safe-area-inset-bottom)); width: auto; max-height: none; padding: 16px 14px; border: 1px solid #e3e8f2; border-radius: 16px; box-shadow: 0 18px 56px rgb(21 31 55 / 22%); }
  .study-directory-heading { flex: none; min-height: 48px; padding: 0 4px 10px; }
  .study-directory-heading button { min-width: 44px; min-height: 44px; }
  .study-chapter-search { margin-bottom: 12px; }
  .study-chapter-list { min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .study-space .study-chapter-link { min-height: 60px; }
  .study-space .study-chapter-toggle { width: 44px; }
  .study-space .study-block-list button { min-height: 44px; padding: 10px; font-size: 15px; }
  .study-reading-workspace { border-radius: 12px; }
  .study-reading-body { min-height: 0; }
  .study-document-scroll { overscroll-behavior: contain; scroll-padding-block: 18px; }
  .study-handout { padding: 12px 17px 34px; font-size: var(--study-reading-size, 18px); line-height: 1.85; }
  .study-handout-section + .study-handout-section { padding-top: 24px; margin-top: 32px; }
  .study-handout-section h2 { margin: 8px 0 20px; font-size: 23px; line-height: 1.42; }
  .study-selection-actions { gap: 6px; padding: 8px 10px; }
  .study-selection-actions span { flex-basis: 100%; }
  .study-selection-actions button { min-height: 42px; }
  .study-space button.study-tools-backdrop { z-index: 91; }
  .study-reading-tools { position: fixed; z-index: 92; inset: auto 8px calc(66px + env(safe-area-inset-bottom)); width: auto; height: min(70dvh, 720px); max-height: calc(100dvh - 88px - env(safe-area-inset-top) - env(safe-area-inset-bottom)); border: 1px solid #e3e8f2; border-radius: 16px 16px 12px 12px; box-shadow: 0 18px 56px rgb(21 31 55 / 22%); }
  .study-tool-heading { min-height: 52px; padding: 7px 12px; }
  .study-tool-heading :deep(.el-button) { width: 42px; height: 42px; }
  .study-note { padding: 12px; }
  .study-note-footer { align-items: start; flex-direction: column; }
  .study-note-footer button { align-self: stretch; min-height: 44px; }
  .study-source-list { overflow: auto; padding: 14px; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom { position: sticky; z-index: 93; bottom: 0; min-height: 62px; flex-wrap: nowrap; padding: 4px 6px calc(4px + env(safe-area-inset-bottom)); border-top: 1px solid #e1e5f0; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(.learning-dock__actions) { width: 100%; display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); justify-content: stretch; align-items: stretch; gap: 2px; margin: 0; overflow: visible; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(button) { box-sizing: border-box; width: 100%; min-width: 0; min-height: 54px; padding: 4px 1px; display: flex; flex-direction: column; justify-content: center; gap: 3px; border-radius: 9px; font-size: 11px; line-height: 1.2; white-space: normal; }
  .study-reading-workspace .learning-dock :deep(button > svg) { flex: none; width: 19px; height: 19px; }
  .study-login-page { grid-template-columns: minmax(0, 1fr); align-content: start; gap: 12px; padding: 18px 14px 28px; }
  .login-story h1 { margin: 8px 0 12px; font-size: 30px; }
  .login-story > p { margin-bottom: 18px; font-size: 16px; }
  .login-purpose { gap: 12px; margin-top: 12px; padding: 13px 0; }
  .login-purpose svg { width: 22px; height: 22px; }
  .login-purpose h3 { font-size: 16px; }
  .login-purpose p { font-size: 14px; line-height: 1.5; }
  .study-login-card { padding: 22px 18px; border-radius: 16px; }
  .study-login-card h2 { font-size: 22px; }
  .study-login-card :is(input, button) { min-height: 44px; }
  .study-create { padding: 14px 12px 24px; }
  .study-page-heading { justify-content: flex-start; gap: 10px; margin-bottom: 12px; }
  .study-page-heading h1 { margin: 0; font-size: 23px; }
  .study-create-back { min-height: 44px; gap: 5px; padding: 0 2px; font-size: 14px; }
  .study-form-section { padding:20px 0 0; margin:20px 0; border-radius:0; }
  .study-purpose-options { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
  .study-purpose-options button { display:flex; min-height:50px; flex-direction:row; align-items: center; padding: 10px; gap: 8px; }
  .study-purpose-options button > svg:not(.purpose-check) { width: 21px; height: 21px; }
  .study-purpose-options strong { font-size: 15px; }
  .study-purpose-options button > span { display: none; }
  .study-purpose-options .purpose-check { right: 10px; top: 10px; width: 16px; height: 16px; }
  .study-purpose-mobile-hint { display: block; margin: 8px 0 0; color: var(--lz-text-secondary); font-size: 13px; line-height: 1.55; }
  .study-create :deep(.el-input__wrapper) { min-height: 44px; box-sizing: border-box; }
  .study-create :deep(.el-input__inner) { min-height: 24px; }
  .study-create :deep(.el-textarea__inner) { min-height: 92px; }
  .study-create select,.study-create input[type=number] { min-height: 44px; }
  .study-settings-row { gap: 10px; }
  .study-source-actions { gap: 8px; }
  .study-source-actions button { min-height: 44px; }
  .study-source-actions > span { flex-basis: 100%; line-height: 1.5; }
  .study-generate-bar { position: sticky; z-index: 5; bottom: 0; margin: 0 -12px; padding: 10px 12px calc(10px + env(safe-area-inset-bottom)); border-top: 1px solid #e3e8f2; background: rgb(255 255 255 / 96%); backdrop-filter: blur(12px); }
  .study-generate-bar > div { min-width: 0; }
  .study-generate-bar button { min-height: 46px; }
}

@media (max-width: 480px) {
  .study-create .study-page-heading { flex-direction: column; align-items: flex-start; gap: 4px; }
  .study-create .study-create-back { border: 0; background: transparent; }
  .study-generate-bar { flex-direction: column; align-items: stretch; gap: 8px; }
  .study-generate-bar > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
  .study-generate-bar > div p { margin: 0; }
  .study-generate-bar button { justify-content: center; }
}

@media (max-width: 380px) {
  .study-space { padding-inline: 4px; }
  .is-creating-page :deep(.product-brand-copy) { display: none; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools) { overflow-x: auto; scrollbar-width: none; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools::-webkit-scrollbar) { display: none; }
  .study-header-actions :deep(.workspace-header-action) { min-width: 44px; }
  .study-settings-row { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 340px) {
  .study-purpose-options { grid-template-columns: minmax(0, 1fr); }
}
</style>
