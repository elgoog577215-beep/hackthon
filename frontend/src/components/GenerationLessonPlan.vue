<template>
  <section class="generation-lesson-plan">
    <header class="generation-lesson-plan__header">
      <div class="generation-lesson-plan__intro">
        <div class="generation-lesson-plan__eyebrow">
          <span>{{ t('courseGeneration.lessonPlan.eyebrow', '唯一正式全课教案') }}</span>
          <i aria-hidden="true" />
          <strong>{{ planStatusLabel }}</strong>
        </div>
        <h2>{{ t('courseGeneration.lessonPlan.title', '课程教案') }}</h2>
        <p>{{ planReady
          ? t('courseGeneration.lessonPlan.ready', '从目标到评价，所有教学安排都来自同一份全课计划')
          : live
            ? t('courseGeneration.lessonPlan.pending', '目录已经确定；详细教案会逐节生成并汇编为全课计划')
            : t('courseGeneration.lessonPlan.legacyUnavailable', '这门旧课程还没有结构化全课教案，现展示已有学习目标') }}</p>
      </div>

      <div class="generation-lesson-plan__summary">
        <div v-if="live && !planReady" class="generation-lesson-plan__progress" role="status">
          <div>
            <span>{{ t('courseGeneration.lessonPlan.generating', '正在规划') }}</span>
            <strong>{{ completedSections }}/{{ totalSections }}</strong>
          </div>
          <div class="generation-lesson-plan__progress-track" aria-hidden="true">
            <i :style="{ width: `${planProgress}%` }" />
          </div>
        </div>
        <dl>
          <div>
            <dt>{{ t('courseGeneration.lessonPlan.sections', '小节') }}</dt>
            <dd>{{ plan?.section_count || sections.length }}</dd>
          </div>
          <div>
            <dt>{{ t('courseGeneration.lessonPlan.knowledge', '知识点') }}</dt>
            <dd>{{ plan?.knowledge_point_count || knowledgeCount }}</dd>
          </div>
          <div>
            <dt>{{ t('courseGeneration.lessonPlan.modules', '教学环节') }}</dt>
            <dd>{{ plan?.teaching_module_count || moduleCount }}</dd>
          </div>
        </dl>
      </div>
    </header>

    <div
      v-if="overallPlan || selectedSection"
      class="generation-lesson-plan__view-switch"
      role="tablist"
      :aria-label="t('courseGeneration.lessonPlan.viewLabel', '教案视图')"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="viewMode === 'overall'"
        :class="{ 'is-active': viewMode === 'overall' }"
        @click="viewMode = 'overall'"
      >
        <BookOpenCheck :size="16" />
        <span>
          <strong>{{ t('courseGeneration.lessonPlan.overallTab', '总体教案') }}</strong>
          <small>{{ t('courseGeneration.lessonPlan.overallTabHelp', '看整门课怎样设计') }}</small>
        </span>
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="viewMode === 'sections'"
        :class="{ 'is-active': viewMode === 'sections' }"
        @click="viewMode = 'sections'"
      >
        <ListTree :size="16" />
        <span>
          <strong>{{ t('courseGeneration.lessonPlan.sectionsTab', '分小节教案') }}</strong>
          <small>{{ t('courseGeneration.lessonPlan.sectionsTabHelp', '看每一节如何落地') }}</small>
        </span>
      </button>
    </div>

    <article
      v-if="viewMode === 'overall' && overallPlan"
      class="generation-lesson-plan__overview"
      role="tabpanel"
    >
      <header class="generation-lesson-plan__overview-hero">
        <div>
          <span>{{ t('courseGeneration.lessonPlan.overallEyebrow', '全课教学设计') }}</span>
          <h3>{{ overallPlan.course_title || t('courseGeneration.lessonPlan.untitledCourse', '未命名课程') }}</h3>
          <p>{{ overallPlan.positioning || t('courseGeneration.lessonPlan.positioningPending', '课程定位将在目录确认后形成。') }}</p>
        </div>
        <aside>
          <UsersRound :size="18" />
          <span>{{ t('courseGeneration.lessonPlan.targetAudience', '教学对象') }}</span>
          <strong>{{ overallPlan.target_audience || t('courseGeneration.lessonPlan.audiencePending', '按课程需求确定') }}</strong>
        </aside>
      </header>

      <div class="generation-lesson-plan__overview-grid">
        <section class="generation-lesson-plan__overview-card is-objectives">
          <header>
            <Target :size="18" />
            <span>
              <small>{{ t('courseGeneration.lessonPlan.overallObjectivesEyebrow', '总体目标') }}</small>
              <strong>{{ t('courseGeneration.lessonPlan.overallObjectives', '学完这门课，学生能够') }}</strong>
            </span>
          </header>
          <ol v-if="overallPlan.learning_objectives.length">
            <li v-for="(objective, index) in overallPlan.learning_objectives" :key="objective">
              <span>{{ String(index + 1).padStart(2, '0') }}</span>
              <p>{{ objective }}</p>
            </li>
          </ol>
          <p v-else class="generation-lesson-plan__card-empty">{{ t('courseGeneration.lessonPlan.objectivesPending', '总体教学目标正在形成。') }}</p>
        </section>

        <section class="generation-lesson-plan__overview-card">
          <header>
            <Route :size="18" />
            <span>
              <small>{{ t('courseGeneration.lessonPlan.entryEyebrow', '学习起点') }}</small>
              <strong>{{ t('courseGeneration.lessonPlan.prerequisitesTitle', '开始前需要具备') }}</strong>
            </span>
          </header>
          <ul v-if="overallPlan.prerequisites.length" class="generation-lesson-plan__plain-list">
            <li v-for="item in overallPlan.prerequisites" :key="item">{{ item }}</li>
          </ul>
          <p v-else class="generation-lesson-plan__card-empty">{{ t('courseGeneration.lessonPlan.noPrerequisites', '没有额外前置要求。') }}</p>
        </section>

        <section class="generation-lesson-plan__overview-card">
          <header>
            <Sparkles :size="18" />
            <span>
              <small>{{ t('courseGeneration.lessonPlan.strategyEyebrow', '教学策略') }}</small>
              <strong>{{ t('courseGeneration.lessonPlan.strategyTitle', '这门课准备怎样教') }}</strong>
            </span>
          </header>
          <p class="generation-lesson-plan__strategy-copy">
            {{ overallPlan.teaching_strategy.rationale || teachingModeSummary }}
          </p>
          <div v-if="teachingModeTags.length" class="generation-lesson-plan__strategy-tags">
            <span v-for="item in teachingModeTags" :key="item">{{ teachingModeLabel(item) }}</span>
          </div>
        </section>

        <section class="generation-lesson-plan__overview-card">
          <header>
            <BadgeCheck :size="18" />
            <span>
              <small>{{ t('courseGeneration.lessonPlan.assessmentEyebrow', '评价设计') }}</small>
              <strong>{{ t('courseGeneration.lessonPlan.assessmentTitle', '怎样知道学生已经学会') }}</strong>
            </span>
          </header>
          <ul v-if="overallPlan.assessment_methods.length" class="generation-lesson-plan__plain-list">
            <li v-for="item in overallPlan.assessment_methods" :key="item">{{ item }}</li>
          </ul>
          <p v-else class="generation-lesson-plan__card-empty">
            {{ t('courseGeneration.lessonPlan.assessmentFallback', '依据各小节的可观察能力与掌握标准进行形成性评价。') }}
          </p>
        </section>
      </div>

      <section class="generation-lesson-plan__overview-section">
        <header>
          <span>
            <small>{{ t('courseGeneration.lessonPlan.courseStructureEyebrow', '教学进程') }}</small>
            <strong>{{ t('courseGeneration.lessonPlan.courseStructureTitle', '章节怎样推动学习发生') }}</strong>
          </span>
          <p>{{ t('courseGeneration.lessonPlan.courseStructureHelp', '章节负责阶段性推进，分小节教案负责把每一步落实为知识与课程块。') }}</p>
        </header>
        <ol class="generation-lesson-plan__chapter-path">
          <li v-for="(chapter, index) in overallPlan.chapters" :key="chapter.chapter_id || index">
            <span>{{ chapter.chapter_number || String(index + 1).padStart(2, '0') }}</span>
            <div>
              <strong>{{ chapter.title }}</strong>
              <p>{{ chapter.learning_focus || t('courseGeneration.lessonPlan.chapterFocusPending', '本章教学责任随目录确定。') }}</p>
            </div>
            <small>{{ chapter.section_count }} {{ t('courseGeneration.lessonPlan.sectionUnit', '小节') }}</small>
          </li>
        </ol>
      </section>

      <section v-if="overallPlan.knowledge_tags.length" class="generation-lesson-plan__overview-section is-knowledge-map">
        <header>
          <span>
            <small>{{ t('courseGeneration.lessonPlan.courseKnowledgeEyebrow', '全课知识') }}</small>
            <strong>{{ t('courseGeneration.lessonPlan.courseKnowledgeTitle', '教案引用的知识坐标') }}</strong>
          </span>
          <p>{{ t('courseGeneration.lessonPlan.courseKnowledgeHelp', '标签来自当前课程知识库；数字表示该知识覆盖的小节数。') }}</p>
        </header>
        <div class="generation-lesson-plan__knowledge-tags">
          <button
            v-for="tag in overallPlan.knowledge_tags"
            :key="tag.knowledge_id || tag.name"
            type="button"
            :disabled="!tag.knowledge_id"
            :title="tag.knowledge_id
              ? t('courseGeneration.lessonPlan.openKnowledge', '在知识库中查看')
              : t('courseGeneration.lessonPlan.knowledgePending', '等待知识库编译')"
            @click="openKnowledge(tag.knowledge_id)"
          >
            <BrainCircuit :size="14" />
            <span>{{ tag.name }}</span>
            <small>{{ tag.section_count }}</small>
          </button>
        </div>
      </section>
    </article>

    <div v-else-if="selectedSection" class="generation-lesson-plan__workspace" role="tabpanel">
      <nav class="generation-lesson-plan__pager" :aria-label="t('courseGeneration.lessonPlan.sectionNavigation', '教案小节导航')">
        <button
          type="button"
          :disabled="!previousSection"
          :title="previousSection?.node.node_name"
          @click="previousSection && emit('select', previousSection.node)"
        >
          <ChevronLeft :size="17" />
          <span>
            <small>{{ t('courseGeneration.lessonPlan.previousSection', '上一节') }}</small>
            <strong>{{ previousSection?.node.node_name || t('courseGeneration.lessonPlan.courseStart', '课程起点') }}</strong>
          </span>
        </button>
        <div>
          <span>{{ String(selectedIndex + 1).padStart(2, '0') }}</span>
          <i aria-hidden="true" />
          <small>{{ String(sections.length).padStart(2, '0') }}</small>
        </div>
        <button
          type="button"
          :disabled="!nextSection"
          :title="nextSection?.node.node_name"
          @click="nextSection && emit('select', nextSection.node)"
        >
          <span>
            <small>{{ t('courseGeneration.lessonPlan.nextSection', '下一节') }}</small>
            <strong>{{ nextSection?.node.node_name || t('courseGeneration.lessonPlan.courseEnd', '课程终点') }}</strong>
          </span>
          <ChevronRight :size="17" />
        </button>
      </nav>

      <article class="generation-lesson-plan__sheet">
        <header class="generation-lesson-plan__sheet-header">
          <div class="generation-lesson-plan__section-mark" aria-hidden="true">
            {{ String(selectedIndex + 1).padStart(2, '0') }}
          </div>
          <div class="generation-lesson-plan__section-title">
            <span>{{ t('courseGeneration.lessonPlan.currentSection', '当前小节') }}</span>
            <h3>{{ selectedSection.node.node_name }}</h3>
            <p>{{ selectedSection.node.learning_objective || t('courseGeneration.lessonPlan.objectivePending', '学习目标随目录确认') }}</p>
          </div>
          <div class="generation-lesson-plan__readiness" :data-ready="Boolean(selectedSection.plan)">
            <CircleCheck v-if="selectedSection.plan" :size="17" />
            <LoaderCircle v-else-if="live" :size="17" />
            <CircleDashed v-else :size="17" />
            <span>{{ selectedSection.plan
              ? t('courseGeneration.lessonPlan.planned', '备课就绪')
              : live
                ? t('courseGeneration.lessonPlan.waiting', '正在形成')
                : t('courseGeneration.lessonPlan.unavailable', '暂无结构化教案') }}</span>
          </div>
        </header>

        <template v-if="selectedSection.plan">
          <section class="generation-lesson-plan__block generation-lesson-plan__flow">
            <div class="generation-lesson-plan__block-heading">
              <div><Route :size="19" /></div>
              <span>
                <small>{{ t('courseGeneration.lessonPlan.flowEyebrow', '课堂路径') }}</small>
                <strong>{{ t('courseGeneration.lessonPlan.flowTitle', '这一节怎样展开') }}</strong>
              </span>
              <p>{{ t('courseGeneration.lessonPlan.flowHelp', '每个环节都绑定具体教学职责和知识范围，正文与课件沿用同一顺序。') }}</p>
            </div>

            <ol v-if="selectedSection.plan.teaching_modules?.length">
              <li
                v-for="(module, moduleIndex) in selectedSection.plan.teaching_modules"
                :key="module.module_id || moduleIndex"
              >
                <div class="generation-lesson-plan__module-index">
                  <span>{{ String(moduleIndex + 1).padStart(2, '0') }}</span>
                  <i aria-hidden="true" />
                </div>
                <div class="generation-lesson-plan__module-copy">
                  <strong>{{ module.teaching_purpose || module.module_id }}</strong>
                  <p v-if="module.teaching_guidance">{{ module.teaching_guidance }}</p>
                  <div v-if="module.knowledge_names?.length">
                    <span v-for="name in module.knowledge_names" :key="name">{{ name }}</span>
                  </div>
                </div>
              </li>
            </ol>
            <p v-else class="generation-lesson-plan__inline-empty">
              {{ t('courseGeneration.lessonPlan.noTeachingFlow', '这一节暂未形成教学环节。') }}
            </p>
          </section>

          <section class="generation-lesson-plan__block generation-lesson-plan__knowledge">
            <div class="generation-lesson-plan__block-heading">
              <div><BrainCircuit :size="19" /></div>
              <span>
                <small>{{ t('courseGeneration.lessonPlan.knowledgeEyebrow', '知识与评价') }}</small>
                <strong>{{ t('courseGeneration.lessonPlan.knowledgeTitle', '教到什么，怎样知道学会') }}</strong>
              </span>
              <p>{{ t('courseGeneration.lessonPlan.knowledgeHelp', '把知识边界、可观察能力、掌握标准和易错纠偏放在同一个备课单元里。') }}</p>
            </div>

            <div v-if="selectedKnowledgeTags.length" class="generation-lesson-plan__section-knowledge-tags">
              <span>{{ t('courseGeneration.lessonPlan.sectionKnowledgeTags', '本节知识标签') }}</span>
              <div>
                <button
                  v-for="tag in selectedKnowledgeTags"
                  :key="tag.knowledge_id || tag.name"
                  type="button"
                  :disabled="!tag.knowledge_id"
                  :data-status="tag.knowledge_status || 'awaiting_compilation'"
                  :title="tag.knowledge_id
                    ? t('courseGeneration.lessonPlan.openKnowledge', '在知识库中查看')
                    : t('courseGeneration.lessonPlan.knowledgePending', '等待知识库编译')"
                  @click="openKnowledge(tag.knowledge_id)"
                >
                  <BrainCircuit :size="13" />
                  {{ tag.name }}
                  <ArrowUpRight v-if="tag.knowledge_id" :size="12" />
                  <small v-else>{{ t('courseGeneration.lessonPlan.compiling', '编译中') }}</small>
                </button>
              </div>
            </div>

            <div v-if="selectedSection.plan.knowledge_structure?.length" class="generation-lesson-plan__knowledge-groups">
              <section
                v-for="(group, groupIndex) in selectedSection.plan.knowledge_structure"
                :key="`${group.concept_group || 'group'}-${groupIndex}`"
                class="generation-lesson-plan__knowledge-group"
              >
                <header>
                  <span>{{ String(groupIndex + 1).padStart(2, '0') }}</span>
                  <div>
                    <h4>{{ group.concept_group || t('courseGeneration.lessonPlan.coreKnowledge', '核心知识') }}</h4>
                    <p v-if="group.description">{{ group.description }}</p>
                  </div>
                </header>

                <details
                  v-for="(point, pointIndex) in group.knowledge_points || []"
                  :key="point.knowledge_id || point.name || pointIndex"
                  :open="pointIndex === 0"
                >
                  <summary>
                    <div>
                      <span>{{ point.name }}</span>
                      <small v-if="point.knowledge_type">{{ knowledgeTypeLabel(point.knowledge_type) }}</small>
                    </div>
                    <p>{{ point.statement || point.description }}</p>
                    <ChevronDown :size="17" aria-hidden="true" />
                  </summary>

                  <div class="generation-lesson-plan__knowledge-detail">
                    <section>
                      <header><Target :size="16" />{{ t('courseGeneration.lessonPlan.observableAbility', '可观察能力') }}</header>
                      <ul v-if="capabilityItems(point).length">
                        <li v-for="(item, itemIndex) in capabilityItems(point)" :key="itemIndex">{{ item }}</li>
                      </ul>
                      <p v-else>{{ t('courseGeneration.lessonPlan.notSpecified', '待补充') }}</p>
                    </section>

                    <section>
                      <header><BadgeCheck :size="16" />{{ t('courseGeneration.lessonPlan.masteryEvidence', '掌握证据') }}</header>
                      <ul v-if="masteryItems(point).length">
                        <li v-for="(item, itemIndex) in masteryItems(point)" :key="itemIndex">
                          <strong>{{ item.primary }}</strong>
                          <span v-if="item.secondary">{{ item.secondary }}</span>
                        </li>
                      </ul>
                      <p v-else>{{ t('courseGeneration.lessonPlan.notSpecified', '待补充') }}</p>
                    </section>

                    <section class="is-warning">
                      <header><TriangleAlert :size="16" />{{ t('courseGeneration.lessonPlan.misconceptionRepair', '易错与纠偏') }}</header>
                      <ul v-if="misconceptionItems(point).length">
                        <li v-for="(item, itemIndex) in misconceptionItems(point)" :key="itemIndex">
                          <strong>{{ item.primary }}</strong>
                          <span v-if="item.secondary">{{ item.secondary }}</span>
                        </li>
                      </ul>
                      <p v-else>{{ t('courseGeneration.lessonPlan.notSpecified', '待补充') }}</p>
                    </section>
                  </div>

                  <div v-if="boundaryItems(point).length" class="generation-lesson-plan__boundaries">
                    <span>{{ t('courseGeneration.lessonPlan.boundaries', '适用边界') }}</span>
                    <i v-for="item in boundaryItems(point)" :key="item">{{ item }}</i>
                  </div>
                </details>
              </section>
            </div>
            <p v-else class="generation-lesson-plan__inline-empty">
              {{ t('courseGeneration.lessonPlan.noKnowledgeStructure', '这一节暂未形成结构化知识与评价。') }}
            </p>
          </section>

          <section
            v-if="selectedSection.plan.reused_knowledge_names?.length || selectedSection.plan.knowledge_relations?.length"
            class="generation-lesson-plan__block generation-lesson-plan__connections"
          >
            <div class="generation-lesson-plan__block-heading">
              <div><GitBranch :size="19" /></div>
              <span>
                <small>{{ t('courseGeneration.lessonPlan.connectionEyebrow', '前后衔接') }}</small>
                <strong>{{ t('courseGeneration.lessonPlan.connectionTitle', '这节课从哪里来、到哪里去') }}</strong>
              </span>
            </div>

            <div class="generation-lesson-plan__connection-grid">
              <div v-if="selectedSection.plan.reused_knowledge_names?.length">
                <span>{{ t('courseGeneration.lessonPlan.reusedKnowledge', '承接已有知识') }}</span>
                <p>{{ selectedSection.plan.reused_knowledge_names.join(' · ') }}</p>
              </div>
              <ul v-if="selectedSection.plan.knowledge_relations?.length">
                <li
                  v-for="(relation, relationIndex) in selectedSection.plan.knowledge_relations"
                  :key="`${relation.source_name || relationIndex}-${relation.target_name || relationIndex}`"
                >
                  <div>
                    <span>{{ relation.source_name || t('courseGeneration.lessonPlan.currentKnowledge', '当前知识') }}</span>
                    <ArrowRight :size="15" />
                    <span>{{ relation.target_name || t('courseGeneration.lessonPlan.relatedKnowledge', '关联知识') }}</span>
                  </div>
                  <p v-if="relation.reason">{{ relation.reason }}</p>
                </li>
              </ul>
            </div>
          </section>
        </template>

        <div v-else-if="live" class="generation-lesson-plan__skeleton" aria-hidden="true">
          <div><i /><i /><i /></div>
          <div><i /><i /><i /></div>
        </div>
        <div v-else class="generation-lesson-plan__legacy">
          <BookOpenCheck :size="24" />
          <strong>{{ t('courseGeneration.lessonPlan.legacySectionTitle', '保留现有学习目标') }}</strong>
          <p>{{ t('courseGeneration.lessonPlan.legacySectionHelp', '这门旧课程没有可展示的结构化教学流程与评价合同。') }}</p>
        </div>
      </article>
    </div>

    <div v-else class="generation-lesson-plan__empty">
      <LoaderCircle :size="22" />
      <strong>{{ t('courseGeneration.lessonPlan.outlinePending', '正在生成课程目录') }}</strong>
      <p>{{ t('courseGeneration.lessonPlan.outlinePendingHelp', '目录出现后，这里会先显示每个小节的教案占位。') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  BookOpenCheck,
  BrainCircuit,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  GitBranch,
  ListTree,
  LoaderCircle,
  Route,
  Sparkles,
  Target,
  TriangleAlert,
  UsersRound,
} from 'lucide-vue-next'
import type {
  CourseTeachingPlanProjection,
  CourseTeachingPlanSection,
  Node,
  Task,
} from '../stores/types'
import { t } from '../shared/i18n'

type KnowledgePoint = NonNullable<CourseTeachingPlanSection['knowledge_structure'][number]['knowledge_points']>[number]
type DetailItem = { primary: string; secondary: string }

const props = withDefaults(defineProps<{
  plan?: CourseTeachingPlanProjection | null
  nodes?: Node[]
  activeNodeId?: string
  live?: boolean
  task?: Task
}>(), {
  plan: null,
  nodes: () => [],
  activeNodeId: '',
  live: false,
  task: undefined,
})

const emit = defineEmits<{
  (event: 'select', node: Node): void
  (event: 'open-knowledge', knowledgeId: string): void
}>()

const viewMode = ref<'overall' | 'sections'>('overall')
const planByNode = computed(() => new Map(
  (props.plan?.sections || []).map(section => [section.node_id, section]),
))
const lessonNodes = computed(() => props.nodes.filter(node => node.node_level === 2))
const sections = computed(() => lessonNodes.value.map(node => ({
  node,
  plan: planByNode.value.get(node.node_id),
})))
const selectedIndex = computed(() => {
  const directIndex = sections.value.findIndex(section => section.node.node_id === props.activeNodeId)
  if (directIndex >= 0) return directIndex
  const childIndex = sections.value.findIndex(section => section.node.parent_node_id === props.activeNodeId)
  return childIndex >= 0 ? childIndex : 0
})
const selectedSection = computed(() => sections.value[selectedIndex.value])
const overallPlan = computed(() => props.plan?.overall)
const previousSection = computed(() => selectedIndex.value > 0 ? sections.value[selectedIndex.value - 1] : undefined)
const nextSection = computed(() => selectedIndex.value < sections.value.length - 1 ? sections.value[selectedIndex.value + 1] : undefined)
const planReady = computed(() => props.plan?.status === 'completed' && Boolean(props.plan.sections?.length))
const completedSections = computed(() => Number(
  props.task?.recovery?.checkpoint?.completed_teaching_plan_sections
  ?? props.task?.phaseDetail?.completed_items
  ?? props.plan?.sections?.length
  ?? 0,
))
const totalSections = computed(() => Number(
  props.task?.recovery?.checkpoint?.total_teaching_plan_sections
  ?? props.task?.phaseDetail?.total_items
  ?? props.plan?.section_count
  ?? sections.value.length
  ?? 0,
))
const planProgress = computed(() => (
  totalSections.value > 0
    ? Math.min(100, Math.round((completedSections.value / totalSections.value) * 100))
    : 0
))
const moduleCount = computed(() => (props.plan?.sections || []).reduce(
  (sum, section) => sum + (section.teaching_modules?.length || 0),
  0,
))
const knowledgeCount = computed(() => (props.plan?.sections || []).reduce(
  (sum, section) => sum + (section.key_points?.length || 0),
  0,
))
const selectedKnowledgeTags = computed(() => {
  const tags = new Map<string, {
    knowledge_id: string
    knowledge_status?: string
    name: string
  }>()
  for (const group of selectedSection.value?.plan?.knowledge_structure || []) {
    for (const point of group.knowledge_points || []) {
      const name = String(point.name || '').trim()
      if (!name) continue
      const key = String(point.knowledge_id || name)
      tags.set(key, {
        knowledge_id: String(point.knowledge_id || ''),
        knowledge_status: point.knowledge_status,
        name,
      })
    }
  }
  return [...tags.values()]
})
const teachingModeTags = computed(() => [
  overallPlan.value?.teaching_strategy.primary_mode,
  overallPlan.value?.teaching_strategy.secondary_mode,
].filter((value): value is string => Boolean(value)))
const teachingModeSummary = computed(() => (
  teachingModeTags.value.length
    ? t('courseGeneration.lessonPlan.strategyFromProfile', '以课程教学画像组织讲解、示例、练习与反馈。')
    : t('courseGeneration.lessonPlan.strategyPending', '教学策略正在随全课教案形成。')
))
const planStatusLabel = computed(() => (
  planReady.value
    ? t('courseGeneration.lessonPlan.planReady', '全课已汇编')
    : props.live
      ? t('courseGeneration.lessonPlan.planBuilding', '生成进行中')
      : t('courseGeneration.lessonPlan.planPreview', '教案预览')
))

function textFromRecord(value: unknown, keys: string[]): string {
  if (typeof value === 'string') return value.trim()
  if (!value || typeof value !== 'object') return ''
  const record = value as Record<string, unknown>
  for (const key of keys) {
    const text = String(record[key] || '').trim()
    if (text) return text
  }
  return ''
}

function detailItems(values: unknown, primaryKeys: string[], secondaryKeys: string[]): DetailItem[] {
  if (!Array.isArray(values)) return []
  return values
    .map(value => ({
      primary: textFromRecord(value, primaryKeys),
      secondary: textFromRecord(value, secondaryKeys),
    }))
    .filter(item => item.primary || item.secondary)
}

function capabilityItems(point: KnowledgePoint): string[] {
  const values = Array.isArray(point.capability_points) ? point.capability_points : []
  const items = values
    .map(value => textFromRecord(value, ['observable_behavior', 'capability', 'description', 'behavior']))
    .filter(Boolean)
  const fallback = String(point.capability || '').trim()
  return items.length ? items : (fallback ? [fallback] : [])
}

function masteryItems(point: KnowledgePoint): DetailItem[] {
  return detailItems(
    point.mastery_criteria,
    ['observable_performance', 'criterion', 'standard', 'performance'],
    ['verification_method', 'verification', 'evidence', 'method'],
  )
}

function misconceptionItems(point: KnowledgePoint): DetailItem[] {
  return detailItems(
    point.misconceptions,
    ['observable_error_pattern', 'error_pattern', 'error', 'mistake'],
    ['repair_strategy', 'repair', 'remediation', 'discrimination'],
  )
}

function boundaryItems(point: KnowledgePoint): string[] {
  return [...(point.conditions || []), ...(point.boundaries || [])].filter(Boolean)
}

function knowledgeTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    concept: t('courseGeneration.lessonPlan.knowledgeTypes.concept', '概念'),
    principle: t('courseGeneration.lessonPlan.knowledgeTypes.principle', '原理'),
    procedure: t('courseGeneration.lessonPlan.knowledgeTypes.procedure', '方法'),
    skill: t('courseGeneration.lessonPlan.knowledgeTypes.skill', '技能'),
    fact: t('courseGeneration.lessonPlan.knowledgeTypes.fact', '事实'),
  }
  return labels[value] || value
}

