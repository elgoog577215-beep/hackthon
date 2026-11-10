<template>
  <div class="study-space" :class="{ 'is-reading-page': !!materialId, 'is-creating-page': creating, 'is-keyboard-open': keyboardOpen && mobileViewport }">
    <ApplicationHeader :inert="mobileViewport && toolsOpen" surface="student" :show-brand="!materialId" :centered="!materialId && !creating" :library="!materialId" :compact-actions="!!materialId && mobileViewport">
      <template v-if="materialId" #context>
        <div class="study-course-context">
          <CourseWorkspaceHeaderAction :label="t('workspaceUi.backToCourses')" icon-only @click="goLibrary"><ArrowLeft :size="18" /></CourseWorkspaceHeaderAction>
          <CourseWorkspaceHeaderAction v-if="!directoryOpen" :label="c('showDirectory')" :icon-only="mobileViewport" :display-label="t('workspaceUi.directory')" @click="openDirectory"><PanelLeftOpen :size="18" /></CourseWorkspaceHeaderAction>
          <h1><MathText :content="material?.title" /></h1>
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
                <button type="button" class="study-chapter-link" :aria-current="activeChapter === section.id ? 'location' : undefined" @click="selectChapter(section.id)"><span class="study-chapter-number">{{ String(section.number).padStart(2, '0') }}</span><MathText class="study-chapter-title" :content="section.title" /></button>
                <button v-if="section.blocks.length" type="button" class="study-chapter-toggle" :aria-label="`${activeLocale === 'zh' ? (sectionExpanded(section.id) ? '收起' : '展开') : (sectionExpanded(section.id) ? 'Collapse' : 'Expand')} ${section.title}`" :aria-expanded="sectionExpanded(section.id)" :aria-controls="`study-directory-${section.id}`" @click="toggleSection(section.id)"><ChevronRight :size="16" :class="{ 'is-open': sectionExpanded(section.id) }" /></button>
              </div>
              <div v-if="sectionExpanded(section.id)" :id="`study-directory-${section.id}`" class="study-block-list">
                <button v-for="block in section.blocks" :key="block.id" type="button" :class="{ active: activeBlock === block.id }" :aria-current="activeBlock === block.id ? 'location' : undefined" @click="jumpToAnchor(block.anchor)"><MathText class="study-block-title" :content="block.title" /><span v-if="block.presentation.label" class="study-block-tag" :title="block.presentation.label" :style="block.presentation.style">{{ block.presentation.label }}</span></button>
              </div>
            </div>
          </nav>
          <p v-if="!filteredReadingSections.length" class="study-nav-hint">{{ readingSections.length ? c('noChapterMatches') : t('workspaceUi.noContents') }}</p>
      </aside>

      <ColumnResizeHandle v-if="materialId && directoryOpen && !mobileViewport" v-bind="leftColumnHandle" />
      <section v-if="!materialId" class="study-main-scroll">
        <StudentLearningHome v-if="!creating" ref="authorizedCourses" :key="user.id" :class="{ 'study-library': route.query.view === 'materials' }" :user-id="user.id" :materials="library" :refreshing="refreshingLibrary" @refresh="refreshLibrary" :initial-filter="route.query.view === 'courses' ? 'teacher' : route.query.view === 'materials' ? 'owned' : 'all'" @create="startNew" @source="createFromCourse" @filter="setCourseFilter" />
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
              <p v-if="material && readingConnection === 'reconnecting'" class="study-connection" role="status">{{ c('readingReconnecting') }}</p>
              <p v-if="!material && ['loading', 'reconnecting'].includes(readingConnection)" class="study-connection" role="status">{{ c(readingConnection === 'loading' ? 'readingLoading' : 'readingReconnecting') }}</p>
              <div class="study-reading-with-reasoning">
              <div v-if="material" ref="readingTarget" class="study-document-scroll" @wheel.passive="navigation.interact" @pointerdown="navigation.interact" @keydown="navigation.interact" @scroll="followChapter" @toggle.capture="followChapter" @pointerup="selectPassage" @keyup="selectPassage">
                <article class="study-handout handout-document" :style="readingStyle">
                  <div v-if="materialStatus !== 'completed' && readingConnection === 'connected'" class="study-progress" role="status"><span>{{ budgetBlocked ? c('generationBudgetExceeded') : ['failed', 'paused'].includes(materialStatus) ? c(material.task?.phase === 'study_concepts' ? 'conceptsInterrupted' : 'interrupted') : c('running') }}</span><progress v-if="isGenerating" :value="material.task?.phase_progress ?? material.task?.progress ?? 0" max="100" /><button v-if="['failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c(budgetBlocked ? 'recheckGeneration' : material.task?.phase === 'study_concepts' ? 'completeConcepts' : 'continue') }}</button></div>
                  <HandoutReadingGuide compact v-if="currentRevision?.sections.length" :target="readingTarget" :title="material.title" />

                  <section v-for="section in currentRevision?.sections || []" :id="sectionAnchor(section.id)" :data-section-id="section.id" :key="section.id" class="study-handout-section">
                    <div class="study-section-kicker">{{ section.source?.kind === 'ai_generated' ? c('directMode') : section.source?.filename || '' }}</div><h2><MathText :content="section.title" /></h2>
                    <div v-for="block in section.blocks" :id="blockAnchor(block.block_id)" :data-block-id="block.block_id" :key="block.block_id">
                      <div class="study-block-content"><HandoutContentBlock :content-type="block.content_type" :label="block.type_label" :title="block.title" :answer-to="block.answer_to" :streaming="!section.complete"><MarkdownRenderer :content="block.content" smooth-stream :animate-initial="newBlockIds.has(block.block_id)" :node-id="block.block_id" /></HandoutContentBlock></div>
                      <div class="study-inline-notes" data-note-controls>

                        <button v-for="note in notesForBlock(block.block_id)" :key="note.id" class="study-inline-note" :class="{ 'is-question': note.question_state === 'open' }" @click="openPersonalNote(note)"><span>{{ c(note.question_state === 'open' ? 'notesOpen' : note.important ? 'notesImportant' : 'notesMyRecord') }}</span><MathText :content="note.content || note.quote" /></button>
                      </div>
                    </div>
                    <div v-if="section.fragment" class="study-draft"><span>{{ c('draft') }}</span><MarkdownRenderer :content="section.fragment" smooth-stream /></div>
                  </section>

                </article>
              </div>

              </div>
            </div>
            <ColumnResizeHandle v-if="material && toolsOpen && !mobileViewport" v-bind="rightColumnHandle" />
            <button v-if="material && toolsOpen" type="button" class="study-mobile-backdrop study-tools-backdrop" :aria-label="t('common.close')" @click="closeTool" />
            <aside ref="studyToolsPanel" v-if="material" v-show="toolsOpen" :role="mobileViewport ? 'dialog' : undefined" :aria-modal="mobileViewport ? true : undefined" :aria-label="c(toolTab)" :tabindex="mobileViewport ? -1 : undefined" class="study-reading-tools" :class="{ 'is-notes': toolTab === 'note' }">
              <header class="study-tool-heading study-tool-tabs" role="tablist" :aria-label="c('readingTools')">
                <button v-for="tab in sideTools" :id="`study-tab-${tab}`" :key="tab" :data-tool="tab" type="button" role="tab" :aria-selected="toolTab === tab" :aria-controls="`study-panel-${tab}`" :tabindex="toolTab === tab ? 0 : -1" @click="openTool(tab)" @keydown="moveToolTab($event, tab)"><component :is="toolIcons[tab]" :size="16" />{{ c(tab === 'paths' ? 'conceptRelations' : tab) }}</button>
                <ElButton text circle class="study-close-tools" :aria-label="c('closeTools')" :title="c('closeTools')" @click="closeTool"><PanelRightClose :size="18" /></ElButton>
              </header>
              <div :id="`study-panel-${toolTab}`" class="study-tool-panel" :role="toolTab === 'note' ? 'region' : 'tabpanel'" :aria-labelledby="toolTab === 'note' ? undefined : `study-tab-${toolTab}`" :aria-label="toolTab === 'note' ? c('note') : undefined">

              <PersonalHandoutAssistant v-if="currentRevision" v-show="toolTab === 'assistant'" :key="`${user.id}:${material.id}:${currentRevision.id}:${noteDiscussion?.note.id || 'handout'}`" :owner-id="user.id" :material-id="material.id" :revision-id="currentRevision.id" :context="assistantContext" :visible="toolTab === 'assistant' && toolsOpen" :note="noteDiscussion?.note" :note-draft="noteDiscussion?.draft" @clear-quote="selectedPassage = null" @session-expired="showError" @save-reply="saveAssistantReply" @note-draft="receiveNoteDraft" @return-note="noteDiscussion && openPersonalNote(noteDiscussion.note)" @clear-note="noteDiscussion = null" />
              <ReadingNotesPanel v-if="toolTab === 'note' && !notesPanel?.editing" :visible="toolsOpen" :reading-root="readingTarget" :external-notes="marginNotes" :location-title="readingLocation" :resolve-rect="personalNoteRect" @open="({ note }) => openMarginNote(note.id)" @locate="note => locateMarginNote(note.id)" />
              <PersonalHandoutNotes v-if="currentRevision" v-show="toolTab === 'note' && notesPanel?.editing" ref="notesPanel" :key="`notes:${user.id}:${material.id}:${currentRevision.id}`" :owner-id="user.id" :material-id="material.id" :revision-id="currentRevision.id" :notes="personalNotes" :sections="currentRevision.sections" :current-section="activeChapter" @saved="acceptPersonalNote" @removed="removePersonalNote" @locate="locatePersonalNote" @discuss="discussPersonalNote" @session-expired="showError">

              </PersonalHandoutNotes>
              <div v-if="toolTab === 'paths' && !hasReasoning" class="study-aid-status" role="status">
                <p>{{ reasoningStatus }}</p>
                <ElButton v-if="!isGenerating && ['completed', 'failed', 'paused'].includes(materialStatus)" :disabled="busy" @click="resume">{{ c(budgetBlocked ? 'recheckGeneration' : 'completeConcepts') }}</ElButton>
              </div>
              <KeepAlive :key="`${user.id}:${material.id}:${currentRevision?.id}`" :max="3">
                <HandoutReferencePanel v-if="toolTab === 'reference'" :sections="currentRevision?.sections || []" :current-section="activeChapter" :current-block="activeBlock" :current-reference="navigationReference" @jump="jumpToReference" />
                <HandoutConceptMap v-else-if="toolTab === 'paths' && hasReasoning" :sections="conceptSections" :current-section="activeChapter" :current-block-anchor="blockAnchor(activeBlock)" :target="readingTarget" :navigate="jumpToAnchor" :origin-label="c('conceptOrigin')" />
              </KeepAlive>
              </div>
            </aside>
          </div>
          <footer v-if="material" class="study-bottom-bar">
            <div class="study-reading-location" :title="readingLocation"><span>{{ c('currentLocation') }}</span><MathText :content="readingLocation" /></div>
            <span v-if="bookmark.status.value !== 'saved'" class="study-bookmark-status" role="status">{{ c(bookmark.status.value === 'conflict' ? 'bookmarkConflict' : bookmark.status.value === 'unavailable' ? 'bookmarkUnavailable' : bookmark.status.value === 'saving' ? 'bookmarkSaving' : 'bookmarkLocal') }}</span>
            <button v-if="!toolsOpen" type="button" data-tool="reopen" @click="openTool(toolTab)"><PanelRightOpen :size="17" />{{ c('readingTools') }}</button>
          </footer>
          <Teleport to="body">
            <div
              v-if="selectedPassage && selectionActionsOpen"
              ref="selectionToolbar"
              class="study-selection-actions"
              :class="{ 'is-below': selectionToolbarPlacement === 'below' }"
              :style="{ top: `${selectionToolbarTop}px`, left: `${selectionToolbarLeft}px` }"
              role="toolbar"
              :aria-label="c('selectionActions')"
              @pointerdown.stop.prevent
            >
              <button data-selection-action="mark" type="button" :aria-label="c('notesMark')" :title="c('notesMark')" @click="markSelection"><Bookmark :size="16" /><span>{{ c('notesMark') }}</span></button>
              <button data-selection-action="annotate" type="button" :aria-label="c('notesAnnotate')" :title="c('notesAnnotate')" @click="annotateSelection(false)"><NotebookPen :size="16" /><span>{{ c('notesAnnotate') }}</span></button>
              <button data-selection-action="question" type="button" :aria-label="c('notesQuestion')" :title="c('notesQuestion')" @click="annotateSelection(true)"><CircleHelp :size="16" /><span>{{ c('notesQuestion') }}</span></button>
              <button data-selection-action="ask" type="button" :aria-label="c('askSelection')" :title="c('askSelection')" @click="askAboutSelection"><MessageCircle :size="16" /><span>{{ c('askSelection') }}</span></button>
              <button data-selection-action="clear" class="study-selection-actions__close" type="button" :aria-label="c('clearQuote')" :title="c('clearQuote')" @click="clearSelection"><X :size="16" /></button>
            </div>
          </Teleport>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStudyBookmark } from '../composables/useStudyBookmark'
