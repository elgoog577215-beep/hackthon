<template>
  <article class="lesson-dossier" :data-print-scope="printScope">
    <header class="lesson-dossier__masthead">
      <div class="lesson-dossier__mark" aria-hidden="true">
        {{ String(identity.sequence || dossier.sequence || 1).padStart(2, '0') }}
      </div>
      <div class="lesson-dossier__title">
        <span>{{ dossier.chapter_title || t('courseGeneration.lessonPlan.dossier.lessonEyebrow', '课时教案') }}</span>
        <h3>{{ dossier.title || t('courseGeneration.lessonPlan.dossier.untitledLesson', '未命名小节') }}</h3>
      </div>
      <dl class="lesson-dossier__facts">
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.dossier.factTemplate', '课型') }}</dt>
          <dd>{{ identity.template_label || t('courseGeneration.lessonPlan.dossier.templateUnbound', '未绑定课型') }}</dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.dossier.factDuration', '课时长度') }}</dt>
          <dd>
            <template v-if="identity.planned_minutes">
              {{ identity.planned_minutes }} {{ t('courseGeneration.lessonPlan.minutesUnit', '分钟') }}
            </template>
            <template v-else>{{ emptyLabel }}</template>
            <small v-if="identity.planned_minutes && minutesBasisLabel">{{ minutesBasisLabel }}</small>
          </dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.dossier.factKnowledge', '知识点') }}</dt>
          <dd>{{ identity.knowledge_point_count || 0 }}</dd>
        </div>
        <div>
          <dt>{{ t('courseGeneration.lessonPlan.dossier.factModules', '教学环节') }}</dt>
          <dd>{{ identity.module_count || 0 }}</dd>
        </div>
      </dl>
    </header>

    <!--
      栏目按 dossier.rubrics 的顺序整列渲染，不按内容多少增删。
      空栏目也占位——教师翻到下一节时看到的是同一张表，而不是另一种排版。
    -->
    <section
      v-for="rubric in contentRubrics"
      :key="rubric.key"
      class="lesson-dossier__rubric"
      :data-rubric="rubric.key"
      :data-status="rubric.status"
    >
      <header>
        <h4>{{ rubricTitle(rubric.key) }}</h4>
        <p>{{ rubricHelp(rubric.key) }}</p>
      </header>

      <p v-if="rubric.status === 'empty'" class="lesson-dossier__empty">{{ emptyLabel }}</p>

      <template v-else-if="rubric.key === 'objectives'">
        <ol class="lesson-dossier__objectives">
          <li v-for="(item, index) in asObjectives(rubric)" :key="index">
            <span>{{ item.text }}</span>
            <em v-if="item.knowledge_name">{{ item.knowledge_name }}</em>
            <small>{{ objectiveSourceLabel(item.source) }}</small>
          </li>
        </ol>
      </template>

      <template v-else-if="rubric.key === 'focus'">
        <div class="lesson-dossier__split">
          <div>
            <strong>{{ t('courseGeneration.lessonPlan.dossier.focusKeyPoints', '教学重点') }}</strong>
            <ul v-if="asStrings(rubric.key_points).length">
              <li v-for="item in asStrings(rubric.key_points)" :key="item">{{ item }}</li>
            </ul>
            <p v-else class="lesson-dossier__empty">{{ emptyLabel }}</p>
          </div>
          <div>
            <strong>{{ t('courseGeneration.lessonPlan.dossier.focusDifficulties', '教学难点') }}</strong>
            <ul v-if="asStrings(rubric.difficulties).length">
              <li v-for="item in asStrings(rubric.difficulties)" :key="item">{{ item }}</li>
            </ul>
            <p v-else class="lesson-dossier__empty">{{ emptyLabel }}</p>
          </div>
        </div>
      </template>

      <template v-else-if="rubric.key === 'knowledge'">
        <table class="lesson-dossier__table">
          <thead>
            <tr>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colKnowledge', '知识点') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colType', '类型') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colStatement', '规范陈述') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colPrerequisite', '前置与边界') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in asKnowledgeRows(rubric)" :key="row.knowledge_id || row.name || index">
              <th scope="row">
                <button
                  type="button"
                  :disabled="!row.knowledge_id"
                  :title="row.knowledge_id
                    ? t('courseGeneration.lessonPlan.openKnowledge', '在知识库中查看')
                    : t('courseGeneration.lessonPlan.knowledgePending', '等待知识库编译')"
                  @click="openKnowledge(row.knowledge_id)"
                >{{ row.name }}</button>
                <small>{{ ownershipLabel(row.ownership) }}</small>
              </th>
              <td>{{ knowledgeTypeLabel(row.knowledge_type) || emptyLabel }}</td>
              <td>{{ row.statement || emptyLabel }}</td>
              <td>
                <span v-if="row.prerequisite_names?.length">{{ row.prerequisite_names.join(' · ') }}</span>
                <i v-for="item in row.boundaries || []" :key="item">{{ item }}</i>
                <template v-if="!row.prerequisite_names?.length && !row.boundaries?.length">{{ emptyLabel }}</template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="asStrings(rubric.reused_knowledge_names).length" class="lesson-dossier__footnote">
          <strong>{{ t('courseGeneration.lessonPlan.reusedKnowledge', '承接已有知识') }}</strong>
          {{ asStrings(rubric.reused_knowledge_names).join(' · ') }}
        </p>
      </template>

      <template v-else-if="rubric.key === 'timeline'">
        <table class="lesson-dossier__table is-timeline">
          <thead>
            <tr>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colClock', '时段') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colStage', '教学环节') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.moduleTeacherActivityLabel', '教师动作') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.moduleStudentActivityLabel', '学生活动') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colKnowledge', '知识点') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in asTimeline(rubric)" :key="entry.module_id || entry.sequence">
              <td class="lesson-dossier__clock">
                <strong v-if="entry.start_minute !== null && entry.end_minute !== null">
                  {{ entry.start_minute }}–{{ entry.end_minute }}'
                </strong>
                <strong v-else-if="entry.minutes">{{ entry.minutes }}'</strong>
                <strong v-else>{{ emptyLabel }}</strong>
                <small v-if="entry.minutes_source === 'derived'">
                  {{ t('courseGeneration.lessonPlan.dossier.minutesDerived', '按课时摊分') }}
                </small>
              </td>
              <th scope="row">
                <span>{{ entry.label }}</span>
                <p v-if="entry.teaching_purpose">{{ entry.teaching_purpose }}</p>
              </th>
              <td>{{ entry.teacher_activity || entry.teaching_guidance || emptyLabel }}</td>
              <td>{{ entry.student_activity || emptyLabel }}</td>
              <td>
                <span v-for="name in entry.knowledge_names" :key="name">{{ name }}</span>
                <template v-if="!entry.knowledge_names.length">{{ emptyLabel }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <template v-else-if="rubric.key === 'alignment'">
        <table class="lesson-dossier__table is-alignment">
          <thead>
            <tr>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colKnowledge', '知识点') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colStage', '教学环节') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.observableAbility', '可观察能力') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colMastery', '掌握标准与验证') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colEvidence', '课堂证据') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in asAlignment(rubric)"
              :key="row.knowledge_id || row.name || index"
              :data-gap="row.gaps.length ? 'true' : 'false'"
            >
              <th scope="row">
                <span>{{ row.name }}</span>
                <small>{{ ownershipLabel(row.ownership) }}</small>
              </th>
              <td>
                <span v-for="item in row.modules" :key="item.module_id">{{ item.label }}</span>
                <b v-if="!row.modules.length">{{ gapLabel('module') }}</b>
              </td>
              <td>
                <ul v-if="row.capabilities.length">
                  <li v-for="item in row.capabilities" :key="item">{{ item }}</li>
                </ul>
                <b v-else>{{ gapLabel('capability') }}</b>
              </td>
              <td>
                <ul v-if="row.mastery.length">
                  <li v-for="(item, itemIndex) in row.mastery" :key="itemIndex">
                    <strong>{{ item.performance }}</strong>
                    <em v-if="item.verification">{{ item.verification }}</em>
                  </li>
                </ul>
                <b v-else>{{ gapLabel('mastery') }}</b>
              </td>
              <td>
                <ul v-if="row.checks.length || row.homework.length">
                  <li v-for="item in row.checks" :key="`check-${item}`">{{ item }}</li>
                  <li v-for="item in row.homework" :key="`homework-${item}`">{{ item }}</li>
                </ul>
                <b v-else>{{ gapLabel('evidence') }}</b>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <template v-else-if="rubric.key === 'misconceptions'">
        <table class="lesson-dossier__table">
          <thead>
            <tr>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colKnowledge', '知识点') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colErrorPattern', '错误表现') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colDiscrimination', '判别方式') }}</th>
              <th scope="col">{{ t('courseGeneration.lessonPlan.dossier.colRepair', '纠偏策略') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in asMisconceptions(rubric)" :key="index">
              <th scope="row">{{ row.knowledge_name }}</th>
              <td>{{ row.error_pattern || emptyLabel }}</td>
              <td>{{ row.discrimination || emptyLabel }}</td>
              <td>{{ row.repair_strategy || emptyLabel }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <template v-else-if="rubric.key === 'assessment'">
        <div class="lesson-dossier__split">
          <div>
            <strong>{{ t('courseGeneration.lessonPlan.inClassChecksLabel', '课堂检查') }}</strong>
            <ul v-if="asChecks(rubric).length">
              <li v-for="(item, index) in asChecks(rubric)" :key="index">
                <span>{{ item.text }}</span>
                <em v-for="name in item.knowledge_names" :key="name">{{ name }}</em>
              </li>
            </ul>
            <p v-else class="lesson-dossier__empty">{{ emptyLabel }}</p>
          </div>
          <div>
            <strong>{{ t('courseGeneration.lessonPlan.masteryEvidence', '掌握证据') }}</strong>
            <ul v-if="asCriteria(rubric).length">
              <li v-for="(item, index) in asCriteria(rubric)" :key="index">
                <span>{{ item.performance }}</span>
                <em v-if="item.knowledge_name">{{ item.knowledge_name }}</em>
                <small v-if="item.verification">{{ item.verification }}</small>
              </li>
            </ul>
            <p v-else class="lesson-dossier__empty">{{ emptyLabel }}</p>
          </div>
        </div>
      </template>

      <template v-else-if="rubric.key === 'homework'">
        <ul class="lesson-dossier__plain">
          <li v-for="(item, index) in asChecks(rubric, 'items')" :key="index">
            <span>{{ item.text }}</span>
            <em v-for="name in item.knowledge_names" :key="name">{{ name }}</em>
          </li>
        </ul>
      </template>

      <template v-else-if="rubric.key === 'resources'">
        <ul class="lesson-dossier__plain">
          <li v-for="item in asStrings(rubric.items)" :key="item">{{ item }}</li>
        </ul>
      </template>

      <template v-else-if="rubric.key === 'notes'">
        <div class="lesson-dossier__notes">
          <div v-if="asStrings(rubric.teacher_activities).length">
            <strong>{{ t('courseGeneration.lessonPlan.teacherActivitiesLabel', '教师活动') }}</strong>
            <ul><li v-for="item in asStrings(rubric.teacher_activities)" :key="item">{{ item }}</li></ul>
          </div>
          <div v-if="asStrings(rubric.student_activities).length">
            <strong>{{ t('courseGeneration.lessonPlan.studentActivitiesLabel', '学生活动') }}</strong>
            <ul><li v-for="item in asStrings(rubric.student_activities)" :key="item">{{ item }}</li></ul>
          </div>
          <div v-if="asStrings(rubric.items).length">
            <strong>{{ t('courseGeneration.lessonPlan.teachingNotesLabel', '教学备注') }}</strong>
            <ul><li v-for="item in asStrings(rubric.items)" :key="item">{{ item }}</li></ul>
          </div>
          <div v-if="asStrings(rubric.guardrails).length" class="is-guardrail">
            <strong>{{ t('courseGeneration.lessonPlan.dossier.guardrails', '课型约束') }}</strong>
            <ul><li v-for="item in asStrings(rubric.guardrails)" :key="item">{{ item }}</li></ul>
          </div>
        </div>
      </template>
    </section>

    <footer class="lesson-dossier__footer">
      <span>{{ t('courseGeneration.lessonPlan.dossier.templateFooter', '本节按学科模板栏目呈现') }}</span>
      <em>{{ dossier.template?.template_label || t('courseGeneration.lessonPlan.dossier.templateUnbound', '未绑定课型') }}</em>
      <small v-if="dossier.template?.module_conformance?.missing_required?.length">
        {{ t('courseGeneration.lessonPlan.dossier.missingRequiredModules', '模板要求但本节缺少的环节') }}：
        {{ dossier.template.module_conformance.missing_required.join('、') }}
      </small>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  CourseLessonDossier,
  LessonDossierAlignmentRow,
  LessonDossierRubric,
  LessonDossierTimelineEntry,
} from '../stores/types'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  dossier: CourseLessonDossier
  printScope?: string
}>(), {
  printScope: 'lesson',
})

