<template>
  <section v-if="skills.length" class="capability-panel">
    <h3>{{ t('knowledgeFirst.capabilities') }}</h3>
    <p class="candidate-note" role="note">{{ t('knowledgeFirst.candidateWarning') }}</p>
    <article v-for="skill in skills" :key="skill.skill_id" class="capability-card">
      <h4>{{ skill.unit_key }} · {{ skill.name }}</h4>
      <p>{{ skill.observable_behavior }}</p>
      <ul class="review-issues"><li v-for="issue in skill.review?.issues || []" :key="issue.field"><strong>{{ issue.field }}</strong> · {{ issue.message }}</li></ul>
      <details open><summary>{{ t('knowledgeFirst.masteryCriteria') }}</summary>
        <div v-for="c in criteria(skill.skill_id)" :key="c.criterion_id" class="teaching-item">
          <strong>{{ c.point_key }} · {{ c.name }}</strong><p>{{ c.observable_performance }}</p>
          <p>{{ t('knowledgeFirst.failureEvidence') }}：{{ c.failure_evidence }}</p>
          <details><summary>{{ t('knowledgeFirst.frozenQuestion') }}</summary><MarkdownRenderer :content="c.probe.question" /><p>{{ t('knowledgeFirst.frozenAnswer') }}：{{ c.probe.answer }}</p></details>
        </div>
      </details>
      <details><summary>{{ t('knowledgeFirst.mistakesAndRepair') }}</summary>
        <div v-for="m in mistakes(skill.skill_id)" :key="m.misconception_id" class="teaching-item">
          <strong>{{ m.name }}</strong><p>{{ t('knowledgeFirst.wrongBelief') }}：{{ m.wrong_rule }}</p><p>{{ m.observable_error_pattern }}</p>
          <div v-for="p in m.predictions" :key="p.probe_key" class="prediction"><code>{{ p.probe_key }}</code><p>{{ p.answer }}</p><small>{{ p.reason }}</small></div>
          <p class="repair-text">{{ m.repair_strategy }}</p>
        </div>
      </details>
      <details><summary>{{ t('knowledgeFirst.discrimination') }}</summary>
        <div v-for="d in diagnostics(skill.skill_id)" :key="d.diagnostic_id">
          <p>{{ d.unknown_prediction_policy }}</p><div v-for="probe in d.probes" :key="probe.key" class="teaching-item"><strong>{{ probe.key }}</strong><MarkdownRenderer :content="probe.question"/><p>{{ t('knowledgeFirst.frozenAnswer') }}：{{ probe.answer }}</p></div>
        </div>
      </details>
      <details><summary>{{ t('knowledgeFirst.practiceAndTransfer') }}</summary>
        <div v-for="p in practices(skill.skill_id)" :key="p.practice_id">
          <p>{{ p.task }}</p><ol><li v-for="step in p.steps" :key="step">{{ step }}</li></ol><p>{{ p.evidence }}</p>
          <h5>{{ t('knowledgeFirst.frozenRetest') }}</h5><MarkdownRenderer :content="p.retest.question"/><p>{{ t('knowledgeFirst.frozenAnswer') }}：{{ p.retest.answer }}</p><p>{{ p.retest.rationale }}</p>
          <ul><li v-for="c in p.mastery_requirements" :key="c">{{ c }}</li></ul>
        </div>
      </details>
    </article>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
const props = defineProps<{ tree: any; pointId: string }>()
const skills = computed(() => (props.tree.skill_units || []).filter((s: any) => (s.knowledge_ids || []).includes(props.pointId)))
const criteria = (id: string) => (props.tree.mastery_criteria || []).filter((c: any) => c.skill_id === id && c.knowledge_ids.includes(props.pointId))
const mistakes = (id: string) => (props.tree.misconceptions || []).filter((m: any) => m.skill_id === id)
const diagnostics = (id: string) => (props.tree.diagnostic_sets || []).filter((d: any) => d.skill_id === id)
const practices = (id: string) => (props.tree.practice_units || []).filter((p: any) => p.skill_id === id)
</script>
<style scoped>
.capability-panel{margin-top:30px;font-size:15px}.capability-card{border:1px solid #dce2f1;border-radius:12px;padding:18px;margin-top:16px}.capability-card h4{font-size:17px;margin:0 0 12px}.candidate-note,.review-issues{background:#fff4e3;border-radius:9px;padding:14px 18px;color:#84551d;line-height:1.8}.review-issues{padding-left:30px}.review-issues strong{font-size:12px;overflow-wrap:anywhere}.capability-card details{margin:12px 0}.capability-card summary{cursor:pointer;color:#586ab0;font-weight:600;padding:9px 0}.capability-card summary:focus-visible{outline:2px solid #7087d7}.teaching-item{padding:14px 0;border-top:1px solid #e9edf5}.teaching-item p,.capability-card li{line-height:1.8}.prediction{background:#f6f7fc;padding:12px;border-radius:8px;margin:8px 0}.prediction p{margin:4px 0}.prediction small{font-size:14px;color:#707b92}.repair-text{white-space:pre-line}.capability-card h5{font-size:15px}
</style>
