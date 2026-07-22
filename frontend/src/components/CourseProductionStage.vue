<template>
  <section
    class="course-production-stage"
    :data-state="stageStatus"
    :aria-label="productionAriaLabel"
    aria-live="polite"
  >
    <article class="formation-sheet">
      <header class="formation-sheet__header">
        <span class="formation-sheet__state" :data-state="stageStatus">
          <TriangleAlert v-if="stageStatus === 'error' || stageStatus === 'blocked'" :size="14" />
          <CirclePause v-else-if="stageStatus === 'paused'" :size="14" />
          <LoaderCircle v-else :size="14" />
          {{ stageLabel }}
        </span>
        <h1>{{ courseName || t('courseGeneration.production.untitled', '新课程') }}</h1>
        <p>{{ stageDescription }}</p>
      </header>

      <section class="formation-outline" :aria-label="t('courseGeneration.production.navigatorLabel', '课程结构')">
        <header>
          <div>
            <span>{{ t('courseGeneration.production.navigatorLabel', '课程结构') }}</span>
            <strong>{{ outlineTitle }}</strong>
          </div>
          <small>{{ outlineMeta }}</small>
        </header>

        <div v-if="stageKey === 'outline'" class="outline-growth-summary" aria-live="polite">
          <div :data-complete="growthSkeletonReady">
            <span><Sprout :size="14" /></span>
            <p>
              <small>{{ t('courseGeneration.production.growthTrunk', '课程主干') }}</small>
              <strong>{{ growthSkeletonReady
                ? t('courseGeneration.production.growthFormed', '已形成')
                : t('courseGeneration.production.growthExtracting', '正在抽取') }}</strong>
            </p>
          </div>
          <div :data-complete="growthCompletedSections > 0">
            <span><GitBranch :size="14" /></span>
            <p>
              <small>{{ t('courseGeneration.production.growthBranches', '小节枝系') }}</small>
              <strong>{{ growthCompletedSections }} / {{ growthTotalSections || '—' }}</strong>
            </p>
          </div>
          <div :data-complete="growthCompletedBatches > 0">
            <span><Database :size="14" /></span>
            <p>
              <small>{{ t('courseGeneration.production.growthCheckpoints', '已存检查点') }}</small>
              <strong>{{ growthCompletedBatches }} / {{ growthTotalBatches || '—' }}</strong>
            </p>
          </div>
        </div>

        <div v-if="growthChapters.length" class="outline-growth-tree">
          <article
            v-for="(chapter, chapterIndex) in growthChapters"
            :key="chapter.id"
            class="growth-chapter"
            :data-state="chapter.status"
            :style="{ '--growth-order': chapterIndex }"
          >
            <button
              type="button"
              class="growth-chapter__head"
              :aria-expanded="isChapterExpanded(chapter.id)"
              :aria-controls="`growth-branch-${chapter.id}`"
              @click="toggleChapter(chapter.id)"
            >
              <span class="growth-chapter__node" aria-hidden="true">
                <Check v-if="chapter.status === 'completed'" :size="13" />
                <Sprout v-else-if="chapter.status === 'growing'" :size="14" />
                <span v-else>{{ String(chapter.chapterNumber).padStart(2, '0') }}</span>
              </span>
              <span class="growth-chapter__copy">
                <small>{{ t('courseGeneration.production.growthChapter', '第 {number} 章').replace('{number}', String(chapter.chapterNumber)) }}</small>
                <strong>{{ chapter.title }}</strong>
                <span v-if="chapter.focus">{{ chapter.focus }}</span>
              </span>
              <span class="growth-chapter__progress">
                <i><b :style="{ width: `${chapter.progress}%` }"></b></i>
                <small>{{ chapter.completedCount }}/{{ chapter.sectionCount }}</small>
              </span>
              <ChevronDown :size="16" :class="{ 'is-open': isChapterExpanded(chapter.id) }" />
            </button>

            <ol
              v-show="isChapterExpanded(chapter.id)"
              :id="`growth-branch-${chapter.id}`"
              class="growth-chapter__sections"
            >
              <li
                v-for="(section, sectionIndex) in chapter.sections"
                :key="section.id"
                :data-state="section.status"
                :style="{ '--section-order': sectionIndex }"
              >
                <span class="growth-section__joint" aria-hidden="true"></span>
                <span class="growth-section__number">{{ section.number }}</span>
                <div>
                  <strong>{{ section.title }}</strong>
                  <p v-if="section.objective">{{ section.objective }}</p>
                </div>
                <span class="growth-section__state">
                  <LoaderCircle v-if="section.status === 'generating'" :size="12" />
                  <TriangleAlert v-else-if="section.status === 'failed'" :size="12" />
                  <Check v-else :size="12" />
                  {{ growthSectionStateLabel(section.status) }}
                </span>
              </li>
              <li
                v-for="bud in chapter.visibleBuds"
                :key="`${chapter.id}-bud-${bud}`"
                class="growth-section growth-section--bud"
                :data-state="chapter.status === 'growing' && bud === 1 ? 'growing' : 'waiting'"
              >
                <span class="growth-section__joint" aria-hidden="true"></span>
                <span class="growth-section__number">{{ chapter.completedCount + bud }}</span>
                <div>
                  <strong>{{ chapter.status === 'growing' && bud === 1
                    ? t('courseGeneration.production.growthSectionForming', '这一节正在形成')
                    : t('courseGeneration.production.growthSectionWaiting', '等待沿主干展开') }}</strong>
                  <p><span></span><span></span></p>
                </div>
                <span class="growth-section__state">
                  <LoaderCircle v-if="chapter.status === 'growing' && bud === 1" :size="12" />
                  <CircleDashed v-else :size="12" />
                  {{ chapter.status === 'growing' && bud === 1
                    ? t('courseGeneration.workspace.generating', '正在生成')
                    : t('courseGeneration.workspace.waiting', '等待生成') }}
                </span>
              </li>
              <li v-if="chapter.hiddenBudCount" class="growth-chapter__more">
                {{ t('courseGeneration.production.growthMoreSections', '还有 {count} 个小节将在本章继续生长')
                  .replace('{count}', String(chapter.hiddenBudCount)) }}
              </li>
            </ol>
          </article>
        </div>

        <div v-else class="outline-germination" aria-live="polite">
          <div class="outline-germination__signal" aria-hidden="true">
            <i></i><i></i><i></i>
            <span><Sprout :size="20" /></span>
          </div>
          <div>
            <strong>{{ t('courseGeneration.production.growthStarting', '正在找到这门课的生长主线') }}</strong>
            <p>{{ t('courseGeneration.production.growthStartingHelp', '先确定整体章节和每章职责，随后小节会在它们的最终位置逐个出现。') }}</p>
          </div>
          <div class="outline-germination__branches" aria-hidden="true">
            <span v-for="row in skeletonRows" :key="row" :style="{ '--seed-order': row }"><i></i><b></b></span>
          </div>
        </div>
      </section>

      <aside v-if="isTerminal" class="formation-recovery" :data-state="stageStatus">
        <span class="formation-recovery__icon">
          <CirclePause v-if="stageStatus === 'paused'" :size="17" />
          <GitCompareArrows v-else-if="stageStatus === 'blocked'" :size="17" />
          <TriangleAlert v-else :size="17" />
        </span>
        <div>
          <strong>{{ terminalTitle }}</strong>
          <p>{{ friendlyError }} {{ recoveryDetail }}</p>
          <div v-if="savedItems.length" class="formation-recovery__saved">
            <span v-for="item in savedItems" :key="item"><Check :size="11" />{{ item }}</span>
          </div>
          <details v-if="technicalError">
            <summary>{{ t('courseGeneration.production.technicalReason', '查看技术原因') }}</summary>
            <code>{{ technicalError }}</code>
          </details>
        </div>
        <button v-if="canResume" type="button" :disabled="acting" @click="emit('resume')">
          <LoaderCircle v-if="acting" :size="15" />
          <RotateCw v-else :size="15" />
          {{ resumeLabel }}
        </button>
      </aside>

      <footer v-else class="formation-sheet__footer">
        <div>
          <span>{{ t('courseGeneration.production.nextLabel', '接下来') }}</span>
          <p>{{ footerHint }}</p>
        </div>
        <span v-if="savedSummary"><Check :size="12" />{{ savedSummary }}</span>
      </footer>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Check, ChevronDown, CircleDashed, CirclePause, Database, GitBranch,
  GitCompareArrows, LoaderCircle, RotateCw, Sprout, TriangleAlert,
} from 'lucide-vue-next'
import type { Node, Task } from '../stores/types'
import { t } from '../shared/i18n'
import {
  canResumeCourseProduction,
  courseProductionRecoveryDetail,
  courseProductionStageIndex,
  courseProductionStageKey,
  courseProductionStageStatus,
  type CourseProductionStageKey,
} from '../utils/course-production'

