<template>
  <article class="formal-lesson-plan" :aria-label="t('courseGeneration.lessonPlan.formalDocumentTitle', '正式课程教案')">
    <header class="formal-lesson-plan__cover">
      <div>
        <span>{{ t('courseGeneration.lessonPlan.formalDocumentTitle', '正式课程教案') }}</span>
        <h3>{{ overall?.course_title || t('courseGeneration.lessonPlan.untitledCourse', '未命名课程') }}</h3>
        <p>{{ overall?.positioning || t('courseGeneration.lessonPlan.positioningPending', '课程定位将在目录确认后形成。') }}</p>
      </div>
      <dl>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.targetAudience', '教学对象') }}</dt>
          <dd>{{ overall?.target_audience || t('courseGeneration.lessonPlan.classroomUnset', '待补充') }}</dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.totalClassHoursLabel', '总课时') }}</dt>
          <dd>{{ classroom.total_class_hours || '—' }}</dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.lessonDurationLabel', '每次课时长') }}</dt>
          <dd>{{ classroom.lesson_duration_minutes
            ? `${classroom.lesson_duration_minutes} ${t('courseGeneration.lessonPlan.minutesUnit', '分钟')}`
            : '—' }}</dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.teachingContextLabel', '授课场景') }}</dt>
          <dd>{{ teachingContext }}</dd>
        </div>
      </dl>
    </header>

    <section class="formal-lesson-plan__section formal-lesson-plan__section--summary">
      <div>
        <header>
          <span>01</span>
          <h4>{{ t('courseGeneration.lessonPlan.formalObjectivesTitle', '教学目标') }}</h4>
        </header>
        <ol v-if="overall?.learning_objectives?.length">
          <li v-for="objective in overall.learning_objectives" :key="objective">{{ objective }}</li>
        </ol>
        <p v-else class="formal-lesson-plan__empty">{{ t('courseGeneration.lessonPlan.objectivesPending', '总体教学目标正在形成。') }}</p>
      </div>
      <div>
        <header>
          <span>02</span>
          <h4>{{ t('courseGeneration.lessonPlan.formalLearnerAnalysisTitle', '学情与起点') }}</h4>
        </header>
        <p v-if="classroom.class_profile">{{ classroom.class_profile }}</p>
        <ul v-if="overall?.prerequisites?.length">
          <li v-for="item in overall.prerequisites" :key="item">{{ item }}</li>
        </ul>
        <p v-else-if="!classroom.class_profile" class="formal-lesson-plan__empty">{{ t('courseGeneration.lessonPlan.noPrerequisites', '没有额外前置要求。') }}</p>
      </div>
    </section>

    <section class="formal-lesson-plan__section">
      <header class="formal-lesson-plan__heading">
        <span>03</span>
        <div>
          <h4>{{ t('courseGeneration.lessonPlan.formalKeyDifficultiesTitle', '教学重点与难点') }}</h4>
          <p>{{ t('courseGeneration.lessonPlan.formalKeyDifficultiesHelp', '从各课时知识责任、能力要求和易错表现汇编') }}</p>
        </div>
      </header>
      <div class="formal-lesson-plan__two-column">
        <div>
          <strong>{{ t('courseGeneration.lessonPlan.formalKeyPoints', '教学重点') }}</strong>
          <ul v-if="keyPoints.length">
            <li v-for="item in keyPoints" :key="item">{{ item }}</li>
          </ul>
          <p v-else class="formal-lesson-plan__empty">{{ t('courseGeneration.lessonPlan.formalPending', '待教案完整后汇编') }}</p>
        </div>
        <div>
          <strong>{{ t('courseGeneration.lessonPlan.formalDifficulties', '教学难点') }}</strong>
          <ul v-if="difficulties.length">
            <li v-for="item in difficulties" :key="item">{{ item }}</li>
          </ul>
          <p v-else class="formal-lesson-plan__empty">{{ t('courseGeneration.lessonPlan.formalPending', '待教案完整后汇编') }}</p>
        </div>
      </div>
    </section>

    <section class="formal-lesson-plan__section">
      <header class="formal-lesson-plan__heading">
        <span>04</span>
        <div>
          <h4>{{ t('courseGeneration.lessonPlan.formalStrategyTitle', '教学策略、准备与评价') }}</h4>
          <p>{{ overall?.teaching_strategy?.rationale || t('courseGeneration.lessonPlan.strategyPending', '教学策略正在随全课教案形成。') }}</p>
        </div>
      </header>
      <div class="formal-lesson-plan__three-column">
        <div>
          <strong>{{ t('courseGeneration.lessonPlan.teachingPreparationLabel', '课前准备') }}</strong>
          <ul v-if="classroom.teaching_preparation?.length">
            <li v-for="item in classroom.teaching_preparation" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ t('courseGeneration.lessonPlan.formalPreparationFallback', '按课时准备资料、案例与课堂检查工具。') }}</p>
        </div>
        <div>
          <strong>{{ t('courseGeneration.lessonPlan.assessmentTitle', '怎样知道学生已经学会') }}</strong>
          <ul v-if="assessmentMethods.length">
            <li v-for="item in assessmentMethods" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ t('courseGeneration.lessonPlan.assessmentFallback', '依据各小节的可观察能力与掌握标准进行形成性评价。') }}</p>
        </div>
        <div>
          <strong>{{ t('courseGeneration.lessonPlan.formalResourcesTitle', '课程依据与资源') }}</strong>
          <ul v-if="resourceRefs.length">
            <li v-for="item in resourceRefs" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ t('courseGeneration.lessonPlan.formalResourcesFallback', '当前未绑定可展示的外部资料引用。') }}</p>
        </div>
      </div>
    </section>

    <section class="formal-lesson-plan__section formal-lesson-plan__process">
      <header class="formal-lesson-plan__heading">
        <span>05</span>
        <div>
          <h4>{{ t('courseGeneration.lessonPlan.formalProcessTitle', '教学过程') }}</h4>
          <p>{{ t('courseGeneration.lessonPlan.formalProcessHelp', '按课时列出时间、师生活动、知识能力与检查证据') }}</p>
        </div>
      </header>

      <section v-for="(section, sectionIndex) in plan.sections" :key="section.node_id" class="formal-lesson-plan__lesson">
        <header>
          <div>
            <span>{{ t('courseGeneration.lessonPlan.formalLessonLabel', '课时 {number}').replace('{number}', String(sectionIndex + 1).padStart(2, '0')) }}</span>
            <h5>{{ sectionTitle(section.node_id, sectionIndex) }}</h5>
          </div>
          <strong>{{ section.planned_minutes
            ? `${section.planned_minutes} ${t('courseGeneration.lessonPlan.minutesUnit', '分钟')}`
            : t('courseGeneration.lessonPlan.formalDurationPending', '时长待补充') }}</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>{{ t('courseGeneration.lessonPlan.formalPhase', '教学环节') }}</th>
              <th>{{ t('courseGeneration.lessonPlan.formalMinutes', '时间') }}</th>
              <th>{{ t('courseGeneration.lessonPlan.formalTeacherActivity', '教师活动') }}</th>
              <th>{{ t('courseGeneration.lessonPlan.formalStudentActivity', '学生活动') }}</th>
              <th>{{ t('courseGeneration.lessonPlan.formalEvidence', '检查与证据') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in teachingRows(section)" :key="row.key">
              <td><strong>{{ row.purpose || t('courseGeneration.lessonPlan.formalPhaseFallback', '教学活动') }}</strong><small v-if="row.knowledge">{{ row.knowledge }}</small></td>
              <td>{{ row.minutes || '—' }}</td>
              <td>{{ row.teacher || fallbackActivity(section.teacher_activities, rowIndex) }}</td>
              <td>{{ row.student || fallbackActivity(section.student_activities, rowIndex) }}</td>
              <td>{{ fallbackActivity(section.in_class_checks, rowIndex) }}</td>
            </tr>
          </tbody>
        </table>
        <footer v-if="section.homework?.length || section.teaching_notes?.length">
          <div v-if="section.homework?.length">
            <strong>{{ t('courseGeneration.lessonPlan.homeworkLabel', '课后任务') }}</strong>
            <span>{{ section.homework.join('；') }}</span>
          </div>
          <div v-if="section.teaching_notes?.length">
            <strong>{{ t('courseGeneration.lessonPlan.teachingNotesLabel', '教学备注') }}</strong>
            <span>{{ section.teaching_notes.join('；') }}</span>
          </div>
        </footer>
      </section>
    </section>

    <footer class="formal-lesson-plan__footer">
      <span>{{ t('courseGeneration.lessonPlan.formalSourceNote', '本教案由当前结构化教案确定性编译；编辑请切换到总体设计或分课时视图。') }}</span>
      <strong>{{ t('courseGeneration.lessonPlan.revisionLabel', '正式修订') }} {{ plan.revision_id || '—' }}</strong>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import type { CourseTeachingPlanProjection, CourseTeachingPlanSection, Node } from '../stores/types'

const props = withDefaults(defineProps<{
  plan: CourseTeachingPlanProjection
  nodes?: Node[]
}>(), { nodes: () => [] })

const overall = computed(() => props.plan.overall)
const classroom = computed(() => overall.value?.classroom || {})
const nodeNames = computed(() => new Map(props.nodes.map(node => [node.node_id, node.node_name])))

function unique(values: Array<string | undefined | null>): string[] {
  return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))]
}

