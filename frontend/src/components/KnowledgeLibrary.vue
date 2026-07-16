<template>
  <Teleport to="body">
    <Transition name="knowledge-tree-modal">
      <div
        v-if="courseStore.showKnowledgeLibrary"
        class="knowledge-tree-overlay"
        @click.self="handleClose"
      >
        <section
          ref="dialogRef"
          class="knowledge-tree-dialog"
          role="dialog"
          aria-modal="true"
          :aria-label="t('knowledgeLibrary.title', '知识库')"
          tabindex="-1"
        >
          <header class="knowledge-tree-header">
            <div class="knowledge-tree-heading">
              <span class="knowledge-tree-brand" aria-hidden="true">
                <Library :size="19" />
              </span>
              <div>
                <h1>{{ t('knowledgeLibrary.title', '知识库') }}</h1>
                <p v-if="libraryView">
                  {{ t('knowledgeLibrary.courseCoverage', '本课覆盖') }} {{ coveredPointCount }} / {{ pointCount }}
                  <span aria-hidden="true">·</span>
                  {{ t('knowledgeLibrary.relationCount', '知识关系') }} {{ formalRelations.length }}
                </p>
                <p v-else>{{ t('knowledgeLibrary.subtitle', '查看学科结构与本课程覆盖') }}</p>
              </div>
            </div>

            <label class="knowledge-tree-search">
              <Search :size="16" aria-hidden="true" />
              <span class="sr-only">{{ t('knowledgeLibrary.search', '搜索知识点') }}</span>
              <input
                v-model="searchQuery"
                type="search"
                :placeholder="t('knowledgeLibrary.searchPlaceholder', '搜索知识点、别名或路径')"
                @keydown.enter.prevent="selectFirstMatch"
              >
              <button
                v-if="searchQuery"
                type="button"
                :title="t('knowledgeLibrary.clearSearch', '清除搜索')"
                :aria-label="t('knowledgeLibrary.clearSearch', '清除搜索')"
                @click="searchQuery = ''"
              >
                <X :size="14" />
              </button>
            </label>

            <button
              type="button"
              class="knowledge-tree-close"
              :title="t('knowledgeLibrary.close', '关闭知识库')"
              :aria-label="t('knowledgeLibrary.close', '关闭知识库')"
              @click="handleClose"
            >
              <X :size="18" />
            </button>
          </header>

          <section v-if="libraryView" class="knowledge-tree-governance" :class="`is-${libraryView.lifecycle_status}`">
            <div class="knowledge-tree-governance-summary">
              <span data-testid="knowledge-lifecycle" class="knowledge-tree-lifecycle">
                {{ lifecycleLabel }}
              </span>
              <div data-testid="knowledge-quality" class="knowledge-tree-quality">
                <strong>{{ t('knowledgeLibrary.qualityScore', '质量') }} {{ libraryView.quality_report?.score ?? '—' }}</strong>
                <span>{{ t('knowledgeLibrary.mappingRate', '映射率') }} {{ percent(libraryView.quality_report?.metrics?.mapped_ratio ?? libraryView.coverage.mapped_ratio) }}</span>
                <span>{{ t('knowledgeLibrary.relationCoverage', '关系覆盖') }} {{ percent(libraryView.quality_report?.metrics?.relation_coverage ?? 0) }}</span>
              </div>
              <div data-testid="knowledge-source-summary" class="knowledge-tree-quality">
                <strong>{{ t('knowledgeLibrary.sources', '来源') }}</strong>
                <span v-for="item in sourceSummaryRows" :key="item.key">{{ item.label }} {{ item.count }}</span>
              </div>
              <span
                v-if="candidateRelationCount && libraryView.lifecycle_status !== 'candidate'"
                data-testid="knowledge-candidate-relations"
                class="knowledge-tree-lifecycle"
              >{{ t('knowledgeLibrary.candidateRelations', '候选关系') }} {{ candidateRelationCount }} {{ t('knowledgeLibrary.notEnabled', '条未启用') }}</span>
              <div v-if="reviewSummary" data-testid="knowledge-diff" class="knowledge-tree-diff">
                <span>{{ t('knowledgeLibrary.diffAdded', '新增') }} {{ reviewSummary.diff.added }}</span>
                <span>{{ t('knowledgeLibrary.diffModified', '修改') }} {{ reviewSummary.diff.modified }}</span>
                <span>{{ t('knowledgeLibrary.diffRemoved', '删除') }} {{ reviewSummary.diff.removed }}</span>
              </div>
            </div>
            <ul
              v-if="libraryView.quality_report?.issues?.length"
              data-testid="knowledge-quality-issues"
              class="knowledge-tree-quality-issues"
            >
              <li v-for="issue in libraryView.quality_report.issues" :key="`${issue.code}:${issue.message}`">
                {{ issue.message }}
              </li>
            </ul>
            <div class="knowledge-tree-governance-actions">
              <input
                v-if="libraryView.lifecycle_status === 'candidate'"
                v-model="reviewNote"
                data-testid="knowledge-review-note"
                type="text"
                :placeholder="t('knowledgeLibrary.reviewNote', '审核备注或退回原因')"
                :disabled="governanceActing"
              >
              <button
                v-if="libraryView.lifecycle_status === 'candidate'"
                data-testid="knowledge-accept"
                type="button"
                :disabled="governanceActing"
                @click="reviewLibrary('accept')"
              >{{ t('knowledgeLibrary.acceptVersion', '接受整个版本') }}</button>
              <button
                v-if="libraryView.lifecycle_status === 'candidate'"
                data-testid="knowledge-reject"
                type="button"
                :disabled="governanceActing"
                @click="reviewLibrary('reject')"
              >{{ t('knowledgeLibrary.rejectVersion', '退回整个版本') }}</button>
              <button
                data-testid="knowledge-rebuild"
                type="button"
                :disabled="governanceActing"
                @click="rebuildLibrary"
              ><RefreshCw :size="14" />{{ t('knowledgeLibrary.rebuild', '重新生成') }}</button>
              <span v-if="governanceError" class="knowledge-tree-governance-error" role="alert">{{ governanceError }}</span>
            </div>
          </section>

          <main class="knowledge-tree-main" :class="{ 'is-detail-open': mobileDetailOpen }">
            <div v-if="loading" class="knowledge-tree-state" role="status">
              <LoaderCircle :size="24" class="knowledge-tree-spinner" />
              <strong>{{ t('knowledgeLibrary.loading', '正在读取知识库') }}</strong>
              <span>{{ t('knowledgeLibrary.loadingHint', '知识、能力、易错、提升与本课覆盖会一起载入') }}</span>
            </div>

            <div v-else-if="loadError" class="knowledge-tree-state knowledge-tree-state--error" role="alert">
              <AlertCircle :size="24" />
              <strong>{{ t('knowledgeLibrary.loadFailed', '知识库暂时无法读取') }}</strong>
              <span>{{ loadError }}</span>
              <button type="button" @click="loadLibrary">
                <RefreshCw :size="15" />
                {{ t('knowledgeLibrary.retry', '重新载入') }}
              </button>
            </div>

            <div v-else-if="!libraryView || !libraryView.nodes.length" class="knowledge-tree-state">
              <FolderTree :size="25" />
              <strong>{{ t('knowledgeLibrary.empty', '当前学科还没有可用的正式知识库') }}</strong>
            </div>

            <template v-else>
              <aside class="knowledge-tree-pane" :aria-label="t('knowledgeLibrary.outline', '学科知识目录')">
                <div class="knowledge-tree-pane-head">
                  <div>
                    <ListTree :size="15" />
                    <strong>{{ t('knowledgeLibrary.outline', '学科知识目录') }}</strong>
                  </div>
                  <div class="knowledge-tree-scope" :aria-label="t('knowledgeLibrary.scope', '知识范围')">
                    <button type="button" :class="{ active: coverageMode === 'course' }" @click="coverageMode = 'course'">
                      {{ t('knowledgeLibrary.coveredOnly', '本课覆盖') }}
                    </button>
                    <button type="button" :class="{ active: coverageMode === 'all' }" @click="coverageMode = 'all'">
                      {{ t('knowledgeLibrary.allKnowledge', '全部知识') }}
                    </button>
                  </div>
                </div>

                <div v-if="searchQuery && visibleRows.length === 0" class="knowledge-tree-no-results">
                  <Search :size="18" />
                  <span>{{ t('knowledgeLibrary.noResults', '当前范围内没有匹配的知识点') }}</span>
                </div>

                <div v-else class="knowledge-tree-scroll">
                  <div class="knowledge-tree-list" role="tree">
                    <div
                      v-for="row in visibleRows"
                      :key="row.node.knowledge_id"
                      class="knowledge-tree-row"
                      :class="[
                        `is-${row.node.node_type}`,
                        { 'is-selected': selectedNode?.knowledge_id === row.node.knowledge_id },
                      ]"
                      :style="{ '--tree-depth': row.depth }"
                      role="treeitem"
                      :aria-level="row.depth + 1"
                      :aria-expanded="row.hasChildren ? row.expanded : undefined"
                      :aria-selected="selectedNode?.knowledge_id === row.node.knowledge_id"
                    >
                      <button
                        v-if="row.hasChildren"
                        type="button"
                        class="knowledge-tree-toggle"
                        :title="row.expanded ? t('knowledgeLibrary.collapse', '收起') : t('knowledgeLibrary.expand', '展开')"
                        :aria-label="row.expanded ? t('knowledgeLibrary.collapse', '收起') : t('knowledgeLibrary.expand', '展开')"
                        @click.stop="toggleNode(row.node.knowledge_id)"
                      >
                        <ChevronDown v-if="row.expanded" :size="14" />
                        <ChevronRight v-else :size="14" />
                      </button>
                      <span v-else class="knowledge-tree-leaf-line" aria-hidden="true"></span>

                      <button
                        type="button"
                        class="knowledge-tree-node"
                        @click="selectNode(row.node, row.hasChildren)"
                      >
                        <component :is="nodeIcon(row.node.node_type)" :size="15" aria-hidden="true" />
                        <span class="knowledge-tree-node-name">{{ row.node.name }}</span>
                        <BookOpenCheck
                          v-if="row.node.covered_by_course"
                          :size="13"
                          class="knowledge-tree-covered-icon"
                          :title="t('knowledgeLibrary.coveredByCourse', '本课程已覆盖')"
                        />
                      </button>
                    </div>
                  </div>
                </div>
              </aside>

              <article class="knowledge-tree-detail" aria-live="polite">
                <button
                  type="button"
                  class="knowledge-tree-back"
                  @click="mobileDetailOpen = false"
                >
                  <ArrowLeft :size="16" />
                  {{ t('knowledgeLibrary.backToLibrary', '返回知识目录') }}
                </button>

                <template v-if="selectedNode">
                  <nav class="knowledge-tree-breadcrumb" :aria-label="t('knowledgeLibrary.path', '知识路径')">
                    <template v-for="(name, index) in selectedNode.path_names" :key="`${name}-${index}`">
                      <span>{{ name }}</span>
                      <ChevronRight v-if="index < selectedNode.path_names.length - 1" :size="12" aria-hidden="true" />
                    </template>
                  </nav>

                  <div class="knowledge-tree-detail-head">
                    <div class="knowledge-tree-detail-icon" aria-hidden="true">
                      <component :is="nodeIcon(selectedNode.node_type)" :size="21" />
                    </div>
                    <div>
                      <div class="knowledge-tree-kicker">
                        {{ nodeTypeLabel(selectedNode.node_type) }}
                        <span v-if="selectedNode.covered_by_course">
                          {{ t('knowledgeLibrary.coveredByCourse', '本课程已覆盖') }}
                        </span>
                      </div>
                      <h2>{{ selectedNode.name }}</h2>
                    </div>
                  </div>

                  <p class="knowledge-tree-description">
                    {{ selectedNode.description || descriptionFallback(selectedNode) }}
                  </p>

                  <div v-if="selectedNode.covered_by_course" class="knowledge-tree-bindings" :aria-label="t('knowledgeLibrary.bindingSummary', '本课绑定概况')">
                    <span><FileText :size="15" />{{ selectedNode.block_ids.length }} {{ t('knowledgeLibrary.contentBlocks', '处正文') }}</span>
                    <span><CheckCircle2 :size="15" />{{ selectedQuestions.length }} {{ t('knowledgeLibrary.questions', '道题目') }}</span>
                    <span><BrainCircuit :size="15" />{{ selectedSkills.length }} {{ t('knowledgeLibrary.skills', '项能力') }}</span>
                  </div>

                  <section v-if="selectedNode.learning_actions.length" class="knowledge-tree-section">
                    <h3><Target :size="17" />{{ t('knowledgeLibrary.learningActions', '学会后应该能做到') }}</h3>
                    <ul class="knowledge-tree-action-list">
                      <li v-for="action in selectedNode.learning_actions" :key="action">{{ action }}</li>
                    </ul>
                  </section>

                  <section v-if="selectedSkillGroups.length" class="knowledge-tree-section">
                    <h3><BrainCircuit :size="17" />{{ t('knowledgeLibrary.skillStructure', '能力、易错与提升') }}</h3>
                    <div class="knowledge-tree-skill-groups">
                      <article v-for="group in selectedSkillGroups" :key="group.skill.skill_unit_id" class="knowledge-tree-skill-group">
                        <div class="knowledge-tree-skill-head">
                          <span>{{ t('knowledgeLibrary.skill', '能力点') }}</span>
                          <strong>{{ group.skill.name }}</strong>
                          <p>{{ group.skill.learning_goal }}</p>
                        </div>
                        <div v-if="group.mistakes.length || group.improvements.length" class="knowledge-tree-skill-children">
                          <div v-if="group.mistakes.length" class="knowledge-tree-skill-branch is-mistake">
                            <h4><AlertTriangle :size="14" />{{ t('knowledgeLibrary.mistakePoints', '易错点') }}</h4>
                            <div v-for="item in group.mistakes" :key="item.mistake_point_id">
                              <strong>{{ item.name }}</strong>
                              <p>{{ item.repair_strategy || item.discrimination }}</p>
                            </div>
                          </div>
                          <div v-if="group.improvements.length" class="knowledge-tree-skill-branch is-improvement">
                            <h4><TrendingUp :size="14" />{{ t('knowledgeLibrary.improvementPoints', '提升点') }}</h4>
                            <div v-for="item in group.improvements" :key="item.improvement_point_id">
                              <strong>{{ item.name }}</strong>
                              <p>{{ item.practice_strategy || item.learning_goal }}</p>
                            </div>
                          </div>
                        </div>
                      </article>
                    </div>
                  </section>

                  <section v-if="selectedChildren.length" class="knowledge-tree-section">
                    <h3><Layers3 :size="17" />{{ childSectionTitle }}</h3>
                    <div class="knowledge-tree-child-list">
                      <button
                        v-for="child in selectedChildren"
                        :key="child.knowledge_id"
                        type="button"
                        @click="selectNode(child, hasChildren(child.knowledge_id))"
                      >
                        <component :is="nodeIcon(child.node_type)" :size="15" />
                        <span>{{ child.name }}</span>
                        <ChevronRight :size="14" />
                      </button>
                    </div>
                  </section>

                  <section v-if="selectedCriteria.length || selectedQuestions.length" class="knowledge-tree-section">
                    <h3><CheckCircle2 :size="17" />{{ t('knowledgeLibrary.assessment', '练习与验收') }}</h3>
                    <ul class="knowledge-tree-evidence-list">
                      <li v-for="criterion in selectedCriteria" :key="criterion.asset_id">
                        {{ criterion.observable_performance || t('knowledgeLibrary.criterionFallback', '完成本知识点的掌握检查') }}
                      </li>
                      <li v-for="question in selectedQuestions.slice(0, 3)" :key="question.asset_id">
                        {{ question.prompt || t('knowledgeLibrary.questionFallback', '已有正式练习') }}
                      </li>
                    </ul>
                  </section>

                  <section v-if="selectedMisconceptions.length" class="knowledge-tree-section">
                    <h3><AlertTriangle :size="17" />{{ t('knowledgeLibrary.courseMisconceptions', '本课特别提醒') }}</h3>
                    <div class="knowledge-tree-misconceptions">
                      <div v-for="item in selectedMisconceptions" :key="item.asset_id">
                        <strong>{{ item.error_pattern || t('knowledgeLibrary.misconceptionFallback', '需要辨析的误区') }}</strong>
                        <p v-if="item.discrimination">{{ item.discrimination }}</p>
                      </div>
                    </div>
                  </section>

                  <section v-if="relatedKnowledge.length" class="knowledge-tree-section">
                    <h3><Link2 :size="17" />{{ t('knowledgeLibrary.relations', '知识关系') }}</h3>
                    <div class="knowledge-tree-relations">
                      <button
                        v-for="entry in relatedKnowledge"
                        :key="entry.relation.relation_id"
                        type="button"
                        @click="selectNode(entry.node, hasChildren(entry.node.knowledge_id))"
                      >
                        <span>{{ relationLabel(entry.relation, entry.direction) }}</span>
                        <strong>{{ entry.node.name }}</strong>
                        <ChevronRight :size="14" />
                      </button>
                    </div>
                  </section>

                  <footer class="knowledge-tree-detail-footer">
                    <div>
                      <span>{{ sourceLabel(selectedNode.source_status) }}</span>
                      <span>{{ selectedNode.code }}</span>
                    </div>
                    <button v-if="jumpTarget" type="button" @click="navigateToCourse">
                      <ExternalLink :size="15" />
                      {{ t('knowledgeLibrary.jumpToContent', '回到对应正文') }}
                    </button>
                  </footer>
                </template>

                <div v-else class="knowledge-tree-detail-empty">
                  <CircleDot :size="24" />
                  <strong>{{ t('knowledgeLibrary.selectPoint', '选择一个知识点查看详情') }}</strong>
                </div>
              </article>
            </template>
          </main>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  ExternalLink,
  FileText,
  FolderTree,
  Layers3,
  Link2,
  ListTree,
  LoaderCircle,
  Library,
  Network,
  RefreshCw,
  Search,
  Target,
  TrendingUp,
  X,
} from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { t } from '../shared/i18n'
import http from '../utils/http'
import logger from '../utils/logger'
import type {
  BoundCriterion,
  BoundMisconception,
  BoundQuestion,
  KnowledgeLibraryRow,
  KnowledgeNodeType,
  KnowledgeLibraryView,
  KnowledgeNode,
  KnowledgeRelation,
  KnowledgeLibraryReview,
  ImprovementPoint,
  MistakePoint,
  SkillUnit,
} from '../types/knowledge-library'