import { readRecoveryDelay } from '../utils/read-recovery'
import { useReadingNavigation } from '../composables/useReadingNavigation'
import { captureReadingPosition, restoreReadingPosition } from '../utils/reading-position'
import { createUuid } from '../utils/client-id'
import { ElButton, ElInput } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, BookOpen, Bookmark, Check, CircleHelp, ClipboardPaste, Download, FileText, MessageCircle, NotebookPen, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Route, Search, Settings2, Sigma, Target, Upload, UserRound, X, ChevronRight } from 'lucide-vue-next'
import { handoutPresentation, handoutContentType } from '../utils/handout-content'
import HandoutContentBlock from '../components/HandoutContentBlock.vue'
import HandoutReadingGuide from '../components/HandoutReadingGuide.vue'
import HandoutReferencePanel from '../components/HandoutReferencePanel.vue'
import HandoutConceptMap from '../components/HandoutConceptMap.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import MathText from '../components/MathText.vue'
import PersonalHandoutAssistant from '../components/PersonalHandoutAssistant.vue'
import ReadingNotesPanel from '../components/ReadingNotesPanel.vue'
import type { Note } from '../stores/types'
import PersonalHandoutNotes from '../components/PersonalHandoutNotes.vue'
import { resolveReferenceAnchor } from '../utils/reference-source-anchor'
import { capturePersonalAnchor, resolvePersonalAnchor, highlightPersonalNotes } from '../utils/personal-note-anchor'
import { studyApi, studySession, StudyApiError, STUDY_UPLOAD_ACCEPT, type StudyMaterial, type StudyPurpose, type StudySource, type StudySummary, type StudyUser, type StudyNote, type AssistantMessage, type NoteDraftSuggestion } from '../api/study'
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
const bookmark = useStudyBookmark()
const refreshingLibrary = ref(false), readingConnection = ref<'loading' | 'connected' | 'reconnecting' | 'unavailable'>('loading')
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
const toolTabs = ['note', 'assistant', 'reference', 'paths'] as const
type StudyTool = typeof toolTabs[number]
const toolTab = ref<StudyTool>('assistant'), toolsOpen = ref(false)
const toolIcons = { assistant: MessageCircle, note: NotebookPen, reference: Sigma, paths: Route }
const sideTools = ['assistant', 'reference', 'paths', 'note'] as const
function toolPreferenceKey() { return `lingzhi-study-tools:${user.value?.id}:${materialId.value}` }
function rememberTool() {
  try { localStorage.setItem(toolPreferenceKey(), JSON.stringify({ tab: toolTab.value, open: toolsOpen.value })) } catch { /* Optional layout preference. */ }
}
function openTool(tab: StudyTool) {
  mobileDirectoryOpen.value = false; toolTab.value = tab; toolsOpen.value = true; rememberTool()
  if (mobileViewport.value) void nextTick(() => studyToolsPanel.value?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus())
}
function closeTool() { toolsOpen.value = false; rememberTool(); void nextTick(() => studyLayoutRoot.value?.querySelector<HTMLButtonElement>('[data-tool="reopen"]')?.focus()) }
function moveToolTab(event: KeyboardEvent, tab: typeof sideTools[number]) {
  const index = sideTools.indexOf(tab)
  const next = event.key === 'ArrowRight' ? (index + 1) % sideTools.length : event.key === 'ArrowLeft' ? (index + sideTools.length - 1) % sideTools.length : event.key === 'Home' ? 0 : event.key === 'End' ? sideTools.length - 1 : -1
  if (next < 0) return
  event.preventDefault(); const target = sideTools[next]!
  openTool(target); void nextTick(() => document.getElementById(`study-tab-${target}`)?.focus())
}
function restoreTool() {
  toolTab.value = 'assistant'; toolsOpen.value = !mobileViewport.value
  try {
    const stored = JSON.parse(localStorage.getItem(toolPreferenceKey()) || sessionStorage.getItem(toolPreferenceKey()) || 'null')
    if (stored && toolTabs.includes(stored.tab)) { toolTab.value = stored.tab; toolsOpen.value = !mobileViewport.value && stored.open !== false }
  } catch { /* A damaged preference never blocks reading. */ }
}
const activeChapter = ref(''), activeBlock = ref(''), selectedPassage = ref<{ section_id: string; section_title: string; block_id: string; block_title: string; quote: string; anchor_prefix?: string; anchor_suffix?: string } | null>(null)
const selectionToolbar = ref<HTMLElement | null>(null)
const selectionActionsOpen = ref(false)
const selectionToolbarLeft = ref(0), selectionToolbarTop = ref(0)
const selectionToolbarPlacement = ref<'above' | 'below'>('above')
let activeSelectionRange: Range | null = null
const readingLocation = computed(() => {
  const section = currentRevision.value?.sections.find(s => s.id === activeChapter.value)
  const block = section?.blocks.find(b => b.block_id === activeBlock.value)
  return [section?.title, block?.title].filter(Boolean).join(' › ') || material.value?.title || ''
})
const assistantContext = computed(() => {
  if (noteDiscussion.value) { const n = noteDiscussion.value.note; return { section_id: n.section_id, section_title: n.section_title, block_id: n.block_id, block_title: n.block_title, quote: n.quote } }
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
  if (navigation.owner.value === 'body') {
    const block = currentRevision.value.sections.find(section => section.id === position.sectionId)?.blocks.find(block => block.block_id === position.blockId)
    const references = block?.references || []
    const preceding = references.filter(ref => { const rect = referenceRect(position.blockId, `${position.blockId}:${ref.id}`); return rect && rect.top <= root.getBoundingClientRect().top + 40 })
    navigation.referenceId.value = preceding.length ? `${position.blockId}:${preceding.at(-1)!.id}` : ''
  }
  bookmark.capture(position)
}
function restorePosition() {
  const root = readingTarget.value
  if (!root) return
  try {
    const saved = bookmark.open(user.value!.id, material.value!.id, currentRevision.value!.id,
      material.value?.reading_positions?.[currentRevision.value!.id])
    if (saved) restoreReadingPosition(root, JSON.stringify(saved))
  } catch { /* Invalid or unavailable storage never prevents reading. */ }
  followChapter()
}
let navigating = false
async function jumpToAnchor(anchor: string, options: {referenceId?: string; rect?: () => DOMRect | null} = {}) {
  navigating = true
  try {
    if (mobileViewport.value) { closeTool(); closeDirectory() }
    await navigation.navigate(anchor, options)
  } finally { navigating = false }
}
function referenceRect(blockId: string, referenceId: string) {
  const block = currentRevision.value?.sections.flatMap(section => section.blocks).find(block => block.block_id === blockId)
  const reference = block?.references?.find(ref => `${blockId}:${ref.id}` === referenceId)
  const element = Array.from(readingTarget.value?.querySelectorAll<HTMLElement>('[data-block-id]') || []).find(node => node.dataset.blockId === blockId)?.querySelector<HTMLElement>('.markdown-renderer')
  return block && reference && element ? resolveReferenceAnchor(element, block.content, reference)?.getBoundingClientRect() || null : null
}
function jumpToReference(blockId: string, referenceId = '') { return jumpToAnchor(blockAnchor(blockId), { referenceId, rect: () => referenceRect(blockId, referenceId) }) }
function selectChapter(id: string) { expandedChapters.value[id] = true; return jumpToAnchor(sectionAnchor(id)) }
function selectPassage() {
  const selection = window.getSelection(), root = readingTarget.value
  if (!selection || !root || selection.isCollapsed || !selection.rangeCount) { hideSelectionActions(); return }
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) { hideSelectionActions(); return }
  const start = range.startContainer.nodeType === 1 ? range.startContainer as Element : range.startContainer.parentElement
  const end = range.endContainer.nodeType === 1 ? range.endContainer as Element : range.endContainer.parentElement
  const sid = start?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId
  if (!sid || sid !== end?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId) { hideSelectionActions(); return }
  const section = currentRevision.value?.sections.find(s => s.id === sid)
  const bid = start?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId
  const block = bid === end?.closest<HTMLElement>('[data-block-id]')?.dataset.blockId ? section?.blocks.find(b => b.block_id === bid) : null
  if (start?.closest('[data-note-controls]') || end?.closest('[data-note-controls]')) { hideSelectionActions(); return }
  const quote = selection.toString().trim()
  if (!section || !quote || quote.length > 3000) { hideSelectionActions(); return }
  const contentRoot = start?.closest<HTMLElement>('[data-block-id]')?.querySelector<HTMLElement>('.markdown-renderer, .handout-block__body')
  const anchor = block && contentRoot ? capturePersonalAnchor(contentRoot, range) : { quote }
  noteDiscussion.value = null
  selectedPassage.value = { section_id: sid, section_title: section.title, block_id: block?.block_id || '', block_title: block?.title || '', ...anchor }
  activeSelectionRange = range.cloneRange()
  selectionActionsOpen.value = true
  void nextTick(positionSelectionActions)
}
function hideSelectionActions() { selectionActionsOpen.value = false; activeSelectionRange = null }
function clearSelection() { hideSelectionActions(); selectedPassage.value = null; window.getSelection()?.removeAllRanges() }
function askAboutSelection() { hideSelectionActions(); noteDiscussion.value = null; openTool('assistant') }
function dismissSelectionActionsOutside(event: PointerEvent) {
  if (!selectionActionsOpen.value || selectionToolbar.value?.contains(event.target as Node)) return
  hideSelectionActions()
}
function positionSelectionActions() {
  if (!selectionActionsOpen.value || !activeSelectionRange) return
  let rect: DOMRect
  try { rect = activeSelectionRange.getBoundingClientRect() } catch { hideSelectionActions(); return }
  if ((!rect.width && !rect.height) && activeSelectionRange.getClientRects().length) rect = activeSelectionRange.getClientRects()[0]!
  if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) { hideSelectionActions(); return }
  const toolbar = selectionToolbar.value
  const width = toolbar?.getBoundingClientRect().width || Math.min(window.innerWidth - 16, 430)
  const height = toolbar?.getBoundingClientRect().height || 48
  const gap = 8
  const canPlaceAbove = rect.top >= height + gap + 8
  selectionToolbarPlacement.value = canPlaceAbove ? 'above' : 'below'
  selectionToolbarTop.value = Math.min(Math.max(canPlaceAbove ? rect.top - gap : rect.bottom + gap, 8), window.innerHeight - height - 8)
  selectionToolbarLeft.value = Math.min(Math.max(rect.left + rect.width / 2, width / 2 + 8), window.innerWidth - width / 2 - 8)
}
const notesPanel = ref<InstanceType<typeof PersonalHandoutNotes> | null>(null)
const noteDiscussion = ref<{ note: StudyNote; draft: string } | null>(null)
const personalNotes = computed(() => Object.values(material.value?.notes || {}).flatMap(n => n.entries || []))
const marginNotes = computed<Note[]>(() => personalNotes.value.map(note => ({ id:note.id, nodeId:note.section_id, highlightId:'', quote:note.quote, content:note.content, color:'amber', createdAt:Date.parse(note.created_at) || 0, sourceType:note.source_type === 'ai' ? 'ai' : 'user', syncState:'saved' })))
function personalNoteRect(note: Note) {
  const saved = personalNotes.value.find(n => n.id === note.id)
  if (!saved || saved.location_status !== 'current' || saved.revision_id !== currentRevision.value?.id) return null
  const block = Array.from(readingTarget.value?.querySelectorAll<HTMLElement>('[data-block-id]') || []).find(n => n.dataset.blockId === saved.block_id)?.querySelector<HTMLElement>('.markdown-renderer, .handout-block__body')
  if (!block) return null
  const range = resolvePersonalAnchor(block,saved, { allowUniqueQuote: true })
  return range?.getBoundingClientRect() || null
}
function openMarginNote(id: string) { const note = personalNotes.value.find(n=>n.id===id); if(note) void openPersonalNote(note) }
function locateMarginNote(id: string) { const note = personalNotes.value.find(n=>n.id===id); if(note) void locatePersonalNote(note) }
function notesForBlock(blockId: string) { return personalNotes.value.filter(n => n.revision_id === currentRevision.value?.id && n.block_id === blockId && n.location_status === 'current') }
function acceptPersonalNote(note: StudyNote) {
  if (!material.value) return
  const group = material.value.notes[note.revision_id] || { content: '', updated_at: note.updated_at, entries: [] }
  group.entries = [...(group.entries || []).filter(n => n.id !== note.id), note]
  material.value.notes[note.revision_id] = group
  if (noteDiscussion.value?.note.id === note.id) noteDiscussion.value = { note, draft: note.content }
}
function removePersonalNote(id: string) {
  if (!material.value) return
  for (const group of Object.values(material.value.notes)) group.entries = group.entries?.filter(n => n.id !== id)
  if (noteDiscussion.value?.note.id === id) noteDiscussion.value = null
}
async function annotateSelection(question: boolean) {
  if (!selectedPassage.value) return
  hideSelectionActions()
  openTool('note'); await nextTick()
  notesPanel.value?.create({ ...selectedPassage.value, question_state: question ? 'open' : 'none' })
}
async function markSelection() {
  if (!selectedPassage.value) return
  hideSelectionActions()
  openTool('note'); await nextTick()
  if (!selectedPassage.value.block_id) { notesPanel.value?.create({ ...selectedPassage.value, content: selectedPassage.value.quote }); return }
  notesPanel.value?.create(selectedPassage.value, 'mark')
  await notesPanel.value?.save()
}