const props = withDefaults(defineProps<{
  task?: Task
  courseName?: string
  nodes?: Node[]
  acting?: boolean
}>(), {
  task: undefined,
  courseName: '',
  nodes: () => [],
  acting: false,
})

const emit = defineEmits<{
  (event: 'resume'): void
}>()

const skeletonRows = [1, 2, 3, 4, 5, 6]
type GrowthSectionStatus = 'saved' | 'generating' | 'finalized' | 'draft' | 'failed' | 'waiting'
type GrowthChapter = {
  id: string
  chapterNumber: number
  title: string
  focus: string
  sectionCount: number
  completedCount: number
  progress: number
  status: 'completed' | 'growing' | 'waiting' | 'failed'
  sections: Array<{
    id: string
    number: string
    title: string
    objective: string
    status: GrowthSectionStatus
  }>
  visibleBuds: number
  hiddenBudCount: number
}

const expandedChapterIds = ref<Set<string>>(new Set())
const stageIndex = computed(() => courseProductionStageIndex(props.task))
const stageKey = computed(() => courseProductionStageKey(props.task))
const stageStatus = computed(() => courseProductionStageStatus(props.task, stageIndex.value))
const isTerminal = computed(() => ['error', 'paused', 'blocked'].includes(stageStatus.value))
const canResume = computed(() => canResumeCourseProduction(props.task))
const progressValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0)))))
const productionAriaLabel = computed(() => {
  const label = t('courseGeneration.production.ariaLabel', '课程生产现场')
  return props.courseName ? `${label}：${props.courseName}` : label
})
const outlineNodes = computed(() => props.nodes
  .filter(node => node.node_level <= 2)
  .slice()
  .sort((left, right) => {
    const source = props.nodes
    return source.findIndex(node => node.node_id === left.node_id) - source.findIndex(node => node.node_id === right.node_id)
  }))

const outlineGrowth = computed<Record<string, any> | null>(() => {
  const value = props.task?.phaseDetail?.outline_growth
  return value && typeof value === 'object' ? value as Record<string, any> : null
})

