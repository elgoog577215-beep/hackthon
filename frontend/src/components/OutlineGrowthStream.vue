<template>
  <section
    v-if="lessons.length"
    class="outline-growth-stream"
    :data-state="reviewReady ? 'review' : 'growing'"
    data-structure="lecture"
    data-testid="outline-growth-stream"
    aria-live="polite"
  >
    <header class="growth-summary">
      <div>
        <strong>{{ summaryTitle }}</strong>
      </div>
      <span>{{ progressLabel }}</span>
    </header>

    <div class="growth-lessons">
      <article
        v-for="(lesson, index) in lessons"
        :key="lesson.id"
        class="growth-lesson"
        :data-state="lesson.status"
        :style="{ '--growth-order': index }"
      >
        <header>
          <span class="lesson-index">
            <Check v-if="lesson.status === 'completed'" :size="14" />
            <LoaderCircle v-else-if="lesson.status === 'growing'" :size="15" class="spin" />
            <span v-else>{{ String(lesson.number).padStart(2, '0') }}</span>
          </span>
          <div>
            <strong><MathText :content="lesson.title" /></strong>
            <small><MathText :content="lessonDisplayDetail(lesson)" /></small>
          </div>
        </header>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, LoaderCircle } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'

type GrowthLesson = {
  id: string
  number: number
  title: string
  detail: string
  status: 'completed' | 'growing' | 'waiting' | 'failed'
}

const props = withDefaults(defineProps<{
  growth?: Record<string, any> | null
  reviewReady?: boolean
}>(), {
  growth: null,
  reviewReady: false,
})

function plainLectureTitle(value: unknown) {
  return String(value || '')
    .replace(/^(?:(?:第\s*)?[0-9一二三四五六七八九十百]+(?:\.\d+)?\s*[章节讲课]\s*|\d+(?:\.\d+)+\s*)+/u, '')
    .trim()
}

const lessons = computed<GrowthLesson[]>(() => {
  const projected = Array.isArray(props.growth?.chapters)
    ? props.growth!.chapters as Record<string, any>[]
    : []
  const activeNumber = Number(props.growth?.active_chapter_number || 0)
  return projected.map((rawLesson, index) => {
    const number = Number(rawLesson.chapter_number || index + 1)
    const unitCount = Math.max(
      Array.isArray(rawLesson.sections) ? rawLesson.sections.length : 0,
      Number(rawLesson.section_count || 0),
    )
    const completedCount = Math.max(
      Array.isArray(rawLesson.sections) ? rawLesson.sections.length : 0,
      Number(rawLesson.completed_section_count || 0),
    )
    const rawStatus = String(rawLesson.status || '')
    const status: GrowthLesson['status'] = rawStatus === 'completed' || (unitCount > 0 && completedCount >= unitCount)
      ? 'completed'
      : rawStatus === 'growing' || activeNumber === number
        ? 'growing'
        : rawStatus === 'failed'
          ? 'failed'
          : 'waiting'
    return {
      id: String(rawLesson.lesson_id || rawLesson.node_id || `lesson-${number}`),
      number,
      title: `第${number}讲 ${plainLectureTitle(rawLesson.title).replace('正在生成本讲主题…', '')}`.trim(),
      detail: String(rawLesson.content_summary || rawLesson.learning_focus || ''),
      status,
    }
  })
})

const completedLectures = computed(() => lessons.value.filter(
  lesson => lesson.status === 'completed',
).length)
const growthState = computed(() => String(props.growth?.state || ''))
const summaryTitle = computed(() => {
  if (growthState.value === 'optimizing') return t('courseWorkbench.autoImprovement.outline', '正在自动优化大纲并复审')
  if (props.reviewReady || growthState.value === 'completed') {
    return t('courseWorkbench.outlineReady', '课程大纲已生成')
  }
  if (growthState.value === 'detailing') {
    return t(
      'courseWorkbench.outlineDetailGenerating',
      '正在生成完整课程大纲',
    )
  }
  if (['skeleton_ready', 'framework_ready'].includes(growthState.value)) {
    return t('courseWorkbench.outlineFrameworkReady', '讲次方案已生成')
  }
  return t(
    'courseWorkbench.outlineFrameworkGrowing',
    '正在生成讲次方案',
  )
})
const progressLabel = computed(() => {
  if (growthState.value === 'optimizing') return t('courseWorkbench.autoImprovement.reviewing', '正在检查最终内容')
  if (!['detailing', 'completed'].includes(growthState.value)) {
    const completed = ['skeleton_ready', 'framework_ready'].includes(growthState.value)
      ? lessons.value.length
      : completedLectures.value
    return t('courseWorkbench.outlineFrameworkProgress', '已生成 {completed}/{total}')
      .replace('{completed}', String(completed))
      .replace('{total}', String(lessons.value.length))
  }
  return t('courseWorkbench.outlineDetailProgress', '已补全 {completed}/{total}')
    .replace('{completed}', String(completedLectures.value))
    .replace('{total}', String(lessons.value.length))
})

function lessonStateLabel(lesson: GrowthLesson) {
  if (lesson.status === 'growing') {
    return t('courseWorkbench.outlineFlow.lessonRunning', '正在生成')
  }
  if (lesson.status === 'failed') {
    return t('courseWorkbench.outlineFlow.lessonFailed', '生成失败，可单独重试')
  }
  if (lesson.status === 'completed') {
    return t('courseWorkbench.outlineFlow.lessonCompleted', '已生成')
  }
  return t('courseWorkbench.outlineFlow.lessonQueued', '等待生成')
}

function lessonDisplayDetail(lesson: GrowthLesson) {
  const lightPlanComplete = ['skeleton_ready', 'framework_ready'].includes(growthState.value)
  if (lesson.status !== 'completed' && !lightPlanComplete) {
    return lessonStateLabel(lesson)
  }
  return lesson.detail || lessonStateLabel(lesson)
}
</script>

<style scoped>
.outline-growth-stream{display:grid;gap:18px}.growth-summary{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:2px 0 16px;border-bottom:1px solid #e7ebf2}.growth-summary>div{display:grid;gap:4px}.growth-summary strong{color:#263147;font-size:14px}.growth-summary small{color:#64748b;font-size:12px}.growth-summary>span{min-width:68px;padding:6px 9px;border-radius:7px;color:#4338ca;background:#eef0ff;font-size:12px;font-weight:800;text-align:center}.growth-lessons{display:grid;gap:12px}.growth-lesson{overflow:hidden;border:1px solid #e1e7f0;border-radius:11px;background:#fff;animation:growth-in .32s ease both;animation-delay:calc(var(--growth-order) * 35ms)}.growth-lesson>header{min-height:62px;display:grid;grid-template-columns:30px minmax(0,1fr);align-items:center;gap:11px;padding:11px 14px}.lesson-index{width:28px;height:28px;display:grid;place-items:center;border-radius:50%;color:#64748b;background:#f1f5f9;font-size:10px;font-weight:800}.growth-lesson[data-state="completed"] .lesson-index{color:#047857;background:#ecfdf5}.growth-lesson[data-state="growing"] .lesson-index{color:#4f46e5;background:#eef2ff}.growth-lesson>header>div{min-width:0;display:grid;gap:3px}.growth-lesson>header strong{overflow:hidden;color:#263147;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.growth-lesson>header small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes growth-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
</style>