async function openPersonalNote(note: StudyNote) { openTool('note'); await nextTick(); notesPanel.value?.open(personalNotes.value.find(n => n.id === note.id) || note) }
function discussPersonalNote(payload: { note: StudyNote; draft: string }) { noteDiscussion.value = payload; hideSelectionActions(); selectedPassage.value = null; openTool('assistant') }
function receiveNoteDraft(value: NoteDraftSuggestion) { notesPanel.value?.receiveSuggestion(value); if (noteDiscussion.value?.note.id === value.noteId) noteDiscussion.value.draft = notesPanel.value?.currentDraft(value.noteId) ?? value.basedOnDraft }
async function saveAssistantReply(message: AssistantMessage) {
  openTool('note'); await nextTick()
  notesPanel.value?.create({ ...message.context_ref, content: message.content, source_message_id: message.message_id })
}
async function locatePersonalNote(note: StudyNote) {
  if (note.location_status !== 'current') return
  await jumpToAnchor(note.block_id ? blockAnchor(note.block_id) : sectionAnchor(note.section_id))
  const root = Array.from(readingTarget.value?.querySelectorAll<HTMLElement>('[data-block-id]') || []).find(n => n.dataset.blockId === note.block_id)?.querySelector<HTMLElement>('.markdown-renderer, .handout-block__body')
  if (root && note.quote) {
    const range = resolvePersonalAnchor(root, note, { allowUniqueQuote: true })
    if (range) { const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range) }
  }
}
function paintPersonalNotes() {
  const ranges: Range[] = []
  for (const block of readingTarget.value?.querySelectorAll<HTMLElement>('[data-block-id]') || []) {
    const content = block.querySelector<HTMLElement>('.markdown-renderer, .handout-block__body')
    if (!content) continue
    for (const note of notesForBlock(block.dataset.blockId || '')) { const range = resolvePersonalAnchor(content, note, { allowUniqueQuote: note.location_status === 'current' }); if (range) ranges.push(range) }
  }
  highlightPersonalNotes(ranges)
}
watch([personalNotes, () => currentRevision.value?.sections], () => { void nextTick(paintPersonalNotes) }, { deep: true })
watch(() => material.value?.id, () => { noteDiscussion.value = null })
onBeforeUnmount(() => highlightPersonalNotes([]))
const readingTarget = ref<HTMLElement | null>(null), noteText = ref(''), savedNote = ref(''), noteSaved = ref(false)
const navigation = useReadingNavigation(readingTarget, followChapter)
const navigationReference = navigation.referenceId
const materialId = computed(() => String(route.params.materialId || ''))
const studyLayoutRoot = ref<HTMLElement | null>(null), studyToolsPanel = ref<HTMLElement | null>(null)
const viewportWidth = ref(window.innerWidth), viewportHeight = ref(window.innerHeight)
const keyboardOpen = ref(false)
let normalViewportWidth = window.innerWidth, normalViewportHeight = window.innerHeight
const mobileViewport = computed(() => viewportWidth.value <= 760 || viewportWidth.value <= 1024 && viewportHeight.value <= 520)
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
  const nextWidth = window.innerWidth, nextHeight = window.innerHeight
  if (nextWidth !== normalViewportWidth) {
    normalViewportWidth = nextWidth
    normalViewportHeight = nextHeight
    keyboardOpen.value = false
  } else if (nextHeight < normalViewportHeight - 140) {
    keyboardOpen.value = true
  } else {
    normalViewportHeight = nextHeight
    keyboardOpen.value = false
  }
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
  if (wasMobile !== mobileViewport.value) mobileDirectoryOpen.value = false
  await nextTick()
  if (sequence !== viewportSequence) return
  if (root && readingTarget.value === root && key === readingPositionKey() && position) restoreReadingPosition(root, JSON.stringify(position))
  reflowing = false
  followChapter()
}
function closePanels(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  if (event.key === 'Escape' && selectionActionsOpen.value) { hideSelectionActions(); return }
  if (event.key === 'Tab' && mobileViewport.value && toolsOpen.value) {
    const controls = Array.from(studyLayoutRoot.value?.querySelectorAll<HTMLElement>('.study-reading-tools button:not(:disabled), .study-reading-tools input:not(:disabled), .study-reading-tools textarea:not(:disabled), .study-reading-tools select:not(:disabled), .study-reading-tools summary, .study-reading-tools a[href]') || []).filter(node => node.getClientRects().length)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    return
  }
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
watch(materialId, () => { navigation.claim('body'); chapterQuery.value = ''; expandedChapters.value = {}; mobileDirectoryOpen.value = false })
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
const budgetBlocked = computed(() => materialStatus.value === 'failed' && material.value?.task?.error_code === 'generation_budget_exceeded')
const isGenerating = computed(() => ['pending', 'running'].includes(materialStatus.value))
const sectionAnchor = (id: string) => `study-${materialId.value}-${id}`
const blockAnchor = (id: string) => `study-${materialId.value}-${id}`
const readingSections = computed(() => (currentRevision.value?.sections || []).map(section => ({ id: section.id, title: section.title, anchor: sectionAnchor(section.id), blocks: section.blocks.map(block => ({ id: block.block_id, title: block.title, anchor: blockAnchor(block.block_id), content: block.content, presentation: handoutPresentation(block.content_type, activeLocale.value, block.type_label), knowledge: block.knowledge_names })) })))
const filteredReadingSections = computed(() => {
  const query = chapterQuery.value.trim().toLocaleLowerCase()
  return readingSections.value.map((section, index) => ({ ...section, number: index + 1 }))
    .filter(section => section.title.toLocaleLowerCase().includes(query) || section.blocks.some(block => (block.title + ' ' + block.presentation.label).toLocaleLowerCase().includes(query)))
})
const hasReasoning = computed(() => conceptSections.value.some(section => section.nodes.length))
const reasoningStatus = computed(() => budgetBlocked.value ? c('generationBudgetExceeded') : c(isGenerating.value ? (material.value?.task?.phase === 'study_concepts' ? 'preparingConcepts' : 'reasoningAfterText') : 'missingConcepts'))
const usablePlans = computed(() => (material.value?.plans || []).filter((raw: any) => {
  const state = material.value?.reading_tool_states?.[raw.node_id]
  return state !== 'stale' && state !== 'missing' && (!raw.handout_revision_id || raw.handout_revision_id === currentRevision.value?.id)
}))
const conceptSections = computed(() => {
  const allowed = new Set((currentRevision.value?.sections || []).flatMap(s => s.blocks.filter(b => !b.answer_to && !['answer', 'exercise', 'question', 'review_question', 'guiding_question'].includes(handoutContentType(b.content_type))).map(b => b.block_id)))
  return buildHandoutConceptSections(usablePlans.value, readingSections.value.map(s => ({ ...s, blocks: s.blocks.filter(b => allowed.has(b.id)) })))
})
let timer: ReturnType<typeof setTimeout> | undefined, requestId = createUuid(), submittedFingerprint = '', disposed = false, epoch = 0, actionSequence = 0, librarySequence = 0
const draftKey = () => `lingzhi-study-draft:${user.value?.id || ''}`
const noteKey = () => `lingzhi-study-note:${user.value?.id}:${material.value?.id}:${currentRevision.value?.id}`

function showError(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : c('requestFailure')
  if (cause instanceof StudyApiError && cause.status === 401) { persistDraft(); epoch++; user.value = null; clearPrivateUi(); clearTimeout(timer) }
}
function clearPrivateUi() { bookmark.close(); librarySequence++; material.value = null; library.value = []; sources.value = []; selectedRanges.value = []; sourceText.value = ''; sourceTitle.value = ''; noteText.value = ''; savedNote.value = ''; creating.value = false; pasting.value = false; sourceBusy.value = false; selectedPassage.value = null; activeChapter.value = ''; Object.assign(form, { title: '', purpose: 'systematic', level: 'beginner', time_minutes: 60, requirements: '' }) }
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
async function refreshLibrary() {
  if (refreshingLibrary.value) return
  refreshingLibrary.value = true
  try { await action(async () => { await Promise.all([loadLibrary(), authorizedCourses.value?.reload()]) }) }
  finally { refreshingLibrary.value = false }
}
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
  let failures = 0
  readingConnection.value = 'loading'
  const retainedRevision = material.value?.id === id ? currentRevision.value?.id : undefined
  if (!retainedRevision) {
    bookmark.close(); newBlockIds.value.clear(); material.value = null; noteText.value = ''; savedNote.value = ''; noteSaved.value = false
    activeChapter.value = ''; selectedPassage.value = null; restoreTool()
  }
  if (!id || !user.value) return
  async function refresh(first = false) {
    try {
      const result = await studyApi.get(id)
      if (disposed || current !== epoch || materialId.value !== id || !user.value) return
      const previousRevision = currentRevision.value?.id
      const previousBlocks = new Set(currentRevision.value?.sections.flatMap(section => section.blocks.map(block => block.block_id)) || [])
      if (previousRevision && previousRevision !== result.revisions.at(-1)?.id) bookmark.close()
      material.value = result
      readingConnection.value = 'connected'; failures = 0
      if (previousRevision !== currentRevision.value?.id) newBlockIds.value.clear()
      else if (!first) for (const section of currentRevision.value?.sections || []) {
        for (const block of section.blocks) if (!previousBlocks.has(block.block_id)) newBlockIds.value.add(block.block_id)
      }
      if ((!retainedRevision && !previousRevision) || (previousRevision && previousRevision !== currentRevision.value?.id)) {
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
    } catch (cause) {
      if (disposed || current !== epoch) return
      const delay = readRecoveryDelay(cause, failures++)
      readingConnection.value = delay === null ? 'unavailable' : 'reconnecting'
      if (delay === null) {
        if (cause instanceof StudyApiError && [403, 404].includes(cause.status)) { bookmark.close(); material.value = null }
        showError(cause)
      }
      else timer = setTimeout(() => { void refresh(first) }, delay)
    }
  }
  await refresh(true)
}
watch(materialId, () => { creating.value = route.query.create === '1' && !materialId.value; void openMaterial() })
watch(() => route.query.create, value => { creating.value = value === '1' && !materialId.value && Boolean(user.value) })
async function resume() { await action(async () => { const owner = user.value?.id, id = materialId.value; await studyApi.resume(id); if (sameOwner(owner) && materialId.value === id) await openMaterial() }) }
function download(blob: Blob, filename: string) { const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) }
async function exportHandout() { await action(async () => { const owner = user.value?.id, title = material.value!.title, blob = await studyApi.export(materialId.value); if (sameOwner(owner)) download(blob, `${title}.md`) }) }
onBeforeRouteUpdate(() => { followChapter(); void bookmark.flush() })
onBeforeRouteLeave(() => { followChapter(); bookmark.close(); persistDraft() })
function recoverReadingConnection() { if (readingConnection.value === 'reconnecting') void openMaterial(); void bookmark.flush() }
function saveReadingBeforeHide(event: Event) { if (event.type === 'pagehide' || document.visibilityState === 'hidden') { followChapter(); void bookmark.flush() } }
onMounted(() => { window.addEventListener('online', recoverReadingConnection); window.addEventListener('pagehide', saveReadingBeforeHide); document.addEventListener('visibilitychange', saveReadingBeforeHide); window.addEventListener('resize', updateViewport); window.addEventListener('resize', positionSelectionActions); window.addEventListener('scroll', positionSelectionActions, true); document.addEventListener('pointerdown', dismissSelectionActionsOutside, true); window.addEventListener('keydown', closePanels); void action(connect) })
onBeforeUnmount(() => { followChapter(); bookmark.close(); window.removeEventListener('online', recoverReadingConnection); window.removeEventListener('pagehide', saveReadingBeforeHide); document.removeEventListener('visibilitychange', saveReadingBeforeHide); window.removeEventListener('resize', updateViewport); window.removeEventListener('resize', positionSelectionActions); window.removeEventListener('scroll', positionSelectionActions, true); document.removeEventListener('pointerdown', dismissSelectionActionsOutside, true); window.removeEventListener('keydown', closePanels); disposed = true; epoch++; clearTimeout(timer); persistDraft() })
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
.study-reading-settings-panel input[type=range] { min-height: 44px; }
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

