<template>
  <div
    class="app-shell"
    :class="{
      'is-fullscreen-concept': isFullscreenConceptRoute,
      'is-course-workspace-route': isCourseWorkspaceRoute,
    }"
  >
    <header
      v-if="!isFullscreenConceptRoute"
      class="app-header glass-panel-elevated"
    >
      <div class="app-header-start">
        <RouterLink class="brand-button" :class="{ 'is-route-hidden': isCourseWorkspaceRoute }" :to="{ name: 'course-library' }" :aria-label="t('app.backToLibrary', '返回课程库')">
          <img class="brand-mark" src="/qizhi-favicon.svg" alt="启智" />
          <span class="brand-name">启智</span>
        </RouterLink>
        <div v-if="!isLearningRoute" id="app-header-route-context" class="route-header-context" />
      </div>

      <div v-if="!isLearningRoute" id="app-header-route-center" class="app-header-center" />

      <div v-if="!isLearningRoute" id="app-header-route-actions" class="route-header-actions" />

      <div v-if="isLearningRoute" class="header-actions">
        <label class="header-search">
          <Search :size="15" />
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="t('app.searchCourse', '搜索课程内容')"
            :aria-label="t('app.searchCourse', '搜索课程内容')"
          />
          <button v-if="searchQuery" type="button" :title="t('app.clearSearch', '清除搜索')" :aria-label="t('app.clearSearch', '清除搜索')" @click="searchQuery = ''">
            <X :size="14" />
          </button>
        </label>

        <el-popover placement="bottom-end" :width="224" trigger="click">
          <template #reference>
            <button type="button" class="header-icon-button" :title="t('app.readingSettings', '阅读设置')" :aria-label="t('app.readingSettings', '阅读设置')">
              <Settings2 :size="17" />
            </button>
          </template>
          <div class="reading-settings">
            <label>
              <span>{{ t('app.fontSize', '字号') }}</span>
              <input
                :value="courseStore.uiSettings.fontSize"
                type="range"
                min="13"
                max="24"
                step="1"
                @input="updateFontSize"
              />
              <strong>{{ courseStore.uiSettings.fontSize }}</strong>
            </label>
            <div>
              <span>{{ t('app.fontFamily', '字体') }}</span>
              <UiSegmentedControl
                class="reading-setting-control"
                size="compact"
                :model-value="courseStore.uiSettings.fontFamily"
                :options="fontOptions"
                :accessibility-label="t('app.fontFamily', '字体')"
                @update:model-value="setFontFamily"
              />
            </div>
            <div>
              <span>{{ t('app.language', '语言') }}</span>
              <UiSegmentedControl
                class="reading-setting-control"
                size="compact"
                :model-value="activeLocale"
                :options="localeOptions"
                :accessibility-label="t('app.language', '语言')"
                @update:model-value="changeLocale"
              />
            </div>
          </div>
        </el-popover>

        <button type="button" class="header-icon-button" :class="{ active: courseStore.isFocusMode }" :title="t('app.focusMode', '专注模式')" :aria-label="t('app.focusMode', '专注模式')" @click="courseStore.toggleFocusMode()">
          <Scan :size="17" />
        </button>

        <el-dropdown trigger="click" @command="handleExport">
          <button type="button" class="header-icon-button" :title="t('app.export', '导出课程')" :aria-label="t('app.export', '导出课程')">
            <Download :size="17" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="markdown">{{ t('app.exportMarkdown', '导出 Markdown') }}</el-dropdown-item>
              <el-dropdown-item command="json">{{ t('app.exportJson', '导出 JSON') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <main class="app-main">
      <RouterView v-slot="{ Component, route: currentRoute }">
        <Transition name="route-surface" mode="out-in">
          <component
            :is="Component"
            :key="currentRoute.name || currentRoute.path"
          />
        </Transition>
      </RouterView>
    </main>

    <AppErrorCenter />
    <KnowledgeLibrary v-if="!isPublicConceptRoute" :learning-mode="isLearningRoute" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Download, Scan, Search, Settings2, X } from 'lucide-vue-next'
import AppErrorCenter from './components/AppErrorCenter.vue'
import KnowledgeLibrary from './components/KnowledgeLibrary.vue'
import UiSegmentedControl from './components/UiSegmentedControl.vue'
import { useCourseStore } from './stores/course'
import { GENERATION_STATE_KEY, useGenerationStore } from './stores/generation'
import { activeLocale, setLocale, t } from './shared/i18n'

const route = useRoute()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()

const reconcileGenerationTasks = () => {
  void generationStore.fetchGlobalTasks()
}
const reconcileGenerationTasksFromStorage = (event: StorageEvent) => {
  if (event.key === GENERATION_STATE_KEY) reconcileGenerationTasks()
}
const reconcileVisibleGenerationTasks = () => {
  if (document.visibilityState === 'visible') reconcileGenerationTasks()
}

onMounted(() => {
  if (window.location.pathname.startsWith('/workspace-concept')) return
  generationStore.restoreGenerationState()
  generationStore.startGlobalMonitor()
  window.addEventListener('storage', reconcileGenerationTasksFromStorage)
  window.addEventListener('focus', reconcileGenerationTasks)
  document.addEventListener('visibilitychange', reconcileVisibleGenerationTasks)
})
onBeforeUnmount(() => {
  generationStore.stopGlobalMonitor()
  window.removeEventListener('storage', reconcileGenerationTasksFromStorage)
  window.removeEventListener('focus', reconcileGenerationTasks)
  document.removeEventListener('visibilitychange', reconcileVisibleGenerationTasks)
})

const isLearningRoute = computed(() => route.name === 'learning')
const isCourseWorkspaceRoute = computed(() => ['course-workspace', 'course-audit-updates'].includes(String(route.name || '')))
const isPublicConceptRoute = computed(() => route.meta.publicConcept === true)
const isFullscreenConceptRoute = computed(() => route.meta.fullscreenConcept === true)
const searchQuery = computed({
  get: () => courseStore.globalSearchQuery,
  set: value => { courseStore.globalSearchQuery = value },
})
const fontOptions = computed(() => [
  { value: 'sans' as const, label: t('app.fontSans', '黑体') },
  { value: 'serif' as const, label: t('app.fontSerif', '宋体') },
  { value: 'mono' as const, label: t('app.fontMono', '等宽') },
])
const localeOptions = computed(() => [
  { value: 'zh', label: t('app.languageChinese', '中文') },
  { value: 'en', label: t('app.languageEnglish', 'English') },
])

function handleExport(command: string) {
  if (command === 'json') courseStore.exportCourseJson()
  else courseStore.exportCourseMarkdown()
}

function updateFontSize(event: Event) {
  const fontSize = Number((event.target as HTMLInputElement).value)
  courseStore.setUiSettings({ fontSize })
}

function setFontFamily(value: string) {
  if (value === 'sans' || value === 'serif' || value === 'mono') courseStore.setUiSettings({ fontFamily: value })
}

function changeLocale(locale: string) {
  if (locale === 'zh' || locale === 'en') void setLocale(locale)
}
</script>

<style scoped>
.app-shell {
  width: 100%;
  height: 100vh;
  display: grid;
  grid-template-rows: 60px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
  overflow: hidden;
  color: var(--lz-text);
  background: transparent;
}
.app-shell.is-fullscreen-concept { grid-template-rows:minmax(0,1fr); gap:0; padding:0; background:var(--lz-canvas); }
.app-shell.is-fullscreen-concept .app-main { border-radius:0; }
.app-shell.is-public-concept { grid-template-rows:minmax(0,1fr); gap:0; padding:0; background:#f5f6f9; }
.app-shell.is-public-concept .app-main { border-radius:0; }

.app-header {
  position: relative;
  z-index: 80;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(480px, 660px) minmax(150px, 1fr);
  align-items: center;
  gap: 16px;
  padding: 0 17px;
  border: 1px solid rgba(255, 255, 255, 0.88);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,.96), rgba(250,250,255,.91));
  box-shadow: 0 8px 26px rgba(79,70,229,.08), inset 0 1px 0 rgba(255,255,255,.96);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.app-shell.is-course-workspace-route .app-header {
  grid-template-columns: minmax(320px, 1.2fr) auto minmax(320px, 1fr);
  gap: 12px;
}

.app-shell.is-course-workspace-route .app-header-start { gap: 0; }

.brand-button,
.header-icon-button,
.header-search button {
  border: 0;
  cursor: pointer;
}

.app-header-start {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.route-header-context {
  min-width: 0;
  flex: 1;
}

.brand-button {
  min-width: 0;
  width: max-content;
  height: 46px;
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  background: transparent;
  text-align: left;
  text-decoration: none;
  border-radius: 13px;
  transition: transform .2s ease, background .2s ease;
}
.brand-button:hover { transform: translateY(-1px); }
.brand-button:hover .brand-mark { transform: scale(1.035); filter: drop-shadow(0 6px 10px rgba(0,16,129,.16)); }
.brand-button.is-route-hidden { display:none; }

.brand-mark {
  width: 34px;
  height: 34px;
  display: block;
  object-fit: contain;
  transition: transform .2s ease, filter .2s ease;
}
.brand-name { color:#001081; font-size:20px; font-weight:850; letter-spacing:.08em; }

.app-header-center { min-width:0; width:100%; justify-self:center; }
.route-header-actions { min-width:0; grid-column:3; justify-self:end; }
.course-context-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.header-actions { position:relative; grid-column:3; justify-self:end; display:flex; align-items:center; justify-content:flex-end; gap:5px; padding-left:13px; }
.header-actions::before { content:""; position:absolute; left:0; width:1px; height:26px; background:linear-gradient(180deg,transparent,#dbe3ef,transparent); }
.header-icon-button { width:36px; height:36px; display:grid; place-items:center; border:1px solid transparent; border-radius:11px; color:var(--lz-text-secondary); background:transparent; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease; }
.header-icon-button:hover, .header-icon-button.active { transform:translateY(-1px); border-color:#e0e7ff; color:var(--lz-brand-strong); background:#f5f3ff; }
.header-search {
  width: clamp(180px, 22vw, 300px);
  height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid var(--lz-border);
  border-radius: 11px;
  color: var(--lz-text-muted);
  background: rgba(248,250,252,.82);
}

.header-search:focus-within { border-color: var(--lz-brand); background: #fff; box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.09); }
.header-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; color: var(--lz-text); font-size:14px; }
.header-search button { width: 22px; height: 22px; display: grid; place-items: center; color: var(--lz-text-muted); background: transparent; }

.app-main { min-width: 0; min-height: 0; overflow: hidden; border-radius: var(--lz-radius-surface); }

.route-surface-enter-active {
  transition: opacity .22s cubic-bezier(.16,1,.3,1), transform .24s cubic-bezier(.16,1,.3,1);
}
.route-surface-leave-active {
  transition: opacity .12s ease-in, transform .14s ease-in;
}
.route-surface-enter-from { opacity:0; transform:translateY(7px); }
.route-surface-leave-to { opacity:0; transform:translateY(-3px); }

.reading-settings { display: grid; gap: 14px; color: var(--lz-text-secondary); font-size:14px; }
.reading-settings label { display: grid; grid-template-columns: auto 1fr 24px; align-items: center; gap: 8px; }
.reading-settings input { accent-color: var(--lz-brand); }
.reading-setting-control { margin-top:6px; }

@media (max-width: 900px) {
  .app-header { grid-template-columns: auto minmax(180px, 1fr) auto; gap: 8px; padding: 0 10px; }
  .app-shell.is-course-workspace-route .app-header { grid-template-columns:minmax(230px,1fr) auto minmax(180px,auto); }
  .brand-name { display:none; }
  .header-search { display: none; }
}

@media (max-width: 1400px) {
}

@media (max-width: 720px) {
  .app-shell.is-course-workspace-route { grid-template-rows:102px minmax(0,1fr); }
  .app-shell.is-course-workspace-route .app-header {
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:58px 44px;
    gap:0 8px;
    padding:0 10px;
  }
  .app-shell.is-course-workspace-route .app-header-start { grid-column:1; grid-row:1; }
  .app-shell.is-course-workspace-route .app-header-center {
    grid-column:1/-1;
    grid-row:2;
    align-self:stretch;
    display:flex;
    align-items:center;
    justify-content:center;
    border-top:1px solid var(--lz-border);
  }
  .app-shell.is-course-workspace-route .route-header-actions { grid-column:2; grid-row:1; }
}

@media (max-width: 600px) {
  .app-shell { grid-template-rows:auto minmax(0,1fr); gap: 0; padding: 0; }
  .app-header { border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
  .app-main { border-radius: 0; }
  .app-header { grid-template-columns: auto minmax(70px, 1fr) auto; min-height:60px; }
  .route-header-actions,.header-actions { grid-column:3; grid-row:1; }
  .brand-mark { width:32px; height:32px; }
  .header-actions .header-icon-button:nth-of-type(1),
  .header-actions :deep(.el-popover__reference-wrapper),
  .header-actions :deep(.el-dropdown) { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .route-surface-enter-active,
  .route-surface-leave-active { transition:none; }
  .route-surface-enter-from,
  .route-surface-leave-to { transform:none; }
}
</style>