const emit = defineEmits<{
  (event: 'open-knowledge', knowledgeId: string): void
}>()

const emptyLabel = computed(() => t('courseGeneration.lessonPlan.notSpecified', '待补充'))

function rubricOf(key: string): LessonDossierRubric | undefined {
  return props.dossier.rubrics?.find(item => item.key === key)
}

// 课时信息单独抽出来做报头，其余栏目按后端顺序整列渲染。
const identity = computed(() => (rubricOf('lesson_identity') || {}) as Record<string, any>)
const contentRubrics = computed(() => (
  (props.dossier.rubrics || []).filter(rubric => rubric.key !== 'lesson_identity')
))

const minutesBasisLabel = computed(() => {
  const labels: Record<string, string> = {
    section_planned: t('courseGeneration.lessonPlan.dossier.basisSection', '本节设定'),
    course_default: t('courseGeneration.lessonPlan.dossier.basisCourse', '全课课时'),
    course_median: t('courseGeneration.lessonPlan.dossier.basisMedian', '按全课常用课时'),
  }
  return labels[String(identity.value.minutes_basis || '')] || ''
})

const RUBRIC_TITLES: Record<string, [string, string]> = {
  objectives: ['courseGeneration.lessonPlan.dossier.rubricObjectives', '教学目标'],
  focus: ['courseGeneration.lessonPlan.dossier.rubricFocus', '重点与难点'],
  knowledge: ['courseGeneration.lessonPlan.dossier.rubricKnowledge', '本节知识与前置'],
  timeline: ['courseGeneration.lessonPlan.dossier.rubricTimeline', '课堂时序'],
  alignment: ['courseGeneration.lessonPlan.dossier.rubricAlignment', '活动·知识·评价对照'],
  misconceptions: ['courseGeneration.lessonPlan.dossier.rubricMisconceptions', '易错点与纠偏'],
  assessment: ['courseGeneration.lessonPlan.dossier.rubricAssessment', '课堂检查与掌握标准'],
  homework: ['courseGeneration.lessonPlan.dossier.rubricHomework', '课后作业'],
  resources: ['courseGeneration.lessonPlan.dossier.rubricResources', '教学资源与准备'],
  notes: ['courseGeneration.lessonPlan.dossier.rubricNotes', '教学备注与约束'],
}