function teachingModeLabel(value: string): string {
  const labels: Record<string, string> = {
    conceptual: t('courseGeneration.lessonPlan.teachingModes.conceptual', '概念建构'),
    worked_examples: t('courseGeneration.lessonPlan.teachingModes.workedExamples', '例题引导'),
    inquiry: t('courseGeneration.lessonPlan.teachingModes.inquiry', '探究学习'),
    project_based: t('courseGeneration.lessonPlan.teachingModes.projectBased', '项目实践'),
    procedural: t('courseGeneration.lessonPlan.teachingModes.procedural', '程序训练'),
    case_based: t('courseGeneration.lessonPlan.teachingModes.caseBased', '案例教学'),
    discussion: t('courseGeneration.lessonPlan.teachingModes.discussion', '讨论辨析'),
  }
  return labels[value] || value.replace(/_/g, ' ')
}

function openKnowledge(knowledgeId: string): void {
  if (!knowledgeId) return
  emit('open-knowledge', knowledgeId)
}
</script>

<style scoped>
.generation-lesson-plan {
  min-height:0;
  flex:1;
  overflow:auto;
  padding:36px clamp(24px,4.3vw,68px) 96px;
  color:#253044;
  background:
    linear-gradient(rgba(87,96,124,.035) 1px,transparent 1px),
    radial-gradient(circle at 91% 2%,rgba(78,88,196,.11),transparent 27%),
    linear-gradient(180deg,#fafaf8 0%,#f4f5f7 100%);
  background-size:100% 32px,auto,auto;
}
.generation-lesson-plan__header {
  width:min(1180px,100%);
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:end;
  gap:36px;
  margin:0 auto 22px;
  padding:0 3px 26px;
  border-bottom:1px solid #d8dce4;
}
.generation-lesson-plan__eyebrow { display:flex; align-items:center; gap:9px; color:#555bb7; font-size:12px; font-weight:800; letter-spacing:.07em; }
.generation-lesson-plan__eyebrow i { width:24px; height:1px; background:#b9bdd2; }
.generation-lesson-plan__eyebrow strong { color:#7b8392; font-size:12px; letter-spacing:0; }
.generation-lesson-plan__header h2 { margin:8px 0 7px; color:#172131; font:700 clamp(31px,3vw,40px)/1.13 Georgia,"Noto Serif SC",serif; letter-spacing:-.025em; }
.generation-lesson-plan__intro > p { max-width:660px; margin:0; color:#687285; font-size:14px; line-height:1.72; }
.generation-lesson-plan__summary { display:grid; gap:10px; }
.generation-lesson-plan__summary dl { display:flex; margin:0; padding:10px 8px; border:1px solid rgba(213,217,226,.95); border-radius:14px; background:rgba(255,255,255,.82); box-shadow:0 10px 30px rgba(36,43,64,.05); backdrop-filter:blur(14px); }
.generation-lesson-plan__summary dl div { min-width:94px; padding:3px 17px; border-left:1px solid #e1e4ea; }
.generation-lesson-plan__summary dl div:first-child { border-left:0; }
.generation-lesson-plan__summary dt { color:#858e9e; font-size:12px; line-height:1.3; }
.generation-lesson-plan__summary dd { margin:5px 0 0; color:#263146; font:750 19px/1 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__progress { padding:10px 13px; border:1px solid #dfe1f6; border-radius:11px; background:#f8f8ff; }
.generation-lesson-plan__progress > div:first-child { display:flex; justify-content:space-between; gap:14px; color:#5a60bb; font-size:12px; font-weight:750; }
.generation-lesson-plan__progress-track { height:4px; overflow:hidden; margin-top:8px; border-radius:999px; background:#e5e7f5; }
.generation-lesson-plan__progress-track i { display:block; height:100%; border-radius:inherit; background:#6268cc; transition:width .25s ease; }
.generation-lesson-plan__view-switch { width:min(1180px,100%); display:flex; gap:5px; margin:0 auto 14px; padding:5px; border:1px solid #dfe2e8; border-radius:14px; background:rgba(255,255,255,.76); box-shadow:0 8px 25px rgba(38,45,63,.04); backdrop-filter:blur(14px); }
.generation-lesson-plan__view-switch button { min-width:0; display:flex; align-items:center; gap:10px; padding:9px 14px; border:0; border-radius:10px; color:#737c8c; background:transparent; cursor:pointer; text-align:left; }
.generation-lesson-plan__view-switch button:hover { color:#4d55ae; background:#f6f6fc; }
.generation-lesson-plan__view-switch button.is-active { color:#4e55ad; background:#f0f1fb; box-shadow:inset 0 0 0 1px #dfe1f5; }
.generation-lesson-plan__view-switch button > span { display:grid; gap:1px; }
.generation-lesson-plan__view-switch button strong { color:inherit; font-size:12px; line-height:1.35; }
.generation-lesson-plan__view-switch button small { color:#969daa; font-size:11px; line-height:1.35; }
.generation-lesson-plan__overview { width:min(1180px,100%); overflow:hidden; margin:0 auto; border:1px solid #d9dde5; border-radius:20px; background:rgba(255,255,255,.97); box-shadow:0 20px 55px rgba(38,45,63,.075); }
.generation-lesson-plan__overview-hero { position:relative; display:grid; grid-template-columns:minmax(0,1fr) minmax(230px,.34fr); gap:40px; padding:38px 40px 34px; border-bottom:1px solid #e0e3e9; background:linear-gradient(120deg,#fbfbf9 0%,#fff 58%,#f2f3ff 100%); }
.generation-lesson-plan__overview-hero::before { content:""; position:absolute; top:0; left:40px; width:72px; height:3px; background:#6269c4; }
.generation-lesson-plan__overview-hero > div > span { color:#696fc0; font-size:12px; font-weight:800; letter-spacing:.09em; }
.generation-lesson-plan__overview-hero h3 { margin:8px 0 9px; color:#1b2636; font:700 28px/1.25 Georgia,"Noto Serif SC",serif; letter-spacing:-.02em; }
.generation-lesson-plan__overview-hero p { max-width:760px; margin:0; color:#687285; font-size:14px; line-height:1.75; }
.generation-lesson-plan__overview-hero aside { align-self:center; display:grid; grid-template-columns:28px minmax(0,1fr); gap:2px 8px; padding:15px 16px; border:1px solid #dfe2ec; border-radius:13px; background:rgba(255,255,255,.72); }
.generation-lesson-plan__overview-hero aside svg { grid-row:1 / 3; align-self:center; color:#6067bd; }
.generation-lesson-plan__overview-hero aside span { color:#9198a5; font-size:11px; font-weight:750; }
.generation-lesson-plan__overview-hero aside strong { color:#4b5669; font-size:13px; line-height:1.5; }
.generation-lesson-plan__overview-grid { display:grid; grid-template-columns:1.18fr .82fr; gap:0; border-bottom:1px solid #e4e6eb; }
.generation-lesson-plan__overview-card { min-width:0; padding:28px 32px 30px; border-top:1px solid #e8eaee; border-left:1px solid #e8eaee; background:#fff; }
.generation-lesson-plan__overview-card:nth-child(-n+2) { border-top:0; }
.generation-lesson-plan__overview-card:nth-child(odd) { border-left:0; }
.generation-lesson-plan__overview-card.is-objectives { background:linear-gradient(135deg,#fdfdfb,#fafaff); }
.generation-lesson-plan__overview-card > header { display:flex; align-items:center; gap:11px; margin-bottom:18px; }
.generation-lesson-plan__overview-card > header > svg { flex:none; color:#5960b7; }
.generation-lesson-plan__overview-card > header span { display:grid; gap:2px; }
.generation-lesson-plan__overview-card > header small { color:#9198a6; font-size:11px; font-weight:750; letter-spacing:.07em; }
.generation-lesson-plan__overview-card > header strong { color:#364154; font-size:15px; line-height:1.4; }
.generation-lesson-plan__overview-card ol { display:grid; gap:10px; margin:0; padding:0; list-style:none; }
.generation-lesson-plan__overview-card ol li { display:grid; grid-template-columns:26px minmax(0,1fr); gap:10px; align-items:start; }
.generation-lesson-plan__overview-card ol li > span { display:grid; place-items:center; width:24px; height:24px; border:1px solid #dde0f0; border-radius:7px; color:#6268b6; background:#f4f4fb; font:700 10px/1 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__overview-card ol p { margin:1px 0 0; color:#596579; font-size:13px; line-height:1.62; }
.generation-lesson-plan__plain-list { display:flex; flex-wrap:wrap; gap:7px; margin:0; padding:0; list-style:none; }
.generation-lesson-plan__plain-list li { padding:7px 10px; border:1px solid #e1e4ea; border-radius:8px; color:#596579; background:#f8f9fa; font-size:12px; line-height:1.4; }
.generation-lesson-plan__strategy-copy,.generation-lesson-plan__card-empty { margin:0; color:#667185; font-size:13px; line-height:1.7; }
.generation-lesson-plan__card-empty { color:#939aa6; }
.generation-lesson-plan__strategy-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:13px; }
.generation-lesson-plan__strategy-tags span { padding:5px 8px; border:1px solid #dfe2f4; border-radius:999px; color:#5b62b6; background:#f5f5fc; font-size:11px; font-weight:750; }
.generation-lesson-plan__overview-section { padding:31px 34px 34px; border-bottom:1px solid #e4e6eb; background:#fcfcfb; }
.generation-lesson-plan__overview-section:last-child { border-bottom:0; }
.generation-lesson-plan__overview-section > header { display:flex; align-items:end; justify-content:space-between; gap:28px; margin-bottom:21px; }
.generation-lesson-plan__overview-section > header > span { display:grid; gap:3px; }
.generation-lesson-plan__overview-section > header small { color:#8e96a4; font-size:11px; font-weight:750; letter-spacing:.07em; }
.generation-lesson-plan__overview-section > header strong { color:#303b4d; font-size:16px; }
.generation-lesson-plan__overview-section > header p { max-width:570px; margin:0; color:#7a8393; font-size:12px; line-height:1.6; text-align:right; }
.generation-lesson-plan__chapter-path { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:0; padding:0; list-style:none; counter-reset:chapters; }
.generation-lesson-plan__chapter-path li { position:relative; min-width:0; display:grid; grid-template-columns:34px minmax(0,1fr); gap:10px; padding:16px; border:1px solid #e0e3e9; border-radius:12px; background:#fff; }
.generation-lesson-plan__chapter-path li > span { display:grid; place-items:center; width:30px; height:30px; border-radius:9px; color:#575eb7; background:#f0f1fb; font:700 11px/1 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__chapter-path li > div { min-width:0; }
.generation-lesson-plan__chapter-path li strong { display:block; color:#414c5f; font-size:13px; line-height:1.45; }
.generation-lesson-plan__chapter-path li p { margin:4px 0 0; color:#7b8493; font-size:11px; line-height:1.55; }
.generation-lesson-plan__chapter-path li > small { grid-column:2; color:#999fac; font-size:11px; }
.generation-lesson-plan__overview-section.is-knowledge-map { background:linear-gradient(130deg,#fbfbff,#fff); }
.generation-lesson-plan__knowledge-tags { display:flex; flex-wrap:wrap; gap:8px; }
.generation-lesson-plan__knowledge-tags button { display:inline-flex; align-items:center; gap:6px; min-height:32px; padding:0 9px; border:1px solid #dfe2f2; border-radius:9px; color:#555cb2; background:#f8f8ff; font-size:12px; cursor:pointer; }
.generation-lesson-plan__knowledge-tags button:hover:not(:disabled) { border-color:#bfc4e8; background:#f0f1fb; transform:translateY(-1px); }
.generation-lesson-plan__knowledge-tags button:disabled { color:#8b91a1; background:#f5f6f8; cursor:default; }
.generation-lesson-plan__knowledge-tags button small { display:grid; place-items:center; min-width:18px; height:18px; border-radius:6px; color:#7278b7; background:#e8e9f7; font-size:11px; font-weight:800; }
.generation-lesson-plan__workspace { width:min(1180px,100%); margin:0 auto; }
.generation-lesson-plan__pager { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); align-items:center; gap:14px; margin:0 2px 12px; }
.generation-lesson-plan__pager > button { min-width:0; display:flex; align-items:center; gap:9px; padding:7px 9px; border:0; border-radius:9px; color:#687285; background:transparent; cursor:pointer; text-align:left; }
.generation-lesson-plan__pager > button:last-child { justify-content:flex-end; text-align:right; }
.generation-lesson-plan__pager > button:hover:not(:disabled) { color:#4f56b8; background:rgba(255,255,255,.68); }
.generation-lesson-plan__pager > button:disabled { opacity:.42; cursor:not-allowed; }
.generation-lesson-plan__pager > button span { min-width:0; display:grid; gap:2px; }
.generation-lesson-plan__pager > button small { color:#939aa7; font-size:12px; }
.generation-lesson-plan__pager > button strong { overflow:hidden; font-size:12px; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }
.generation-lesson-plan__pager > div { display:flex; align-items:center; gap:7px; color:#333d50; font:700 12px/1 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__pager > div i { width:22px; height:1px; background:#aeb4c0; }
.generation-lesson-plan__pager > div small { color:#8c94a2; font-size:12px; }
.generation-lesson-plan__sheet { overflow:hidden; border:1px solid #d9dde5; border-radius:19px; background:rgba(255,255,255,.97); box-shadow:0 20px 55px rgba(38,45,63,.075); }
.generation-lesson-plan__sheet-header { position:relative; display:grid; grid-template-columns:70px minmax(0,1fr) auto; align-items:start; gap:22px; padding:30px 34px 28px; border-bottom:1px solid #e1e4e9; background:linear-gradient(110deg,#fbfbfd 0%,#fff 66%,#f5f5ff 100%); }
.generation-lesson-plan__sheet-header::after { content:""; position:absolute; right:30px; bottom:0; width:130px; height:3px; background:linear-gradient(90deg,transparent,#7378d6); }
.generation-lesson-plan__section-mark { display:grid; place-items:center; width:58px; height:58px; border:1px solid #d9dcec; border-radius:15px; color:#535ab7; background:#f4f4ff; font:700 18px Georgia,"Noto Serif SC",serif; }
.generation-lesson-plan__section-title > span { color:#8a92a1; font-size:12px; font-weight:750; letter-spacing:.08em; }
.generation-lesson-plan__section-title h3 { margin:5px 0 8px; color:#1d2737; font:700 23px/1.35 Georgia,"Noto Serif SC",serif; }
.generation-lesson-plan__section-title p { max-width:760px; margin:0; color:#687285; font-size:14px; line-height:1.68; }
.generation-lesson-plan__readiness { display:inline-flex; align-items:center; gap:7px; margin-top:3px; padding:7px 10px; border:1px solid #e2e5ea; border-radius:999px; color:#788191; background:#f7f8fa; font-size:12px; font-weight:750; white-space:nowrap; }
.generation-lesson-plan__readiness[data-ready="true"] { border-color:#cceadd; color:#08785a; background:#effaf5; }
.generation-lesson-plan__readiness svg { flex:none; }
.generation-lesson-plan__readiness:not([data-ready="true"]) svg { animation:lesson-plan-spin .9s linear infinite; }
.generation-lesson-plan__block { padding:30px 34px 34px; border-bottom:1px solid #e4e7ec; }
.generation-lesson-plan__block:last-child { border-bottom:0; }
.generation-lesson-plan__block-heading { display:grid; grid-template-columns:38px minmax(190px,.58fr) minmax(260px,1fr); align-items:center; gap:13px 16px; margin-bottom:23px; }
.generation-lesson-plan__block-heading > div { display:grid; place-items:center; width:36px; height:36px; border:1px solid #dfe2e9; border-radius:10px; color:#555cb8; background:#f7f7fc; }
.generation-lesson-plan__block-heading > span { display:grid; gap:3px; }
.generation-lesson-plan__block-heading small { color:#8c94a2; font-size:12px; font-weight:750; letter-spacing:.06em; }
.generation-lesson-plan__block-heading strong { color:#283346; font-size:16px; line-height:1.35; }
.generation-lesson-plan__block-heading > p { justify-self:end; max-width:510px; margin:0; color:#7a8393; font-size:13px; line-height:1.6; text-align:right; }
.generation-lesson-plan__flow ol { display:grid; gap:0; margin:0; padding:0 0 0 7px; list-style:none; }
.generation-lesson-plan__flow li { display:grid; grid-template-columns:44px minmax(0,1fr); gap:14px; }
.generation-lesson-plan__module-index { display:grid; grid-template-rows:28px 1fr; justify-items:center; color:#5d63bd; font:700 12px/28px ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__module-index span { width:28px; height:28px; border:1px solid #cfd3ef; border-radius:50%; background:#f7f7ff; text-align:center; }
.generation-lesson-plan__module-index i { width:1px; min-height:26px; background:#dfe2e9; }
.generation-lesson-plan__flow li:last-child .generation-lesson-plan__module-index i { background:linear-gradient(#dfe2e9,transparent); }
.generation-lesson-plan__module-copy { margin:0 0 14px; padding:0 0 17px; border-bottom:1px solid #eceef2; }
.generation-lesson-plan__flow li:last-child .generation-lesson-plan__module-copy { margin-bottom:0; border-bottom:0; }
.generation-lesson-plan__module-copy > strong { display:block; color:#303b4e; font-size:15px; line-height:1.5; }
.generation-lesson-plan__module-copy > p { margin:5px 0 9px; color:#667185; font-size:13px; line-height:1.65; }
.generation-lesson-plan__module-copy > div { display:flex; flex-wrap:wrap; gap:6px; }
.generation-lesson-plan__module-copy > div span { padding:4px 8px; border:1px solid #e0e3f6; border-radius:6px; color:#555cb8; background:#f8f8ff; font-size:12px; line-height:1.35; }
.generation-lesson-plan__knowledge { background:#fcfcfb; }
.generation-lesson-plan__section-knowledge-tags { display:grid; grid-template-columns:140px minmax(0,1fr); align-items:start; gap:14px; margin:-3px 0 22px; padding:14px 15px; border:1px solid #e1e4ec; border-radius:12px; background:linear-gradient(110deg,#f7f7fc,#fff); }
.generation-lesson-plan__section-knowledge-tags > span { padding-top:6px; color:#727a8d; font-size:12px; font-weight:800; }
.generation-lesson-plan__section-knowledge-tags > div { display:flex; flex-wrap:wrap; gap:7px; }
.generation-lesson-plan__section-knowledge-tags button { display:inline-flex; align-items:center; gap:5px; min-height:29px; padding:0 9px; border:1px solid #dcdff0; border-radius:999px; color:#555cb3; background:#fff; font-size:11px; font-weight:750; cursor:pointer; }
.generation-lesson-plan__section-knowledge-tags button:hover:not(:disabled) { border-color:#bfc4e4; box-shadow:0 5px 14px rgba(77,84,160,.09); transform:translateY(-1px); }
.generation-lesson-plan__section-knowledge-tags button:disabled { color:#868e9d; background:#f5f6f8; cursor:default; }
.generation-lesson-plan__section-knowledge-tags button small { margin-left:2px; color:#a0a6b0; font-size:11px; font-weight:650; }
.generation-lesson-plan__knowledge-groups { display:grid; gap:22px; }
.generation-lesson-plan__knowledge-group { overflow:hidden; border:1px solid #dfe2e8; border-radius:14px; background:#fff; }
.generation-lesson-plan__knowledge-group > header { display:flex; gap:12px; padding:17px 19px 15px; border-bottom:1px solid #e7e9ed; background:#f8f8f6; }
.generation-lesson-plan__knowledge-group > header > span { color:#6a7190; font:700 12px/1.7 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__knowledge-group h4 { margin:0; color:#303a4b; font-size:14px; line-height:1.5; }
.generation-lesson-plan__knowledge-group > header p { margin:3px 0 0; color:#7b8493; font-size:12px; line-height:1.55; }
.generation-lesson-plan__knowledge-group details { border-top:1px solid #eceef1; }
.generation-lesson-plan__knowledge-group > header + details { border-top:0; }
.generation-lesson-plan__knowledge-group summary { display:grid; grid-template-columns:minmax(180px,.55fr) minmax(260px,1fr) auto; align-items:center; gap:18px; padding:16px 19px; cursor:pointer; list-style:none; }
.generation-lesson-plan__knowledge-group summary::-webkit-details-marker { display:none; }
.generation-lesson-plan__knowledge-group summary > div { display:flex; align-items:center; flex-wrap:wrap; gap:7px; }
.generation-lesson-plan__knowledge-group summary > div span { color:#2f394b; font-size:14px; font-weight:750; }
.generation-lesson-plan__knowledge-group summary > div small { padding:3px 6px; border-radius:5px; color:#6870b5; background:#f0f1fb; font-size:12px; }
.generation-lesson-plan__knowledge-group summary > p { margin:0; color:#737d8e; font-size:13px; line-height:1.55; }
.generation-lesson-plan__knowledge-group summary > svg { color:#8a92a0; transition:transform .18s ease; }
.generation-lesson-plan__knowledge-group details[open] summary { background:#fdfdff; }
.generation-lesson-plan__knowledge-group details[open] summary > svg { transform:rotate(180deg); }
.generation-lesson-plan__knowledge-detail { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; padding:0 19px 15px; }
.generation-lesson-plan__knowledge-detail > section { min-width:0; padding:14px; border:1px solid #e5e7ec; border-radius:10px; background:#fafbfc; }
.generation-lesson-plan__knowledge-detail > section.is-warning { border-color:#eee2d4; background:#fffaf3; }
.generation-lesson-plan__knowledge-detail header { display:flex; align-items:center; gap:7px; color:#525d70; font-size:12px; font-weight:800; }
.generation-lesson-plan__knowledge-detail header svg { color:#646bc2; }
.generation-lesson-plan__knowledge-detail .is-warning header svg { color:#b8752f; }
.generation-lesson-plan__knowledge-detail ul { display:grid; gap:7px; margin:10px 0 0; padding:0; list-style:none; }
.generation-lesson-plan__knowledge-detail li { position:relative; padding-left:12px; color:#596579; font-size:12px; line-height:1.55; }
.generation-lesson-plan__knowledge-detail li::before { content:""; position:absolute; top:.62em; left:0; width:4px; height:4px; border-radius:50%; background:#9197b9; }
.generation-lesson-plan__knowledge-detail li strong,.generation-lesson-plan__knowledge-detail li span { display:block; }
.generation-lesson-plan__knowledge-detail li strong { color:#4f5a6e; font-size:12px; }
.generation-lesson-plan__knowledge-detail li span { margin-top:2px; color:#7b8493; }
.generation-lesson-plan__knowledge-detail section > p { margin:10px 0 0; color:#9aa1ad; font-size:12px; }
.generation-lesson-plan__boundaries { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin:0 19px 17px; padding-top:13px; border-top:1px dashed #e0e3e8; }
.generation-lesson-plan__boundaries > span { margin-right:2px; color:#7b8493; font-size:12px; font-weight:750; }
.generation-lesson-plan__boundaries i { padding:3px 7px; border-radius:5px; color:#6c7484; background:#f0f2f5; font-size:12px; font-style:normal; }
.generation-lesson-plan__connections { background:linear-gradient(120deg,#fbfbff,#fff); }
.generation-lesson-plan__connections .generation-lesson-plan__block-heading { grid-template-columns:38px minmax(0,1fr); }
.generation-lesson-plan__connection-grid { display:grid; grid-template-columns:minmax(220px,.75fr) minmax(0,1.5fr); gap:12px; }
.generation-lesson-plan__connection-grid > div,.generation-lesson-plan__connection-grid > ul { margin:0; padding:16px 17px; border:1px solid #e1e4ea; border-radius:11px; background:rgba(255,255,255,.8); }
.generation-lesson-plan__connection-grid > div > span { color:#777f90; font-size:12px; font-weight:750; }
.generation-lesson-plan__connection-grid > div > p { margin:7px 0 0; color:#4f5a6d; font-size:13px; line-height:1.6; }
.generation-lesson-plan__connection-grid > ul { display:grid; gap:12px; list-style:none; }
.generation-lesson-plan__connection-grid li + li { padding-top:12px; border-top:1px solid #eceef2; }
.generation-lesson-plan__connection-grid li > div { display:flex; align-items:center; gap:8px; color:#4d5780; font-size:12px; font-weight:750; }
.generation-lesson-plan__connection-grid li > p { margin:5px 0 0; color:#778091; font-size:12px; line-height:1.55; }
.generation-lesson-plan__inline-empty { margin:0; padding:24px; border:1px dashed #d9dde5; border-radius:11px; color:#858d9c; background:#fafbfc; font-size:13px; text-align:center; }
.generation-lesson-plan__skeleton { display:grid; gap:18px; padding:34px; }
.generation-lesson-plan__skeleton > div { display:grid; gap:10px; padding:20px; border:1px solid #e5e7ec; border-radius:12px; }
.generation-lesson-plan__skeleton i { height:13px; border-radius:4px; background:linear-gradient(90deg,#eef0f4 20%,#f8f9fb 45%,#eef0f4 70%); background-size:220% 100%; animation:lesson-plan-shimmer 1.4s ease infinite; }
.generation-lesson-plan__skeleton i:nth-child(2) { width:78%; }
.generation-lesson-plan__skeleton i:nth-child(3) { width:56%; }
.generation-lesson-plan__legacy,.generation-lesson-plan__empty { display:grid; place-items:center; min-height:250px; color:#7b8496; text-align:center; }
.generation-lesson-plan__legacy { min-height:300px; }
.generation-lesson-plan__legacy strong,.generation-lesson-plan__empty strong { margin-top:12px; color:#384356; font-size:16px; }
.generation-lesson-plan__legacy p,.generation-lesson-plan__empty p { margin:6px 0 0; font-size:13px; line-height:1.6; }
.generation-lesson-plan__empty svg { animation:lesson-plan-spin .9s linear infinite; }
@keyframes lesson-plan-spin { to { transform:rotate(360deg); } }
@keyframes lesson-plan-shimmer { to { background-position:-220% 0; } }
@media (max-width:900px) {
  .generation-lesson-plan__header { grid-template-columns:1fr; align-items:start; gap:16px; }
  .generation-lesson-plan__summary { width:100%; }
  .generation-lesson-plan__summary dl div { min-width:0; flex:1; }
  .generation-lesson-plan__overview-hero { grid-template-columns:1fr; gap:20px; }
  .generation-lesson-plan__overview-hero aside { max-width:520px; }
  .generation-lesson-plan__chapter-path { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .generation-lesson-plan__sheet-header { grid-template-columns:58px minmax(0,1fr); }
  .generation-lesson-plan__readiness { grid-column:2; justify-self:start; }
  .generation-lesson-plan__block-heading { grid-template-columns:38px minmax(0,1fr); }
  .generation-lesson-plan__block-heading > p { grid-column:2; justify-self:start; text-align:left; }
  .generation-lesson-plan__knowledge-detail { grid-template-columns:1fr; }
}
@media (max-width:767px) {
  .generation-lesson-plan { padding:22px 10px 86px; background-size:100% 28px,auto,auto; }
  .generation-lesson-plan__header { margin-bottom:14px; padding:0 6px 20px; }
  .generation-lesson-plan__header h2 { font-size:29px; }
  .generation-lesson-plan__summary dl div { padding:3px 10px; }
  .generation-lesson-plan__view-switch { width:calc(100% - 4px); }
  .generation-lesson-plan__view-switch button { flex:1; padding:9px 10px; }
  .generation-lesson-plan__view-switch button small { display:none; }
  .generation-lesson-plan__overview { border-radius:15px; }
  .generation-lesson-plan__overview-hero { padding:29px 20px 24px; }
  .generation-lesson-plan__overview-hero::before { left:20px; }
  .generation-lesson-plan__overview-hero h3 { font-size:24px; }
  .generation-lesson-plan__overview-grid { grid-template-columns:1fr; }
  .generation-lesson-plan__overview-card,.generation-lesson-plan__overview-card:nth-child(-n+2) { padding:24px 20px; border-top:1px solid #e8eaee; border-left:0; }
  .generation-lesson-plan__overview-card:first-child { border-top:0; }
  .generation-lesson-plan__overview-section { padding:25px 20px 27px; }
  .generation-lesson-plan__overview-section > header { display:grid; gap:8px; }
  .generation-lesson-plan__overview-section > header p { text-align:left; }
  .generation-lesson-plan__chapter-path { grid-template-columns:1fr; }
  .generation-lesson-plan__pager { grid-template-columns:1fr auto 1fr; gap:5px; }
  .generation-lesson-plan__pager > button { padding:7px 3px; }
  .generation-lesson-plan__pager > button strong { display:none; }
  .generation-lesson-plan__pager > div i { width:12px; }
  .generation-lesson-plan__sheet { border-radius:15px; }
  .generation-lesson-plan__sheet-header { grid-template-columns:46px minmax(0,1fr); gap:13px; padding:22px 16px 20px; }
  .generation-lesson-plan__section-mark { width:44px; height:44px; border-radius:12px; font-size:15px; }
  .generation-lesson-plan__section-title h3 { font-size:20px; }
  .generation-lesson-plan__readiness { grid-column:1 / -1; margin:0; }
  .generation-lesson-plan__block { padding:24px 16px 27px; }
  .generation-lesson-plan__block-heading { align-items:start; gap:10px 11px; margin-bottom:18px; }
  .generation-lesson-plan__block-heading > p { grid-column:1 / -1; }
  .generation-lesson-plan__section-knowledge-tags { grid-template-columns:1fr; gap:8px; }
  .generation-lesson-plan__section-knowledge-tags > span { padding-top:0; }
  .generation-lesson-plan__knowledge-group summary { grid-template-columns:minmax(0,1fr) auto; gap:8px; }
  .generation-lesson-plan__knowledge-group summary > p { grid-column:1 / -1; grid-row:2; }
  .generation-lesson-plan__knowledge-group summary > svg { grid-column:2; grid-row:1; }
  .generation-lesson-plan__knowledge-detail { padding:0 12px 13px; }
  .generation-lesson-plan__boundaries { margin:0 12px 14px; }
  .generation-lesson-plan__connection-grid { grid-template-columns:1fr; }
}
@media (prefers-reduced-motion:reduce) {
  .generation-lesson-plan__progress-track i,
  .generation-lesson-plan__readiness svg,
  .generation-lesson-plan__empty svg,
  .generation-lesson-plan__skeleton i,
  .generation-lesson-plan__knowledge-group summary > svg { animation:none; transition:none; }
}
</style>