.study-block-list { margin: 6px 5px 12px 25px; padding-left: 12px; border-left: 1px dashed #d8dcea; }
.study-space .study-block-list button { position: relative; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; column-gap:8px; width: 100%; min-height: 38px; border: 0; border-radius: 7px; padding: 8px 9px; background: transparent; text-align: left; color: #788196; font-size: 14px; font-weight: 400; line-height: 1.55; overflow-wrap: anywhere; }
.study-block-list .study-block-title { min-width:0; }
.study-block-tag { max-width:7em; overflow:hidden; border:1px solid var(--handout-edge, #e1e5ec); border-radius:6px; padding:2px 6px; color:var(--handout-accent, #657080); background:var(--handout-tint, #f0f2f6); font-size:11px; font-weight:600; line-height:1.3; text-overflow:ellipsis; white-space:nowrap; }
.study-space .study-block-list button:hover { background: #f0f1f7; color: #4d5267; }
.study-space .study-block-list button.active { color: #6254a7; background: #efedf7; font-weight: 550; }
.study-nav-hint { color: #8890a1; padding: 0 10px; font-size: 15px; }
.study-main-scroll { flex: 1; min-width: 0; overflow: auto; }
.study-reading-workspace { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; border: 1px solid #e5e7ee; border-radius: 12px; overflow: hidden; background: white; }
.study-reading-body { display: flex; flex: 1; min-width: 0; min-height: 0; }
.study-reading-with-reasoning { display:flex; flex:1; min-width:0; min-height:0; }
.study-reading-with-reasoning > .study-document-scroll { min-width:0; }
.study-reasoning-panel { position:relative; flex:0 0 330px; min-height:0; overflow:auto; margin:24px 18px 24px 0; background:transparent; }
.study-reasoning-panel :deep(.handout-concept-map) { position:static; max-height:none; overflow:visible; }
.study-reasoning-panel :deep(.handout-concept-map > header) { position:relative; padding-right:48px; }
.study-reasoning-close { position:absolute; top:14px; right:12px; }
.study-reading-pane { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: white; }
.study-selection-actions { position:fixed; z-index:120; display:flex; align-items:center; gap:3px; max-width:min(430px,calc(100vw - 16px)); overflow-x:auto; padding:5px; border:1px solid rgba(199,210,254,.9); border-radius:12px; color:var(--lz-text-secondary); background:rgba(255,255,255,.98); box-shadow:0 10px 28px rgba(33,38,64,.17),0 2px 6px rgba(33,38,64,.08); font:600 13px/1.3 var(--study-ui-font); scrollbar-width:none; transform:translate(-50%,-100%); }
.study-selection-actions::-webkit-scrollbar { display:none; }
.study-selection-actions.is-below { transform:translateX(-50%); }
.study-selection-actions button { min-height:38px; flex:none; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 9px; border:0; border-radius:8px; color:inherit; background:transparent; font:inherit; white-space:nowrap; cursor:pointer; }
.study-selection-actions button:hover,.study-selection-actions button:focus-visible { color:var(--lz-brand-strong); background:#f1effa; outline:none; }
.study-selection-actions .study-selection-actions__close { width:36px; padding:0; margin-left:2px; border-left:1px solid #e8e7ef; border-radius:0 8px 8px 0; }
.study-document-scroll { min-height: 0; flex: 1; overflow: auto; scroll-behavior: smooth; }
.study-handout :deep(.code-block-wrapper) { border-radius:8px; border:0; box-shadow:none; }
.study-handout :deep(.code-block-wrapper) { min-width:0; max-width:100%; }
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
.study-reading-tools:has(.personal-assistant), .study-reading-tools:has(.handout-reference), .study-reading-tools:has(.handout-paths), .study-reading-tools:has(.handout-knowledge), .study-reading-tools.is-notes { overflow: hidden; }
.study-inline-notes { display:flex; flex-wrap:wrap; align-items:center; gap:7px; margin:-2px 0 20px; }
.study-inline-notes button { border:0; background:transparent; color:#8b799d; font:13px/1.6 var(--study-ui-font); cursor:pointer; padding:3px 6px; }
.study-inline-notes .study-note-add { display:inline-flex; align-items:center; justify-content:center; gap:6px; min-height:40px; padding:0 12px; border:1px solid #ded9ed; border-radius:9px; background:#faf9fd; font-size:14px; line-height:20px; font-weight:500; }
.study-inline-notes .study-inline-note { max-width:100%; text-align:left; background:#f3eef9; border-radius:4px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; color:#715b88; }
.study-inline-note > span:first-child { margin-right:7px; font-weight:600; }.study-inline-notes .is-question { color:#9d713d; background:#faf4e9; }
:global(::highlight(lingzhi-personal-notes)) { background:#f5e0a5; color:inherit; }
.study-aid-status { padding:12px 16px; flex:none; font-size:14px; line-height:1.65; color:#756787; border-bottom:1px solid #e7e2ee; }.study-aid-status p { margin:0 0 8px; }
.study-tool-heading, .study-reasoning-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 56px; box-sizing: border-box; padding: 10px 18px; border-bottom: 1px solid #e9ebf1; background: #fafbfe; flex: none; font-size: 15px; }
.study-note { padding: 20px; display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 16px; }
.study-note > p { color: var(--lz-text-muted); font-size: 15px; margin: 0; }
.study-note-editor { flex: 1; min-height: 100px; }
.study-note-editor :deep(.el-textarea__inner) { height: 100%; padding: 14px; line-height: 1.85; border-radius: 10px; box-shadow: 0 0 0 1px #e5e7ef inset; background: #fcfcfe; }

.study-note-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex: none; padding-top: 12px; border-top: 1px solid #efedf4; }
.study-note-status { color: var(--lz-text-muted); font-size: 15px; }
.study-note-footer button { flex: none; }
.study-space :deep(.el-button + .el-button) { margin-left: 0; }
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
.study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(.learning-dock__actions > button) { font-size: 15px; font-weight: 600; min-height: 40px; border-radius: 8px; }
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

@media (max-width: 760px), (max-width:1024px) and (max-height:520px) {
  .study-space, .study-space.is-reading-page { padding: max(6px, env(safe-area-inset-top, 0px)) max(6px, env(safe-area-inset-right, 0px)) 0 max(6px, env(safe-area-inset-left, 0px)); gap: 7px; }
  .study-home-navigation { display: none; }
  .study-home-mobile-title { display: block; }
  .study-error { padding: 8px 12px; font-size: 14px; }
  .study-error { gap: 8px; }
  .study-error button { flex: none; min-width: max-content; min-height: 44px; padding-inline: 12px; white-space: nowrap; }
  .study-space button:not(.study-mobile-backdrop) { min-height: 44px; }
  .study-space :deep(.app-header:has(.study-course-context)) { grid-template-columns: minmax(0,1fr) auto; min-height: 52px; gap: 4px; padding: 0 4px; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools) { grid-column: 2; }
  .study-course-context { gap: 2px; }
  .study-course-context h1 { flex: 1; min-width: 0; max-width: none; font-size: 15px; }
  .study-course-context :deep(.workspace-header-action) { min-height: 44px; padding-inline: 6px; }
  .study-course-context :deep(.workspace-header-action.is-icon-only) { width: 44px; min-width: 44px; }
  .study-header-actions { flex-wrap: wrap; justify-content: flex-start; gap: 8px; }
  .study-header-actions :deep(.workspace-header-action) { min-height: 44px; }
  .study-reading-settings summary { min-height: 44px; }
  .study-reading-settings-panel { position: static; width: 100%; padding: 12px 0; border: 0; box-shadow: none; box-sizing: border-box; }
  .study-reading-settings-panel :deep(.ui-segmented-control button) { box-sizing: border-box; min-height: 44px; }
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
  .study-handout :deep(pre), .study-handout :deep(table) { max-width:100%; overflow-x:auto; overscroll-behavior-inline:contain; -webkit-overflow-scrolling:touch; }
  .study-handout :deep(table) { display:block; }
  .study-handout :deep(img), .study-handout :deep(svg) { max-width:100%; height:auto; }
  .study-handout-section + .study-handout-section { padding-top: 24px; margin-top: 32px; }
  .study-handout-section h2 { margin: 8px 0 20px; font-size: 23px; line-height: 1.42; }
  .study-selection-actions { gap:1px; max-width:calc(100vw - 12px); padding:4px; border-radius:11px; font-size:12px; }
  .study-selection-actions button { min-height:44px; gap:4px; padding:0 7px; }
  .study-selection-actions button svg { width:15px; height:15px; }
  .study-selection-actions .study-selection-actions__close { width:34px; }
  .study-space button.study-tools-backdrop { z-index: 91; }
  .study-reading-tools { position: fixed; z-index: 92; inset:0; width:100%; height:var(--app-visual-viewport-height, 100dvh); max-height:none; padding-bottom:env(safe-area-inset-bottom); border:0; border-radius:0; box-shadow:none; }
  .study-tool-heading, .study-reasoning-heading { box-sizing:border-box; min-height:calc(56px + env(safe-area-inset-top)); height:auto; padding:calc(6px + env(safe-area-inset-top)) 16px 6px 8px; gap:8px; background:#fff; }
  .study-tool-heading > .el-button { order:-1; flex:none; margin:0; }
  .study-tool-heading strong { font-size:16px; }
  .study-tool-heading strong { margin-right:auto; }
  .study-tool-icon { flex:none; color:#7864a2; }
  .study-tool-heading :deep(.el-button) { width: 44px; height: 44px; }
  .study-inline-notes button,.study-inline-notes .study-note-add { min-height:44px; }
  .study-inline-notes { user-select:none; }
  .study-note { padding: 12px; }
  .study-note-footer { align-items: start; flex-direction: column; }
  .study-note-footer button { align-self: stretch; min-height: 44px; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom { position: sticky; z-index: 93; bottom: 0; min-height: 62px; flex-wrap: nowrap; padding: 4px 6px calc(4px + env(safe-area-inset-bottom)); border-top: 1px solid #e1e5f0; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(.learning-dock__actions) { width: 100%; display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); justify-content: stretch; align-items: stretch; gap: 2px; margin: 0; overflow: visible; }
  .study-reading-workspace .learning-dock.is-toolbar.is-bottom :deep(.learning-dock__actions > button) { box-sizing: border-box; width: 100%; min-width: 0; min-height: 54px; padding: 4px 1px; display: flex; flex-direction: column; justify-content: center; gap: 3px; border-radius: 9px; font-size:12px; line-height:1.25; white-space:normal; }
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
  .study-purpose-options button { display:flex; min-height:56px; flex-direction:row; align-items: center; padding: 10px; gap: 8px; }
  .study-purpose-options button > svg:not(.purpose-check) { width: 21px; height: 21px; }
  .study-purpose-options strong { font-size: 15px; }
  .study-purpose-options button > span { display: none; }
  .study-purpose-options .purpose-check { right: 10px; top: 10px; width: 16px; height: 16px; }
  .study-purpose-mobile-hint { display: block; margin: 8px 0 0; color: var(--lz-text-secondary); font-size: 14px; line-height: 1.55; }
  .study-create :deep(.el-input__wrapper) { min-height: 44px; box-sizing: border-box; }
  .study-create :deep(.el-input__inner) { min-height: 24px; font-size: 16px; }
  .study-create :deep(.el-textarea__inner) { min-height: 92px; font-size: 16px; }
  .study-space :is(input:not([type=checkbox]):not([type=file]), textarea, select) { font-size: 16px; }
  .study-chapter-search :deep(.el-input__inner) { font-size: 16px; }
  .study-space :is(input::placeholder, textarea::placeholder) { color: #64748b; opacity: 1; }
  .study-create select,.study-create input[type=number] { min-height: 44px; }
  .study-settings-row { gap: 10px; }
  .study-source-actions { gap: 8px; }
  .study-source-actions button { min-height: 44px; }
  .study-source-actions > span { flex-basis: 100%; line-height: 1.5; }
  .study-main-scroll { scroll-padding-bottom: calc(148px + env(safe-area-inset-bottom, 0px)); }
  .study-generate-bar { position: sticky; z-index: 5; bottom: 0; margin: 0 -12px; padding: 10px 12px calc(10px + env(safe-area-inset-bottom)); border-top: 1px solid #e3e8f2; background: rgb(255 255 255 / 96%); backdrop-filter: blur(12px); }
  .study-generate-bar > div { min-width: 0; }
  .study-generate-bar button { min-height: 46px; }
  .study-space.is-creating-page.is-keyboard-open .study-main-scroll { scroll-padding-bottom: 16px; }
  .study-space.is-creating-page.is-keyboard-open .study-generate-bar { display: none; }
}

@media (max-width: 480px) {
  .study-create .study-page-heading { flex-direction: row; align-items: center; gap: 8px; }
  .study-create .study-create-back { border: 0; background: transparent; }
  .study-generate-bar { flex-direction: row; align-items: center; gap: 8px; }
  .study-generate-bar > div { display: flex; flex: 1; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }
  .study-generate-bar > div p { margin: 0; }
  .study-generate-bar button { justify-content: center; max-width: 44%; padding-inline: 8px; font-size: 14px; }
}

@media (max-width: 380px) {
  .study-space { padding-inline: 4px; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools) { overflow-x: auto; scrollbar-width: none; }
  .study-space :deep(.app-header:has(.study-course-context) > .app-header-tools::-webkit-scrollbar) { display: none; }
  .study-header-actions :deep(.workspace-header-action) { min-width: 44px; }
  .study-settings-row { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 340px) {
  .study-purpose-options { grid-template-columns: minmax(0, 1fr); }
  .study-generate-bar { flex-direction: column; align-items: stretch; }
  .study-generate-bar button { max-width: none; }
}
@media (min-width:768px) {
  .study-reading-workspace .learning-dock :deep(.learning-dock__location) { display:none; }
  .study-reading-workspace .learning-dock :deep(.learning-dock__actions) { flex:1; min-width:0; flex-wrap:nowrap; justify-content:flex-start; overflow-x:auto; scrollbar-width:thin; }
  .study-reading-workspace .learning-dock :deep(.learning-dock__actions > button) { flex:none; }
}
@media(max-width:760px), (max-width:1024px) and (max-height:520px) {
  .study-reading-workspace .learning-dock :deep(.learning-dock__actions > button.is-active) { box-shadow:inset 0 2px #8c78bc; background:#f0ecfa; }
  .study-reading-workspace .learning-dock :deep(.learning-dock__more-panel p) { display:none; }
  .study-reading-workspace .learning-dock :deep(.learning-dock__more-actions) { gap:10px; }
  .study-reading-workspace .learning-dock :deep(.learning-dock__more-action) { min-height:60px; }
}

.study-tool-panel { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; overflow:hidden; }
.study-tool-tabs { overflow-x:auto; scrollbar-width:thin; justify-content:flex-start; gap:2px; padding:6px 8px; min-height:48px; }
.study-tool-tabs > button[role=tab] { flex:1; white-space:nowrap; min-width:max-content; display:flex; align-items:center; justify-content:center; gap:5px; border:0; border-radius:6px; padding:9px 4px; background:transparent; color:#6d6578; font:600 13px/1.4 var(--study-ui-font); cursor:pointer; }
.study-tool-tabs > button[aria-selected=true] { background:#eee8fa; color:#6745a0; }
.study-tool-tabs > button:focus-visible { outline:2px solid #7953a0; outline-offset:-2px; }
.study-tool-panel > .handout-concept-map { position:static; flex:1; min-height:0; max-height:none; overflow:auto; border:0; }
.study-tool-panel > .handout-concept-map :deep(> header) { display:none; }
.study-bottom-bar { display:flex; align-items:center; gap:16px; min-height:52px; padding:6px 16px; border-top:1px solid #e6e3ee; background:#fcfcfe; font:14px/1.5 var(--study-ui-font); }
.study-bottom-bar button { display:flex; align-items:center; gap:7px; flex:none; border:0; border-radius:6px; padding:8px; background:transparent; color:#68547f; font:inherit; cursor:pointer; }
.study-bottom-bar button[aria-pressed=true] { background:#eee8fa; }
.study-reading-location { display:flex; align-items:center; gap:10px; flex:1; min-width:0; color:#697384; }
.study-reading-location > span:first-child { flex:none; font-size:12px; color:#858091; }
.study-reading-location > :last-child { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
@media(max-width:760px) { .study-bottom-bar { gap:6px; padding:6px 8px; } .study-reading-location > span:first-child { display:none; } .study-tool-tabs { padding-top:calc(6px + env(safe-area-inset-top)); } }
@media(min-width:1025px){.study-reading-tools{width:max(var(--column-right-width),min(35vw,470px));}}
.study-connection { padding:12px 18px; color:var(--lz-text); font-size:15px; }
.study-bookmark-status { font-size:13px; color:var(--lz-text); max-width:360px; }
.study-tool-heading .study-close-tools { flex:none; margin-left:auto; }
@media(max-width:760px) { .study-bottom-bar { flex-wrap:wrap; } .study-bookmark-status { order:3; flex-basis:100%; max-width:none; } }
</style>
