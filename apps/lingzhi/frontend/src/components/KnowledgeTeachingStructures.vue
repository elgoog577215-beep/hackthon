<template>
  <section class="teaching-structures" data-testid="knowledge-teaching-structures">
    <p class="design-note">{{ t('knowledgeTeaching.draftHint') }}</p>
    <p v-if="coverage?.status === 'needs_core_review'" class="review-note">{{ t('knowledgeTeaching.coreReview') }} <MarkdownRenderer :content="coverage.note" /></p>
    <h3>{{ t('knowledgeTeaching.checks') }}</h3>
    <p v-if="!criteria.length">{{ t('knowledgeTeaching.noChecks') }}</p>
    <article v-for="criterion in criteria" :key="criterion.criterion_id" data-testid="structured-criterion">
      <h4>{{ criterion.name }}</h4>
      <span class="kind">{{ t(`knowledgeTeaching.dimensions.${criterion.dimension}`) }}</span>
      <MarkdownRenderer :content="criterion.observable_performance" />
      <h5>{{ t('knowledgeTeaching.method') }}</h5><MarkdownRenderer :content="criterion.verification_method" />
      <template v-if="criterion.controlled_conditions?.length"><h5>{{ t('knowledgeTeaching.controls') }}</h5><ul><li v-for="value in criterion.controlled_conditions" :key="value"><MarkdownRenderer :content="value" /></li></ul></template>
      <h5>{{ t('knowledgeTeaching.checkpoints') }}</h5>
      <ol><li v-for="item in criterion.checkpoints" :key="item.checkpoint_id"><strong>{{ item.label }}</strong><MarkdownRenderer :content="item.pass_condition" /></li></ol>
      <p class="rule">{{ format('scoreRule', { count: criterion.scoring.max_score }) }}</p>
      <p>{{ format('evidenceRule', { count: criterion.evidence_policy.min_independent_successes, variants: criterion.evidence_policy.min_distinct_variants }) }}</p>
      <p v-if="criterion.readiness !== 'ready'" class="review-note">{{ t('knowledgeTeaching.notReady') }}</p>
      <p class="unknown">{{ t('knowledgeTeaching.noStudentScore') }}</p>
    </article>
    <h3>{{ t('knowledgeTeaching.mistakes') }}</h3>
    <p v-if="!mistakes.length">{{ coverage?.no_mistakes || t('knowledgeTeaching.noMistakes') }}</p>
    <article v-for="mistake in mistakes" :key="mistake.misconception_id" data-testid="structured-mistake">
      <h4>{{ mistake.name }}</h4>
      <h5>{{ t('knowledgeTeaching.pattern') }}</h5><MarkdownRenderer :content="mistake.observable_error_pattern" />
      <h5>{{ t('knowledgeTeaching.hypothesis') }}</h5><MarkdownRenderer :content="mistake.hypothesis" />
      <ul><li v-for="reason in mistake.alternative_explanations" :key="reason"><MarkdownRenderer :content="reason" /></li></ul>
      <h5>{{ t('knowledgeTeaching.discrimination') }}</h5><MarkdownRenderer :content="mistake.discrimination" />
      <h5>{{ t('knowledgeTeaching.repair') }}</h5><MarkdownRenderer :content="mistake.repair_strategy" />
      <h5>{{ t('knowledgeTeaching.retest') }}</h5><MarkdownRenderer :content="mistake.retest" />
      <div v-if="otherKnowledge(mistake).length" class="shared"><span>{{ t('knowledgeTeaching.sharedWith') }}</span><button v-for="point in otherKnowledge(mistake)" :key="point.knowledge_id" type="button" @click="$emit('select-knowledge', point.knowledge_id)">{{ point.name }}</button></div>
    </article>
    <h3>{{ t('knowledgeTeaching.extensions') }}</h3>
    <p v-if="!extensions.length">{{ coverage?.no_extensions || t('knowledgeTeaching.noExtensions') }}</p>
    <article v-for="extension in extensions" :key="extension.extension_id" data-testid="structured-extension">
      <h4>{{ extension.name }}</h4><span class="kind">{{ t('knowledgeTeaching.optional') }}</span>
      <h5>{{ t('knowledgeTeaching.goal') }}</h5><MarkdownRenderer :content="extension.goal" />
      <MarkdownRenderer :content="extension.explanation" />
      <h5>{{ t('knowledgeTeaching.prerequisites') }}</h5><p>{{ prerequisiteNames(extension).join('、') }}</p><MarkdownRenderer v-if="extension.prerequisite_notes" :content="extension.prerequisite_notes" />
      <h5>{{ t('knowledgeTeaching.task') }}</h5><MarkdownRenderer :content="extension.task" />
      <h5>{{ t('knowledgeTeaching.success') }}</h5><ul><li v-for="item in extension.success_criteria" :key="item"><MarkdownRenderer :content="item" /></li></ul>
      <p v-if="!extension.resource_refs?.length" class="unknown">{{ t('knowledgeTeaching.resourcesPending') }}</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