const growthChapters = computed<GrowthChapter[]>(() => {
  const projected = Array.isArray(outlineGrowth.value?.chapters)
    ? outlineGrowth.value!.chapters as Record<string, any>[]
    : []
  if (projected.length) {
    const activeChapter = Number(outlineGrowth.value?.active_chapter_number || 0)
    return projected.map((chapter, index) => {
      const chapterNumber = Number(chapter.chapter_number || index + 1)
      const sections = (Array.isArray(chapter.sections) ? chapter.sections : []).map((section: Record<string, any>, sectionIndex: number) => ({
        id: String(section.node_id || `growth-${chapterNumber}-${sectionIndex + 1}`),
        number: String(section.section_number || `${chapterNumber}.${sectionIndex + 1}`),
        title: String(section.title || t('courseGeneration.production.growthSectionSaved', '已形成小节')),
        objective: String(section.learning_objective || ''),
        status: 'saved' as GrowthSectionStatus,
      }))
      const sectionCount = Math.max(sections.length, Number(chapter.section_count || 0))
      const completedCount = Math.min(sectionCount, Math.max(sections.length, Number(chapter.completed_section_count || 0)))
      const rawStatus = String(chapter.status || '')
      const status: GrowthChapter['status'] = rawStatus === 'completed' || (sectionCount > 0 && completedCount >= sectionCount)
        ? 'completed'
        : rawStatus === 'growing' || activeChapter === chapterNumber
          ? 'growing'
          : rawStatus === 'failed'
            ? 'failed'
            : 'waiting'
      const remaining = Math.max(0, sectionCount - sections.length)
      return {
        id: `chapter-${chapterNumber}`,
        chapterNumber,
        title: String(chapter.title || t('courseGeneration.production.growthChapter', '第 {number} 章').replace('{number}', String(chapterNumber))),
        focus: String(chapter.learning_focus || ''),
        sectionCount,
        completedCount,
        progress: sectionCount ? Math.round(100 * completedCount / sectionCount) : 0,
        status,
        sections,
        visibleBuds: Math.min(3, remaining),
        hiddenBudCount: Math.max(0, remaining - 3),
      }
    })
  }

  const chapterNodes = outlineNodes.value.filter(node => node.node_level === 1)
  if (!chapterNodes.length) return []
  return chapterNodes.map((chapter, index) => {
    const sections = outlineNodes.value.filter(node => node.parent_node_id === chapter.node_id)
    const projectedSections = sections.map((section, sectionIndex) => {
      const state = nodeState(section) as GrowthSectionStatus
      const numberMatch = section.node_name.match(/^([\d.]+)\s*/)
      return {
        id: section.node_id,
        number: numberMatch?.[1] || `${index + 1}.${sectionIndex + 1}`,
        title: section.node_name.replace(/^[\d.]+\s*/, ''),
        objective: section.learning_objective || '',
        status: state,
      }
    })
    const completedCount = projectedSections.filter(section => ['saved', 'draft', 'finalized'].includes(section.status)).length
    const hasFailed = projectedSections.some(section => section.status === 'failed')
    const hasGrowing = projectedSections.some(section => section.status === 'generating')
    return {
      id: chapter.node_id,
      chapterNumber: index + 1,
      title: chapter.node_name.replace(/^第\s*\d+\s*章\s*/, ''),
      focus: chapter.learning_objective || '',
      sectionCount: sections.length,
      completedCount,
      progress: sections.length ? Math.round(100 * completedCount / sections.length) : 0,
      status: hasFailed ? 'failed' : hasGrowing ? 'growing' : completedCount === sections.length && sections.length ? 'completed' : 'waiting',
      sections: projectedSections,
      visibleBuds: 0,
      hiddenBudCount: 0,
    }
  })
})

const growthSkeletonReady = computed(() => growthChapters.value.length > 0)
const growthCompletedSections = computed(() => {
  if (outlineGrowth.value) return Number(outlineGrowth.value.completed_sections || 0)
  return stageKey.value === 'outline'
    ? outlineNodes.value.filter(node => node.node_level === 2).length
    : growthChapters.value.reduce((sum, chapter) => sum + chapter.completedCount, 0)
})
const growthTotalSections = computed(() => {
  if (outlineGrowth.value) return Number(outlineGrowth.value.total_sections || 0)
  return growthChapters.value.reduce((sum, chapter) => sum + chapter.sectionCount, 0)
})
const growthCompletedBatches = computed(() => Number(
  outlineGrowth.value?.completed_batches ?? props.task?.phaseDetail?.completed_batches ?? 0,
))
const growthTotalBatches = computed(() => Number(
  outlineGrowth.value?.total_batches ?? props.task?.phaseDetail?.total_batches ?? 0,
))

watch(growthChapters, chapters => {
  if (!chapters.length) return
  const next = new Set(expandedChapterIds.value)
  const active = chapters.find(chapter => chapter.status === 'growing')
  if (active) next.add(active.id)
  if (!next.size) next.add(chapters[0]!.id)
  expandedChapterIds.value = next
}, { immediate: true })

function isChapterExpanded(chapterId: string) {
  return expandedChapterIds.value.has(chapterId)
}

function toggleChapter(chapterId: string) {
  const next = new Set(expandedChapterIds.value)
  if (next.has(chapterId)) next.delete(chapterId)
  else next.add(chapterId)
  expandedChapterIds.value = next
}

function growthSectionStateLabel(state: GrowthSectionStatus) {
  if (state === 'saved') return t('courseGeneration.production.growthSavedToOutline', '已写入目录')
  if (state === 'generating') return t('courseGeneration.workspace.generating', '正在生成')
  if (state === 'finalized') return t('courseGeneration.workspace.finalized', '已定稿')
  if (state === 'failed') return t('courseGeneration.workspace.failed', '生成失败')
  if (state === 'draft') return t('courseGeneration.workspace.draft', 'AI 草稿')
  return t('courseGeneration.workspace.waiting', '等待生成')
}

