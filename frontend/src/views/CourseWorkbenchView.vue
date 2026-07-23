<template>
  <section class="course-workbench-view">
    <div v-if="loading" class="workbench-loading">
      <LoaderCircle :size="24" class="spin" />
      <strong>正在连接同一课程源…</strong>
      <span>PPT、正文、学习记录与课程生长将从这里汇合</span>
    </div>

    <template v-else>
      <header class="workbench-hero">
        <div class="workbench-hero__copy">
          <span class="workbench-eyebrow"><Workflow :size="14" /> 启智统一课程工作台</span>
          <h1>{{ courseTitle }}</h1>
          <p>教师的每一次设计修改、学生的每一次真实反馈，都在同一门课程上继续向前。你可以按流程操作，也可以从任一步直接进入。</p>
          <div class="workbench-meta">
            <span><Layers3 :size="13" /> {{ nodeCount }} 个课程节点</span>
            <span><GitBranch :size="13" /> 版本 {{ versionLabel }}</span>
            <span><Link2 :size="13" /> 单一课程源</span>
          </div>
        </div>
        <div class="workbench-hero__actions">
          <button type="button" class="primary" @click="openSurface('learning')">
            <Play :size="16" /> {{ resumeLabel }}
          </button>
          <button type="button" @click="openSurface('design')">
            <Presentation :size="16" /> 打开教学设计
          </button>
        </div>
      </header>

      <section class="course-loop" aria-label="教师设计到课程生长的完整闭环">
        <article class="loop-surface is-teacher">
          <div class="surface-heading">
            <span class="surface-icon"><Presentation :size="20" /></span>
            <div><small>教师侧</small><h2>PPT 与教学设计</h2></div>
            <span class="surface-state">可独立操作</span>
          </div>
          <p>修改学习目标后，先分析语义影响，再决定哪些教案、正文、例题和理解检查需要同步。</p>
          <ul>
            <li><Check :size="13" /> PPT 与课程正文共用同一课程文档</li>
            <li><Check :size="13" /> 修改前后差异和影响范围可确认</li>
            <li><Check :size="13" /> 未受影响内容保持原样</li>
          </ul>
          <button type="button" @click="openSurface('design')">进入 PPT 工作台 <ArrowRight :size="14" /></button>
        </article>

        <div class="loop-bridge" :class="{ 'is-synced': Boolean(syncState) }">
          <span class="bridge-line"></span>
          <div class="bridge-core">
            <RefreshCw :size="20" />
            <small>同源课程引擎</small>
            <strong>{{ syncState ? '改动已交接' : '实时保持一致' }}</strong>
          </div>
          <div v-if="syncState" class="bridge-diff">
            <small>最近一次 PPT 修改</small>
            <span>{{ syncState.beforeText }}</span>
            <ArrowDown :size="12" />
            <strong>{{ syncState.afterText }}</strong>
          </div>
          <p v-else>这里不是复制文件，而是让 PPT、教案和课程正文引用同一个结构化来源。</p>
        </div>

        <article class="loop-surface is-learner">
          <div class="surface-heading">
            <span class="surface-icon"><BookOpenText :size="20" /></span>
            <div><small>学习侧</small><h2>学习现场与 AI 生长</h2></div>
            <span class="surface-state is-purple">持续演化</span>
          </div>
          <p>课程先呈现教师确认后的正式内容，再把学生对话、练习和学习记录转成可审核的生长方案。</p>
          <ul>
            <li><Check :size="13" /> 同源修改自动定位到对应正文</li>
            <li><Check :size="13" /> AI 建议必须确认后才进入课程</li>
            <li><Check :size="13" /> 已应用 {{ appliedCount }} 个方案，待确认 {{ pendingCount }} 个</li>
          </ul>
          <div class="surface-actions">
            <button type="button" @click="openSurface('learning')">进入学习现场 <ArrowRight :size="14" /></button>
            <button type="button" class="purple" @click="openSurface('growth')">打开课程生长 <Sparkles :size="14" /></button>
          </div>
        </article>
      </section>

      <section class="flex-entry">
        <div>
          <small>灵活操作</small>
          <h2>不必每次从头走，也不会丢失上下文</h2>
          <p>流程条始终显示当前所在位置；任意跳转后，课程 ID、目标小节、同源差异和学习证据都会继续保留。</p>
        </div>
        <div class="entry-grid">
          <button type="button" @click="openSurface('design')"><Presentation :size="17" /><span><strong>从教学设计开始</strong><small>编辑 PPT、分析影响</small></span></button>
          <button type="button" @click="openSurface('learning')"><BookOpenText :size="17" /><span><strong>从课程正文开始</strong><small>阅读、练习、查看同源改动</small></span></button>
          <button type="button" @click="openSurface('growth')"><Sparkles :size="17" /><span><strong>从学习证据开始</strong><small>对话、审核、课程生长</small></span></button>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown, ArrowRight, BookOpenText, Check, GitBranch, Layers3, Link2, LoaderCircle,
  Play, Presentation, RefreshCw, Sparkles, Workflow,
} from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useCourseEvolutionStore } from '../stores/courseEvolution'
import { peekPptSameSourceHighlight, type PptSameSourceHighlightState } from '../utils/ppt-same-source'