const props = defineProps<{ tree: any; knowledgeId: string }>()
defineEmits<{ 'select-knowledge': [id: string] }>()
const points = computed<any[]>(() => props.tree.allKnowledgePoints || props.tree.knowledge_points || [])
const point = computed(() => points.value.find(p => p.knowledge_id === props.knowledgeId))
function bound(rows: any[]) { return (Array.isArray(rows) ? rows : []).filter(row => row.knowledge_ids?.includes(props.knowledgeId) && row.knowledge_revision_refs?.[props.knowledgeId] === point.value?.revision_id) }
const criteria = computed(() => bound(props.tree.mastery_criteria).filter(c => c.checkpoints && c.scoring && c.evidence_policy))
const mistakes = computed(() => bound(props.tree.misconceptions))
const extensions = computed(() => bound(props.tree.extensions))
const coverage = computed(() => { const value = props.tree.teaching_coverage?.[props.knowledgeId]; return value?.knowledge_revision === point.value?.revision_id ? value : null })
function otherKnowledge(row: any) { return points.value.filter(p => p.knowledge_id !== props.knowledgeId && row.knowledge_ids?.includes(p.knowledge_id) && row.knowledge_revision_refs?.[p.knowledge_id] === p.revision_id) }
function prerequisiteNames(row: any) { return points.value.filter(p => row.prerequisite_knowledge_refs?.[p.knowledge_id] === p.revision_id).map(p => p.name) }
function format(key: string, values: Record<string, number>) { return Object.entries(values).reduce((text, [name, value]) => text.split(`{${name}}`).join(String(value)), t(`knowledgeTeaching.${key}`)) }
</script>

<style scoped>
.teaching-structures { font-size: 15px; line-height: 1.65; color: #293650; }
h3 { margin: 22px 0 10px; color: #43386d; font-size: 18px; } h4 { margin: 0 0 8px; font-size: 16px; } h5 { margin: 12px 0 3px; font-size: 15px; }
article { margin: 10px 0 18px; padding: 14px; border: 1px solid #dedaf0; border-radius: 12px; background: #fcfbff; }
.design-note, .rule { padding: 10px 12px; border-radius: 8px; background: #f0edfc; } .review-note { padding: 10px; background: #fff5e8; color: #87552d; border-radius: 8px; }
.kind { display: inline-block; margin-bottom: 8px; color: #68549f; font-size: 15px; } .unknown { color: #6a7284; }
ul, ol { padding-left: 22px; margin: 6px 0; } li { margin: 6px 0; } p { margin: 6px 0; }
.shared { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; } .shared button { font: inherit; color: #6350a5; border: 1px solid #ddd5f4; background: white; padding: 4px 8px; border-radius: 7px; cursor: pointer; }
</style>
