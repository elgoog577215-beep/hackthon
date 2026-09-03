<template>
  <section
    v-if="chapters.length"
    class="outline-growth-stream"
    :data-state="reviewReady ? 'review' : 'growing'"
    :data-structure="isLectureMode ? 'lecture' : 'legacy'"
    data-testid="outline-growth-stream"
    aria-live="polite"
  >
    <header class="growth-summary">
      <div>
        <strong>{{ summaryTitle }}</strong>
      </div>
      <span>{{ progressLabel }}</span>
    </header>

    <div class="growth-chapters">
      <article
        v-for="(chapter, index) in chapters"
        :key="chapter.id"
        class="growth-chapter"
        :data-state="chapter.status"
        :style="{ '--growth-order': index }"
      >
        <header>
          <span class="chapter-index">
            <Check v-if="chapter.status === 'completed'" :size="14" />
            <LoaderCircle v-else-if="chapter.status === 'growing'" :size="15" class="spin" />
            <span v-else>{{ String(chapter.number).padStart(2, '0') }}</span>
          </span>
          <div>
            <strong>{{ chapter.title }}</strong>
            <small>{{ chapterDisplayDetail(chapter) }}</small>
          </div>
          <small v-if="!isLectureMode" class="chapter-count">{{ chapter.completedCount }}/{{ chapter.sectionCount || '—' }}</small>
        </header>

        <ol v-if="!isLectureMode && (chapter.sections.length || chapter.status === 'growing')">
          <li
            v-for="(section, sectionIndex) in chapter.sections"
            :key="section.id"
            :style="{ '--section-order': sectionIndex }"
          >
            <span>{{ section.number }}</span>
            <div>
              <strong>{{ section.title }}</strong>
              <small v-if="section.objective">{{ section.objective }}</small>
            </div>
            <Check :size="13" />
          </li>
          <li v-if="chapter.status === 'growing' && chapter.completedCount < chapter.sectionCount" class="section-forming">
            <span>{{ nextSectionNumber(chapter) }}</span>
            <div><strong>{{ t('courseWorkbench.outlineSectionForming', '正在形成下一个小节…') }}</strong></div>
            <LoaderCircle :size="13" class="spin" />
          </li>
        </ol>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, LoaderCircle } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { Node } from '../stores/types'

type GrowthSection = {
  id: string
  number: string
  title: string
  objective: string
}

type GrowthChapter = {
  id: string
  number: number
  title: string
  detail: string
  sectionCount: number
  completedCount: number
  status: 'completed' | 'growing' | 'waiting' | 'failed'
  sections: GrowthSection[]
}

const props = withDefaults(defineProps<{
  growth?: Record<string, any> | null
  nodes?: Node[]
  reviewReady?: boolean
}>(), {
  growth: null,
  nodes: () => [],
  reviewReady: false,
})

const isLectureMode = computed(() => {
  if (props.growth?.authoring_structure_version === 'lecture_v1') return true
  const projected = Array.isArray(props.growth?.chapters) ? props.growth!.chapters : []
  return projected.length > 0 && projected.every((item: any) => Number(item?.section_count || 0) === 1)
})

function plainLectureTitle(value: unknown) {
  return String(value || '')
    .replace(/^(?:(?:第\s*)?\d+(?:\.\d+)?\s*[章节讲]\s*|\d+(?:\.\d+)+\s*)+/, '')
    .trim()
}