type Surface = 'design' | 'learning' | 'growth'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const evolutionStore = useCourseEvolutionStore()
const loading = ref(true)
const syncState = ref<PptSameSourceHighlightState | null>(null)
let loadAttempt = 0

const courseId = computed(() => String(route.params.courseId || ''))
const courseTitle = computed(() => courseStore.currentCourse?.course_name
  || (courseId.value === 'demo-matrix-growth-v2' ? '矩阵与线性变换' : '启智课程'))
const nodeCount = computed(() => courseStore.nodes.length || courseStore.currentCourse?.node_count || 0)
const versionLabel = computed(() => (courseStore.currentCourseVersionId || courseStore.currentDocumentRevision || '当前').slice(0, 12))
const appliedCount = computed(() => evolutionStore.courseId === courseId.value ? evolutionStore.appliedPlans.length : 0)
const pendingCount = computed(() => evolutionStore.courseId === courseId.value ? evolutionStore.pendingPlans.length : 0)
const targetNodeId = computed(() => syncState.value?.sectionId || courseStore.currentCourse?.resume?.node_id || '')
const resumeLabel = computed(() => targetNodeId.value ? '继续当前课程' : '进入课程学习')

async function loadWorkbench() {
  const id = courseId.value
  if (!id) return
  const attempt = ++loadAttempt
  loading.value = true
  syncState.value = peekPptSameSourceHighlight(sessionStorage, id)
  try {
    if (!courseStore.courseList.length) await courseStore.fetchCourseList()
    if (courseStore.currentCourseId !== id || !courseStore.nodes.length) await courseStore.loadCourse(id)
    if (courseStore.currentCourseProjection === 'published') await evolutionStore.load(id).catch(() => undefined)
  } finally {
    if (attempt === loadAttempt) loading.value = false
  }
}

function openSurface(surface: Surface) {
  const id = courseId.value
  if (!id) return
  if (surface === 'design') {
    void router.push({ name: 'ppt-workspace', params: { courseId: id } })
    return
  }
  const nodeId = targetNodeId.value
  void router.push({
    name: 'learning',
    params: { courseId: id, ...(nodeId ? { nodeId } : {}) },
    query: surface === 'growth' ? { surface: 'growth' } : {},
  })
}

watch(courseId, loadWorkbench)
onMounted(loadWorkbench)
</script>