const RUBRIC_HELPS: Record<string, [string, string]> = {
  objectives: ['courseGeneration.lessonPlan.dossier.helpObjectives', '目录目标与各知识点的可观察行为'],
  focus: ['courseGeneration.lessonPlan.dossier.helpFocus', '重点来自本节首次负责的知识，难点由教案单独声明'],
  knowledge: ['courseGeneration.lessonPlan.dossier.helpKnowledge', '每个知识点的规范陈述、前置依赖与适用边界'],
  timeline: ['courseGeneration.lessonPlan.dossier.helpTimeline', '环节顺序与课件、正文一致；未单独设定的环节按课时长度摊分'],
  alignment: ['courseGeneration.lessonPlan.dossier.helpAlignment', '一行一个知识点：在哪个环节教、要求什么能力、按什么标准验收'],
  misconceptions: ['courseGeneration.lessonPlan.dossier.helpMisconceptions', '课堂上先辨别再纠正，不要只提醒“注意”'],
  assessment: ['courseGeneration.lessonPlan.dossier.helpAssessment', '当堂能收上来的证据，以及判定掌握的标准'],
  homework: ['courseGeneration.lessonPlan.dossier.helpHomework', '课后任务及其对应的知识点'],
  resources: ['courseGeneration.lessonPlan.dossier.helpResources', '上课前需要准备的材料与工具'],
  notes: ['courseGeneration.lessonPlan.dossier.helpNotes', '备课提醒，以及本课型不允许的讲法'],
}

