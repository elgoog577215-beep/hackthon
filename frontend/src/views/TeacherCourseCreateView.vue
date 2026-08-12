<template>
  <section class="course-create-page">
    <header class="product-bar">
      <button type="button" class="brand" @click="backToCourses"><img src="/qizhi-favicon.svg" alt="" /><strong>启智</strong></button>
      <nav :aria-label="t('teacherWorkbench.breadcrumb', '当前位置')">
        <button type="button" @click="backToCourses">{{ t('teacherWorkbench.courseWorkbench', '课程工作台') }}</button>
        <ChevronRight :size="14" /><strong>{{ t('teacherCourseCreate.title', '新建课程') }}</strong>
      </nav>
      <div class="product-actions"><button type="button" @click="backToCourses"><X :size="16" />{{ t('common.cancel', '取消') }}</button></div>
    </header>

    <div class="create-shell">
      <aside class="step-sidebar">
        <div class="step-title"><span>{{ draft.title.trim().slice(0, 1) || '+' }}</span><div><strong>{{ draft.title || t('teacherCourseCreate.untitled', '未命名课程') }}</strong><small>{{ t('teacherCourseCreate.savedLocally', '创建前草稿保存在本机') }}</small></div></div>
        <nav aria-label="新建课程步骤">
          <button v-for="item in steps" :key="item.id" type="button" :class="{ active: step === item.id, completed: step > item.id }" :disabled="item.id > maxReachableStep" @click="step = item.id">
            <span>{{ item.id }}</span><span><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></span><Check v-if="step > item.id" :size="14" />
          </button>
        </nav>
        <button type="button" class="discard-button" @click="discardDraft"><Trash2 :size="15" />{{ t('teacherCourseCreate.discard', '放弃本次草稿') }}</button>
      </aside>

      <main class="create-main">
        <div class="status-bar" role="status"><strong>{{ draft.title || t('teacherCourseCreate.title', '新建课程') }}</strong><span>{{ t('teacherCourseCreate.step', '步骤') }} {{ step }}/3</span><span>{{ saveStateLabel }}</span><span v-if="step > 1">{{ academicTerm || '未设置学期' }}</span><span v-if="step > 1">预计 {{ draft.expectedSessions }} 课次</span><span class="spacer"></span><span>{{ t('teacherCourseCreate.createOnce', '提交时只创建一次真实生成任务') }}</span></div>

        <form class="step-body" @submit.prevent="continueStep">
          <template v-if="step === 1">
            <header><small>01</small><h1>{{ t('teacherCourseCreate.identityTitle', '先确定课程身份') }}</h1></header>
            <div class="form-grid">
              <label class="wide"><span>{{ t('teacherCourseCreate.courseName', '课程名称') }}</span><input v-model.trim="draft.title" maxlength="200" autocomplete="off" :placeholder="t('teacherCourseCreate.courseNamePlaceholder', '例如：设计思维与创新设计')" autofocus /></label>
              <label><span>{{ t('teacherCourseCreate.audience', '授课对象') }}</span><input v-model.trim="draft.audience" maxlength="100" :placeholder="t('teacherCourseCreate.audiencePlaceholder', '例如：本科二年级')" /></label>
              <label><span>{{ t('teacherCourseCreate.courseCode', '课程代码（可后补）') }}</span><input v-model.trim="draft.courseCode" maxlength="64" placeholder="CS0900G" /></label>
              <label class="wide"><span>{{ t('teacherCourseCreate.goal', '课程目标摘要') }}</span><textarea v-model.trim="draft.goal" rows="4" maxlength="1500" :placeholder="t('teacherCourseCreate.goalPlaceholder', '写清学生完成课程后能做什么；AI 会把它作为大纲生成依据。')"></textarea></label>
            </div>
          </template>

          <template v-else-if="step === 2">
            <header><small>02</small><h1>{{ t('teacherCourseCreate.scheduleTitle', '补充排课基础') }}</h1></header>
            <div class="schedule-sections">
              <section><h2>学期与课程容量</h2><div class="form-grid schedule-grid">
                <label><span>{{ t('teacherCourseCreate.academicYear', '学年') }}</span><input v-model.trim="draft.academicYear" placeholder="2026-2027" /></label>
                <label><span>{{ t('teacherCourseCreate.term', '学期') }}</span><select v-model="draft.term"><option value="">{{ t('teacherCourseCreate.termUnset', '暂不设置') }}</option><option>{{ t('teacherCourseCreate.autumnWinter', '秋冬') }}</option><option>{{ t('teacherCourseCreate.springSummer', '春夏') }}</option></select></label>
                <label><span>{{ t('teacherCourseCreate.totalHours', '总学时') }}</span><input v-model.number="draft.totalHours" type="number" min="1" max="300" /></label>
                <label><span>{{ t('teacherCourseCreate.expectedSessions', '预计课次') }}</span><input v-model.number="draft.expectedSessions" type="number" min="1" max="120" /></label>
              </div></section>
              <section><h2>默认上课设置</h2><div class="form-grid schedule-grid">
                <label><span>{{ t('teacherCourseCreate.lessonDuration', '单次课时长（分钟）') }}</span><input v-model.number="draft.lessonDuration" type="number" min="15" max="300" step="5" /></label>
                <label><span>{{ t('teacherCourseCreate.defaultLocation', '常用地点（可后补）') }}</span><input v-model.trim="draft.defaultLocation" :placeholder="t('teacherCourseCreate.locationPlaceholder', '例如：紫金港西1-205')" /></label>
              </div></section>
            </div>
            <div class="boundary-note"><Info :size="16" /><span>{{ t('teacherCourseCreate.scheduleBoundary', '这些字段用于后续教学日历。现在可以跳过；确认大纲后，教学日历与分讲教案可以并行。') }}</span></div>
          </template>

          <template v-else>
            <header><small>03</small><h1>{{ t('teacherCourseCreate.startTitle', '选择教学大纲起点') }}</h1></header>
            <div class="starting-summary"><strong>{{ draft.title }}</strong><span>{{ draft.audience }}</span><span>{{ academicTerm || '学期可后补' }}</span><span>{{ draft.totalHours }} 学时 · 预计 {{ draft.expectedSessions }} 课次</span></div>
            <div class="starting-options">
              <button type="button" class="starting-option" data-testid="start-ai-course" @click="openGenerationDialog">
                <Sparkles :size="20" /><span><strong>{{ t('teacherCourseCreate.aiStart', 'AI 规划大纲') }}</strong><small>{{ t('teacherCourseCreate.aiStartDetail', '使用现有真实生成流程，可加入参考资料和联网搜索。') }}</small></span><ArrowRight :size="17" />
              </button>
              <button type="button" class="starting-option" data-testid="import-outline-course" :disabled="importing" @click="fileInput?.click()">
                <Upload :size="20" /><span><strong>{{ t('teacherCourseCreate.importStart', '导入已有大纲') }}</strong><small>{{ t('teacherCourseCreate.importStartDetail', '第一版先接现有 Markdown 导入；Word/PDF 识别在正式导入变更中实现。') }}</small></span><ArrowRight :size="17" />
              </button>
              <button type="button" class="starting-option" disabled>
                <FilePlus2 :size="20" /><span><strong>{{ t('teacherCourseCreate.blankStart', '空白开始') }}</strong><small>{{ t('teacherCourseCreate.blankStartDetail', '当前后端没有空白课程壳接口，暂不伪造成功。') }}</small></span><LockKeyhole :size="16" />
              </button>
              <input ref="fileInput" type="file" accept=".md,.markdown,text/markdown" class="sr-only" @change="importOutline" />
            </div>
            <div v-if="operationError" class="error-bar" role="alert"><TriangleAlert :size="16" /><span><strong>{{ t('teacherCourseCreate.failed', '未能开始课程') }}</strong>{{ operationError }}</span></div>
          </template>

          <footer>
            <button v-if="step > 1" type="button" class="secondary-button" @click="step -= 1"><ArrowLeft :size="16" />{{ t('common.previous', '上一步') }}</button>
            <span></span>
            <button v-if="step < 3" type="submit" class="primary-button">{{ t('common.next', '下一步') }}<ArrowRight :size="16" /></button>
          </footer>
        </form>
      </main>
    </div>

    <CourseGenerationDialog
      v-model="generationDialogOpen"
      :busy="creating"
      :initial-subject="draft.title"
      :initial-audience="draft.audience"
      :initial-academic-term="academicTerm"
      :initial-total-class-hours="draft.totalHours"
      :initial-lesson-duration-minutes="draft.lessonDuration"
      @generate="generateCourse"
      @error="message => operationError = message"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Check, ChevronRight, FilePlus2, Info, LockKeyhole, Sparkles, Trash2, TriangleAlert, Upload, X } from 'lucide-vue-next'