const courseStore = useCourseStore()
const dialogRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const loadError = ref('')
const searchQuery = ref('')
const coverageMode = ref<'course' | 'all'>('course')
const libraryView = ref<KnowledgeLibraryView | null>(null)
const selectedNode = ref<KnowledgeNode | null>(null)
const expandedIds = ref<Set<string>>(new Set())
const mobileDetailOpen = ref(false)
const questions = ref<BoundQuestion[]>([])
const criteria = ref<BoundCriterion[]>([])
const misconceptions = ref<BoundMisconception[]>([])
const reviewSummary = ref<KnowledgeLibraryReview | null>(null)
const reviewNote = ref('')
const governanceActing = ref(false)
const governanceError = ref('')

const nodeById = computed(() => new Map(
  (libraryView.value?.nodes || []).map(node => [node.knowledge_id, node]),
))

const childrenByParent = computed(() => {
  const result = new Map<string | null, KnowledgeNode[]>()
  for (const node of libraryView.value?.nodes || []) {
    const key = node.parent_id || null
    const siblings = result.get(key) || []
    siblings.push(node)
    result.set(key, siblings)
  }
  for (const siblings of result.values()) {
    siblings.sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name))
  }
  return result
})

const pointCount = computed(() => (
  libraryView.value?.nodes.filter(node => node.node_type === 'knowledge_point').length || 0
))