function rubricTitle(key: string): string {
  const entry = RUBRIC_TITLES[key]
  return entry ? t(entry[0], entry[1]) : key
}

function rubricHelp(key: string): string {
  const entry = RUBRIC_HELPS[key]
  return entry ? t(entry[0], entry[1]) : ''
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function asObjectives(rubric: LessonDossierRubric) {
  return (rubric.items as Array<{ text: string; source: string; knowledge_name: string }>) || []
}

function asKnowledgeRows(rubric: LessonDossierRubric) {
  return (rubric.rows as Array<Record<string, any>>) || []
}

function asTimeline(rubric: LessonDossierRubric): LessonDossierTimelineEntry[] {
  return (rubric.entries as LessonDossierTimelineEntry[]) || []
}

function asAlignment(rubric: LessonDossierRubric): LessonDossierAlignmentRow[] {
  return (rubric.rows as LessonDossierAlignmentRow[]) || []
}

function asMisconceptions(rubric: LessonDossierRubric) {
  return (rubric.rows as Array<Record<string, string>>) || []
}

function asChecks(rubric: LessonDossierRubric, key = 'checks') {
  return (rubric[key] as Array<{ text: string; knowledge_names: string[] }>) || []
}

function asCriteria(rubric: LessonDossierRubric) {
  return (rubric.criteria as Array<{
    knowledge_name: string
    performance: string
    verification: string
  }>) || []
}

function objectiveSourceLabel(source: string): string {
  return source === 'capability'
    ? t('courseGeneration.lessonPlan.dossier.sourceCapability', '可观察行为')
    : t('courseGeneration.lessonPlan.dossier.sourceOutline', '目录目标')
}

function ownershipLabel(ownership: string): string {
  return ownership === 'reused'
    ? t('courseGeneration.lessonPlan.dossier.ownershipReused', '承接')
    : t('courseGeneration.lessonPlan.dossier.ownershipOwned', '本节新授')
}

// 缺口不是“暂无”，是“这门课在这里没有教学落点”。用单独措辞，教师才会去补。
function gapLabel(gap: string): string {
  const labels: Record<string, string> = {
    module: t('courseGeneration.lessonPlan.dossier.gapModule', '无教学环节承载'),
    capability: t('courseGeneration.lessonPlan.dossier.gapCapability', '未写可观察能力'),
    mastery: t('courseGeneration.lessonPlan.dossier.gapMastery', '未写掌握标准'),
    evidence: t('courseGeneration.lessonPlan.dossier.gapEvidence', '无课堂证据'),
  }
  return labels[gap] || gap
}

function knowledgeTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    concept: t('courseGeneration.lessonPlan.knowledgeTypes.concept', '概念'),
    principle: t('courseGeneration.lessonPlan.knowledgeTypes.principle', '原理'),
    procedure: t('courseGeneration.lessonPlan.knowledgeTypes.procedure', '方法'),
    skill: t('courseGeneration.lessonPlan.knowledgeTypes.skill', '技能'),
    fact: t('courseGeneration.lessonPlan.knowledgeTypes.fact', '事实'),
  }
  return value ? (labels[value] || value) : ''
}

