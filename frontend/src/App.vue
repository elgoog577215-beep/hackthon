<template>
  <div class="app-shell" :class="{ 'is-ppt-workspace': isPptRoute, 'has-course-workflow': isCourseRoute }">
    <header v-if="!isPptRoute" class="app-header glass-panel-elevated">
      <button class="brand-button" type="button" :aria-label="t('app.backToLibrary', '返回课程库')" @click="router.push('/courses')">
        <img class="brand-mark" src="/qizhi-favicon.svg" alt="启智" />
        <span class="brand-name">启智</span>
      </button>

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

        <button type="button" class="header-ppt-button" title="打开启智课程闭环" @click="openCourseWorkbench">
          <Workflow :size="17" />
          <span>课程闭环</span>
        </button>

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
              <div class="segmented-control">
                <button v-for="font in fontOptions" :key="font.value" type="button" :class="{ active: courseStore.uiSettings.fontFamily === font.value }" @click="courseStore.setUiSettings({ fontFamily: font.value })">
                  {{ font.label }}
                </button>
              </div>
            </div>
            <div>
              <span>{{ t('app.language', '语言') }}</span>
              <div class="segmented-control language-control">
                <button type="button" :class="{ active: activeLocale === 'zh' }" :aria-pressed="activeLocale === 'zh'" @click="changeLocale('zh')">
                  {{ t('app.languageChinese', '中文') }}
                </button>
                <button type="button" :class="{ active: activeLocale === 'en' }" :aria-pressed="activeLocale === 'en'" @click="changeLocale('en')">
                  {{ t('app.languageEnglish', 'English') }}
                </button>
              </div>
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

    <CourseWorkflowBar v-if="isCourseRoute" />

    <main class="app-main">
      <router-view />
    </main>

    <KnowledgeLibrary />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Scan, Search, Settings2, Workflow, X } from 'lucide-vue-next'
import CourseWorkflowBar from './components/CourseWorkflowBar.vue'
import KnowledgeLibrary from './components/KnowledgeLibrary.vue'
import { useCourseStore } from './stores/course'
import { GENERATION_STATE_KEY, useGenerationStore } from './stores/generation'
import { activeLocale, setLocale, t } from './shared/i18n'

const router = useRouter()
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
const isPptRoute = computed(() => route.name === 'ppt-workspace')
const isCourseRoute = computed(() => (
  route.name === 'course-workbench' || route.name === 'learning' || route.name === 'ppt-workspace'
))
const searchQuery = computed({
  get: () => courseStore.globalSearchQuery,
  set: value => { courseStore.globalSearchQuery = value },
})
const fontOptions = computed(() => [
  { value: 'sans' as const, label: t('app.fontSans', '黑体') },
  { value: 'serif' as const, label: t('app.fontSerif', '宋体') },
  { value: 'mono' as const, label: t('app.fontMono', '等宽') },
])

function handleExport(command: string) {
  if (command === 'json') courseStore.exportCourseJson()
  else courseStore.exportCourseMarkdown()
}

function openCourseWorkbench() {
  const courseId = courseStore.currentCourseId || String(route.params.courseId || '')
  if (courseId) void router.push({ name: 'course-workbench', params: { courseId } })
}

function updateFontSize(event: Event) {
  const fontSize = Number((event.target as HTMLInputElement).value)
  courseStore.setUiSettings({ fontSize })
}

function changeLocale(locale: 'zh' | 'en') {
  void setLocale(locale)
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
.app-shell.has-course-workflow:not(.is-ppt-workspace) { grid-template-rows:60px 52px minmax(0,1fr); gap:8px; }
.app-shell.is-ppt-workspace { grid-template-rows:52px minmax(0,1fr); gap:0; padding:0; background:#e9edf3; }
.app-shell.is-ppt-workspace .app-main { border-radius:0; }

.app-header {
  position: relative;
  z-index: 80;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(190px, 1fr);
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

.brand-button,
.header-icon-button,
.header-search button,
.segmented-control button {
  border: 0;
  cursor: pointer;
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
  border-radius: 13px;
  transition: transform .2s ease, background .2s ease;
}
.brand-button:hover { transform: translateY(-1px); }
.brand-button:hover .brand-mark { transform: scale(1.035); filter: drop-shadow(0 6px 10px rgba(0,16,129,.16)); }

.brand-mark {
  width: 34px;
  height: 34px;
  display: block;
  object-fit: contain;
  transition: transform .2s ease, filter .2s ease;
}
.brand-name { color:#001081; font-size:20px; font-weight:850; letter-spacing:.08em; }

.course-context-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.header-actions { position:relative; display:flex; align-items:center; justify-content:flex-end; gap:5px; padding-left:13px; }
.header-actions::before { content:""; position:absolute; left:0; width:1px; height:26px; background:linear-gradient(180deg,transparent,#dbe3ef,transparent); }
.header-icon-button { width:36px; height:36px; display:grid; place-items:center; border:1px solid transparent; border-radius:11px; color:var(--lz-text-secondary); background:transparent; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease; }
.header-icon-button:hover, .header-icon-button.active { transform:translateY(-1px); border-color:#e0e7ff; color:var(--lz-brand-strong); background:#f5f3ff; }
.header-ppt-button {
  min-height:36px;
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:0 12px;
  border:1px solid #c7d6f8;
  border-radius:11px;
  color:#214cae;
  background:#eef3ff;
  font-size:11px;
  font-weight:720;
  cursor:pointer;
  transition:transform .16s ease,box-shadow .16s ease,background .16s ease;
}
.header-ppt-button:hover { transform:translateY(-1px); background:#e4ecff; box-shadow:0 6px 14px rgba(37,86,216,.13); }

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
.header-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; color: var(--lz-text); font-size: 12px; }
.header-search button { width: 22px; height: 22px; display: grid; place-items: center; color: var(--lz-text-muted); background: transparent; }

.app-main { min-width: 0; min-height: 0; overflow: hidden; border-radius: var(--lz-radius-surface); }

.reading-settings { display: grid; gap: 14px; color: var(--lz-text-secondary); font-size: 12px; }
.reading-settings label { display: grid; grid-template-columns: auto 1fr 24px; align-items: center; gap: 8px; }
.reading-settings input { accent-color: var(--lz-brand); }
.segmented-control { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; margin-top: 6px; padding: 3px; border-radius: 7px; background: var(--lz-surface-muted); }
.segmented-control button { min-height: 28px; border-radius: 5px; color: var(--lz-text-secondary); background: transparent; font-size: 11px; }
.segmented-control button.active { color: var(--lz-brand-strong); background: #fff; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08); }
.language-control { grid-template-columns: repeat(2, 1fr); }

@media (max-width: 900px) {
  .app-header { grid-template-columns: auto minmax(0, 1fr); gap: 8px; padding: 0 10px; }
  .header-search { display: none; }
}

@media (max-width: 600px) {
  .app-shell { gap: 0; padding: 0; }
  .app-header { border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
  .app-main { border-radius: 0; }
  .app-header { grid-template-columns: auto minmax(0, 1fr); }
  .brand-mark { width:32px; height:32px; }
  .header-actions .header-icon-button:nth-of-type(1),
  .header-actions :deep(.el-popover__reference-wrapper),
  .header-actions :deep(.el-dropdown) { display: none; }
  .header-ppt-button { width:36px; padding:0; justify-content:center; }
  .header-ppt-button span { display:none; }
}
</style>
