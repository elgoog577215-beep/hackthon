<template>
  <section class="arrangement-summary" data-testid="lesson-arrangement-summary">
    <header>
      <div>
        <small>{{ t('courseWorkbench.arrangement.lessonType', '本讲课型') }}</small>
        <strong>{{ arrangement.lesson_type_label }}</strong>
        <span>{{ totalMinutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }} · {{ arrangement.blocks.length }} {{ t('courseWorkbench.arrangement.blocks', '个教学块') }}</span>
      </div>
      <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded
          ? t('courseWorkbench.arrangement.collapse', '收起教学结构')
          : t('courseWorkbench.arrangement.expand', '查看教学结构') }}
        <ChevronDown :size="15" :class="{ rotated: expanded }" />
      </button>
    </header>

    <p v-if="arrangement.lesson_type_recommendation_reason" class="arrangement-reason">
      {{ arrangement.lesson_type_recommendation_reason }}
    </p>

    <div v-if="expanded" class="arrangement-blocks">
      <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
        <header>
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <div><strong>{{ block.name }}</strong><small>{{ block.section_title }}</small></div>
          <b>{{ block.planned_minutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }}</b>
        </header>
        <p v-if="block.purpose || block.content_summary">{{ block.purpose || block.content_summary }}</p>
        <dl>
          <div><dt>{{ t('courseWorkbench.arrangement.teacherAction', '教师动作') }}</dt><dd>{{ block.teacher_activity }}</dd></div>
          <div><dt>{{ t('courseWorkbench.arrangement.studentAction', '学生行动') }}</dt><dd>{{ block.student_activity }}</dd></div>
          <div><dt>{{ t('courseWorkbench.arrangement.evidence', '学习证据') }}</dt><dd>{{ block.expected_output }}</dd></div>
          <div v-if="block.check_method"><dt>{{ t('courseWorkbench.arrangement.check', '怎样检查') }}</dt><dd>{{ block.check_method }}</dd></div>
          <div v-if="block.feedback_strategy"><dt>{{ t('courseWorkbench.arrangement.feedback', '反馈预案') }}</dt><dd>{{ block.feedback_strategy }}</dd></div>
          <div v-if="block.adaptation_options?.length" class="adaptation-row">
            <dt>{{ t('courseWorkbench.arrangement.adaptation', '三档处理') }}</dt>
            <dd><span v-for="item in block.adaptation_options" :key="item">{{ item }}</span></dd>
          </div>
          <div v-if="block.safety_boundary"><dt>{{ t('courseWorkbench.arrangement.safety', '专业边界') }}</dt><dd>{{ block.safety_boundary }}</dd></div>
        </dl>
      </article>
    </div>

    <footer v-if="impactLabels.length">
      <TriangleAlert :size="15" />
      <div>
        <strong>{{ t('courseWorkbench.arrangement.changeImpact', '调整本讲结构的影响') }}</strong>
        <span>{{ impactLabels.join('；') }}。{{ t('courseWorkbench.arrangement.lastUsable', '已有版本会保留，不会被静默覆盖。') }}</span>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, TriangleAlert } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { TeacherLessonArrangement } from '../stores/teacherLessonAuthoring'

const props = withDefaults(defineProps<{
  arrangement: TeacherLessonArrangement
  impactLabels?: string[]
}>(), { impactLabels: () => [] })

const expanded = ref(false)
const totalMinutes = computed(() => props.arrangement.blocks.reduce(
  (sum, block) => sum + Number(block.planned_minutes || 0),
  0,
))
</script>

<style scoped>
.arrangement-summary{border-bottom:1px solid #e6ebf2;background:#fff}.arrangement-summary>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 24px}.arrangement-summary>header>div{min-width:0;display:flex;align-items:baseline;gap:10px}.arrangement-summary>header small{color:#7a8799;font-size:10px;font-weight:750}.arrangement-summary>header strong{color:#29354a;font-size:14px}.arrangement-summary>header span{color:#7b8797;font-size:11px}.arrangement-summary>header button{display:flex;align-items:center;gap:5px;padding:7px 9px;border:0;border-radius:7px;color:#514dc0;background:#f3f2ff;font-size:11px;font-weight:700;cursor:pointer}.arrangement-summary>header button:hover{background:#eae9ff}.arrangement-summary>header button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.arrangement-summary>header button svg{transition:transform .16s ease}.arrangement-summary>header button svg.rotated{transform:rotate(180deg)}.arrangement-reason{margin:0;padding:0 24px 15px;color:#657286;font-size:12px;line-height:1.6}.arrangement-blocks{display:grid;gap:10px;padding:4px 24px 20px;background:#fafbfc}.arrangement-blocks article{padding:14px 16px;border:1px solid #e2e7ef;border-radius:10px;background:#fff}.arrangement-blocks article>header{display:grid;grid-template-columns:24px minmax(0,1fr) auto;align-items:center;gap:9px}.arrangement-blocks article>header>span{color:#7773d1;font-size:10px;font-weight:800}.arrangement-blocks article>header>div{min-width:0;display:grid;gap:2px}.arrangement-blocks article>header strong{color:#29354a;font-size:12.5px}.arrangement-blocks article>header small{overflow:hidden;color:#8a96a7;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.arrangement-blocks article>header b{color:#667085;font-size:10px}.arrangement-blocks article>p{margin:10px 0 0 33px;color:#667386;font-size:11.5px;line-height:1.55}.arrangement-blocks dl{display:grid;gap:7px;margin:12px 0 0 33px}.arrangement-blocks dl>div{display:grid;grid-template-columns:62px minmax(0,1fr);gap:10px}.arrangement-blocks dt{color:#8a96a7;font-size:10px;font-weight:750}.arrangement-blocks dd{margin:0;color:#4d5a6d;font-size:11.5px;line-height:1.55}.adaptation-row dd{display:grid;gap:3px}.arrangement-summary>footer{display:flex;align-items:flex-start;gap:9px;padding:11px 24px;border-top:1px solid #eceff4;color:#776513;background:#fffdf5}.arrangement-summary>footer>div{display:grid;gap:2px}.arrangement-summary>footer strong{font-size:11px}.arrangement-summary>footer span{color:#736f61;font-size:10.5px;line-height:1.5}@media(max-width:760px){.arrangement-summary>header{align-items:flex-start;padding-inline:16px}.arrangement-summary>header>div{display:grid;gap:3px}.arrangement-reason,.arrangement-blocks,.arrangement-summary>footer{padding-inline:16px}.arrangement-blocks dl{margin-left:0}.arrangement-blocks dl>div{grid-template-columns:1fr;gap:2px}}
</style>