import CourseGenerationDialog from '../components/CourseGenerationDialog.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'

type Draft = {
  title: string
  audience: string
  courseCode: string
  goal: string
  academicYear: string
  term: string
  totalHours: number
  lessonDuration: number
  expectedSessions: number
  defaultLocation: string
  step: number
  updatedAt: string
}

const STORAGE_KEY = 'teacher_course_create_draft_v1'
const router = useRouter()
const courseStore = useCourseStore()
const step = ref(1)
const generationDialogOpen = ref(false)
const creating = ref(false)
const importing = ref(false)
const operationError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const savedAt = ref('')
const draft = reactive<Draft>({ title: '', audience: '大学本科生', courseCode: '', goal: '', academicYear: '', term: '', totalHours: 32, lessonDuration: 45, expectedSessions: 16, defaultLocation: '', step: 1, updatedAt: '' })
const steps = computed(() => [
  { id: 1, label: t('teacherCourseCreate.identity', '课程身份'), detail: t('teacherCourseCreate.identityDetail', '名称、对象、目标') },
  { id: 2, label: t('teacherCourseCreate.schedule', '排课基础'), detail: t('teacherCourseCreate.scheduleDetail', '学期、学时、课次') },
  { id: 3, label: t('teacherCourseCreate.outlineStart', '大纲起点'), detail: t('teacherCourseCreate.outlineStartDetail', '生成、导入或空白') },
])
const maxReachableStep = computed(() => draft.title.trim() ? 3 : 1)
const academicTerm = computed(() => [draft.academicYear, draft.term].filter(Boolean).join(' '))
const saveStateLabel = computed(() => savedAt.value ? t('teacherCourseCreate.saved', '草稿已保存') : t('teacherCourseCreate.unsaved', '正在保存草稿'))