const keyPoints = computed(() => unique(props.plan.sections.flatMap(section => section.key_points || [])))
const difficulties = computed(() => unique(props.plan.sections.flatMap(section => section.key_difficulties || [])))
const resourceRefs = computed(() => unique(props.plan.sections.flatMap(section => section.resource_refs || [])))
const assessmentMethods = computed(() => unique([
  ...(overall.value?.assessment_methods || []),
  ...(classroom.value.course_assessment_plan || []),
]))
const teachingContext = computed(() => {
  const labels: Record<string, string> = {
    classroom: t('courseGeneration.lessonPlan.contextClassroom', '线下课堂'),
    online: t('courseGeneration.lessonPlan.contextOnline', '在线授课'),
    blended: t('courseGeneration.lessonPlan.contextBlended', '混合式授课'),
    self_study: t('courseGeneration.lessonPlan.contextSelfStudy', '自主学习'),
  }
  return labels[String(classroom.value.teaching_context || '')] || t('courseGeneration.lessonPlan.classroomUnset', '待补充')
})

function sectionTitle(nodeId: string, index: number): string {
  return nodeNames.value.get(nodeId)
    || t('courseGeneration.lessonPlan.formalLessonUntitled', '第 {number} 课时').replace('{number}', String(index + 1))
}

