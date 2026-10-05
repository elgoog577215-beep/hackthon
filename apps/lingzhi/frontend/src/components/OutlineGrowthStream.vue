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

    <p v-if="receivedChars" class="growth-received">{{ t('courseWorkbench.outlineStream.received').replace('{count}', String(receivedChars)) }}</p>
    <div v-if="coursePreview.length" class="growth-course-preview" data-testid="outline-course-stream">
      <section v-for="field in coursePreview" :key="field.field">
        <strong>{{ t(`courseWorkbench.outlineStream.fields.${field.field}`) }}</strong>
        <p><MathText :content="field.text" /></p>
      </section>
    </div>
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
            <LoaderCircle v-else-if="lesson.status === 'growing' && running" :size="15" class="spin" />
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
  running?: boolean
  mode?: 'full' | 'plan_first'
}>(), {
  growth: null,
  reviewReady: false,
  running: true,
  mode: 'plan_first',
})

function plainLectureTitle(value: unknown) {
  return String(value || '')
    .replace(/^(?:(?:第\s*)?[0-9一二三四五六七八九十百]+(?:\.\d+)?\s*[章节讲课]\s*|\d+(?:\.\d+)+\s*)+/u, '')
    .trim()
}

const receivedChars = computed(() => Number(props.growth?.streamed_content_chars || 0))
const coursePreview = computed(() => (Array.isArray(props.growth?.course_preview) ? props.growth!.course_preview : [])
  .filter((field: any) => typeof field?.field === 'string' && typeof field?.text === 'string'))
const fullGeneration = computed(() => props.mode === 'full' || props.growth?.state === 'full_growing')
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
      title: `${t('courseWorkbench.outlineStream.lecture').replace('{number}', String(number))} ${plainLectureTitle(rawLesson.title).replace('正在生成本讲主题…', '')}`.trim(),
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
  if (props.reviewReady || growthState.value === 'completed') {
    return t('courseWorkbench.outlineReady', '课程大纲已生成')
  }
  if (!props.running) return t('courseWorkbench.outlineStream.retained')
  if (growthState.value === 'validating') return t('courseWorkbench.outlineStream.validating')
  if (fullGeneration.value || growthState.value === 'detailing') {
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
  if (fullGeneration.value && !props.reviewReady && growthState.value !== 'completed') {
    return t('courseWorkbench.outlineStream.parsed')
      .replace('{completed}', String(completedLectures.value)).replace('{total}', String(lessons.value.length))
  }
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
  if (lesson.status !== 'completed' && !props.running) return t('courseWorkbench.outlineStream.incomplete')
  if (fullGeneration.value) return t(`courseWorkbench.outlineStream.${lesson.status === 'completed' ? 'parsedLesson' : lesson.status === 'growing' ? 'receiving' : 'notReceived'}`)
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
  if (lesson.detail) return lesson.detail
  if (lesson.status !== 'completed' && !lightPlanComplete) {
    return lessonStateLabel(lesson)
  }
  return lesson.detail || lessonStateLabel(lesson)
}
</script>

<style scoped>
.growth-received{margin:0;color:#64748b;font-size:15px}.growth-course-preview{display:grid;gap:16px}.growth-course-preview strong{color:#263147;font-size:15px}.growth-course-preview p{margin:6px 0 0;white-space:pre-wrap;line-height:1.7;font-size:15px;color:#475569}

.outline-growth-stream{display:grid;gap:18px}.growth-summary{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:2px 0 16px;border-bottom:1px solid #e7ebf2}.growth-summary>div{display:grid;gap:4px}.growth-summary strong{color:#263147;font-size:14px}.growth-summary small{color:#64748b;font-size:12px}.growth-summary>span{min-width:68px;padding:6px 9px;border-radius:7px;color:#4338ca;background:#eef0ff;font-size:12px;font-weight:800;text-align:center}.growth-lessons{display:grid;gap:12px}.growth-lesson{overflow:hidden;border:1px solid #e1e7f0;border-radius:11px;background:#fff;animation:growth-in .32s ease both;animation-delay:calc(var(--growth-order) * 35ms)}.growth-lesson>header{min-height:62px;display:grid;grid-template-columns:30px minmax(0,1fr);align-items:center;gap:11px;padding:11px 14px}.lesson-index{width:28px;height:28px;display:grid;place-items:center;border-radius:50%;color:#64748b;background:#f1f5f9;font-size:10px;font-weight:800}.growth-lesson[data-state="completed"] .lesson-index{color:#047857;background:#ecfdf5}.growth-lesson[data-state="growing"] .lesson-index{color:#4f46e5;background:#eef2ff}.growth-lesson>header>div{min-width:0;display:grid;gap:3px}.growth-lesson>header strong{overflow:hidden;color:#263147;font-size:15px;text-overflow:ellipsis;white-space:normal}.growth-lesson>header small{overflow:hidden;color:#64748b;font-size:15px;text-overflow:ellipsis;white-space:pre-wrap}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes growth-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
</style>