function openKnowledge(knowledgeId: string): void {
  if (knowledgeId) emit('open-knowledge', knowledgeId)
}
</script>

<style scoped>
.lesson-dossier {
  display:flex;
  flex-direction:column;
  gap:20px;
  color:#253044;
}

.lesson-dossier__masthead {
  display:grid;
  grid-template-columns:auto 1fr auto;
  gap:16px;
  align-items:center;
  padding:18px 20px;
  border:1px solid rgba(87,96,124,.18);
  border-radius:14px;
  background:linear-gradient(135deg,rgba(78,88,196,.07),rgba(255,255,255,.9));
}
.lesson-dossier__mark {
  font-size:28px;
  font-weight:700;
  line-height:1;
  color:rgba(78,88,196,.55);
  font-variant-numeric:tabular-nums;
}
.lesson-dossier__title span {
  display:block;
  font-size:12px;
  letter-spacing:.08em;
  color:#6b7387;
}
.lesson-dossier__title h3 { margin:2px 0 0; font-size:19px; line-height:1.35; }
.lesson-dossier__facts { display:flex; gap:18px; margin:0; flex-wrap:wrap; }
.lesson-dossier__facts dt { font-size:12px; color:#6b7387; }
.lesson-dossier__facts dd { margin:2px 0 0; font-size:14px; font-weight:600; }
.lesson-dossier__facts dd small {
  display:block;
  font-weight:400;
  font-size:11px;
  color:#8a90a2;
}

.lesson-dossier__rubric {
  border:1px solid rgba(87,96,124,.16);
  border-radius:14px;
  background:#fff;
  padding:16px 18px 18px;
  break-inside:avoid;
}
.lesson-dossier__rubric > header { margin-bottom:12px; }
.lesson-dossier__rubric h4 {
  margin:0;
  font-size:15px;
  font-weight:650;
  display:flex;
  align-items:center;
  gap:8px;
}
.lesson-dossier__rubric h4::before {
  content:'';
  width:4px;
  height:15px;
  border-radius:2px;
  background:rgba(78,88,196,.6);
}
.lesson-dossier__rubric > header p { margin:5px 0 0 12px; font-size:12px; color:#798093; }
.lesson-dossier__rubric[data-status='empty'] { background:rgba(247,248,250,.75); }

.lesson-dossier__empty { margin:0; font-size:13px; color:#9aa0b1; }

.lesson-dossier__table { width:100%; border-collapse:collapse; font-size:13px; }
.lesson-dossier__table th,
.lesson-dossier__table td {
  border:1px solid rgba(87,96,124,.18);
  padding:8px 10px;
  text-align:left;
  vertical-align:top;
  line-height:1.55;
}
.lesson-dossier__table thead th {
  background:rgba(78,88,196,.07);
  font-size:12px;
  font-weight:600;
  white-space:nowrap;
}
.lesson-dossier__table tbody th { width:16%; font-weight:600; }
.lesson-dossier__table tbody tr { break-inside:avoid; }
.lesson-dossier__table ul { margin:0; padding-left:16px; }
.lesson-dossier__table li { margin-bottom:3px; }
.lesson-dossier__table li em { display:block; font-style:normal; font-size:12px; color:#798093; }
.lesson-dossier__table tbody th small,
.lesson-dossier__table tbody th button + small {
  display:block;
  font-weight:400;
  font-size:11px;
  color:#8a90a2;
}
.lesson-dossier__table tbody th button {
  border:0;
  padding:0;
  background:none;
  font:inherit;
  color:#4e58c4;
  cursor:pointer;
  text-align:left;
}
.lesson-dossier__table tbody th button:disabled { color:inherit; cursor:default; }
.lesson-dossier__table td span { display:inline-block; margin:0 6px 4px 0; }
.lesson-dossier__table td i {
  display:inline-block;
  font-style:normal;
  margin:2px 5px 0 0;
  padding:1px 7px;
  border-radius:999px;
  font-size:11px;
  background:rgba(87,96,124,.09);
}
.lesson-dossier__table td b {
  font-weight:600;
  font-size:12px;
  color:#b4552f;
}
.lesson-dossier__table tr[data-gap='true'] { background:rgba(240,176,110,.09); }

.is-timeline .lesson-dossier__clock { width:11%; white-space:nowrap; font-variant-numeric:tabular-nums; }
.is-timeline .lesson-dossier__clock strong { font-size:13px; }
.is-timeline .lesson-dossier__clock small { display:block; font-size:11px; color:#8a90a2; }
.is-timeline tbody th p { margin:3px 0 0; font-weight:400; font-size:12px; color:#798093; }

.lesson-dossier__objectives { margin:0; padding-left:20px; font-size:13px; line-height:1.7; }
.lesson-dossier__objectives em { font-style:normal; color:#4e58c4; margin-left:6px; }
.lesson-dossier__objectives small { margin-left:6px; font-size:11px; color:#9aa0b1; }

.lesson-dossier__split { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.lesson-dossier__split strong { display:block; font-size:13px; margin-bottom:6px; }
.lesson-dossier__split ul,
.lesson-dossier__plain { margin:0; padding-left:18px; font-size:13px; line-height:1.7; }
.lesson-dossier__split li em,
.lesson-dossier__plain li em {
  font-style:normal;
  margin-left:6px;
  font-size:11px;
  color:#4e58c4;
}
.lesson-dossier__split li small { display:block; font-size:11px; color:#798093; }

.lesson-dossier__notes { display:grid; gap:12px; }
.lesson-dossier__notes strong { display:block; font-size:13px; margin-bottom:5px; }
.lesson-dossier__notes ul { margin:0; padding-left:18px; font-size:13px; line-height:1.7; }
.lesson-dossier__notes .is-guardrail ul { color:#8a5a2c; }

.lesson-dossier__footnote { margin:10px 0 0; font-size:12px; color:#798093; }
.lesson-dossier__footnote strong { margin-right:6px; color:#253044; }

.lesson-dossier__footer {
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  align-items:baseline;
  font-size:12px;
  color:#798093;
}
.lesson-dossier__footer em { font-style:normal; font-weight:600; color:#4e58c4; }
.lesson-dossier__footer small { width:100%; color:#b4552f; }

@container lesson-plan (max-width:760px) {
  .lesson-dossier__masthead { grid-template-columns:auto 1fr; }
  .lesson-dossier__facts { grid-column:1 / -1; }
  .lesson-dossier__split { grid-template-columns:1fr; }
  .lesson-dossier__table { font-size:12px; }
}
</style>

<style>
/*
  打印：教师要的是一张能直接带进教室的纸。
  非 scoped，因为要盖住整个应用外壳——只在 @media print 内生效，屏幕上没有副作用。
*/
@media print {
  body * { visibility:hidden !important; }
  .lesson-dossier,
  .lesson-dossier * { visibility:visible !important; }
  .lesson-dossier {
    position:absolute !important;
    inset:0 auto auto 0;
    width:100%;
    padding:0;
    gap:12px;
    background:#fff;
  }
  .lesson-dossier button { color:inherit !important; }
  .lesson-dossier__masthead,
  .lesson-dossier__rubric {
    background:#fff !important;
    border-color:#999 !important;
    break-inside:avoid;
  }
  .lesson-dossier__rubric > header p { display:none; }
  .lesson-dossier__table th,
  .lesson-dossier__table td { border-color:#999 !important; }
  .lesson-dossier__table thead { display:table-header-group; }
  .lesson-dossier__table thead th { background:#eee !important; }
  @page { margin:14mm 12mm; }
}
</style>