const coveredPointCount = computed(() => (
  libraryView.value?.nodes.filter(node => node.node_type === 'knowledge_point' && node.covered_by_course).length || 0
))

const formalRelations = computed(() => (
  libraryView.value?.relations.filter(relation => (
    relation.status === 'accepted'
    || (libraryView.value?.lifecycle_status === 'candidate' && relation.status === 'candidate')
  )) || []
))

const candidateRelationCount = computed(() => (
  libraryView.value?.relations.filter(relation => relation.status === 'candidate').length || 0
))

const sourceSummaryRows = computed(() => {
  const labels: Record<string, string> = {
    course_source: t('knowledgeLibrary.sourceCourse', '课程来源'),
    material_source: t('knowledgeLibrary.sourceMaterial', '资料来源'),
    model_inferred: t('knowledgeLibrary.sourceModel', '模型推断'),
    curated: t('knowledgeLibrary.sourceCurated', '人工预制'),
  }
  return Object.entries(libraryView.value?.source_summary || {})
    .filter(([, count]) => Number(count) > 0)
    .map(([key, count]) => ({ key, count, label: labels[key] || key }))
})

const lifecycleLabel = computed(() => ({
  accepted: t('knowledgeLibrary.lifecycleAccepted', '正式知识库'),
  candidate: t('knowledgeLibrary.lifecycleCandidate', '候选知识库'),
  degraded: t('knowledgeLibrary.lifecycleDegraded', '课程索引 · 待重建'),
  rejected: t('knowledgeLibrary.lifecycleRejected', '已退回知识库'),
}[libraryView.value?.lifecycle_status || 'degraded']))