function persistDraft() {
  const updatedAt = new Date().toISOString()
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...draft, step: step.value, updatedAt }))
  savedAt.value = updatedAt
}
function restoreDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (saved && typeof saved === 'object') Object.assign(draft, saved)
    step.value = Math.min(Math.max(Number(draft.step || 1), 1), draft.title.trim() ? 3 : 1)
    savedAt.value = draft.updatedAt
  } catch { localStorage.removeItem(STORAGE_KEY) }
}
function continueStep() {
  operationError.value = ''
  if (step.value === 1 && !draft.title.trim()) { operationError.value = t('teacherCourseCreate.nameRequired', '请先填写课程名称。'); ElMessage.warning(operationError.value); return }
  if (step.value < 3) step.value += 1
}
function backToCourses() { void router.push('/courses') }
async function discardDraft() {
  try {
    await ElMessageBox.confirm(t('teacherCourseCreate.discardConfirm', '确认放弃当前新建课程草稿？'), t('teacherCourseCreate.discard', '放弃本次草稿'), { type: 'warning', confirmButtonText: t('teacherCourseCreate.discard', '放弃本次草稿'), cancelButtonText: t('common.cancel', '取消') })
    localStorage.removeItem(STORAGE_KEY)
    backToCourses()
  } catch { /* cancelled */ }
}
function openGenerationDialog() { operationError.value = ''; generationDialogOpen.value = true }
async function generateCourse(payload: { subject: string; options: CourseGenerationOptions }) {
  if (creating.value) return
  creating.value = true
  operationError.value = ''
  try {
    const result = await courseStore.generateCourse(payload.subject, payload.options)
    if (!result?.courseId) { operationError.value = t('courseLibrary.createFailed', '课程创建失败'); return }
    localStorage.removeItem(STORAGE_KEY)
    generationDialogOpen.value = false
    void router.push({ name: 'teacher-course-production', params: { courseId: result.courseId } })
    void courseStore.fetchCourseList()
  } catch (error: any) { operationError.value = String(error?.response?.data?.detail || error?.message || t('courseLibrary.createFailed', '课程创建失败')) }
  finally { creating.value = false }
}
async function importOutline(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || importing.value) return
  importing.value = true
  operationError.value = ''
  try {
    const result = await courseStore.importMarkdown(file)
    localStorage.removeItem(STORAGE_KEY)
    void router.push({ name: 'teacher-course-overview', params: { courseId: result.course_id } })
  } catch (error: any) { operationError.value = String(error?.response?.data?.detail || error?.message || t('courseLibrary.importFailed', '课程导入失败')) }
  finally { importing.value = false; target.value = '' }
}