<style scoped>
.course-workbench-view { width:100%; height:100%; overflow:auto; padding:clamp(18px,3vw,34px); border:1px solid rgba(255,255,255,.86); border-radius:var(--lz-radius-surface); background:linear-gradient(145deg,rgba(248,251,255,.96),rgba(255,255,255,.9)); box-shadow:var(--lz-shadow-panel); }
.workbench-loading { min-height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#2d4770; }
.workbench-loading strong { margin-top:14px; font-size:16px; }.workbench-loading span { margin-top:6px; color:#718096; font-size:12px; }.spin { animation:spin 1s linear infinite; }
.workbench-hero { max-width:1320px; display:flex; align-items:flex-end; justify-content:space-between; gap:30px; margin:0 auto; padding:8px 4px 26px; }
.workbench-hero__copy { max-width:820px; }.workbench-eyebrow { display:inline-flex; align-items:center; gap:7px; color:#2556d8; font-size:11px; font-weight:800; letter-spacing:.08em; }
.workbench-hero h1 { margin:10px 0 0; color:#172b4d; font-family:"Songti SC","STSong","Noto Serif CJK SC",serif; font-size:clamp(30px,4vw,48px); line-height:1.12; }
.workbench-hero p { max-width:760px; margin:13px 0 0; color:#5f6f84; font-size:14px; line-height:1.75; }.workbench-meta { display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }
.workbench-meta span { display:inline-flex; align-items:center; gap:5px; padding:5px 8px; border:1px solid #dce6f5; border-radius:999px; color:#55708e; background:#f8fbff; font-size:9px; font-weight:700; }
.workbench-hero__actions { display:flex; flex-direction:column; gap:8px; flex:0 0 auto; }.workbench-hero__actions button,.loop-surface button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 14px; border:1px solid #d5deeb; border-radius:9px; color:#31527d; background:#fff; font-size:11px; font-weight:750; cursor:pointer; }
.workbench-hero__actions button.primary { border-color:#2556d8; color:#fff; background:#2556d8; box-shadow:0 9px 20px rgba(37,86,216,.22); }
.course-loop { max-width:1320px; display:grid; grid-template-columns:minmax(0,1fr) minmax(210px,.58fr) minmax(0,1fr); gap:16px; margin:0 auto; }
.loop-surface { min-width:0; display:flex; flex-direction:column; padding:22px; border:1px solid #dce4ef; border-radius:18px; background:#fff; box-shadow:0 14px 34px rgba(31,55,90,.07); }
.loop-surface.is-teacher { border-top:3px solid #2556d8; }.loop-surface.is-learner { border-top:3px solid #7c3aed; }
.surface-heading { display:flex; align-items:center; gap:10px; }.surface-icon { width:40px; height:40px; flex:0 0 40px; display:grid; place-items:center; border-radius:12px; color:#2556d8; background:#edf3ff; }.is-learner .surface-icon { color:#7c3aed; background:#f5efff; }
.surface-heading > div { min-width:0; flex:1; }.surface-heading small { color:#8290a3; font-size:8px; font-weight:800; letter-spacing:.12em; }.surface-heading h2 { margin:3px 0 0; color:#26364d; font-size:16px; }.surface-state { padding:4px 7px; border-radius:999px; color:#315a95; background:#edf5ff; font-size:8px; font-weight:750; }.surface-state.is-purple { color:#6d28a8; background:#f6edff; }
.loop-surface > p { margin:15px 0 0; color:#68778b; font-size:11px; line-height:1.7; }.loop-surface ul { display:grid; gap:8px; margin:16px 0 20px; padding:0; list-style:none; }.loop-surface li { display:flex; align-items:flex-start; gap:7px; color:#42556f; font-size:10px; line-height:1.45; }.loop-surface li svg { flex:0 0 auto; margin-top:1px; color:#5278c8; }.is-learner li svg { color:#8b5acf; }.loop-surface > button,.surface-actions { margin-top:auto; }.surface-actions { display:flex; flex-wrap:wrap; gap:7px; }.surface-actions button.purple { border-color:#decdf8; color:#6d28a8; background:#faf7ff; }
.loop-bridge { position:relative; min-height:340px; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:16px 11px; text-align:center; }.bridge-line { position:absolute; top:50%; right:-16px; left:-16px; height:2px; background:linear-gradient(90deg,#9bb6ef,#e6bf45,#bea2ed); }.bridge-core { position:relative; z-index:1; width:126px; height:126px; display:flex; flex-direction:column; align-items:center; justify-content:center; border:1px solid #d2deef; border-radius:50%; color:#486581; background:#fff; box-shadow:0 13px 32px rgba(31,55,90,.12); }.bridge-core small { margin-top:7px; color:#7b8ca0; font-size:8px; }.bridge-core strong { margin-top:3px; color:#284765; font-size:10px; }.loop-bridge.is-synced .bridge-core { border-color:#edcb54; color:#986a00; background:#fffdf1; }
.bridge-diff { position:relative; z-index:1; width:100%; display:grid; gap:4px; margin-top:13px; padding:10px; border:1px solid #efda87; border-radius:10px; color:#69562c; background:#fffdf6; font-size:8px; line-height:1.4; }.bridge-diff small { color:#9a7311; font-weight:800; }.bridge-diff span { text-decoration:line-through; opacity:.65; }.bridge-diff svg { justify-self:center; }.bridge-diff strong { color:#60480b; }.loop-bridge > p { position:relative; z-index:1; margin:13px 0 0; padding:8px; color:#718096; background:rgba(248,251,255,.94); font-size:9px; line-height:1.55; }
.flex-entry { max-width:1320px; display:grid; grid-template-columns:minmax(240px,.75fr) minmax(0,1.4fr); align-items:center; gap:28px; margin:18px auto 0; padding:20px 22px; border:1px solid #dce5f1; border-radius:16px; background:linear-gradient(100deg,#f5f8ff,#fff 55%,#faf7ff); }.flex-entry > div > small { color:#2556d8; font-size:9px; font-weight:800; letter-spacing:.12em; }.flex-entry h2 { margin:6px 0 0; color:#26364d; font-size:17px; }.flex-entry p { margin:7px 0 0; color:#718096; font-size:10px; line-height:1.6; }.entry-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }.entry-grid button { min-width:0; display:flex; align-items:center; gap:9px; padding:11px; border:1px solid #dbe3ee; border-radius:10px; color:#425e86; background:#fff; text-align:left; cursor:pointer; }.entry-grid button:hover { border-color:#9fb7eb; transform:translateY(-1px); }.entry-grid button > span { min-width:0; display:flex; flex-direction:column; }.entry-grid strong { font-size:10px; }.entry-grid small { margin-top:3px; overflow:hidden; color:#8290a3; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:980px) { .course-loop { grid-template-columns:1fr; }.loop-bridge { min-height:190px; }.bridge-line { top:-16px; bottom:-16px; left:50%; width:2px; height:auto; }.bridge-diff,.loop-bridge > p { max-width:420px; }.flex-entry { grid-template-columns:1fr; }.workbench-hero { align-items:flex-start; flex-direction:column; }.workbench-hero__actions { flex-direction:row; } }
@media (max-width:680px) { .course-workbench-view { padding:12px; }.entry-grid { grid-template-columns:1fr; }.workbench-hero__actions,.surface-actions { width:100%; }.workbench-hero__actions button,.surface-actions button { flex:1; } }
</style>