const chapters = computed<GrowthChapter[]>(() => {
  const projected = Array.isArray(props.growth?.chapters)
    ? props.growth!.chapters as Record<string, any>[]
    : []
  if (projected.length) {
    const activeNumber = Number(props.growth?.active_chapter_number || 0)
    return projected.map((chapter, index) => {
      const number = Number(chapter.chapter_number || index + 1)
      const sections = (Array.isArray(chapter.sections) ? chapter.sections : []).map((section: Record<string, any>, sectionIndex: number): GrowthSection => ({
        id: String(section.node_id || `growth-${number}-${sectionIndex + 1}`),
        number: String(section.section_number || `${number}.${sectionIndex + 1}`),
        title: String(section.title || t('courseGeneration.production.growthSectionSaved', '已形成小节')),
        objective: String(section.learning_objective || ''),
      }))
      const sectionCount = Math.max(sections.length, Number(chapter.section_count || 0))
      const completedCount = Math.min(sectionCount, Math.max(sections.length, Number(chapter.completed_section_count || 0)))
      const rawStatus = String(chapter.status || '')
      const status: GrowthChapter['status'] = rawStatus === 'completed' || (sectionCount > 0 && completedCount >= sectionCount)
        ? 'completed'
        : rawStatus === 'growing' || activeNumber === number
          ? 'growing'
          : rawStatus === 'failed'
            ? 'failed'
            : 'waiting'
      return {
        id: `chapter-${number}`,
        number,
        title: isLectureMode.value
          ? `第${number}讲 ${plainLectureTitle(chapter.title).replace('正在生成本讲主题…', '')}`.trim()
          : String(chapter.title || t('courseGeneration.production.growthChapter', '第 {number} 章').replace('{number}', String(number))),
        detail: String(chapter.content_summary || chapter.learning_focus || ''),
        sectionCount,
        completedCount,
        status,
        sections,
      }
    })
  }

  const chapterNodes = props.nodes.filter(node => Number(node.node_level || 0) === 1)
  return chapterNodes.map((chapter, index): GrowthChapter => {
    const sections = props.nodes.filter(node => node.parent_node_id === chapter.node_id)
    return {
      id: chapter.node_id,
      number: index + 1,
      title: isLectureMode.value
        ? `第${index + 1}讲 ${plainLectureTitle(chapter.node_name)}`.trim()
        : chapter.node_name,
      detail: chapter.content_summary || chapter.learning_objective || '',
      sectionCount: sections.length,
      completedCount: sections.length,
      status: 'completed',
      sections: sections.map((section, sectionIndex) => ({
        id: section.node_id,
        number: section.node_name.match(/^([\d.]+)\s*/)?.[1] || `${index + 1}.${sectionIndex + 1}`,
        title: section.node_name.replace(/^[\d.]+\s*/, ''),
        objective: section.learning_objective || '',
      })),
    }
  })
})

const completedSections = computed(() => props.growth
  ? Number(props.growth.completed_sections || 0)
  : chapters.value.reduce((sum, chapter) => sum + chapter.completedCount, 0))
const totalSections = computed(() => props.growth
  ? Number(props.growth.total_sections || 0)
  : chapters.value.reduce((sum, chapter) => sum + chapter.sectionCount, 0))
const completedLectures = computed(() => chapters.value.filter(
  chapter => chapter.status === 'completed',
).length)
const growthState = computed(() => String(props.growth?.state || ''))
const summaryTitle = computed(() => {
  if (props.reviewReady || growthState.value === 'completed') {
    return t('courseWorkbench.outlineReady', '课程大纲已生成')
  }
  if (isLectureMode.value && growthState.value === 'detailing') {
    return t(
      'courseWorkbench.outlineDetailGenerating',
      '正在生成完整课程大纲',
    )
  }
  if (isLectureMode.value && ['skeleton_ready', 'framework_ready'].includes(growthState.value)) {
    return t('courseWorkbench.outlineFrameworkReady', '讲次方案已生成')
  }
  if (isLectureMode.value) {
    return t(
      'courseWorkbench.outlineFrameworkGrowing',
      '正在生成讲次方案',
    )
  }
  return t('courseWorkbench.outlineGrowing', '课程结构正在形成')
})
const progressLabel = computed(() => {
  if (!isLectureMode.value) {
    return `${completedSections.value} / ${totalSections.value || '—'}`
  }
  if (!['detailing', 'completed'].includes(growthState.value)) {
    const completed = ['skeleton_ready', 'framework_ready'].includes(growthState.value)
      ? chapters.value.length
      : completedLectures.value
    return t('courseWorkbench.outlineFrameworkProgress', '已生成 {completed}/{total}')
      .replace('{completed}', String(completed))
      .replace('{total}', String(chapters.value.length))
  }
  return t('courseWorkbench.outlineDetailProgress', '已补全 {completed}/{total}')
    .replace('{completed}', String(completedLectures.value))
    .replace('{total}', String(chapters.value.length))
})

