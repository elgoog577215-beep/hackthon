<template>
  <section
    class="arrangement-summary"
    :class="{ 'has-sticky-actions': stickyActions }"
    data-testid="lesson-arrangement-summary"
    :data-state="arrangement.source_state !== 'current' ? 'stale' : arrangement.ready === true ? 'ready' : 'review'"
  >
    <header class="arrangement-toolbar">
      <div class="arrangement-context">
        <span class="arrangement-state" role="status">
          <Check v-if="arrangement.ready === true" :size="17" />
          <TriangleAlert v-else :size="17" />
          {{ arrangement.source_state !== 'current'
            ? t('courseWorkbench.arrangement.stale', '教学结构需更新')
            : arrangement.ready === true
              ? t('courseWorkbench.arrangement.generated', '教学结构已生成')
              : t('courseWorkbench.arrangement.review', '教学结构预览') }}
        </span>
      </div>
      <div class="arrangement-actions">
        <div v-if="$slots['generation-actions']" class="arrangement-generation-actions">
          <slot name="generation-actions" />
        </div>
      </div>
    </header>

    <p v-if="error" class="arrangement-error" role="alert"><TriangleAlert :size="14" />{{ error }}</p>

    <section v-if="!generating && !collapsed" class="arrangement-document">
      <div class="arrangement-blocks">
        <article v-for="(block, index) in arrangement.blocks" :key="block.block_id">
          <header>
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div><strong><MathText :content="block.name" /></strong><MathText :content="block.section_title" /></div>
            <b>{{ block.planned_minutes }} {{ t('courseWorkbench.arrangement.minutes', '分钟') }}</b>
          </header>
          <dl>
            <div><dt>{{ t('courseWorkbench.arrangement.blockGoal', '环节目标') }}</dt><dd><MathText :content="block.purpose" /></dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.classroomActivity', '课堂活动') }}</dt><dd><MathText :content="blockActivity(block)" /></dd></div>
            <div><dt>{{ t('courseWorkbench.arrangement.attainmentJudgement', '达成判断') }}</dt><dd><MathText :content="blockAttainment(block)" /></dd></div>
          </dl>
        </article>
      </div>
    </section>

    <footer v-if="!generating && !collapsed && impactLabels.length">
      <TriangleAlert :size="14" />
      <div>
        <strong>{{ t('courseWorkbench.arrangement.changeImpact', '调整后的影响') }}</strong>
        <span>{{ impactLabels.join('；') }}。{{ t('courseWorkbench.arrangement.lastUsable', '最后可用版本会保留，不会被静默覆盖。') }}</span>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { Check, TriangleAlert } from 'lucide-vue-next'
import MathText from './MathText.vue'
import { t } from '../shared/i18n'
import type { TeacherLessonArrangement } from '../stores/teacherLessonAuthoring'

withDefaults(defineProps<{
  arrangement: TeacherLessonArrangement
  impactLabels?: string[]
  collapsed?: boolean
  generating?: boolean
  stickyActions?: boolean
  error?: string
}>(), {
  impactLabels: () => [],
  collapsed: false,
  generating: false,
  stickyActions: false,
  error: '',
})

function uniqueText(values: unknown[]): string {
  return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))].join('；')
}

function blockActivity(block: TeacherLessonArrangement['blocks'][number]): string {
  return uniqueText([block.content_summary, block.teacher_activity, block.student_activity]) || '-'
}

function blockAttainment(block: TeacherLessonArrangement['blocks'][number]): string {
  return uniqueText([block.expected_output, block.check_method]) || '-'
}

</script>

<style scoped>
.arrangement-summary{position:relative;background:#fff}.arrangement-toolbar{position:relative;z-index:2;min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 16px;border-bottom:1px solid #dfe5ee;background:#fff}.arrangement-summary.has-sticky-actions .arrangement-toolbar{position:sticky;z-index:8;top:0}.arrangement-context,.arrangement-actions{min-width:0;display:flex;align-items:center;gap:11px;white-space:nowrap}.arrangement-actions{flex:none;justify-content:flex-end}.arrangement-state{flex:none;display:flex;align-items:center;gap:6px;color:#207148;font-size:15px;font-weight:680;white-space:nowrap}.arrangement-summary[data-state="stale"] .arrangement-state,.arrangement-summary[data-state="review"] .arrangement-state{color:#9a6700}.arrangement-generation-actions{flex:none;display:flex;align-items:center;justify-content:flex-end}.arrangement-error{display:flex;align-items:center;gap:7px;margin:0;padding:12px 20px;color:#a33a31;background:#fff3f2;font-size:15px}.arrangement-document{padding:0 24px 12px}.arrangement-blocks{display:grid}.arrangement-blocks article{padding:22px 2px 24px;border-bottom:1px solid #e7ebf1}.arrangement-blocks article:last-child{border-bottom:0}.arrangement-blocks article>header{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:start;gap:12px}.arrangement-blocks article>header>span{width:30px;height:30px;display:grid;place-items:center;border:1px solid #d8deea;border-radius:50%;color:#5e5ab9;font-size:15px;font-weight:800}.arrangement-blocks article>header>div{min-width:0;display:grid;gap:4px}.arrangement-blocks article>header strong{color:#243044;font-size:17px;line-height:1.45}.arrangement-blocks article>header>div>span{overflow:hidden;color:#667386;font-size:15px;line-height:1.55;text-overflow:ellipsis;white-space:nowrap}.arrangement-blocks article>header b{padding-top:4px;color:#59667a;font-size:15px;white-space:nowrap}.arrangement-blocks dl{display:grid;gap:11px;margin:16px 0 0 46px}.arrangement-blocks dl>div{display:grid;grid-template-columns:76px minmax(0,1fr);gap:14px}.arrangement-blocks dt{color:#68758a;font-size:15px;font-weight:720}.arrangement-blocks dd{margin:0;color:#3f4d62;font-size:16px;line-height:1.75}.arrangement-summary>footer{display:flex;align-items:flex-start;gap:10px;margin:0 24px;padding:14px 2px 4px;border-top:1px solid #eadfb8;color:#776513}.arrangement-summary>footer>div{display:grid;gap:4px}.arrangement-summary>footer strong,.arrangement-summary>footer span{font-size:15px;line-height:1.6}.arrangement-summary>footer span{color:#6d685a}@media(max-width:900px){.arrangement-toolbar{gap:10px;padding-inline:12px}.arrangement-context,.arrangement-actions{gap:8px}.arrangement-document{padding-inline:18px}.arrangement-blocks article>header{grid-template-columns:34px minmax(0,1fr)}.arrangement-blocks article>header b{grid-column:2}.arrangement-blocks dl{margin-left:46px}}
</style>