function fallbackActivity(values: string[] | undefined, index: number): string {
  if (!values?.length) return t('courseGeneration.lessonPlan.formalPending', '待教案完整后汇编')
  return values[index] || values[values.length - 1] || '—'
}

function teachingRows(section: CourseTeachingPlanSection) {
  if (section.teaching_modules?.length) {
    return section.teaching_modules.map((module, index) => ({
      key: module.module_id || `${section.node_id}-${index}`,
      purpose: module.teaching_purpose,
      minutes: module.planned_minutes
        ? `${module.planned_minutes} ${t('courseGeneration.lessonPlan.minutesUnit', '分钟')}`
        : '',
      teacher: module.teacher_activity || module.teaching_guidance || '',
      student: module.student_activity || '',
      knowledge: module.knowledge_names?.join('、') || '',
    }))
  }
  return [{
    key: `${section.node_id}-fallback`,
    purpose: t('courseGeneration.lessonPlan.formalPhaseFallback', '教学活动'),
    minutes: section.planned_minutes
      ? `${section.planned_minutes} ${t('courseGeneration.lessonPlan.minutesUnit', '分钟')}`
      : '',
    teacher: '',
    student: '',
    knowledge: section.key_points?.join('、') || '',
  }]
}
</script>

<style scoped>
.formal-lesson-plan { box-sizing:border-box; width:min(1180px,100%); margin:0 auto; overflow:hidden; border:1px solid #d9dde5; border-radius:16px; color:#263247; background:#fff; box-shadow:0 18px 50px rgba(31,41,55,.07); }
.formal-lesson-plan__cover { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr); gap:42px; padding:46px 50px 40px; border-bottom:1px solid #e4e7ed; background:linear-gradient(135deg,#fbfbff 0%,#fff 58%,#f6f7fd 100%); }
.formal-lesson-plan__cover > div > span { color:#5c65b5; font-size:12px; font-weight:850; letter-spacing:.12em; }
.formal-lesson-plan__cover h3 { margin:9px 0 10px; color:#202b3d; font-size:32px; line-height:1.25; letter-spacing:-.02em; }
.formal-lesson-plan__cover p { max-width:720px; margin:0; color:#697488; font-size:14px; line-height:1.8; }
.formal-lesson-plan__cover dl { align-self:end; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); margin:0; border-top:1px solid #dfe3eb; border-left:1px solid #dfe3eb; }
.formal-lesson-plan__cover dl > div { min-width:0; padding:11px 13px; border-right:1px solid #dfe3eb; border-bottom:1px solid #dfe3eb; }
.formal-lesson-plan__cover dt { color:#8992a1; font-size:11px; }
.formal-lesson-plan__cover dd { margin:4px 0 0; overflow:hidden; color:#364259; font-size:13px; font-weight:750; text-overflow:ellipsis; white-space:nowrap; }
.formal-lesson-plan__section { padding:36px 50px; border-bottom:1px solid #e8eaef; }
.formal-lesson-plan__section--summary { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:36px; }
.formal-lesson-plan__section--summary > div { min-width:0; }
.formal-lesson-plan__section--summary header,.formal-lesson-plan__heading { display:flex; align-items:flex-start; gap:13px; margin-bottom:19px; }
.formal-lesson-plan__section--summary header > span,.formal-lesson-plan__heading > span { flex:none; width:32px; height:32px; display:grid; place-items:center; border:1px solid #cbd0e8; border-radius:8px; color:#5861aa; background:#f5f6fd; font:800 11px/1 ui-monospace,SFMono-Regular,monospace; }
.formal-lesson-plan h4 { margin:4px 0 0; color:#273248; font-size:18px; line-height:1.35; }
.formal-lesson-plan__heading > div { min-width:0; }
.formal-lesson-plan__heading p { margin:4px 0 0; color:#7b8494; font-size:12px; line-height:1.6; }
.formal-lesson-plan ol,.formal-lesson-plan ul { display:grid; gap:8px; margin:0; padding-left:20px; }
.formal-lesson-plan li,.formal-lesson-plan__section--summary p { color:#536075; font-size:13px; line-height:1.7; }
.formal-lesson-plan__two-column,.formal-lesson-plan__three-column { display:grid; gap:12px; }
.formal-lesson-plan__two-column { grid-template-columns:repeat(2,minmax(0,1fr)); }
.formal-lesson-plan__three-column { grid-template-columns:repeat(3,minmax(0,1fr)); }
.formal-lesson-plan__two-column > div,.formal-lesson-plan__three-column > div { min-width:0; padding:18px 19px; border:1px solid #e1e4ea; border-radius:10px; background:#fbfbfc; }
.formal-lesson-plan__two-column strong,.formal-lesson-plan__three-column strong { display:block; margin-bottom:10px; color:#3e4a60; font-size:13px; }
.formal-lesson-plan__three-column p { margin:0; color:#687487; font-size:12px; line-height:1.7; }
.formal-lesson-plan__empty { margin:0; color:#929aa8!important; font-size:12px!important; }
.formal-lesson-plan__process { padding-bottom:46px; }
.formal-lesson-plan__lesson { overflow:hidden; margin-top:18px; border:1px solid #dde1e8; border-radius:11px; }
.formal-lesson-plan__lesson > header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:15px 18px; border-bottom:1px solid #e4e7ed; background:#f7f8fb; }
.formal-lesson-plan__lesson > header div { min-width:0; }
.formal-lesson-plan__lesson > header span { color:#6973bb; font-size:10px; font-weight:850; letter-spacing:.08em; }
.formal-lesson-plan__lesson h5 { margin:3px 0 0; color:#2c384d; font-size:15px; line-height:1.4; }
.formal-lesson-plan__lesson > header > strong { flex:none; color:#5b6578; font-size:12px; }
.formal-lesson-plan table { width:100%; border-collapse:collapse; table-layout:fixed; }
.formal-lesson-plan th,.formal-lesson-plan td { padding:11px 12px; border-right:1px solid #e5e8ed; border-bottom:1px solid #e5e8ed; vertical-align:top; text-align:left; overflow-wrap:anywhere; }
.formal-lesson-plan th:last-child,.formal-lesson-plan td:last-child { border-right:0; }
.formal-lesson-plan tbody tr:last-child td { border-bottom:0; }
.formal-lesson-plan th { color:#697386; background:#fcfcfd; font-size:11px; font-weight:800; }
.formal-lesson-plan td { color:#566276; font-size:12px; line-height:1.6; }
.formal-lesson-plan th:nth-child(1) { width:17%; }
.formal-lesson-plan th:nth-child(2) { width:9%; }
.formal-lesson-plan td strong { display:block; color:#3b475c; font-size:12px; }
.formal-lesson-plan td small { display:block; margin-top:3px; color:#87909f; font-size:10px; line-height:1.5; }
.formal-lesson-plan__lesson > footer { display:grid; gap:7px; padding:12px 17px; border-top:1px solid #e4e7ed; background:#fbfbfc; }
.formal-lesson-plan__lesson > footer div { display:grid; grid-template-columns:72px minmax(0,1fr); gap:9px; color:#606d80; font-size:12px; line-height:1.55; }
.formal-lesson-plan__lesson > footer strong { color:#3d495e; }
.formal-lesson-plan__footer { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:18px 50px; color:#7c8594; background:#f7f8fa; font-size:11px; }
.formal-lesson-plan__footer strong { color:#5a6374; font:750 11px/1.4 ui-monospace,SFMono-Regular,monospace; }
@media (max-width:900px) {
  .formal-lesson-plan__cover { grid-template-columns:1fr; gap:26px; padding:36px 30px; }
  .formal-lesson-plan__cover dl { max-width:620px; }
  .formal-lesson-plan__section { padding:30px; }
  .formal-lesson-plan__three-column { grid-template-columns:1fr; }
  .formal-lesson-plan__lesson { overflow-x:auto; }
  .formal-lesson-plan table { min-width:760px; }
  .formal-lesson-plan__footer { padding-inline:30px; }
}
@media (max-width:640px) {
  .formal-lesson-plan { border-radius:13px; }
  .formal-lesson-plan__cover { padding:28px 20px; }
  .formal-lesson-plan__cover h3 { font-size:26px; }
  .formal-lesson-plan__cover dl,.formal-lesson-plan__section--summary,.formal-lesson-plan__two-column { grid-template-columns:1fr; }
  .formal-lesson-plan__section { padding:26px 20px; }
  .formal-lesson-plan__footer { align-items:flex-start; flex-direction:column; padding:16px 20px; }
}
@media print {
  .formal-lesson-plan { width:100%; border:0; box-shadow:none; }
  .formal-lesson-plan__lesson { break-inside:avoid; }
}
</style>