const normalizedQuery = computed(() => searchQuery.value.trim().toLocaleLowerCase())

const matchingIds = computed(() => {
  const query = normalizedQuery.value
  if (!query || !libraryView.value) return new Set<string>()
  return new Set(libraryView.value.nodes.filter(node => {
    const searchable = [
      node.name,
      node.description,
      ...node.aliases,
      ...node.path_names,
    ].join(' ').toLocaleLowerCase()
    return searchable.includes(query)
  }).map(node => node.knowledge_id))
})

const includedSearchIds = computed(() => {
  const included = new Set<string>()
  for (const knowledgeId of matchingIds.value) {
    let current = nodeById.value.get(knowledgeId)
    while (current) {
      included.add(current.knowledge_id)
      current = current.parent_id ? nodeById.value.get(current.parent_id) : undefined
    }
  }
  return included
})

const includedCoverageIds = computed(() => {
  if (coverageMode.value === 'all') return new Set(libraryView.value?.nodes.map(node => node.knowledge_id) || [])
  const included = new Set<string>()
  for (const node of libraryView.value?.nodes || []) {
    if (!node.covered_by_course) continue
    let current: KnowledgeNode | undefined = node
    while (current) {
      included.add(current.knowledge_id)
      current = current.parent_id ? nodeById.value.get(current.parent_id) : undefined
    }
  }
  return included
})

const visibleRows = computed<KnowledgeLibraryRow[]>(() => {
  if (!libraryView.value) return []
  const rows: KnowledgeLibraryRow[] = []
  const searching = Boolean(normalizedQuery.value)
  const walk = (node: KnowledgeNode, depth: number) => {
    if (!includedCoverageIds.value.has(node.knowledge_id)) return
    if (searching && !includedSearchIds.value.has(node.knowledge_id)) return
    const children = (childrenByParent.value.get(node.knowledge_id) || [])
      .filter(child => includedCoverageIds.value.has(child.knowledge_id))
    const expanded = searching || expandedIds.value.has(node.knowledge_id)
    rows.push({ node, depth, hasChildren: children.length > 0, expanded })
    if (expanded) children.forEach(child => walk(child, depth + 1))
  }
  for (const root of childrenByParent.value.get(null) || []) walk(root, 0)
  return rows
})

const selectedChildren = computed(() => (
  selectedNode.value
    ? (childrenByParent.value.get(selectedNode.value.knowledge_id) || [])
      .filter(child => includedCoverageIds.value.has(child.knowledge_id))
    : []
))

const questionById = computed(() => new Map(questions.value.map(item => [item.question_id || item.asset_id, item])))
const criterionById = computed(() => new Map(criteria.value.map(item => [item.criterion_id || item.asset_id, item])))
const misconceptionById = computed(() => new Map(
  misconceptions.value.map(item => [item.misconception_id || item.asset_id, item]),
))
const skillById = computed(() => new Map((libraryView.value?.skill_units || []).map(item => [item.skill_unit_id, item])))

const selectedQuestions = computed(() => (
  (selectedNode.value?.question_ids || [])
    .map(id => questionById.value.get(id))
    .filter((item): item is BoundQuestion => Boolean(item))
))

const selectedCriteria = computed(() => (
  (selectedNode.value?.criterion_ids || [])
    .map(id => criterionById.value.get(id))
    .filter((item): item is BoundCriterion => Boolean(item))
))

const selectedMisconceptions = computed(() => (
  (selectedNode.value?.misconception_ids || [])
    .map(id => misconceptionById.value.get(id))
    .filter((item): item is BoundMisconception => Boolean(item))
))

const selectedSkills = computed(() => (
  (selectedNode.value?.skill_unit_ids || [])
    .map(id => skillById.value.get(id))
    .filter((item): item is SkillUnit => Boolean(item))
))

const selectedSkillGroups = computed(() => selectedSkills.value.map(skill => ({
  skill,
  mistakes: (libraryView.value?.mistake_points || [])
    .filter((item: MistakePoint) => item.skill_unit_id === skill.skill_unit_id),
  improvements: (libraryView.value?.improvement_points || [])
    .filter((item: ImprovementPoint) => item.skill_unit_id === skill.skill_unit_id),
})))

const relatedKnowledge = computed(() => {
  const selectedId = selectedNode.value?.knowledge_id
  if (!selectedId) return []
  const entries: Array<{
    relation: KnowledgeRelation
    node: KnowledgeNode
    direction: 'incoming' | 'outgoing'
  }> = []
  for (const relation of formalRelations.value) {
    const outgoing = relation.source_knowledge_id === selectedId
    const incoming = relation.target_knowledge_id === selectedId
    if (!outgoing && !incoming) continue
    const otherId = outgoing ? relation.target_knowledge_id : relation.source_knowledge_id
    const node = nodeById.value.get(otherId)
    if (node) entries.push({ relation, node, direction: outgoing ? 'outgoing' : 'incoming' })
  }
  return entries
})

const jumpTarget = computed(() => {
  if (!selectedNode.value) return ''
  if (selectedNode.value.section_ids.length) return selectedNode.value.section_ids[0]
  const queue = [...selectedChildren.value]
  while (queue.length) {
    const child = queue.shift()!
    if (child.section_ids.length) return child.section_ids[0]
    queue.push(...(childrenByParent.value.get(child.knowledge_id) || []))
  }
  return ''
})

const childSectionTitle = computed(() => {
  if (selectedNode.value?.node_type === 'concept') return t('knowledgeLibrary.knowledgePoints', '细知识点')
  if (selectedNode.value?.node_type === 'topic') return t('knowledgeLibrary.concepts', '核心概念')
  return t('knowledgeLibrary.children', '下级知识')
})

