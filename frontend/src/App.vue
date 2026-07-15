<template>
  <div class="app-shell">
    <header class="app-header glass-panel-elevated">
      <button class="brand-button" type="button" :aria-label="t('app.backToLibrary', '返回课程库')" @click="router.push('/courses')">
        <span class="brand-mark"><GraduationCap :size="21" /></span>
        <span class="brand-copy">
          <strong>{{ t('app.brand', '灵知') }}</strong>
          <small>{{ t('app.product', 'KnowledgeMap') }}</small>
        </span>
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
      <router-view />
    </main>

    <KnowledgeLibrary />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, GraduationCap, Scan, Search, Settings2, X } from 'lucide-vue-next'
import KnowledgeLibrary from './components/KnowledgeLibrary.vue'
import { useCourseStore } from './stores/course'
import { t } from './shared/i18n'

const router = useRouter()
const route = useRoute()
const courseStore = useCourseStore()

const isLearningRoute = computed(() => route.name === 'learning')
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

function updateFontSize(event: Event) {
  const fontSize = Number((event.target as HTMLInputElement).value)
  courseStore.setUiSettings({ fontSize })
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
.brand-button:hover .brand-mark { transform: scale(1.05) rotate(-4deg); box-shadow:0 9px 20px rgba(99,102,241,.3),inset 0 1px 0 rgba(255,255,255,.32); }
.brand-button:hover .brand-copy strong { color:#4f46e5; }

.brand-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255,255,255,.35);
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 55%, #a855f7 100%);
  box-shadow: 0 7px 16px rgba(99, 102, 241, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.28);
  transition: transform .25s ease, box-shadow .25s ease;
}

.brand-copy,
.course-context-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.brand-copy strong { font-size:17px; line-height:1.05; color:#312e81; transition:color .2s ease; }
.brand-copy small { margin-top:3px; font-size:9px; color:#94a3b8; font-weight:600; }

.header-actions { position:relative; display:flex; align-items:center; justify-content:flex-end; gap:5px; padding-left:13px; }
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
.header-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; color: var(--lz-text); font-size: 12px; }
.header-search button { width: 22px; height: 22px; display: grid; place-items: center; color: var(--lz-text-muted); background: transparent; }

.app-main { min-width: 0; min-height: 0; overflow: hidden; border-radius: var(--lz-radius-surface); }

.reading-settings { display: grid; gap: 14px; color: var(--lz-text-secondary); font-size: 12px; }
.reading-settings label { display: grid; grid-template-columns: auto 1fr 24px; align-items: center; gap: 8px; }
.reading-settings input { accent-color: var(--lz-brand); }
.segmented-control { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; margin-top: 6px; padding: 3px; border-radius: 7px; background: var(--lz-surface-muted); }
.segmented-control button { min-height: 28px; border-radius: 5px; color: var(--lz-text-secondary); background: transparent; font-size: 11px; }
.segmented-control button.active { color: var(--lz-brand-strong); background: #fff; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08); }

@media (max-width: 900px) {
  .app-header { grid-template-columns: auto minmax(0, 1fr); gap: 8px; padding: 0 10px; }
  .brand-copy small, .header-search { display: none; }
}

@media (max-width: 600px) {
  .app-shell { gap: 0; padding: 0; }
  .app-header { border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
  .app-main { border-radius: 0; }
  .app-header { grid-template-columns: auto minmax(0, 1fr); }
  .brand-copy { display: none; }
  .header-actions .header-icon-button:nth-of-type(1),
  .header-actions :deep(.el-popover__reference-wrapper),
  .header-actions :deep(.el-dropdown) { display: none; }
}
</style>