watch([step, () => ({ ...draft })], persistDraft, { deep: true })
onMounted(restoreDraft)
</script>

<style scoped>
.course-create-page{min-height:100vh;height:100vh;overflow:hidden;color:var(--lz-text-primary);background:var(--lz-canvas)}button,input,textarea,select{font:inherit}.product-bar{height:52px;display:grid;grid-template-columns:220px minmax(0,1fr) auto;align-items:center;border-bottom:1px solid var(--lz-border);background:var(--lz-surface)}.brand{height:100%;display:flex;align-items:center;gap:10px;padding:0 20px;border:0;border-right:1px solid var(--lz-border);color:var(--lz-text-primary);background:transparent;cursor:pointer}.brand img{width:25px;height:25px}.brand strong{font-size:17px}.product-bar nav{min-width:0;display:flex;align-items:center;gap:8px;padding:0 24px;color:var(--lz-text-muted);font-size:12px}.product-bar nav button{padding:0;border:0;color:inherit;background:transparent;cursor:pointer}.product-bar nav strong{color:var(--lz-text-primary)}.product-actions{padding-right:14px}.product-actions button{height:34px;display:flex;align-items:center;gap:6px;padding:0 11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}
.create-shell{height:calc(100vh - 52px);display:grid;grid-template-columns:220px minmax(0,1fr)}.step-sidebar{min-height:0;display:flex;flex-direction:column;border-right:1px solid var(--lz-border);background:var(--lz-surface)}.step-title{min-height:76px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--lz-border)}.step-title>span{width:36px;height:36px;display:grid;place-items:center;border-radius:10px;color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-weight:800}.step-title>div{min-width:0;display:grid;gap:3px}.step-title strong,.step-title small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.step-title strong{font-size:12px}.step-title small{color:var(--lz-text-muted);font-size:9px}.step-sidebar nav{display:grid;gap:4px;padding:12px 8px}.step-sidebar nav button{min-height:52px;display:grid;grid-template-columns:26px minmax(0,1fr) 18px;align-items:center;gap:7px;padding:6px 9px;border:1px solid transparent;border-radius:8px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.step-sidebar nav button:disabled{opacity:.45;cursor:not-allowed}.step-sidebar nav button.active{border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.step-sidebar nav button>span:first-child{width:23px;height:23px;display:grid;place-items:center;border-radius:50%;color:var(--lz-text-muted);background:var(--lz-fill);font-size:9px;font-weight:800}.step-sidebar nav button.completed>span:first-child{color:var(--lz-success);background:var(--lz-success-soft)}.step-sidebar nav button>span:nth-child(2){min-width:0;display:grid;gap:2px}.step-sidebar nav strong{font-size:11px}.step-sidebar nav small{color:var(--lz-text-muted);font-size:9px}.discard-button{margin-top:auto;height:42px;display:flex;align-items:center;gap:7px;padding:0 17px;border:0;border-top:1px solid var(--lz-border);color:var(--lz-text-muted);background:transparent;cursor:pointer}
.create-main{min-width:0;min-height:0;display:grid;grid-template-rows:42px minmax(0,1fr)}.status-bar{display:flex;align-items:center;padding:0 16px;border-bottom:1px solid var(--lz-border);background:var(--lz-surface);font-size:11px;white-space:nowrap}.status-bar>strong,.status-bar>span{padding:0 11px;border-right:1px solid var(--lz-border)}.status-bar>strong{padding-left:0}.status-bar .spacer{flex:1;border:0}.step-body{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr) 54px;overflow:auto;padding:24px clamp(24px,5vw,72px) 0;background:var(--lz-surface)}.step-body>header{max-width:860px;width:100%;margin:0 auto 18px}.step-body>header small{color:var(--lz-brand);font-size:10px;font-weight:800}.step-body h1{margin:4px 0 0;font-size:22px}.form-grid,.starting-options,.boundary-note,.error-bar{width:100%;max-width:860px;margin:0 auto}.form-grid{align-self:start;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px 22px}.form-grid label{display:grid;gap:7px;color:var(--lz-text-secondary);font-size:10px;font-weight:700}.form-grid label.wide{grid-column:1/-1}.form-grid input,.form-grid textarea,.form-grid select{width:100%;box-sizing:border-box;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-primary);background:var(--lz-surface);outline:0}.form-grid input,.form-grid select{height:38px;padding:0 10px}.form-grid textarea{padding:10px;resize:vertical;line-height:1.6}.form-grid input:focus,.form-grid textarea:focus,.form-grid select:focus{border-color:var(--lz-brand);box-shadow:0 0 0 3px rgb(99 102 241 / 9%)}.boundary-note{align-self:start;display:flex;align-items:flex-start;gap:8px;margin-top:18px;padding:10px 12px;border:1px solid var(--lz-warning-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-warning-soft);font-size:10px;line-height:1.6}.starting-options{align-self:start;border-top:1px solid var(--lz-border)}.starting-option{width:100%;min-height:68px;display:grid;grid-template-columns:32px minmax(0,1fr) 20px;align-items:center;gap:10px;padding:10px 8px;border:0;border-bottom:1px solid var(--lz-border);color:var(--lz-brand-strong);background:transparent;text-align:left;cursor:pointer}.starting-option:hover:not(:disabled){background:var(--lz-brand-soft)}.starting-option:disabled{opacity:.55;cursor:not-allowed}.starting-option>span{display:grid;gap:4px}.starting-option strong{color:var(--lz-text-primary);font-size:12px}.starting-option small{color:var(--lz-text-muted);font-size:10px;line-height:1.5}.error-bar{align-self:start;display:flex;gap:8px;margin-top:14px;padding:10px 12px;border:1px solid var(--lz-danger-border);border-radius:8px;color:var(--lz-danger);background:var(--lz-danger-soft);font-size:10px}.error-bar span{display:grid;gap:3px}.step-body>footer{position:sticky;bottom:0;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;margin-top:22px;padding:9px 0;border-top:1px solid var(--lz-border);background:var(--lz-surface)}.primary-button,.secondary-button{height:36px;display:inline-flex;align-items:center;gap:6px;padding:0 13px;border-radius:8px;cursor:pointer}.primary-button{border:1px solid var(--lz-brand);color:#fff;background:var(--lz-brand)}.secondary-button{border:1px solid var(--lz-border);color:var(--lz-text-secondary);background:var(--lz-surface)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
/* Compact teacher-workbench proportions: dense steps, readable form column, no bottom-docked action. */
.product-bar{grid-template-columns:188px minmax(0,1fr) auto}.product-bar nav{padding-inline:20px}.product-actions button{height:32px;border-radius:8px}
.create-shell{grid-template-columns:188px minmax(0,1fr)}.step-title{min-height:68px;padding-inline:13px}.step-title>span{width:32px;height:32px;border-radius:9px}.step-sidebar nav{gap:3px;padding:10px 7px}.step-sidebar nav button{min-height:50px;grid-template-columns:25px minmax(0,1fr) 16px;gap:6px;padding:6px 8px}.discard-button{padding-inline:14px}
.status-bar{padding-inline:14px}.status-bar>strong,.status-bar>span{padding-inline:10px}.status-bar>strong{padding-left:0}
.step-body{display:block;padding:30px clamp(28px,5vw,64px) 48px}.step-body>header{max-width:760px;margin-bottom:22px}.step-body h1{font-size:24px;line-height:1.3}.form-grid,.starting-options,.starting-summary,.schedule-sections,.boundary-note,.error-bar{max-width:760px}.form-grid{gap:16px 20px}.form-grid label{font-size:11px}.form-grid input,.form-grid select{height:42px;padding-inline:11px;font-size:12px}.form-grid textarea{min-height:104px;padding:10px 11px;font-size:12px}.schedule-sections{width:100%;margin:0 auto;display:grid;gap:20px}.schedule-sections section{display:grid;gap:12px}.schedule-sections section+section{padding-top:18px;border-top:1px solid var(--lz-border)}.schedule-sections h2{margin:0;color:var(--lz-text-primary);font-size:12px}.starting-summary{min-height:36px;display:flex;align-items:center;margin:-6px auto 12px;overflow-x:auto;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:10px;white-space:nowrap}.starting-summary strong,.starting-summary span{padding:0 10px;border-right:1px solid var(--lz-border)}.starting-summary strong{padding-left:0;color:var(--lz-text-primary);font-size:11px}.starting-option{min-height:72px;gap:11px;padding-block:11px}.starting-option strong{font-size:13px}.boundary-note{margin-top:18px}.step-body>footer{position:static;width:100%;max-width:760px;display:flex;align-items:center;margin:24px auto 0;padding:14px 0 0}.step-body>footer>span{flex:1}
@media(max-width:900px){.product-bar{grid-template-columns:64px minmax(0,1fr) auto}.brand{justify-content:center;padding:0}.brand strong{display:none}.create-shell{grid-template-columns:64px minmax(0,1fr)}.step-title>div,.step-sidebar nav button>span:nth-child(2),.discard-button{display:none}.step-title{justify-content:center;padding:0}.step-sidebar nav button{grid-template-columns:1fr;justify-items:center;padding:0}.step-sidebar nav button>svg{display:none}.status-bar>span:last-child{display:none}.step-body{padding-inline:24px}}
@media(max-width:680px){.course-create-page{height:auto;min-height:100vh;overflow:auto}.create-shell{height:auto;display:block}.step-sidebar{min-height:auto;border-right:0;border-bottom:1px solid var(--lz-border)}.step-title{display:none}.step-sidebar nav{display:flex;overflow-x:auto;padding:6px 8px}.step-sidebar nav button{flex:0 0 auto;width:auto;min-height:34px;display:inline-flex;gap:6px;padding:0 10px}.step-sidebar nav button>span:nth-child(2){display:block}.step-sidebar nav small{display:none}.create-main{min-height:calc(100vh - 94px);grid-template-rows:38px minmax(0,1fr)}.status-bar>span{display:none}.step-body{padding:18px 14px 0}.form-grid{grid-template-columns:1fr}.form-grid label.wide{grid-column:auto}.product-bar nav{padding:0 10px}.product-bar nav button,.product-bar nav svg{display:none}.product-actions button{width:34px;padding:0}.product-actions button{font-size:0}}
</style>