const stageLabels = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.lifecycle.requirements', '需求'),
  outline: t('courseGeneration.lifecycle.outline', '目录'),
  teaching: t('courseGeneration.lifecycle.teaching', '教案与知识库'),
  content: t('courseGeneration.lifecycle.content', '正文生成'),
  release: t('courseGeneration.lifecycle.release', '确认发布'),
}))
const statusLabels = computed(() => ({
  active: t('courseGeneration.lifecycle.inProgress', '进行中'),
  review: t('courseGeneration.lifecycle.needsConfirmation', '待确认'),
  error: t('courseGeneration.lifecycle.interrupted', '已中断'),
  paused: t('courseGeneration.lifecycle.paused', '已暂停'),
  blocked: t('courseGeneration.lifecycle.blocked', '需处理'),
  completed: t('courseGeneration.lifecycle.completed', '已完成'),
  pending: t('courseGeneration.lifecycle.pending', '未开始'),
}))
const stageLabel = computed(() => `${stageLabels.value[stageKey.value]} · ${statusLabels.value[stageStatus.value]}`)
const descriptions = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsDescription', '主题、难度、编排偏好与资料边界会被写入同一份生产契约。'),
  outline: t('courseGeneration.production.outlineDescription', '系统正在把学习需求转成可确认的章节顺序、学习目标与课程范围。'),
  teaching: t('courseGeneration.production.teachingDescription', '系统先冻结全课知识职责，再按预算生成详细教案，并从同一计划编译课程知识库。'),
  content: t('courseGeneration.production.contentDescription', '各小节按真实前置关系并行生成，已完成的草稿会立即保存并出现在课程目录中。'),
  release: t('courseGeneration.production.releaseDescription', '系统正在核对结构、稳定引用与同源版本链；通过后由你确认发布。'),
}))
const stageDescription = computed(() => descriptions.value[stageKey.value])
const outlineTitle = computed(() => {
  if (growthChapters.value.length) {
    if (stageKey.value === 'outline' && growthCompletedSections.value < growthTotalSections.value) {
      return t('courseGeneration.production.outlineGrowing', '目录正在沿章节主干生长')
    }
    return t('courseGeneration.production.outlineVisible', '目录已经进入课程工作区')
  }
  return t('courseGeneration.production.outlineForming', '目录会在最终位置逐步出现')
})
const outlineMeta = computed(() => {
  if (growthTotalSections.value) {
    return t('courseGeneration.production.growthNodeProgress', '{completed}/{total} 个小节')
      .replace('{completed}', String(growthCompletedSections.value))
      .replace('{total}', String(growthTotalSections.value))
  }
  if (outlineNodes.value.length) {
    return t('courseGeneration.production.nodeCount', '{count} 个节点')
      .replace('{count}', String(outlineNodes.value.length))
  }
  return t('courseGeneration.production.progressValue', '{progress}%')
    .replace('{progress}', String(progressValue.value))
})

function nodeState(node: Node) {
  const status = String(node.generation_status || '')
  if (status === 'generating' || node.content_state === 'generating') return 'generating'
  if (status === 'error' || node.content_state === 'failed' || node.content_state === 'error') return 'failed'
  if (status === 'completed' || node.content_state === 'finalized') return 'finalized'
  if (node.content_state === 'draft' || Boolean(node.node_content)) return 'draft'
  return 'waiting'
}

const savedItems = computed(() => {
  const checkpoint = props.task?.recovery?.checkpoint
  if (!checkpoint) return []
  const items: string[] = []
  if (checkpoint.requirements_ready) items.push(t('courseGeneration.production.savedRequirements', '课程需求'))
  if (checkpoint.outline_ready) items.push(t('courseGeneration.production.savedOutline', '课程目录'))
  if (checkpoint.teaching_plan_ready) items.push(t('courseGeneration.production.savedPlan', '全课教案'))
  if (Number(checkpoint.completed_nodes || 0) > 0) {
    items.push(t('courseGeneration.production.savedLessons', '{count} 节正文')
      .replace('{count}', String(checkpoint.completed_nodes)))
  }
  return items
})
const savedSummary = computed(() => savedItems.value.length
  ? t('courseGeneration.production.savedInline', '已保存：{items}').replace('{items}', savedItems.value.join(' · '))
  : '')
const nextDetails = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsNext', '需求确认后立即生成课程目录；不会再增加额外确认门。'),
  outline: t('courseGeneration.production.outlineNext', '目录确认后，系统自动生成全课教案、知识库与各节正文。'),
  teaching: t('courseGeneration.production.teachingNext', '全课教案汇编通过后，正文会按依赖波次并行生成。'),
  content: t('courseGeneration.production.contentNext', '所有小节完成后进入确定性发布检查，不追加 AI 返工循环。'),
  release: t('courseGeneration.production.releaseNext', '确认发布后，当前页面会原地切换为正式学习现场。'),
}))
const footerHint = computed(() => nextDetails.value[stageKey.value])
const recoveryDetail = computed(() => courseProductionRecoveryDetail(props.task))
const technicalError = computed(() => String(props.task?.error || '').trim())
const terminalTitle = computed(() => {
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedTitle', '课程生产已暂停')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedTitle', '课程生产需要处理冲突')
  return t('courseGeneration.production.interruptedTitle', '课程生产暂时中断')
})
const friendlyError = computed(() => {
  const error = technicalError.value.toLowerCase()
  if (/authentication|credential|api[_ -]?key/.test(error)) {
    return t('courseGeneration.production.authError', 'AI 服务暂时无法完成身份校验。')
  }
  if (/timeout|timed out/.test(error)) {
    return t('courseGeneration.production.timeoutError', 'AI 服务响应超时，本阶段尚未完成。')
  }
  if (/unavailable|connection|network/.test(error)) {
    return t('courseGeneration.production.unavailableError', 'AI 服务暂时不可用，本阶段尚未完成。')
  }
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedDescription', '当前模型调用已经停止。')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedDescription', '当前产物与课程真源存在冲突。')
  return t('courseGeneration.production.genericError', '本阶段尚未完成。')
})
const resumeLabel = computed(() => props.task?.status === 'paused'
  ? t('courseGeneration.production.continueAction', '继续课程生产')
  : t('courseGeneration.production.retryAction', '重试当前阶段'))
</script>