function hasChildren(knowledgeId: string): boolean {
  return Boolean(childrenByParent.value.get(knowledgeId)?.length)
}

function toggleNode(knowledgeId: string): void {
  const next = new Set(expandedIds.value)
  if (next.has(knowledgeId)) next.delete(knowledgeId)
  else next.add(knowledgeId)
  expandedIds.value = next
}

function selectNode(node: KnowledgeNode, expandable = false): void {
  selectedNode.value = node
  mobileDetailOpen.value = true
  if (expandable && !expandedIds.value.has(node.knowledge_id)) toggleNode(node.knowledge_id)
}

function selectFirstMatch(): void {
  const matches = visibleRows.value.filter(row => matchingIds.value.has(row.node.knowledge_id))
  const match = matches.find(row => row.node.node_type === 'knowledge_point') || matches[0]
  if (match) selectNode(match.node, match.hasChildren)
}

async function loadLibrary(): Promise<void> {
  const courseId = courseStore.currentCourseId
  if (!courseId) return
  loading.value = true
  loadError.value = ''
  try {
    const response = await http.get(`/api/courses/${courseId}/learning-assets`)
    const assets = response.data?.assets || {}
    const view = assets.knowledge_library?.[0]
    if (!view || view.schema_version !== 'knowledge_library_view_v3') {
      throw new Error(t('knowledgeLibrary.unsupported', '当前课程尚未接入正式知识库'))
    }
    libraryView.value = view as KnowledgeLibraryView
    reviewSummary.value = null
    if (view.lifecycle_status === 'candidate') {
      try {
        const review = await http.get(`/api/courses/${courseId}/knowledge-library/review`)
        reviewSummary.value = review.data as KnowledgeLibraryReview
      } catch (error) {
        logger.error(error)
      }
    }
    questions.value = assets.questions || []
    criteria.value = assets.mastery_criteria || []
    misconceptions.value = assets.misconceptions || []
    expandedIds.value = new Set(
      view.nodes
        .filter((node: KnowledgeNode) => ['subject', 'domain', 'topic', 'concept'].includes(node.node_type) && node.covered_by_course)
        .map((node: KnowledgeNode) => node.knowledge_id),
    )
    selectedNode.value = view.nodes.find((node: KnowledgeNode) => node.knowledge_id === view.root_node_id) || view.nodes[0] || null
    mobileDetailOpen.value = false
  } catch (error: any) {
    logger.error(error)
    loadError.value = errorMessage(error, t('knowledgeLibrary.loadFailed', '知识库暂时无法读取'))
    libraryView.value = null
  } finally {
    loading.value = false
  }
}