function chapterStateLabel(chapter: GrowthChapter) {
  if (chapter.status === 'growing') {
    return t('courseWorkbench.outlineFlow.lessonRunning', '正在生成')
  }
  if (chapter.status === 'failed') {
    return t('courseWorkbench.outlineFlow.lessonFailed', '生成失败，可单独重试')
  }
  if (chapter.status === 'completed') {
    return t('courseWorkbench.outlineFlow.lessonCompleted', '已生成')
  }
  return t('courseWorkbench.outlineFlow.lessonQueued', '等待生成')
}

function chapterDisplayDetail(chapter: GrowthChapter) {
  const lightPlanComplete = ['skeleton_ready', 'framework_ready'].includes(growthState.value)
  if (chapter.status !== 'completed' && !lightPlanComplete) {
    return chapterStateLabel(chapter)
  }
  return chapter.detail || chapterStateLabel(chapter)
}

function nextSectionNumber(chapter: GrowthChapter) {
  return `${chapter.number}.${chapter.completedCount + 1}`
}
</script>

<style scoped>
.outline-growth-stream{display:grid;gap:18px}.growth-summary{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:2px 0 16px;border-bottom:1px solid #e7ebf2}.growth-summary>div{display:grid;gap:4px}.growth-summary strong{color:#263147;font-size:14px}.growth-summary small{color:#64748b;font-size:12px}.growth-summary>span{min-width:68px;padding:6px 9px;border-radius:7px;color:#4338ca;background:#eef0ff;font-size:12px;font-weight:800;text-align:center}.growth-chapters{display:grid;gap:12px}.growth-chapter{overflow:hidden;border:1px solid #e1e7f0;border-radius:11px;background:#fff;animation:growth-in .32s ease both;animation-delay:calc(var(--growth-order) * 35ms)}.growth-chapter>header{min-height:62px;display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:11px;padding:11px 14px}.chapter-index{width:28px;height:28px;display:grid;place-items:center;border-radius:50%;color:#64748b;background:#f1f5f9;font-size:10px;font-weight:800}.growth-chapter[data-state="completed"] .chapter-index{color:#047857;background:#ecfdf5}.growth-chapter[data-state="growing"] .chapter-index{color:#4f46e5;background:#eef2ff}.growth-chapter>header>div{min-width:0;display:grid;gap:3px}.growth-chapter>header strong{overflow:hidden;color:#263147;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.growth-chapter>header small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.chapter-count{font-weight:750}.growth-chapter ol{display:grid;gap:0;margin:0;padding:0 14px 10px 55px;list-style:none}.growth-chapter li{min-height:48px;display:grid;grid-template-columns:46px minmax(0,1fr) 18px;align-items:center;gap:8px;border-top:1px solid #eef2f6;color:#16a34a;animation:growth-in .28s ease both;animation-delay:calc(var(--section-order) * 28ms)}.growth-chapter li>span{color:#6366f1;font-size:11px;font-weight:750}.growth-chapter li>div{min-width:0;display:grid;gap:2px}.growth-chapter li strong{color:#334155;font-size:12px}.growth-chapter li small{color:#64748b;font-size:11px;line-height:1.45}.growth-chapter .section-forming{color:#4f46e5}.growth-chapter .section-forming strong{color:#64748b;font-weight:650}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes growth-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
</style>