<style scoped>
.course-production-stage {
  min-height:0;
  flex:1;
  overflow:auto;
  padding:18px clamp(18px,3vw,40px) 28px;
  background:#f6f7f9;
}
.formation-sheet {
  width:min(1200px,100%);
  margin:0 auto;
  overflow:hidden;
  border:1px solid #dde1e8;
  border-radius:12px;
  background:#fff;
  box-shadow:0 10px 28px rgba(30,41,59,.06);
}
.formation-sheet__header {
  padding:22px 28px 18px;
  border-bottom:1px solid #e7e9ee;
}
.formation-sheet__state {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#4f55b5;
  font-size:12px;
  font-weight:850;
  line-height:1.35;
  letter-spacing:.05em;
}
.formation-sheet__state[data-state="error"],
.formation-sheet__state[data-state="blocked"] { color:#a85b1a; }
.formation-sheet__state[data-state="paused"] { color:#667085; }
.formation-sheet__state svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-sheet__header h1 {
  margin:6px 0 5px;
  color:#17202e;
  font:720 clamp(24px,2vw,30px)/1.22 var(--font-sans);
  letter-spacing:-.015em;
}
.formation-sheet__header p {
  max-width:820px;
  margin:0;
  color:#687386;
  font-size:14px;
  line-height:1.6;
}
.formation-outline { padding:0 28px; }
.formation-outline > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:14px 0 12px;
  border-bottom:1px solid #e9ebef;
}
.formation-outline > header div { display:flex; align-items:baseline; gap:12px; }
.formation-outline > header span {
  color:#8a93a3;
  font-size:11px;
  font-weight:800;
  letter-spacing:.06em;
}
.formation-outline > header strong { color:#354052; font-size:14px; line-height:1.4; }
.formation-outline > header small {
  color:#697386;
  font:700 12px/1 ui-monospace,SFMono-Regular,monospace;
}
.outline-growth-summary {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:1px;
  margin:16px 0 12px;
  overflow:hidden;
  border:1px solid #e2e7e3;
  border-radius:12px;
  background:#e2e7e3;
}
.outline-growth-summary > div {
  min-width:0;
  display:grid;
  grid-template-columns:34px minmax(0,1fr);
  align-items:center;
  gap:9px;
  padding:10px 12px;
  background:rgba(250,252,250,.96);
}
.outline-growth-summary > div > span {
  width:34px;
  height:34px;
  display:grid;
  place-items:center;
  border:1px solid #dfe6e1;
  border-radius:50% 50% 46% 54%;
  color:#7b847e;
  background:#fff;
  transition:color .3s ease,border-color .3s ease,background .3s ease;
}
.outline-growth-summary > div[data-complete="true"] > span {
  border-color:#b7d9c8;
  color:#137258;
  background:#eef8f3;
}
.outline-growth-summary p { min-width:0; margin:0; }
.outline-growth-summary small,
.outline-growth-summary strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.outline-growth-summary small { color:#8a938d; font-size:10px; font-weight:750; letter-spacing:.04em; }
.outline-growth-summary strong { margin-top:2px; color:#34453d; font-size:12px; line-height:1.35; }
.outline-growth-tree {
  position:relative;
  display:grid;
  gap:9px;
  margin:0 0 18px;
  padding:10px 12px 12px 25px;
  overflow:hidden;
  border:1px solid #e1e6e2;
  border-radius:14px;
  background:
    radial-gradient(circle at 92% 0,rgba(101,112,206,.08),transparent 30%),
    linear-gradient(180deg,#fbfcfa 0%,#f7faf8 100%);
}
.outline-growth-tree::before {
  content:"";
  position:absolute;
  top:25px;
  bottom:25px;
  left:22px;
  width:2px;
  border-radius:999px;
  background:linear-gradient(180deg,#a6c9b8,#bed1c6 70%,rgba(190,209,198,0));
  transform-origin:top;
  animation:growth-stem 1s cubic-bezier(.2,.78,.26,1) both;
}
.growth-chapter {
  --chapter-color:#81968c;
  position:relative;
  animation:growth-arrive .5s cubic-bezier(.2,.8,.25,1) both;
  animation-delay:calc(var(--growth-order) * 60ms);
}
.growth-chapter::before {
  content:"";
  position:absolute;
  z-index:0;
  top:24px;
  left:-3px;
  width:17px;
  height:1px;
  background:#b7c9c0;
  transform-origin:left;
  animation:growth-branch .45s ease-out both;
  animation-delay:calc(120ms + var(--growth-order) * 60ms);
}
.growth-chapter[data-state="growing"] { --chapter-color:#5e62c4; }
.growth-chapter[data-state="completed"] { --chapter-color:#168063; }
.growth-chapter[data-state="failed"] { --chapter-color:#b65f20; }
.growth-chapter__head {
  position:relative;
  z-index:1;
  width:100%;
  min-height:54px;
  display:grid;
  grid-template-columns:38px minmax(0,1fr) minmax(96px,150px) 20px;
  align-items:center;
  gap:10px;
  padding:7px 10px 7px 7px;
  border:1px solid #e1e6e3;
  border-radius:11px;
  color:inherit;
  background:rgba(255,255,255,.92);
  box-shadow:0 3px 10px rgba(40,58,48,.035);
  text-align:left;
  cursor:pointer;
  transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease;
}
.growth-chapter__head:hover {
  border-color:#cbd8d0;
  box-shadow:0 8px 20px rgba(40,58,48,.07);
  transform:translateY(-1px);
}
.growth-chapter__head:focus-visible { outline:3px solid rgba(94,98,196,.18); outline-offset:2px; }
.growth-chapter[data-state="growing"] .growth-chapter__head {
  border-color:#cbcdf0;
  background:linear-gradient(90deg,rgba(247,247,255,.97),rgba(255,255,255,.96));
  box-shadow:0 8px 24px rgba(84,88,176,.09);
}
.growth-chapter__node {
  position:relative;
  width:34px;
  height:34px;
  display:grid;
  place-items:center;
  border:1px solid color-mix(in srgb,var(--chapter-color) 45%,#fff);
  border-radius:50% 50% 44% 56%;
  color:var(--chapter-color);
  background:color-mix(in srgb,var(--chapter-color) 9%,#fff);
  font:800 10px/1 ui-monospace,SFMono-Regular,monospace;
}
.growth-chapter[data-state="growing"] .growth-chapter__node::before,
.growth-chapter[data-state="growing"] .growth-chapter__node::after {
  content:"";
  position:absolute;
  inset:-1px;
  border:1px solid rgba(94,98,196,.36);
  border-radius:inherit;
  animation:growth-ring 2s ease-out infinite;
}
.growth-chapter[data-state="growing"] .growth-chapter__node::after { animation-delay:1s; }
.growth-chapter__copy { min-width:0; display:block; }
.growth-chapter__copy small { display:block; color:var(--chapter-color); font-size:9px; font-weight:850; letter-spacing:.08em; }
.growth-chapter__copy strong {
  display:block;
  margin-top:2px;
  overflow:hidden;
  color:#24332c;
  font-size:14px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.growth-chapter__copy > span {
  display:block;
  margin-top:2px;
  overflow:hidden;
  color:#7a857f;
  font-size:11px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.growth-chapter__progress { display:grid; grid-template-columns:minmax(45px,1fr) auto; align-items:center; gap:7px; }
.growth-chapter__progress > i { height:4px; overflow:hidden; border-radius:999px; background:#edf0ee; }
.growth-chapter__progress b {
  display:block;
  height:100%;
  border-radius:inherit;
  background:var(--chapter-color);
  transition:width .5s cubic-bezier(.2,.78,.25,1);
}
.growth-chapter__progress small { color:#7c8781; font:750 10px/1 ui-monospace,SFMono-Regular,monospace; }
.growth-chapter__head > svg { color:#9aa49f; transition:transform .25s ease,color .2s ease; }
.growth-chapter__head > svg.is-open { color:var(--chapter-color); transform:rotate(180deg); }
.growth-chapter__sections {
  position:relative;
  display:grid;
  margin:0 0 0 42px;
  padding:4px 0 2px 20px;
  list-style:none;
}
.growth-chapter__sections::before {
  content:"";
  position:absolute;
  top:0;
  bottom:14px;
  left:7px;
  width:1px;
  background:#cbd8d1;
  transform-origin:top;
  animation:growth-stem .45s ease-out both;
}
.growth-chapter__sections > li {
  position:relative;
  min-height:48px;
  display:grid;
  grid-template-columns:42px minmax(0,1fr) auto;
  align-items:center;
  gap:9px;
  padding:6px 8px 6px 5px;
  border-bottom:1px solid rgba(222,229,225,.75);
  animation:growth-arrive .38s ease-out both;
  animation-delay:calc(var(--section-order,0) * 45ms);
}
.growth-chapter__sections > li:last-child { border-bottom:0; }
.growth-section__joint {
  position:absolute;
  top:50%;
  left:-13px;
  width:14px;
  height:1px;
  background:#cbd8d1;
}
.growth-section__joint::after {
  content:"";
  position:absolute;
  top:-3px;
  right:-1px;
  width:7px;
  height:7px;
  border:1px solid #91ad9f;
  border-radius:50%;
  background:#f8faf8;
}
li[data-state="growing"] .growth-section__joint::after,
li[data-state="generating"] .growth-section__joint::after {
  border-color:#6d70ca;
  background:#e8e9ff;
  box-shadow:0 0 0 4px rgba(109,112,202,.1);
  animation:growth-breathe 1.4s ease-in-out infinite;
}
li[data-state="failed"] .growth-section__joint::after { border-color:#bd6729; background:#fff0df; }
.growth-section__number { color:#6f7d76; font:760 10px/1 ui-monospace,SFMono-Regular,monospace; }
.growth-chapter__sections li > div { min-width:0; }
.growth-chapter__sections li > div strong {
  display:block;
  overflow:hidden;
  color:#35453d;
  font-size:12px;
  line-height:1.4;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.growth-chapter__sections li > div p {
  margin:2px 0 0;
  overflow:hidden;
  color:#89928d;
  font-size:10px;
  line-height:1.45;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.growth-section__state { display:inline-flex; align-items:center; gap:5px; color:#73867d; font-size:10px; white-space:nowrap; }
li[data-state="growing"] .growth-section__state,
li[data-state="generating"] .growth-section__state { color:#575cb8; }
li[data-state="failed"] .growth-section__state { color:#a9571d; }
.growth-section__state svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.growth-section--bud > div strong { color:#7c8781!important; font-weight:650; }
.growth-section--bud > div p { display:flex; align-items:center; gap:5px; }
.growth-section--bud > div p span {
  width:42%;
  height:5px;
  border-radius:99px;
  background:linear-gradient(90deg,#e9eeeb,#f8faf9,#e9eeeb);
  background-size:200% 100%;
  animation:formation-shimmer 1.8s linear infinite;
}
.growth-section--bud > div p span:last-child { width:24%; }
.growth-chapter__more {
  min-height:32px!important;
  display:block!important;
  padding:9px 8px!important;
  color:#8b948f;
  font-size:10px;
}
.outline-germination {
  min-height:310px;
  display:grid;
  grid-template-columns:120px minmax(0,1fr) minmax(220px,.85fr);
  align-items:center;
  gap:24px;
  margin:0 0 18px;
  padding:26px clamp(20px,4vw,44px);
  overflow:hidden;
  border:1px solid #e1e6e2;
  border-radius:14px;
  background:
    radial-gradient(circle at 12% 50%,rgba(40,135,100,.11),transparent 25%),
    radial-gradient(circle at 88% 10%,rgba(94,98,196,.09),transparent 28%),
    #fafcfa;
}
.outline-germination__signal { position:relative; width:112px; height:112px; display:grid; place-items:center; }
.outline-germination__signal > i { position:absolute; inset:8px; border:1px solid rgba(35,128,94,.15); border-radius:47% 53% 50% 50%; animation:growth-orbit 7s linear infinite; }
.outline-germination__signal > i:nth-child(2) { inset:20px 2px; animation-duration:9s; animation-direction:reverse; }
.outline-germination__signal > i:nth-child(3) { inset:1px 24px; animation-duration:6s; }
.outline-germination__signal > span {
  position:relative;
  z-index:1;
  width:52px;
  height:52px;
  display:grid;
  place-items:center;
  border:1px solid #acd5c3;
  border-radius:50% 48% 52% 45%;
  color:#167b5e;
  background:#eef8f3;
  box-shadow:0 12px 30px rgba(31,110,81,.13);
  animation:growth-breathe 1.8s ease-in-out infinite;
}
.outline-germination > div:nth-child(2) strong { color:#25382f; font-size:18px; line-height:1.35; }
.outline-germination > div:nth-child(2) p { max-width:520px; margin:7px 0 0; color:#748078; font-size:12px; line-height:1.7; }
.outline-germination__branches { display:grid; gap:12px; }
.outline-germination__branches > span { display:grid; grid-template-columns:12px minmax(0,1fr); align-items:center; gap:8px; opacity:0; animation:growth-arrive .45s ease forwards; animation-delay:calc(var(--seed-order) * 100ms); }
.outline-germination__branches i { width:8px; height:8px; border:1px solid #b6c8bf; border-radius:50%; }
.outline-germination__branches b { height:8px; border-radius:99px; background:linear-gradient(90deg,#e6ece8,#f7f9f8,#e6ece8); background-size:200% 100%; animation:formation-shimmer 1.8s linear infinite; }
.outline-germination__branches span:nth-child(2n) b { width:76%; }
.outline-germination__branches span:nth-child(3n) b { width:88%; }
.formation-outline__nodes {
  display:grid;
  margin:0;
  padding:4px 0 14px;
  list-style:none;
}
.formation-outline__nodes li {
  display:grid;
  grid-template-columns:34px 16px minmax(0,1fr) auto;
  align-items:start;
  gap:10px;
  padding:11px 0;
  border-bottom:1px solid #f0f1f4;
}
.formation-outline__nodes li:last-child { border-bottom:0; }
.formation-outline__index {
  padding-top:3px;
  color:#9aa1ae;
  font:700 11px/1.2 ui-monospace,SFMono-Regular,monospace;
}
.formation-outline__marker {
  width:10px;
  height:10px;
  margin-top:3px;
  border:1.5px solid #aab1bf;
  border-radius:50%;
  background:#fff;
}
.formation-outline__nodes li[data-level="1"] .formation-outline__marker {
  width:12px;
  height:12px;
  margin-top:2px;
  border:0;
  border-radius:3px;
  background:#4f5b70;
}
.formation-outline__nodes li[data-state="generating"] .formation-outline__marker {
  border-color:#676bd6;
  background:#dfe1ff;
  box-shadow:0 0 0 3px #f0f0ff;
}
.formation-outline__nodes li[data-state="finalized"] .formation-outline__marker {
  border-color:#158467;
  background:#bce8d8;
}
.formation-outline__nodes li[data-state="failed"] .formation-outline__marker {
  border-color:#c36420;
  background:#fee1bf;
}
.formation-outline__nodes li > div { min-width:0; }
.formation-outline__nodes li > div strong {
  display:block;
  overflow:hidden;
  color:#354052;
  font-size:14px;
  line-height:1.4;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.formation-outline__nodes li[data-level="1"] > div strong { color:#1f2937; font-size:15px; }
.formation-outline__nodes li > div p {
  margin:4px 0 0;
  overflow:hidden;
  color:#7b8494;
  font-size:12px;
  line-height:1.55;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.formation-outline__status {
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:2px 0 0 10px;
  color:#8790a0;
  font-size:11px;
  line-height:1.4;
  white-space:nowrap;
}
li[data-state="generating"] .formation-outline__status { color:#5056b5; }
li[data-state="finalized"] .formation-outline__status { color:#087a5b; }
li[data-state="failed"] .formation-outline__status { color:#b54708; }
.formation-outline__status svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-outline__skeleton { display:grid; padding:4px 0 14px; }
.formation-outline__skeleton > div {
  display:grid;
  grid-template-columns:34px 16px minmax(0,1fr);
  align-items:start;
  gap:10px;
  padding:11px 0;
  border-bottom:1px solid #f0f1f4;
}
.formation-outline__skeleton > div:last-child { border-bottom:0; }
.formation-outline__skeleton span {
  width:22px;
  height:8px;
  margin-top:3px;
  border-radius:2px;
  background:#edf0f3;
}
.formation-outline__skeleton i {
  width:10px;
  height:10px;
  margin-top:2px;
  border:1px solid #d9dde4;
  border-radius:50%;
  background:#fff;
}
.formation-outline__skeleton div[data-level="1"] i {
  width:12px;
  height:12px;
  margin-top:1px;
  border:0;
  border-radius:3px;
  background:#d7dce3;
}
.formation-outline__skeleton p { display:grid; gap:8px; margin:0; }
.formation-outline__skeleton b,
.formation-outline__skeleton small {
  display:block;
  height:11px;
  border-radius:3px;
  background:linear-gradient(90deg,#eceff3 20%,#f7f8fa 45%,#eceff3 70%);
  background-size:220% 100%;
  animation:formation-shimmer 1.5s ease infinite;
}
.formation-outline__skeleton b { width:52%; }
.formation-outline__skeleton small { width:76%; height:8px; }
.formation-outline__skeleton div:nth-child(2) b,
.formation-outline__skeleton div:nth-child(5) b { width:68%; }
.formation-recovery {
  display:grid;
  grid-template-columns:40px minmax(0,1fr) auto;
  align-items:start;
  gap:13px;
  margin:0 28px 16px;
  padding:14px;
  border:1px solid #efd3a8;
  border-radius:9px;
  color:#75431c;
  background:#fffbf3;
}
.formation-recovery[data-state="paused"] {
  border-color:#d8dde5;
  color:#4b5565;
  background:#f7f8fa;
}
.formation-recovery__icon {
  width:40px;
  height:40px;
  display:grid;
  place-items:center;
  border-radius:8px;
  color:#b54708;
  background:#fff0d9;
}
.formation-recovery[data-state="paused"] .formation-recovery__icon {
  color:#667085;
  background:#e8ebf0;
}
.formation-recovery strong { color:#643713; font-size:14px; line-height:1.4; }
.formation-recovery[data-state="paused"] strong { color:#344054; }
.formation-recovery p {
  margin:5px 0 0;
  color:#84664c;
  font-size:12px;
  line-height:1.65;
}
.formation-recovery__saved {
  display:flex;
  flex-wrap:wrap;
  gap:5px;
  margin-top:7px;
}
.formation-recovery__saved span {
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:4px 8px;
  border-radius:999px;
  color:#26715d;
  background:#edf8f4;
  font-size:11px;
  font-weight:750;
}
.formation-recovery details { margin-top:8px; color:#8a6b4f; font-size:11px; }
.formation-recovery summary { width:max-content; cursor:pointer; }
.formation-recovery code {
  display:block;
  max-height:90px;
  margin-top:5px;
  padding:6px 8px;
  overflow:auto;
  border-left:2px solid #d89b43;
  background:rgba(255,255,255,.72);
  white-space:pre-wrap;
}
.formation-recovery > button {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 15px;
  border:1px solid #a85b1a;
  border-radius:7px;
  color:#fff;
  background:#a85b1a;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.formation-recovery > button:disabled { opacity:.55; cursor:wait; }
.formation-recovery > button svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-sheet__footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:13px 28px 14px;
  border-top:1px solid #e2e5ea;
  background:#fafbfc;
}
.formation-sheet__footer > div { min-width:0; }
.formation-sheet__footer > div span {
  color:#8a93a3;
  font-size:11px;
  font-weight:800;
  letter-spacing:.08em;
}
.formation-sheet__footer p { margin:3px 0 0; color:#687386; font-size:13px; line-height:1.55; }
.formation-sheet__footer > span {
  flex:0 0 auto;
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#26715d;
  font-size:11px;
  font-weight:750;
}
@keyframes formation-spin { to { transform:rotate(360deg); } }
@keyframes formation-shimmer { to { background-position:-220% 0; } }
@keyframes growth-stem { from { transform:scaleY(0); opacity:.2; } to { transform:scaleY(1); opacity:1; } }
@keyframes growth-branch { from { transform:scaleX(0); opacity:.2; } to { transform:scaleX(1); opacity:1; } }
@keyframes growth-arrive { from { opacity:0; transform:translateY(7px) scale(.99); } to { opacity:1; transform:none; } }
@keyframes growth-ring { 0% { opacity:.7; transform:scale(.82); } 75%,100% { opacity:0; transform:scale(1.65); } }
@keyframes growth-breathe { 50% { transform:translateY(-2px) scale(1.035); } }
@keyframes growth-orbit { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .course-production-stage { padding:10px 8px 18px; }
  .formation-sheet { border-radius:10px; }
  .formation-sheet__header { padding:17px 16px 14px; }
  .formation-sheet__header h1 { font-size:22px; }
  .formation-sheet__header p { font-size:13px; }
  .formation-outline { padding:0 16px; }
  .formation-outline > header div { align-items:flex-start; flex-direction:column; gap:3px; }
  .outline-growth-summary { grid-template-columns:1fr; gap:1px; margin-top:12px; }
  .outline-growth-summary > div { min-height:49px; padding:7px 10px; }
  .outline-growth-summary > div > span { width:31px; height:31px; }
  .outline-growth-tree { padding:8px 8px 10px 18px; }
  .outline-growth-tree::before { left:15px; }
  .growth-chapter::before { left:-3px; width:10px; }
  .growth-chapter__head { grid-template-columns:34px minmax(0,1fr) 18px; gap:8px; padding:7px; }
  .growth-chapter__node { width:31px; height:31px; }
  .growth-chapter__progress { grid-column:2; grid-row:2; width:min(150px,100%); margin-top:-4px; }
  .growth-chapter__head > svg { grid-column:3; grid-row:1/3; }
  .growth-chapter__copy > span { white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
  .growth-chapter__sections { margin-left:29px; padding-left:15px; }
  .growth-chapter__sections > li { grid-template-columns:36px minmax(0,1fr); gap:7px; padding:7px 3px; }
  .growth-section__state { grid-column:2; justify-self:start; }
  .growth-chapter__more { grid-column:1/-1!important; }
  .outline-germination { min-height:380px; grid-template-columns:1fr; justify-items:center; gap:14px; padding:22px 18px; text-align:center; }
  .outline-germination__signal { width:96px; height:96px; }
  .outline-germination__branches { width:100%; }
  .formation-outline__nodes li { grid-template-columns:26px 13px minmax(0,1fr); gap:8px; padding:10px 0; }
  .formation-outline__status { grid-column:3; justify-self:start; padding:3px 0 0; }
  .formation-outline__skeleton > div { grid-template-columns:26px 13px minmax(0,1fr); gap:8px; padding:10px 0; }
  .formation-recovery { grid-template-columns:36px minmax(0,1fr); margin:0 16px 12px; padding:12px; }
  .formation-recovery__icon { width:36px; height:36px; }
  .formation-recovery > button { grid-column:1/-1; width:100%; }
  .formation-sheet__footer { align-items:flex-start; flex-direction:column; gap:7px; padding:12px 16px; }
}
@media (prefers-reduced-motion:reduce) {
  .formation-sheet svg,
  .formation-outline__skeleton b,
  .formation-outline__skeleton small,
  .outline-growth-tree::before,
  .growth-chapter,
  .growth-chapter::before,
  .growth-chapter__sections::before,
  .growth-chapter__sections > li,
  .growth-chapter__node::before,
  .growth-chapter__node::after,
  .growth-section__joint::after,
  .growth-section--bud span,
  .outline-germination *,
  .outline-germination__branches > span { animation:none!important; }
}
</style>