function percent(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`
}

async function reviewLibrary(decision: 'accept' | 'reject'): Promise<void> {
  const courseId = courseStore.currentCourseId
  const revisionId = libraryView.value?.binding_revision_id || libraryView.value?.revision_id
  if (!courseId || !revisionId) return
  governanceActing.value = true
  governanceError.value = ''
  try {
    await http.post(`/api/courses/${courseId}/knowledge-library/review`, {
      revision_id: revisionId,
      decision,
      note: reviewNote.value.trim(),
    })
    await loadLibrary()
  } catch (error: any) {
    logger.error(error)
    governanceError.value = errorMessage(error, t('knowledgeLibrary.reviewFailed', '审核操作失败'))
  } finally {
    governanceActing.value = false
  }
}

async function rebuildLibrary(): Promise<void> {
  const courseId = courseStore.currentCourseId
  if (!courseId) return
  governanceActing.value = true
  governanceError.value = ''
  try {
    const response = await http.post(`/api/courses/${courseId}/knowledge-library/rebuild`, { force: true })
    await loadLibrary()
    if (response.data?.library?.lifecycle_status === 'degraded') {
      const messages = (response.data?.quality_report?.blocking_issues || [])
        .map((item: { message?: string }) => item.message)
        .filter(Boolean)
      governanceError.value = messages.length
        ? `${t('knowledgeLibrary.qualityBlocked', '重新生成完成，但未通过质量门禁')}：${messages.join('；')}`
        : t('knowledgeLibrary.qualityBlocked', '重新生成完成，但未通过质量门禁')
    }
  } catch (error: any) {
    logger.error(error)
    governanceError.value = errorMessage(error, t('knowledgeLibrary.rebuildFailed', '重新生成失败'))
  } finally {
    governanceActing.value = false
  }
}

function errorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}

async function navigateToCourse(): Promise<void> {
  const nodeId = jumpTarget.value
  if (!nodeId) return
  handleClose()
  await new Promise(resolve => setTimeout(resolve, 150))
  courseStore.scrollToNode(nodeId)
}

function handleClose(): void {
  courseStore.showKnowledgeLibrary = false
}

function handleKeydown(event: KeyboardEvent): void {
  if (!courseStore.showKnowledgeLibrary || event.key !== 'Escape') return
  if (mobileDetailOpen.value) mobileDetailOpen.value = false
  else handleClose()
}

function nodeIcon(type: KnowledgeNodeType) {
  return {
    subject: Library,
    domain: BookOpen,
    topic: Layers3,
    concept: Network,
    knowledge_point: CircleDot,
  }[type]
}

function nodeTypeLabel(type: KnowledgeNodeType): string {
  return {
    subject: t('knowledgeLibrary.typeSubject', '学科'),
    domain: t('knowledgeLibrary.typeDomain', '领域'),
    topic: t('knowledgeLibrary.typeTopic', '主题'),
    concept: t('knowledgeLibrary.typeConcept', '概念'),
    knowledge_point: t('knowledgeLibrary.typePoint', '细知识点'),
  }[type]
}

function descriptionFallback(_node: KnowledgeNode): string {
  return t('knowledgeLibrary.descriptionFallback', '该节点来自正式知识库，用于组织稳定知识语义。')
}

function sourceLabel(source: string): string {
  if (source === 'curated') return t('knowledgeLibrary.sourceCurated', '正式学科库')
  return t('knowledgeLibrary.sourceFormal', '版本化知识条目')
}

function relationLabel(relation: KnowledgeRelation, direction: 'incoming' | 'outgoing'): string {
  const labels: Record<string, string> = {
    prerequisite: direction === 'incoming'
      ? t('knowledgeLibrary.prerequisite', '前置知识')
      : t('knowledgeLibrary.followingDepends', '后续依赖'),
    derives: t('knowledgeLibrary.derives', '推导关系'),
    contrasts_with: t('knowledgeLibrary.contrasts', '对比辨析'),
    applies_to: t('knowledgeLibrary.applies', '应用关系'),
    related: t('knowledgeLibrary.related', '相关知识'),
  }
  return labels[relation.relation_type] || relation.relation_type
}

watch(() => courseStore.showKnowledgeLibrary, async show => {
  if (show) {
    await loadLibrary()
    document.addEventListener('keydown', handleKeydown)
    await nextTick()
    dialogRef.value?.focus()
  } else {
    document.removeEventListener('keydown', handleKeydown)
    searchQuery.value = ''
    mobileDetailOpen.value = false
  }
})

watch(() => courseStore.currentCourseId, () => {
  if (courseStore.showKnowledgeLibrary) void loadLibrary()
})
</script>

<style scoped>
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.knowledge-tree-overlay { position:fixed; inset:0; z-index:120; display:grid; place-items:center; padding:24px; background:rgba(38,43,72,.32); backdrop-filter:blur(5px); }
.knowledge-tree-dialog { width:min(1320px, calc(100vw - 48px)); height:min(850px, calc(100vh - 48px)); min-height:560px; display:flex; flex-direction:column; overflow:hidden; border:1px solid rgba(221,226,243,.95); border-radius:20px; background:#fff; box-shadow:0 28px 80px rgba(42,48,86,.22), 0 3px 14px rgba(42,48,86,.08); outline:none; }
.knowledge-tree-header { min-height:72px; flex:0 0 auto; display:grid; grid-template-columns:minmax(260px,1fr) minmax(260px,420px) 38px; align-items:center; gap:20px; padding:12px 16px 12px 20px; border-bottom:1px solid #e8eaf4; background:rgba(255,255,255,.98); }
.knowledge-tree-heading { min-width:0; display:flex; align-items:center; gap:12px; }
.knowledge-tree-brand { width:38px; height:38px; flex:0 0 38px; display:grid; place-items:center; border:1px solid #ddd6fe; border-radius:11px; color:#6d4aff; background:#f4f1ff; box-shadow:0 4px 12px rgba(109,74,255,.12); }
.knowledge-tree-heading h1 { margin:0; color:#252a43; font-size:16px; line-height:1.3; font-weight:760; letter-spacing:0; }
.knowledge-tree-heading p { margin:3px 0 0; overflow:hidden; color:#858ba3; font-size:11px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.knowledge-tree-heading p span { margin:0 5px; color:#c2c6d4; }
.knowledge-tree-search { min-width:0; height:38px; display:flex; align-items:center; gap:8px; padding:0 10px; border:1px solid #e2e5f0; border-radius:10px; color:#8b91a8; background:#f8f9fc; transition:border-color .16s ease, background .16s ease, box-shadow .16s ease; }
.knowledge-tree-search:focus-within { border-color:#aaa0ff; background:#fff; box-shadow:0 0 0 3px rgba(109,74,255,.09); }
.knowledge-tree-search input { min-width:0; flex:1; border:0; outline:0; color:#333850; background:transparent; font-size:12px; }
.knowledge-tree-search input::placeholder { color:#a6abbd; }
.knowledge-tree-search button, .knowledge-tree-close { display:grid; place-items:center; border:0; color:#868ca3; background:transparent; cursor:pointer; }
.knowledge-tree-search button { width:24px; height:24px; border-radius:6px; }
.knowledge-tree-search button:hover { color:#5f46e8; background:#efedff; }
.knowledge-tree-close { width:36px; height:36px; border:1px solid #e2e5ef; border-radius:10px; }
.knowledge-tree-close:hover { color:#d14343; border-color:#f0caca; background:#fff6f6; }
.knowledge-tree-governance { flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:14px; padding:9px 16px 9px 20px; border-bottom:1px solid #e7e9f2; background:#fafaff; }
.knowledge-tree-governance.is-candidate { background:#fffaf0; }
.knowledge-tree-governance.is-degraded, .knowledge-tree-governance.is-rejected { background:#fff5f4; }
.knowledge-tree-governance-summary, .knowledge-tree-quality, .knowledge-tree-diff, .knowledge-tree-governance-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.knowledge-tree-lifecycle { padding:4px 9px; border:1px solid #d8d2ff; border-radius:999px; color:#5f46d7; background:#f2efff; font-size:10px; font-weight:750; }
.is-candidate .knowledge-tree-lifecycle { color:#95670b; border-color:#efd695; background:#fff7dd; }
.is-degraded .knowledge-tree-lifecycle, .is-rejected .knowledge-tree-lifecycle { color:#a74444; border-color:#efc4c4; background:#fff; }
.knowledge-tree-quality, .knowledge-tree-diff { color:#747b91; font-size:10px; }
.knowledge-tree-quality strong { color:#3d435a; }
.knowledge-tree-quality-issues { max-width:360px; margin:0; padding-left:16px; color:#a64242; font-size:10px; line-height:1.45; }
.knowledge-tree-quality-issues li + li { margin-top:2px; }
.knowledge-tree-diff { padding-left:8px; border-left:1px solid #dcdeea; }
.knowledge-tree-governance-actions { justify-content:flex-end; }
.knowledge-tree-governance-actions input { width:190px; height:30px; padding:0 9px; border:1px solid #dddfea; border-radius:8px; outline:0; color:#42485d; background:#fff; font-size:10px; }
.knowledge-tree-governance-actions input:focus { border-color:#9486ec; box-shadow:0 0 0 2px rgba(109,74,255,.08); }
.knowledge-tree-governance-actions button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 10px; border:1px solid #dedfea; border-radius:8px; color:#535a70; background:#fff; font-size:10px; font-weight:700; cursor:pointer; }
.knowledge-tree-governance-actions button:hover:not(:disabled) { color:#593fda; border-color:#bfb7f6; background:#f7f5ff; }
.knowledge-tree-governance-actions button:disabled { opacity:.55; cursor:not-allowed; }
.knowledge-tree-governance-error { color:#b14242; font-size:10px; }
.knowledge-tree-main { min-height:0; flex:1; position:relative; display:grid; grid-template-columns:370px minmax(0,1fr); overflow:hidden; background:#fff; }
.knowledge-tree-pane { min-width:0; display:flex; flex-direction:column; overflow:hidden; border-right:1px solid #e7e9f2; background:#fafbfe; }
.knowledge-tree-pane-head { min-height:45px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 14px 0 18px; border-bottom:1px solid #eceef5; color:#70778f; }
.knowledge-tree-pane-head > div { display:flex; align-items:center; gap:7px; }
.knowledge-tree-pane-head strong { color:#3c425a; font-size:12px; font-weight:700; }
.knowledge-tree-scope { display:grid !important; grid-template-columns:1fr 1fr; gap:2px !important; padding:2px; border:1px solid #e2e4ed; border-radius:8px; background:#f4f5f9; }
.knowledge-tree-scope button { min-width:58px; height:24px; padding:0 7px; border:0; border-radius:6px; color:#7b8195; background:transparent; font-size:9.5px; font-weight:650; cursor:pointer; }
.knowledge-tree-scope button.active { color:#5540c8; background:#fff; box-shadow:0 1px 4px rgba(64,58,115,.12); }
.knowledge-tree-scroll { min-height:0; flex:1; overflow:auto; padding:9px 8px 16px; scrollbar-width:thin; scrollbar-color:#ccd0dd transparent; }
.knowledge-tree-list { min-width:0; }
.knowledge-tree-row { --tree-depth:0; position:relative; min-height:38px; display:grid; grid-template-columns:24px minmax(0,1fr); align-items:center; padding-left:calc(var(--tree-depth) * 18px); border-radius:8px; }
.knowledge-tree-row::before { content:""; position:absolute; top:-8px; bottom:-8px; left:calc(19px + var(--tree-depth) * 18px); width:1px; background:#e0e3ef; opacity:0; pointer-events:none; }
.knowledge-tree-row.is-domain::before, .knowledge-tree-row.is-topic::before, .knowledge-tree-row.is-concept::before { opacity:1; }
.knowledge-tree-row:hover { background:#f2f3fa; }
.knowledge-tree-row.is-selected { background:#eeecff; box-shadow:inset 3px 0 0 #7257ff; }
.knowledge-tree-toggle { z-index:1; width:24px; height:30px; display:grid; place-items:center; padding:0; border:0; border-radius:6px; color:#9aa0b3; background:transparent; cursor:pointer; }
.knowledge-tree-toggle:hover { color:#5f46e8; background:#e7e3ff; }
.knowledge-tree-leaf-line { z-index:1; width:7px; height:7px; justify-self:center; border:2px solid #c3c8d8; border-radius:50%; background:#fafbfe; }
.knowledge-tree-row.is-selected .knowledge-tree-leaf-line { border-color:#7257ff; background:#7257ff; }
.knowledge-tree-node { min-width:0; height:34px; display:grid; grid-template-columns:18px minmax(0,1fr) 16px; align-items:center; gap:7px; padding:0 8px 0 3px; border:0; color:#535a72; background:transparent; text-align:left; cursor:pointer; }
.knowledge-tree-node svg { color:#858ca5; }
.is-subject .knowledge-tree-node, .is-domain .knowledge-tree-node { color:#30364d; font-weight:700; }
.is-subject .knowledge-tree-node svg { color:#7257ff; }
.is-domain .knowledge-tree-node svg { color:#4f6fa8; }
.is-topic .knowledge-tree-node { color:#4b526b; font-weight:650; }
.is-concept .knowledge-tree-node { color:#555c73; font-weight:620; }
.is-knowledge_point .knowledge-tree-node { color:#60677e; font-size:11px; }
.knowledge-tree-row.is-selected .knowledge-tree-node, .knowledge-tree-row.is-selected .knowledge-tree-node svg { color:#553bd5; }
.knowledge-tree-node-name { min-width:0; overflow:hidden; font-size:11.5px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.knowledge-tree-covered-icon { color:#3d8a65 !important; }
.knowledge-tree-no-results { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; padding:32px; color:#969caf; font-size:12px; }
.knowledge-tree-detail { min-width:0; overflow:auto; padding:30px clamp(28px,4vw,64px) 24px; color:#383e55; background:#fff; scrollbar-width:thin; scrollbar-color:#d4d7e2 transparent; }
.knowledge-tree-back { display:none; }
.knowledge-tree-breadcrumb { display:flex; align-items:center; flex-wrap:wrap; gap:5px; margin-bottom:20px; color:#9298aa; font-size:10.5px; }
.knowledge-tree-breadcrumb span:last-of-type { color:#6650d7; }
.knowledge-tree-detail-head { display:flex; align-items:flex-start; gap:13px; }
.knowledge-tree-detail-icon { width:42px; height:42px; flex:0 0 42px; display:grid; place-items:center; border:1px solid #ded9ff; border-radius:11px; color:#6c50ec; background:#f5f3ff; }
.knowledge-tree-kicker { display:flex; align-items:center; gap:8px; min-height:18px; color:#6a7088; font-size:10px; font-weight:700; }
.knowledge-tree-kicker span { padding:2px 7px; border:1px solid #f0d899; border-radius:9px; color:#95670b; background:#fff9e9; font-size:9px; font-weight:650; }
.knowledge-tree-detail h2 { max-width:820px; margin:4px 0 0; color:#252b43; font-size:25px; line-height:1.35; font-weight:760; letter-spacing:0; overflow-wrap:anywhere; }
.knowledge-tree-description { max-width:880px; margin:20px 0 0; color:#646b82; font-size:13.5px; line-height:1.85; }
.knowledge-tree-bindings { max-width:880px; display:flex; align-items:center; flex-wrap:wrap; gap:6px 22px; margin:22px 0 0; padding:11px 0; border-top:1px solid #eceef5; border-bottom:1px solid #eceef5; }
.knowledge-tree-bindings span { display:inline-flex; align-items:center; gap:6px; color:#6e758d; font-size:11px; font-weight:650; }
.knowledge-tree-bindings span:nth-child(1) svg { color:#4f6fa8; }
.knowledge-tree-bindings span:nth-child(2) svg { color:#27825a; }
.knowledge-tree-bindings span:nth-child(3) svg { color:#c68417; }
.knowledge-tree-section { max-width:880px; margin-top:28px; }
.knowledge-tree-section h3 { display:flex; align-items:center; gap:8px; margin:0 0 12px; color:#333950; font-size:14px; line-height:1.4; font-weight:730; }
.knowledge-tree-section h3 svg { color:#7056e8; }
.knowledge-tree-action-list, .knowledge-tree-evidence-list { display:grid; gap:8px; margin:0; padding-left:20px; color:#5f667c; font-size:12px; line-height:1.75; }
.knowledge-tree-action-list li::marker { color:#6f57df; }
.knowledge-tree-evidence-list li::marker { color:#4e8b6b; }
.knowledge-tree-child-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.knowledge-tree-child-list button, .knowledge-tree-relations button { min-width:0; display:grid; align-items:center; border:1px solid #e5e7f0; border-radius:8px; color:#4d546c; background:#fbfbfd; cursor:pointer; transition:border-color .15s ease, background .15s ease, color .15s ease; }
.knowledge-tree-child-list button { grid-template-columns:18px minmax(0,1fr) 15px; gap:8px; min-height:42px; padding:7px 10px; text-align:left; }
.knowledge-tree-child-list button:hover, .knowledge-tree-relations button:hover { color:#5940d5; border-color:#cbc4fb; background:#f7f5ff; }
.knowledge-tree-child-list button span { overflow:hidden; font-size:11px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
.knowledge-tree-misconceptions { display:grid; gap:0; border-top:1px solid #eceef4; }
.knowledge-tree-misconceptions > div { padding:12px 0; border-bottom:1px solid #eceef4; }
.knowledge-tree-misconceptions strong { color:#5d4c36; font-size:11.5px; }
.knowledge-tree-misconceptions p { margin:5px 0 0; color:#747b90; font-size:11px; line-height:1.65; }
.knowledge-tree-skill-groups { border-top:1px solid #e8eaf2; }
.knowledge-tree-skill-group { padding:14px 0; border-bottom:1px solid #e8eaf2; }
.knowledge-tree-skill-head { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:baseline; gap:4px 9px; }
.knowledge-tree-skill-head > span { padding:2px 6px; border-radius:5px; color:#5d49c8; background:#f0edff; font-size:9px; font-weight:720; }
.knowledge-tree-skill-head > strong { color:#363c54; font-size:12.5px; line-height:1.5; }
.knowledge-tree-skill-head > p { grid-column:2; margin:1px 0 0; color:#747b90; font-size:11px; line-height:1.65; }
.knowledge-tree-skill-children { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin:12px 0 0 26px; }
.knowledge-tree-skill-branch { min-width:0; padding-left:11px; border-left:2px solid #e1e4ef; }
.knowledge-tree-skill-branch.is-mistake { border-left-color:#e6bd7c; }
.knowledge-tree-skill-branch.is-improvement { border-left-color:#77c49b; }
.knowledge-tree-skill-branch h4 { display:flex; align-items:center; gap:5px; margin:0 0 7px; color:#5f657c; font-size:10px; font-weight:720; }
.knowledge-tree-skill-branch > div + div { margin-top:9px; padding-top:9px; border-top:1px dashed #e7e9f0; }
.knowledge-tree-skill-branch strong { color:#474d64; font-size:11px; line-height:1.45; }
.knowledge-tree-skill-branch p { margin:3px 0 0; color:#7b8195; font-size:10.5px; line-height:1.6; }
.knowledge-tree-relations { display:grid; gap:7px; }
.knowledge-tree-relations button { grid-template-columns:80px minmax(0,1fr) 15px; gap:10px; min-height:42px; padding:7px 10px; text-align:left; }
.knowledge-tree-relations button span { color:#8b729e; font-size:10px; }
.knowledge-tree-relations button strong { overflow:hidden; font-size:11.5px; text-overflow:ellipsis; white-space:nowrap; }
.knowledge-tree-detail-footer { max-width:880px; display:flex; align-items:center; justify-content:space-between; gap:20px; margin-top:32px; padding-top:18px; border-top:1px solid #e8eaf2; }
.knowledge-tree-detail-footer > div { min-width:0; display:flex; flex-wrap:wrap; gap:6px 12px; color:#9aa0b1; font-size:9.5px; }
.knowledge-tree-detail-footer button, .knowledge-tree-state button { min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border:1px solid #6a50e8; border-radius:9px; color:#fff; background:#6a50e8; font-size:11px; font-weight:700; cursor:pointer; }
.knowledge-tree-detail-footer button:hover, .knowledge-tree-state button:hover { border-color:#563ccd; background:#563ccd; }
.knowledge-tree-detail-empty, .knowledge-tree-state { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:9px; padding:32px; color:#9298ab; text-align:center; }
.knowledge-tree-detail-empty strong, .knowledge-tree-state strong { color:#50576f; font-size:13px; }
.knowledge-tree-state span { max-width:460px; font-size:11px; line-height:1.6; }
.knowledge-tree-state button { margin-top:4px; }
.knowledge-tree-state--error svg { color:#ce5555; }
.knowledge-tree-spinner { color:#6d52e8; animation:knowledge-tree-spin .8s linear infinite; }
.knowledge-tree-modal-enter-active, .knowledge-tree-modal-leave-active { transition:opacity .18s ease; }
.knowledge-tree-modal-enter-active .knowledge-tree-dialog, .knowledge-tree-modal-leave-active .knowledge-tree-dialog { transition:transform .18s ease, opacity .18s ease; }
.knowledge-tree-modal-enter-from, .knowledge-tree-modal-leave-to { opacity:0; }
.knowledge-tree-modal-enter-from .knowledge-tree-dialog, .knowledge-tree-modal-leave-to .knowledge-tree-dialog { opacity:0; transform:translateY(8px) scale(.995); }
@keyframes knowledge-tree-spin { to { transform:rotate(360deg); } }

@media (max-width:900px) {
  .knowledge-tree-dialog { width:calc(100vw - 28px); height:calc(100vh - 28px); }
  .knowledge-tree-header { grid-template-columns:minmax(210px,1fr) minmax(220px,340px) 38px; gap:12px; }
  .knowledge-tree-main { grid-template-columns:320px minmax(0,1fr); }
  .knowledge-tree-detail { padding-inline:28px; }
  .knowledge-tree-child-list { grid-template-columns:1fr; }
  .knowledge-tree-skill-children { grid-template-columns:1fr; }
}

@media (max-width:700px) {
  .knowledge-tree-overlay { padding:0; background:#fff; }
  .knowledge-tree-dialog { width:100vw; height:100dvh; min-height:0; border:0; border-radius:0; box-shadow:none; }
  .knowledge-tree-header { min-height:112px; grid-template-columns:minmax(0,1fr) 38px; grid-template-rows:48px 44px; gap:4px 10px; padding:8px 12px 10px; }
  .knowledge-tree-governance { align-items:flex-start; flex-direction:column; padding:9px 12px; }
  .knowledge-tree-governance-actions { width:100%; justify-content:flex-start; }
  .knowledge-tree-governance-actions input { width:100%; }
  .knowledge-tree-heading { grid-column:1; grid-row:1; }
  .knowledge-tree-brand { width:34px; height:34px; flex-basis:34px; border-radius:10px; }
  .knowledge-tree-heading h1 { font-size:14px; }
  .knowledge-tree-heading p { font-size:9.5px; }
  .knowledge-tree-close { grid-column:2; grid-row:1; }
  .knowledge-tree-search { grid-column:1 / -1; grid-row:2; height:40px; }
  .knowledge-tree-main { display:block; }
  .knowledge-tree-pane, .knowledge-tree-detail { position:absolute; inset:0; border:0; }
  .knowledge-tree-pane { background:#fafbfe; }
  .knowledge-tree-detail { display:none; padding:18px 18px calc(28px + env(safe-area-inset-bottom)); background:#fff; }
  .knowledge-tree-main.is-detail-open .knowledge-tree-pane { display:none; }
  .knowledge-tree-main.is-detail-open .knowledge-tree-detail { display:block; }
  .knowledge-tree-back { min-height:34px; display:inline-flex; align-items:center; gap:6px; margin:0 0 16px; padding:0 8px; border:0; border-radius:8px; color:#6650d6; background:#f2efff; font-size:11px; font-weight:700; }
  .knowledge-tree-breadcrumb { margin-bottom:15px; }
  .knowledge-tree-detail h2 { font-size:21px; }
  .knowledge-tree-description { font-size:13px; }
  .knowledge-tree-bindings { gap:8px 15px; }
  .knowledge-tree-detail-footer { align-items:flex-start; flex-direction:column; }
  .knowledge-tree-detail-footer button { width:100%; }
}
</style>
