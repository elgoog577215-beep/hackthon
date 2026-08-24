<template>
  <Teleport to="body">
    <div v-if="modelValue" class="course-information-layer" @keydown.esc="close">
      <button
        class="course-information-backdrop"
        type="button"
        :aria-label="t('common.close', '关闭')"
        @click="close"
      />
      <section
        ref="dialogRef"
        class="course-information-dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="dialog-heading">
          <span class="dialog-heading__mark"><Database :size="18" /></span>
          <h2 :id="titleId">{{ t('courseFiles.workbench.courseInformationTitle', '课程基础信息') }}</h2>
          <button class="icon-button" type="button" :aria-label="t('common.close', '关闭')" :disabled="saving" @click="close">
            <X :size="18" />
          </button>
        </header>

        <div class="dialog-body">
          <section v-if="loading" class="dialog-state" role="status">
            <LoaderCircle class="spin" :size="22" />
            <strong>{{ t('courseFiles.workbench.courseInformationLoading', '正在读取课程基础信息') }}</strong>
          </section>

          <section v-else-if="loadError && !original" class="dialog-state is-error" role="alert">
            <TriangleAlert :size="22" />
            <strong>{{ t('courseFiles.workbench.courseInformationLoadFailed', '课程基础信息读取失败') }}</strong>
            <p>{{ loadError }}</p>
            <button type="button" @click="loadInformation">{{ t('common.retry', '重试') }}</button>
          </section>

          <template v-else-if="original">
            <p v-if="successMessage" class="save-status" role="status"><CheckCircle2 :size="16" />{{ successMessage }}</p>
            <p v-if="saveError" class="save-error" role="alert">
              <TriangleAlert :size="16" />
              <span>{{ saveError }}</span>
              <button v-if="conflict" type="button" @click="loadInformation">{{ t('courseFiles.workbench.reloadLatest', '重新读取最新设置') }}</button>
            </p>

            <div v-if="mode === 'view'" class="information-view">
              <section class="course-identity">
                <div>
                  <small>{{ t('teacherCourseCreate.courseName', '课程名称') }}</small>
                  <strong>{{ original.course_name }}</strong>
                </div>
                <b>{{ t('courseFiles.workbench.revisionLabel', '修订 {revision}').replace('{revision}', String(envelope?.revision ?? 0)) }}</b>
              </section>

              <section v-for="group in viewGroups" :key="group.title" class="information-group">
                <header><component :is="group.icon" :size="17" /><h3>{{ group.title }}</h3></header>
                <dl>
                  <div v-for="item in group.items" :key="item.label" :class="{ wide: item.wide }">
                    <dt>{{ item.label }}</dt>
                    <dd :data-empty="item.empty || undefined">{{ item.value }}</dd>
                  </div>
                </dl>
              </section>
            </div>

            <form v-else-if="mode === 'edit'" class="information-form" @submit.prevent="reviewChanges">
              <section class="form-section">
                <header><BookOpen :size="17" /><h3>{{ t('courseFiles.workbench.identityAndSchedule', '课程身份与排课') }}</h3></header>
                <div class="field-grid field-grid--three">
                  <label><span>{{ t('teacherCourseCreate.courseCode', '课程代码') }}</span><input v-model.trim="draft.course_profile.course_code" maxlength="64" /></label>
                  <label><span>{{ t('teacherCourseCreate.courseCategory', '课程类别') }}</span><input v-model.trim="draft.course_profile.course_category" maxlength="100" /></label>
                  <label><span>{{ t('teacherCourseCreate.credits', '学分') }}</span><input v-model.number="draft.course_profile.credits" type="number" min="0" max="100" step="0.5" /></label>
                  <label><span>{{ t('teacherCourseCreate.targetMajor', '面向专业') }}</span><input v-model.trim="draft.course_profile.target_major" maxlength="200" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.targetAudience', '教学对象') }} <b>*</b></span><input v-model.trim="draft.course_profile.target_grade" required maxlength="500" /></label>
                  <label><span>{{ t('teacherCourseCreate.defaultLocation', '常用地点') }}</span><input v-model.trim="draft.course_profile.default_location" maxlength="200" /></label>
                  <label><span>{{ t('teacherCourseCreate.academicYear', '学年') }}</span><input v-model.trim="draft.academic_year" maxlength="30" placeholder="2026-2027" /></label>
                  <label><span>{{ t('teacherCourseCreate.term', '学期') }}</span><input v-model.trim="draft.term" maxlength="30" placeholder="秋冬" /></label>
                </div>
              </section>

              <section class="form-section">
                <header><Clock3 :size="17" /><h3>{{ t('courseFiles.workbench.teachingArrangement', '授课安排') }}</h3></header>
                <div class="field-grid field-grid--three">
                  <label><span>{{ t('courseGeneration.teacherBrief.totalHours', '总课时') }} <b>*</b></span><input v-model.number="draft.generation_request.teacher_course_brief.total_class_hours" required type="number" min="1" max="1000" step="1" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.lessonMinutes', '每次课时长（分钟）') }} <b>*</b></span><input v-model.number="draft.generation_request.teacher_course_brief.lesson_duration_minutes" required type="number" min="20" max="240" step="1" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.classSize', '预计班级人数') }}</span><input v-model.number="draft.generation_request.teacher_course_brief.class_size" type="number" min="1" max="1000" step="1" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.chapterCount', '预计章节数') }}</span><input v-model.number="draft.generation_request.teacher_course_brief.chapter_count" type="number" min="1" max="100" step="1" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.sectionCount', '预计课次') }}</span><input v-model.number="draft.generation_request.teacher_course_brief.section_count" type="number" min="1" max="1000" step="1" /></label>
                  <label class="wide"><span>{{ t('courseGeneration.teacherBrief.classProfile', '班级与学情特点') }}</span><textarea v-model.trim="draft.generation_request.teacher_course_brief.class_profile" maxlength="2000" rows="3" /></label>
                </div>
              </section>

              <section class="form-section">
                <header><SlidersHorizontal :size="17" /><h3>{{ t('courseFiles.workbench.courseDesignSettings', '课程设计设置') }}</h3></header>
                <fieldset class="course-type-field">
                  <legend>{{ t('courseGeneration.courseTypes.label', '教学类型') }}</legend>
                  <div class="course-type-options">
                    <button v-for="item in courseTypeOptions" :key="item.value" type="button" :class="{ active: courseType === item.value }" :aria-pressed="courseType === item.value" @click="selectCourseType(item.value)"><component :is="item.icon" :size="16" /><span>{{ item.label }}</span></button>
                  </div>
                </fieldset>
                <div class="field-grid field-grid--three">
                  <label><span>{{ t('courseGeneration.pedagogy.label', '学科类型') }}</span><select v-model="draft.generation_request.pedagogy_mode"><option v-for="item in pedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                  <label><span>{{ t('courseGeneration.pedagogy.secondaryLabel', '辅助学科类型') }}</span><select v-model="draft.generation_request.secondary_mode"><option value="">{{ t('courseGeneration.pedagogy.secondaryNone', '无辅助学科类型') }}</option><option v-for="item in secondaryPedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                  <label><span>{{ t('courseFiles.workbench.difficulty', '难度') }}</span><select v-model="draft.generation_request.difficulty"><option v-for="item in difficultyOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                  <label><span>{{ t('courseFiles.workbench.productionMode', '生产模式') }}</span><select v-model="draft.generation_request.production_mode"><option v-for="item in productionModeOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                </div>

                <div class="intent-fields">
                  <label v-if="courseType === 'systematic'"><span>{{ t('courseFiles.workbench.learningGoal', '课程目标') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.learning_goal" required maxlength="5000" rows="3" /></label>
                  <template v-else-if="courseType === 'project'">
                    <label><span>{{ t('courseGeneration.project.goalLabel', '项目目标') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.project_goal" required maxlength="3000" rows="2" /></label>
                    <label><span>{{ t('courseGeneration.project.deliverableLabel', '预期交付物') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.expected_deliverable" required maxlength="3000" rows="2" /></label>
                  </template>
                  <template v-else-if="courseType === 'inquiry'">
                    <label><span>{{ t('courseGeneration.inquiry.questionLabel', '核心问题') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.core_question" required maxlength="3000" rows="2" /></label>
                    <label><span>{{ t('courseGeneration.inquiry.outputLabel', '期望结果') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.desired_output" required maxlength="3000" rows="2" /></label>
                  </template>
                  <template v-else>
                    <div class="field-grid field-grid--two">
                      <label><span>{{ t('courseGeneration.exam.nameLabel', '考试名称') }} <b>*</b></span><input v-model.trim="draft.generation_request.course_intent.exam_name" required maxlength="1000" /></label>
                      <label><span>{{ t('courseGeneration.exam.dateLabel', '考试日期') }} <b>*</b></span><input v-model="draft.generation_request.course_intent.exam_date" required type="date" /></label>
                    </div>
                    <label><span>{{ t('courseGeneration.exam.scopeLabel', '考试范围') }} <b>*</b></span><textarea v-model.trim="draft.generation_request.course_intent.exam_scope" required maxlength="5000" rows="3" /></label>
                  </template>
                </div>
              </section>

              <section class="form-section">
                <header><FileText :size="17" /><h3>{{ t('courseFiles.workbench.additionalCourseInformation', '其他课程信息') }}</h3></header>
                <div class="intent-fields">
                  <label><span>{{ t('teacherCourseCreate.courseIntro', '课程简介') }}</span><textarea v-model.trim="draft.course_profile.course_intro" maxlength="3000" rows="3" /></label>
                  <label><span>{{ t('teacherCourseCreate.assessmentMethod', '考核方式') }}</span><textarea v-model.trim="draft.course_profile.assessment_method" maxlength="500" rows="2" /></label>
                  <label><span>{{ t('courseGeneration.teacherBrief.additionalRequirements', '其他教学要求') }}</span><textarea v-model.trim="draft.generation_request.teacher_course_brief.additional_requirements" maxlength="10000" rows="3" /></label>
                </div>
              </section>
            </form>

            <section v-else-if="mode === 'review'" class="review-panel">
              <header><FileDiff :size="19" /><h3>{{ restoreRevision === null ? t('courseFiles.workbench.reviewCourseInformationChanges', '确认本次修改') : t('courseFiles.workbench.reviewCourseInformationRestore', '确认恢复历史设置') }}</h3></header>
              <div class="change-list">
                <article v-for="change in changes" :key="change.key">
                  <strong>{{ change.label }}</strong>
                  <div><span>{{ change.before }}</span><ArrowRight :size="15" /><b>{{ change.after }}</b></div>
                </article>
              </div>
            </section>

            <section v-else class="history-panel">
              <header><History :size="19" /><h3>{{ t('courseFiles.workbench.courseInformationHistory', '修改记录') }}</h3></header>
              <ol>
                <li v-for="version in envelope?.versions || []" :key="version.revision">
                  <span><History :size="15" /></span>
                  <div><strong>{{ t('courseFiles.workbench.revisionLabel', '修订 {revision}').replace('{revision}', String(version.revision)) }}</strong><small>{{ version.current ? t('courseFiles.workbench.currentRevision', '当前使用') : formatDate(version.committed_at) }}</small></div>
                  <b v-if="version.current">{{ t('courseFiles.workbench.currentRevision', '当前使用') }}</b>
                  <button v-else type="button" @click="prepareRestore(version)"><RotateCcw :size="14" />{{ t('courseFiles.workbench.restoreRevision', '恢复此版') }}</button>
                </li>
              </ol>
            </section>
          </template>
        </div>

        <footer v-if="original && !loading" class="dialog-footer">
          <template v-if="mode === 'view'">
            <button class="secondary-button" type="button" @click="mode = 'history'"><History :size="15" />{{ t('courseFiles.workbench.courseInformationHistory', '修改记录') }}</button>
            <span />
            <button class="secondary-button" type="button" @click="close">{{ t('common.close', '关闭') }}</button>
            <button class="primary-button" type="button" @click="startEditing"><Pencil :size="15" />{{ t('courseFiles.workbench.editCourseInformation', '编辑课程信息') }}</button>
          </template>
          <template v-else-if="mode === 'edit'">
            <span /><span />
            <button class="secondary-button" type="button" @click="cancelEditing">{{ t('common.cancel', '取消') }}</button>
            <button class="primary-button" type="button" :disabled="!canReview" @click="reviewChanges"><FileDiff :size="15" />{{ t('courseFiles.workbench.reviewChanges', '查看修改') }}</button>
          </template>
          <template v-else-if="mode === 'review'">
            <span /><span />
            <button class="secondary-button" type="button" :disabled="saving" @click="mode = restoreRevision === null ? 'edit' : 'history'">{{ t('common.back', '返回') }}</button>
            <button class="primary-button" type="button" :disabled="saving || !changes.length" @click="saveChanges"><LoaderCircle v-if="saving" class="spin" :size="15" /><Check v-else :size="15" />{{ saving ? t('courseFiles.workbench.baselineSaving', '正在保存') : t('courseFiles.workbench.confirmSaveCourseInformation', '确认保存') }}</button>
          </template>
          <template v-else>
            <span /><span />
            <button class="secondary-button" type="button" @click="mode = 'view'">{{ t('common.back', '返回') }}</button>
            <button class="primary-button" type="button" @click="startEditing"><Pencil :size="15" />{{ t('courseFiles.workbench.editCourseInformation', '编辑课程信息') }}</button>
          </template>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  ArrowRight, BookOpen, Check, CheckCircle2, Clock3, Database, FileDiff,
  FileText, Hammer, History, LoaderCircle, MessageCircleQuestion, Pencil,
  RotateCcw, SlidersHorizontal, Timer, TriangleAlert, X,
} from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import {
  PEDAGOGY_MODE_OPTIONS,
  type CourseType,
} from '../shared/prompt-config'
import http, { teacherRequestConfig } from '../utils/http'

type CourseProfile = {
  course_code: string
  course_goal: string
  default_location: string
  target_grade: string
  course_category: string
  target_major: string
  credits: number | null
  total_hours: number | null
  assessment_method: string
  course_intro: string
  teaching_goals: string
}

type CourseInformation = {
  course_name: string
  academic_year: string
  term: string
  course_profile: CourseProfile
  generation_request: Record<string, any> & {
    teacher_course_brief: Record<string, any>
    course_intent: Record<string, any>
  }
}

type CourseInformationVersion = {
  revision: number
  current: boolean
  source: string
  committed_at: string
  changed_fields: string[]
  information: CourseInformation
}

type CourseInformationEnvelope = {
  course_id: string
  revision: number
  document_revision: string
  information: CourseInformation
  versions: CourseInformationVersion[]
}

type ChangeItem = { key: string; label: string; before: string; after: string }

const props = defineProps<{ modelValue: boolean; courseId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  updated: [payload: CourseInformationEnvelope]
}>()
const titleId = `course-information-title-${Math.random().toString(36).slice(2)}`
const dialogRef = ref<HTMLElement | null>(null)
const envelope = ref<CourseInformationEnvelope | null>(null)
const original = ref<CourseInformation | null>(null)
const draft = ref<CourseInformation>(emptyInformation())
const mode = ref<'view' | 'edit' | 'review' | 'history'>('view')
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const saveError = ref('')
const successMessage = ref('')
const conflict = ref(false)
const restoreRevision = ref<number | null>(null)
let previousFocus: HTMLElement | null = null

const courseTypeOptions = computed(() => ([
  { value: 'systematic' as const, icon: BookOpen, label: t('courseGeneration.courseTypes.systematic.label', '系统学习') },
  { value: 'project' as const, icon: Hammer, label: t('courseGeneration.courseTypes.project.label', '项目实战') },
  { value: 'inquiry' as const, icon: MessageCircleQuestion, label: t('courseGeneration.courseTypes.inquiry.label', '问题探究') },
  { value: 'exam' as const, icon: Timer, label: t('courseGeneration.courseTypes.exam.label', '考试冲刺') },
]))
const difficultyOptions = computed(() => ['beginner', 'intermediate', 'advanced'].map(value => ({ value, label: t(`courseGeneration.difficulty.${value}.label`, value) })))
const pedagogyOptions = computed(() => PEDAGOGY_MODE_OPTIONS.map(item => ({ value: item.value, label: t(item.labelKey, item.value) })))
const secondaryPedagogyOptions = computed(() => pedagogyOptions.value.filter(item => item.value !== 'auto' && item.value !== draft.value.generation_request.pedagogy_mode))
const productionModeOptions = computed(() => ([
  { value: 'manual', label: t('teacherCourseCreate.productionModeManual', '分步确认') },
  { value: 'automatic', label: t('teacherCourseCreate.productionModeAutomatic', '自动衔接') },
]))
const courseType = computed(() => String(draft.value.generation_request.course_type || 'systematic') as CourseType)

const viewGroups = computed(() => {
  if (!original.value) return []
  const info = original.value
  const profile = info.course_profile
  const request = info.generation_request
  const brief = request.teacher_course_brief || {}
  return [
    {
      title: t('courseFiles.workbench.identityAndSchedule', '课程身份与排课'), icon: BookOpen, items: [
        item(t('teacherCourseCreate.courseCode', '课程代码'), profile.course_code),
        item(t('teacherCourseCreate.courseCategory', '课程类别'), profile.course_category),
        item(t('teacherCourseCreate.credits', '学分'), profile.credits),
        item(t('teacherCourseCreate.targetMajor', '面向专业'), profile.target_major),
        item(t('courseGeneration.teacherBrief.targetAudience', '教学对象'), profile.target_grade || brief.target_audience),
        item(t('teacherCourseCreate.academicYear', '学年'), info.academic_year),
        item(t('teacherCourseCreate.term', '学期'), info.term),
        item(t('teacherCourseCreate.defaultLocation', '常用地点'), profile.default_location),
      ],
    },
    {
      title: t('courseFiles.workbench.teachingArrangement', '授课安排'), icon: Clock3, items: [
        item(t('courseGeneration.teacherBrief.totalHours', '总课时'), brief.total_class_hours, t('courseFiles.workbench.hoursUnit', '{value} 学时')),
        item(t('courseGeneration.teacherBrief.lessonMinutes', '每次课时长'), brief.lesson_duration_minutes, t('courseFiles.workbench.minutesUnit', '{value} 分钟')),
        item(t('courseGeneration.teacherBrief.classSize', '预计班级人数'), brief.class_size),
        item(t('courseGeneration.teacherBrief.chapterCount', '预计章节数'), brief.chapter_count),
        item(t('courseGeneration.teacherBrief.sectionCount', '预计课次'), brief.section_count),
        item(t('courseGeneration.teacherBrief.classProfile', '班级与学情特点'), brief.class_profile, undefined, true),
      ],
    },
    {
      title: t('courseFiles.workbench.courseDesignSettings', '课程设计设置'), icon: SlidersHorizontal, items: [
        item(t('courseGeneration.courseTypes.label', '教学类型'), optionLabel(courseTypeOptions.value, request.course_type)),
        item(t('courseGeneration.pedagogy.label', '学科类型'), optionLabel(pedagogyOptions.value, request.pedagogy_mode)),
        item(t('courseGeneration.pedagogy.secondaryLabel', '辅助学科类型'), optionLabel(pedagogyOptions.value, request.secondary_mode)),
        item(t('courseFiles.workbench.difficulty', '难度'), optionLabel(difficultyOptions.value, request.difficulty)),
        item(t('courseFiles.workbench.productionMode', '生产模式'), optionLabel(productionModeOptions.value, request.production_mode)),
        item(t('courseFiles.workbench.learningGoal', '课程目标'), intentSummary(request), undefined, true),
      ],
    },
    {
      title: t('courseFiles.workbench.additionalCourseInformation', '其他课程信息'), icon: FileText, items: [
        item(t('teacherCourseCreate.courseIntro', '课程简介'), profile.course_intro, undefined, true),
        item(t('teacherCourseCreate.assessmentMethod', '考核方式'), profile.assessment_method, undefined, true),
        item(t('courseGeneration.teacherBrief.additionalRequirements', '其他教学要求'), brief.additional_requirements, undefined, true),
      ],
    },
  ]
})

const changes = computed<ChangeItem[]>(() => {
  if (!original.value) return []
  const before = original.value
  const after = draft.value
  const descriptors = comparisonDescriptors(before, after)
  return descriptors.filter(entry => stable(entry.before) !== stable(entry.after)).map(entry => ({
    key: entry.key,
    label: entry.label,
    before: display(entry.before),
    after: display(entry.after),
  }))
})

const intentComplete = computed(() => {
  const intent = draft.value.generation_request.course_intent || {}
  if (courseType.value === 'project') return Boolean(String(intent.project_goal || '').trim() && String(intent.expected_deliverable || '').trim())
  if (courseType.value === 'inquiry') return Boolean(String(intent.core_question || '').trim() && String(intent.desired_output || '').trim())
  if (courseType.value === 'exam') return Boolean(String(intent.exam_name || '').trim() && String(intent.exam_date || '').trim() && String(intent.exam_scope || '').trim())
  return Boolean(String(intent.learning_goal || '').trim())
})
const canReview = computed(() => {
  const brief = draft.value.generation_request.teacher_course_brief || {}
  return changes.value.length > 0
    && Boolean(String(draft.value.course_profile.target_grade || '').trim())
    && Number.isInteger(brief.total_class_hours) && brief.total_class_hours >= 1 && brief.total_class_hours <= 1000
    && Number.isInteger(brief.lesson_duration_minutes) && brief.lesson_duration_minutes >= 20 && brief.lesson_duration_minutes <= 240
    && intentComplete.value
})

function emptyInformation(): CourseInformation {
  return {
    course_name: '', academic_year: '', term: '',
    course_profile: {
      course_code: '', course_goal: '', default_location: '', target_grade: '', course_category: '',
      target_major: '', credits: null, total_hours: null, assessment_method: '', course_intro: '', teaching_goals: '',
    },
    generation_request: {
      subject: '', target_audience: '大学生', difficulty: 'intermediate', course_type: 'systematic',
      composition_style: 'balanced', pedagogy_mode: 'auto', secondary_mode: '', production_mode: 'manual',
      course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: '' },
      teacher_course_brief: {
        schema_version: 'teacher_course_brief_v1', target_audience: '大学生', total_class_hours: 32,
        lesson_duration_minutes: 45, teaching_context: 'classroom', academic_term: '', class_profile: '', additional_requirements: '',
      },
    },
  }
}

function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }

function normalizeInformation(value: CourseInformation): CourseInformation {
  const fallback = emptyInformation()
  const info = clone(value || fallback)
  info.course_profile = { ...fallback.course_profile, ...(info.course_profile || {}) }
  info.generation_request = { ...fallback.generation_request, ...(info.generation_request || {}) } as CourseInformation['generation_request']
  info.generation_request.subject = String(info.generation_request.subject || info.course_name || '').trim()
  info.generation_request.course_type = ['systematic', 'project', 'inquiry', 'exam'].includes(String(info.generation_request.course_type)) ? info.generation_request.course_type : 'systematic'
  info.generation_request.teacher_course_brief = { ...fallback.generation_request.teacher_course_brief, ...(info.generation_request.teacher_course_brief || {}) }
  info.generation_request.course_intent = info.generation_request.course_intent || intentForType(info.generation_request.course_type as CourseType, info)
  info.course_profile.target_grade = String(info.course_profile.target_grade || info.generation_request.teacher_course_brief.target_audience || info.generation_request.target_audience || '大学生')
  info.generation_request.teacher_course_brief.target_audience = info.course_profile.target_grade
  return info
}

function intentForType(type: CourseType, info: CourseInformation) {
  const existingGoal = intentSummary(info.generation_request) || info.course_name
  if (type === 'project') return { schema_version: 'course_intent_v1', type, project_goal: existingGoal, expected_deliverable: '' }
  if (type === 'inquiry') return { schema_version: 'course_intent_v1', type, core_question: existingGoal, desired_output: '' }
  if (type === 'exam') return { schema_version: 'course_intent_v1', type, exam_name: info.course_name, exam_date: '', exam_scope: existingGoal }
  return { schema_version: 'course_intent_v1', type, learning_goal: existingGoal }
}

function selectCourseType(type: CourseType) {
  if (type === courseType.value) return
  draft.value.generation_request.course_type = type
  draft.value.generation_request.course_purpose = type === 'exam' ? 'exam_sprint' : 'systematic'
  draft.value.generation_request.composition_style = ({ systematic: 'balanced', project: 'project_driven', inquiry: 'inquiry_driven', exam: 'example_driven' } as const)[type]
  draft.value.generation_request.course_intent = intentForType(type, draft.value)
}

function item(label: string, rawValue: unknown, template?: string, wide = false) {
  const empty = rawValue === undefined || rawValue === null || String(rawValue).trim() === ''
  const base = empty ? t('courseFiles.workbench.notSet', '待填写') : String(rawValue)
  return { label, value: template && !empty ? template.replace('{value}', base) : base, empty, wide }
}

function optionLabel(options: Array<{ value: string; label: string }>, value: unknown) {
  if (!value) return ''
  return options.find(item => item.value === value)?.label || String(value)
}

function intentSummary(request: Record<string, any>) {
  const intent = request.course_intent || {}
  if (intent.type === 'project') return [intent.project_goal, intent.expected_deliverable].filter(Boolean).join(' · ')
  if (intent.type === 'inquiry') return [intent.core_question, intent.desired_output].filter(Boolean).join(' · ')
  if (intent.type === 'exam') return [intent.exam_name, intent.exam_date, intent.exam_scope].filter(Boolean).join(' · ')
  return String(intent.learning_goal || intent.desired_outcome || '')
}

function comparisonDescriptors(before: CourseInformation, after: CourseInformation) {
  const bp = before.course_profile; const ap = after.course_profile
  const br = before.generation_request; const ar = after.generation_request
  const bb = br.teacher_course_brief || {}; const ab = ar.teacher_course_brief || {}
  return [
    descriptor('course_code', t('teacherCourseCreate.courseCode', '课程代码'), bp.course_code, ap.course_code),
    descriptor('course_category', t('teacherCourseCreate.courseCategory', '课程类别'), bp.course_category, ap.course_category),
    descriptor('credits', t('teacherCourseCreate.credits', '学分'), bp.credits, ap.credits),
    descriptor('target_major', t('teacherCourseCreate.targetMajor', '面向专业'), bp.target_major, ap.target_major),
    descriptor('target_grade', t('courseGeneration.teacherBrief.targetAudience', '教学对象'), bp.target_grade, ap.target_grade),
    descriptor('academic_year', t('teacherCourseCreate.academicYear', '学年'), before.academic_year, after.academic_year),
    descriptor('term', t('teacherCourseCreate.term', '学期'), before.term, after.term),
    descriptor('default_location', t('teacherCourseCreate.defaultLocation', '常用地点'), bp.default_location, ap.default_location),
    descriptor('total_hours', t('courseGeneration.teacherBrief.totalHours', '总课时'), bb.total_class_hours, ab.total_class_hours),
    descriptor('lesson_minutes', t('courseGeneration.teacherBrief.lessonMinutes', '每次课时长'), bb.lesson_duration_minutes, ab.lesson_duration_minutes),
    descriptor('class_size', t('courseGeneration.teacherBrief.classSize', '预计班级人数'), bb.class_size, ab.class_size),
    descriptor('chapter_count', t('courseGeneration.teacherBrief.chapterCount', '预计章节数'), bb.chapter_count, ab.chapter_count),
    descriptor('section_count', t('courseGeneration.teacherBrief.sectionCount', '预计课次'), bb.section_count, ab.section_count),
    descriptor('class_profile', t('courseGeneration.teacherBrief.classProfile', '班级与学情特点'), bb.class_profile, ab.class_profile),
    descriptor('course_type', t('courseGeneration.courseTypes.label', '教学类型'), optionLabel(courseTypeOptions.value, br.course_type), optionLabel(courseTypeOptions.value, ar.course_type)),
    descriptor('pedagogy_mode', t('courseGeneration.pedagogy.label', '学科类型'), optionLabel(pedagogyOptions.value, br.pedagogy_mode), optionLabel(pedagogyOptions.value, ar.pedagogy_mode)),
    descriptor('secondary_mode', t('courseGeneration.pedagogy.secondaryLabel', '辅助学科类型'), optionLabel(pedagogyOptions.value, br.secondary_mode), optionLabel(pedagogyOptions.value, ar.secondary_mode)),
    descriptor('difficulty', t('courseFiles.workbench.difficulty', '难度'), optionLabel(difficultyOptions.value, br.difficulty), optionLabel(difficultyOptions.value, ar.difficulty)),
    descriptor('production_mode', t('courseFiles.workbench.productionMode', '生产模式'), optionLabel(productionModeOptions.value, br.production_mode), optionLabel(productionModeOptions.value, ar.production_mode)),
    descriptor('course_intent', t('courseFiles.workbench.learningGoal', '课程目标与课型要求'), intentSummary(br), intentSummary(ar)),
    descriptor('course_intro', t('teacherCourseCreate.courseIntro', '课程简介'), bp.course_intro, ap.course_intro),
    descriptor('assessment_method', t('teacherCourseCreate.assessmentMethod', '考核方式'), bp.assessment_method, ap.assessment_method),
    descriptor('additional_requirements', t('courseGeneration.teacherBrief.additionalRequirements', '其他教学要求'), bb.additional_requirements, ab.additional_requirements),
  ]
}

function descriptor(key: string, label: string, before: unknown, after: unknown) { return { key, label, before, after } }
function stable(value: unknown) { return JSON.stringify(value ?? '') }
function display(value: unknown) { return value === undefined || value === null || String(value).trim() === '' ? t('courseFiles.workbench.notSet', '待填写') : String(value) }

async function loadInformation() {
  if (!props.courseId) return
  loading.value = true; loadError.value = ''; saveError.value = ''; conflict.value = false
  try {
    const response = await http.get(`/api/courses/${props.courseId}/course-information`, teacherRequestConfig({ silentError: true }))
    envelope.value = response.data as CourseInformationEnvelope
    original.value = normalizeInformation(envelope.value.information)
    draft.value = clone(original.value)
    mode.value = 'view'; restoreRevision.value = null
  } catch (reason: any) {
    loadError.value = String(reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || t('courseFiles.workbench.courseInformationLoadFailed', '课程基础信息读取失败'))
  } finally { loading.value = false }
}

function startEditing() {
  if (!original.value) return
  draft.value = clone(original.value); restoreRevision.value = null; saveError.value = ''; successMessage.value = ''; mode.value = 'edit'
}
function cancelEditing() { if (original.value) draft.value = clone(original.value); restoreRevision.value = null; saveError.value = ''; mode.value = 'view' }
function reviewChanges() { if (canReview.value) mode.value = 'review' }
function prepareRestore(version: CourseInformationVersion) { draft.value = normalizeInformation(version.information); restoreRevision.value = version.revision; saveError.value = ''; successMessage.value = ''; mode.value = 'review' }

async function saveChanges() {
  if (!envelope.value || saving.value || !changes.value.length) return
  saving.value = true; saveError.value = ''; conflict.value = false
  const commandId = `course-information-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  try {
    const response = await http.put(`/api/courses/${props.courseId}/course-information`, {
      information: draft.value,
      expected_revision: envelope.value.revision,
      expected_document_revision: envelope.value.document_revision,
      idempotency_key: commandId,
      source: restoreRevision.value === null ? 'manual' : 'restore',
      restore_revision: restoreRevision.value,
    }, teacherRequestConfig({ silentError: true }))
    envelope.value = response.data as CourseInformationEnvelope
    original.value = normalizeInformation(envelope.value.information)
    draft.value = clone(original.value)
    successMessage.value = restoreRevision.value === null
      ? t('courseFiles.workbench.courseInformationSaved', '课程基础信息已保存')
      : t('courseFiles.workbench.courseInformationRestored', '已从历史设置创建新修订')
    restoreRevision.value = null; mode.value = 'view'
    emit('updated', envelope.value)
  } catch (reason: any) {
    conflict.value = reason?.response?.status === 409
    saveError.value = conflict.value
      ? t('courseFiles.workbench.courseInformationConflict', '课程基础信息已在别处更新，请重新读取后再修改。')
      : String(reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || t('courseFiles.workbench.courseInformationSaveFailed', '课程基础信息保存失败，已保留本次输入。'))
  } finally { saving.value = false }
}

function formatDate(value: string) {
  if (!value) return t('courseFiles.workbench.historyTimeUnavailable', '时间未记录')
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(activeLocale.value === 'en' ? 'en-US' : 'zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function close() {
  if (saving.value) return
  if ((mode.value === 'edit' || mode.value === 'review') && changes.value.length) {
    if (!window.confirm(t('courseFiles.workbench.discardCourseInformationChanges', '尚有未保存的课程信息修改，确定关闭吗？'))) return
  }
  emit('update:modelValue', false)
  previousFocus?.focus()
}

watch(
  () => props.modelValue,
  async open => {
    if (!open) return
    previousFocus = document.activeElement as HTMLElement | null
    successMessage.value = ''
    await loadInformation()
    await nextTick()
    dialogRef.value?.focus()
  },
  { immediate: true }
)
watch(() => props.courseId, () => { if (props.modelValue) void loadInformation() })
</script>

<style scoped>
.course-information-layer{position:fixed;inset:0;z-index:530;display:grid;place-items:center;padding:24px}.course-information-backdrop{position:absolute;inset:0;border:0;background:rgba(30,41,59,.42)}.course-information-dialog{position:relative;width:min(980px,100%);max-height:calc(100dvh - 48px);display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;border:1px solid #dfe5ee;border-radius:16px;color:var(--lz-text);background:#fff;box-shadow:0 28px 76px rgba(15,23,42,.25);outline:none}.dialog-heading{min-height:76px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:12px 20px;border-bottom:1px solid #e8edf4}.dialog-heading__mark{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.dialog-heading>div{min-width:0}.dialog-heading h2{margin:0;color:#202b40;font-size:20px;letter-spacing:-.015em}.dialog-heading p{margin:4px 0 0;color:#64748b;font-size:12px;line-height:1.45}.icon-button{width:36px;height:36px;display:grid;place-items:center;border:0;border-radius:9px;color:#64748b;background:transparent;cursor:pointer}.icon-button:hover{background:#f1f5f9}.icon-button:focus-visible,.secondary-button:focus-visible,.primary-button:focus-visible,.history-panel button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.dialog-body{min-height:0;overflow:auto;padding:0 30px 30px}.dialog-state{min-height:360px;display:grid;place-items:center;align-content:center;gap:10px;color:#64748b;text-align:center}.dialog-state strong{color:#334155;font-size:14px}.dialog-state p{max-width:580px;margin:0;font-size:12px;line-height:1.6}.dialog-state button{min-height:38px;padding:0 13px;border:1px solid #d7dde7;border-radius:8px;color:#4338ca;background:#fff;font-weight:700;cursor:pointer}.dialog-state.is-error>svg{color:#dc2626}.save-status,.save-error{display:flex;align-items:flex-start;gap:8px;margin:16px 0 0;padding:10px 12px;border-radius:9px;font-size:12px;line-height:1.5}.save-status{color:#166534;background:#ecfdf5}.save-error{color:#991b1b;background:#fff1f2}.save-error>span{flex:1}.save-error button{padding:0;border:0;color:inherit;background:transparent;font-weight:800;text-decoration:underline;cursor:pointer}.course-identity{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;padding:26px 0 22px;border-bottom:1px solid #e8edf4}.course-identity>div{min-width:0;display:grid;gap:5px}.course-identity small{color:#64748b;font-size:12px}.course-identity strong{overflow-wrap:anywhere;color:#172033;font-size:22px;letter-spacing:-.02em}.course-identity span{color:#7b8798;font-size:11px}.course-identity>b{flex:none;padding:5px 8px;border-radius:7px;color:#4f46e5;background:#eef2ff;font-size:11px}.information-group,.form-section{padding:24px 0;border-bottom:1px solid #e8edf4}.information-group:last-child,.form-section:last-child{border-bottom:0}.information-group>header,.form-section>header,.review-panel>header,.history-panel>header{display:flex;align-items:flex-start;gap:9px;margin-bottom:16px}.information-group>header svg,.form-section>header svg,.review-panel>header svg,.history-panel>header svg{flex:none;margin-top:1px;color:#5b57e8}.information-group h3,.form-section h3,.review-panel h3,.history-panel h3{margin:0;color:#263147;font-size:14px}.form-section header p,.review-panel header p,.history-panel header p{margin:3px 0 0;color:#64748b;font-size:11px;line-height:1.5}.information-group dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px 28px;margin:0}.information-group dl>div{min-width:0;display:grid;align-content:start;gap:5px}.information-group dl>div.wide{grid-column:1/-1}.information-group dt{color:#7b8798;font-size:11px}.information-group dd{margin:0;overflow-wrap:anywhere;color:#334155;font-size:13px;font-weight:700;line-height:1.55}.information-group dd[data-empty=true]{color:#a0a8b5;font-weight:500}.field-grid{display:grid;gap:14px}.field-grid--three{grid-template-columns:repeat(3,minmax(0,1fr))}.field-grid--two{grid-template-columns:repeat(2,minmax(0,1fr))}.field-grid label,.intent-fields label{min-width:0;display:grid;align-content:start;gap:7px}.field-grid label.wide{grid-column:1/-1}.field-grid label>span,.intent-fields label>span,.course-type-field legend{color:#475569;font-size:12px;font-weight:750}.field-grid b,.intent-fields b{color:#dc2626}.information-form input,.information-form select,.information-form textarea{width:100%;border:1px solid #cfd7e3;border-radius:8px;color:#172033;background:#fff;outline:none;font:inherit;font-size:13px}.information-form input,.information-form select{min-height:42px;padding:0 10px}.information-form textarea{padding:10px 11px;resize:vertical;line-height:1.6}.information-form input:focus,.information-form select:focus,.information-form textarea:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.course-type-field{min-width:0;margin:0 0 16px;padding:0;border:0}.course-type-field legend{margin-bottom:8px}.course-type-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.course-type-options button{min-width:0;min-height:44px;display:flex;align-items:center;justify-content:center;gap:7px;padding:7px 9px;border:1px solid #d9dfe8;border-radius:9px;color:#64748b;background:#fff;font-size:12px;font-weight:750;cursor:pointer}.course-type-options button:hover{border-color:#aaa7f2;background:#f8f7ff}.course-type-options button.active{border-color:#7c78ec;color:#4338ca;background:#eef0ff}.course-type-options button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.intent-fields{display:grid;gap:13px;margin-top:16px}.review-panel,.history-panel{padding:28px 0}.change-list{display:grid;border-top:1px solid #e8edf4}.change-list article{display:grid;grid-template-columns:minmax(130px,190px) minmax(0,1fr);gap:18px;padding:15px 0;border-bottom:1px solid #e8edf4}.change-list article>strong{color:#475569;font-size:12px}.change-list article>div{min-width:0;display:grid;grid-template-columns:minmax(0,1fr) 18px minmax(0,1fr);align-items:start;gap:10px}.change-list span,.change-list b{overflow-wrap:anywhere;font-size:12px;line-height:1.55}.change-list span{color:#7b8798;text-decoration:line-through}.change-list b{color:#263147}.change-list svg{margin-top:2px;color:#94a3b8}.history-panel ol{margin:0;padding:0;border-top:1px solid #e8edf4;list-style:none}.history-panel li{min-height:68px;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;border-bottom:1px solid #e8edf4}.history-panel li>span{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;color:#5b57e8;background:#eef2ff}.history-panel li>div{min-width:0;display:grid;gap:3px}.history-panel li strong{color:#334155;font-size:13px}.history-panel li small{color:#7b8798;font-size:11px}.history-panel li>b{padding:4px 7px;border-radius:6px;color:#166534;background:#ecfdf5;font-size:10px}.history-panel li>button{min-height:34px;display:flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d7dde7;border-radius:8px;color:#4338ca;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.dialog-footer{min-height:68px;display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:8px;padding:10px 20px;border-top:1px solid #e8edf4;background:#fbfcfe}.primary-button,.secondary-button{min-height:40px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border-radius:8px;font-size:12px;font-weight:750;cursor:pointer}.primary-button{border:1px solid #514bdc;color:#fff;background:#514bdc;box-shadow:0 7px 18px rgba(81,75,220,.16)}.secondary-button{border:1px solid #d7dde7;color:#475569;background:#fff}.primary-button:disabled,.secondary-button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.course-information-layer{align-items:end;padding:0}.course-information-dialog{max-height:calc(100dvh - 16px);border-radius:16px 16px 0 0}.dialog-body{padding-inline:18px}.field-grid--three,.field-grid--two,.information-group dl{grid-template-columns:1fr 1fr}.course-type-options{grid-template-columns:repeat(2,minmax(0,1fr))}.change-list article{grid-template-columns:1fr;gap:7px}.dialog-footer{grid-template-columns:1fr 1fr}.dialog-footer>span{display:none}.dialog-footer button{width:100%}.dialog-footer .secondary-button:first-child{grid-column:1/-1}.information-group dl>div.wide,.field-grid label.wide{grid-column:1/-1}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
