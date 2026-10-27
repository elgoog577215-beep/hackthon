<template>
  <section class="teaching-structures" data-testid="knowledge-teaching-structures">
    <p class="design-note">{{ t('knowledgeTeaching.draftHint') }}</p>
    <p v-if="coverage?.status === 'needs_core_review'" class="review-note">{{ t('knowledgeTeaching.coreReview') }} <MarkdownRenderer :content="coverage.note" /></p>
    <div role="tablist" :aria-label="t('knowledgeDetailLayout.sections')" class="teaching-tabs">
      <button v-for="(item,index) in sections" :key="item.key" role="tab" :id="`${uid}-${item.key}`" :aria-controls="`${uid}-panel`" :aria-selected="active === item.key" :tabindex="active === item.key ? 0 : -1" @click="active = item.key" @keydown="tabKey($event,index)">{{ t(item.label) }} <span>{{ item.count }}</span></button>
    </div>
    <div role="tabpanel" :id="`${uid}-panel`" :aria-labelledby="`${uid}-${active}`">
    <section v-if="active === 'checks'">
    <p v-if="!criteria.length">{{ t('knowledgeTeaching.noChecks') }}</p>
    <details :name="uid" v-for="criterion in criteria" :key="criterion.criterion_id" data-testid="structured-criterion" @toggle="criterionToggle($event,criterion.criterion_id)">
      <summary><MathText :content="criterion.name" /><span v-if="criterion.review_notes?.length || criterion.readiness && criterion.readiness !== 'ready'" class="pending">{{ t('knowledgeDetailLayout.pending') }}</span></summary>
      <div class="record-body">
      <div v-if="criterion.review_notes?.length" class="review-note"><strong>{{ t('knowledgeTeaching.reviewContent') }}</strong><p v-for="note in criterion.review_notes" :key="note"><MarkdownRenderer :content="note" /></p></div>
      <span class="kind">{{ t(`knowledgeTeaching.dimensions.${criterion.dimension}`) }}</span>
      <MarkdownRenderer :content="criterion.observable_performance" />
      <h5>{{ t('knowledgeTeaching.method') }}</h5><MarkdownRenderer :content="criterion.verification_method" />
      <p>{{ t('unifiedGeneration.formLabel') }} · {{ t(criterion.assessment_format === 'single_choice' ? 'unifiedGeneration.formChoice' : criterion.assessment_format === 'numeric_response' ? 'unifiedGeneration.formNumeric' : 'unifiedGeneration.formShort') }}</p>
      <template v-if="criterion.controlled_conditions?.length"><h5>{{ t('knowledgeTeaching.controls') }}</h5><ul><li v-for="value in criterion.controlled_conditions" :key="value"><MarkdownRenderer :content="value" /></li></ul></template>
      <h5>{{ t('knowledgeTeaching.checkpoints') }}</h5>
      <ol><li v-for="item in criterion.checkpoints" :key="item.checkpoint_id"><MathText tag="strong" :content="item.label" /><MarkdownRenderer :content="item.pass_condition" /></li></ol>
      <CriterionQuestionSupply v-if="openCriterion === criterion.criterion_id && courseId && canGenerate && criterion.readiness === 'ready'" :course-id="courseId" :knowledge-id="knowledgeId" :knowledge-revision="point.revision_id" :criterion-id="criterion.criterion_id" :criterion-revision="criterion.revision_id" />
      <p v-else-if="courseId && !canGenerate" class="unknown">{{ t('criterionSupply.adoptFirst') }}</p>
      <p class="rule">{{ format('scoreRule', { count: criterion.scoring.max_score }) }}</p>

      <p v-if="criterion.readiness !== 'ready'" class="review-note">{{ t('knowledgeTeaching.notReady') }}</p>

      </div>
    </details>
    </section>
    <section v-else-if="active === 'mistakes'">
    <p v-if="!mistakes.length">{{ coverage?.no_mistakes || t('knowledgeTeaching.noMistakes') }}</p>
    <details :name="uid" v-for="mistake in mistakes" :key="mistake.misconception_id" data-testid="structured-mistake">
      <summary><MathText :content="mistake.name" /><span v-if="mistake.review_notes?.length || mistake.readiness && mistake.readiness !== 'ready'" class="pending">{{ t('knowledgeDetailLayout.pending') }}</span></summary>
      <div class="record-body">
      <div v-if="mistake.review_notes?.length" class="review-note"><strong>{{ t('knowledgeTeaching.reviewContent') }}</strong><p v-for="note in mistake.review_notes" :key="note"><MarkdownRenderer :content="note" /></p></div>
      <h5>{{ t('knowledgeTeaching.pattern') }}</h5><MarkdownRenderer :content="mistake.observable_error_pattern" />
      <h5>{{ t('knowledgeTeaching.hypothesis') }}</h5><MarkdownRenderer :content="mistake.hypothesis" />
      <ul><li v-for="reason in mistake.alternative_explanations" :key="reason"><MarkdownRenderer :content="reason" /></li></ul>
      <h5>{{ t('knowledgeTeaching.discrimination') }}</h5><MarkdownRenderer :content="mistake.discrimination" />
      <h5>{{ t('knowledgeTeaching.repair') }}</h5><MarkdownRenderer :content="mistake.repair_strategy" />
      <h5>{{ t('knowledgeTeaching.retest') }}</h5><MarkdownRenderer :content="mistake.retest" />
      <div v-if="otherKnowledge(mistake).length" class="shared"><span>{{ t('knowledgeTeaching.sharedWith') }}</span><button v-for="point in otherKnowledge(mistake)" :key="point.knowledge_id" type="button" @click="$emit('select-knowledge', point.knowledge_id)"><MathText :content="point.name" /></button></div>
      </div>
    </details>
    </section>
    <section v-else>
    <p v-if="!extensions.length">{{ coverage?.no_extensions || t('knowledgeTeaching.noExtensions') }}</p>
    <details :name="uid" v-for="extension in extensions" :key="extension.extension_id" data-testid="structured-extension">
      <summary><MathText :content="extension.name" /><span v-if="extension.review_notes?.length || extension.readiness && extension.readiness !== 'ready'" class="pending">{{ t('knowledgeDetailLayout.pending') }}</span></summary>
      <div class="record-body">
      <div v-if="extension.review_notes?.length" class="review-note"><strong>{{ t('knowledgeTeaching.reviewContent') }}</strong><p v-for="note in extension.review_notes" :key="note"><MarkdownRenderer :content="note" /></p></div><span class="kind">{{ t('knowledgeTeaching.optional') }}</span>
      <h5>{{ t('knowledgeTeaching.goal') }}</h5><MarkdownRenderer :content="extension.goal" />
      <MarkdownRenderer :content="extension.explanation" />
      <h5>{{ t('knowledgeTeaching.prerequisites') }}</h5><MathText tag="p" :content="prerequisiteNames(extension).join('、')" /><MarkdownRenderer v-if="extension.prerequisite_notes" :content="extension.prerequisite_notes" />
      <h5>{{ t('knowledgeTeaching.task') }}</h5><MarkdownRenderer :content="extension.task" />
      <h5>{{ t('knowledgeTeaching.success') }}</h5><ul><li v-for="item in extension.success_criteria" :key="item"><MarkdownRenderer :content="item" /></li></ul>
      <p v-if="!extension.resource_refs?.length" class="unknown">{{ t('knowledgeTeaching.resourcesPending') }}</p>
      </div>
    </details>
    </section>
    </div>
    <details class="evidence-policy"><summary>{{ t('knowledgeDetailLayout.policy') }}</summary>
      <p>{{ t('knowledgeDetailLayout.binaryRule') }}</p>
      <p v-if="criteria[0]">{{ format('evidenceRule', { count: criteria[0].evidence_policy.min_independent_successes, variants: criteria[0].evidence_policy.min_distinct_variants }) }}</p>
      <p>{{ t('knowledgeTeaching.noStudentScore') }}</p>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch, useId } from 'vue'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import CriterionQuestionSupply from './CriterionQuestionSupply.vue'
const uid = useId(); const active = ref('checks');const openCriterion=ref('')
function criterionToggle(event:Event,id:string){if((event.target as HTMLDetailsElement).open)openCriterion.value=id;else if(openCriterion.value===id)openCriterion.value=''}
const props = defineProps<{ tree: any; knowledgeId: string; courseId?:string; canGenerate?:boolean }>()
defineEmits<{ 'select-knowledge': [id: string] }>()
const points = computed<any[]>(() => props.tree.allKnowledgePoints || props.tree.knowledge_points || [])
const point = computed(() => points.value.find(p => p.knowledge_id === props.knowledgeId))
function bound(rows: any[]) { return (Array.isArray(rows) ? rows : []).filter(row => row.knowledge_ids?.includes(props.knowledgeId) && row.knowledge_revision_refs?.[props.knowledgeId] === point.value?.revision_id) }
const criteria = computed(() => bound(props.tree.mastery_criteria).filter(c => c.checkpoints && c.scoring && c.evidence_policy))
const mistakes = computed(() => bound(props.tree.misconceptions))
const extensions = computed(() => bound(props.tree.extensions))
const sections = computed(() => [{key:'checks',label:'knowledgeDetailLayout.checks',count:criteria.value.length},{key:'mistakes',label:'knowledgeDetailLayout.mistakes',count:mistakes.value.length},{key:'extensions',label:'knowledgeDetailLayout.extensions',count:extensions.value.length}])
watch(() => props.knowledgeId, () => { active.value = 'checks';openCriterion.value='' })
function tabKey(event:KeyboardEvent,index:number) { if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); const next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3; active.value=sections.value[next]!.key; (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus() }
const coverage = computed(() => { const value = props.tree.teaching_coverage?.[props.knowledgeId]; return value?.knowledge_revision === point.value?.revision_id ? value : null })
function otherKnowledge(row: any) { return points.value.filter(p => p.knowledge_id !== props.knowledgeId && row.knowledge_ids?.includes(p.knowledge_id) && row.knowledge_revision_refs?.[p.knowledge_id] === p.revision_id) }
function prerequisiteNames(row: any) { return points.value.filter(p => row.prerequisite_knowledge_refs?.[p.knowledge_id] === p.revision_id).map(p => p.name) }
function format(key: string, values: Record<string, number>) { return Object.entries(values).reduce((text, [name, value]) => text.split(`{${name}}`).join(String(value)), t(`knowledgeTeaching.${key}`)) }
</script>

<style scoped>
.teaching-structures { font-size: 15px; line-height: 1.65; color: #293650; }
h3 { margin: 22px 0 10px; color: #43386d; font-size: 18px; } h4 { margin: 0 0 8px; font-size: 16px; } h5 { margin: 12px 0 3px; font-size: 15px; }
details[data-testid] { margin: 10px 0 18px; padding: 14px; border: 1px solid #dedaf0; border-radius: 12px; background: #fcfbff; }
.design-note, .rule { padding: 10px 12px; border-radius: 8px; background: #f0edfc; } .review-note { padding: 10px; background: #fff5e8; color: #87552d; border-radius: 8px; }
.kind { display: inline-block; margin-bottom: 8px; color: #68549f; font-size: 15px; } .unknown { color: #6a7284; }
ul, ol { padding-left: 22px; margin: 6px 0; } li { margin: 6px 0; } p { margin: 6px 0; }
.shared { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; } .shared button { font: inherit; color: #6350a5; border: 1px solid #ddd5f4; background: white; padding: 4px 8px; border-radius: 7px; cursor: pointer; }
</style>

<style scoped>
.teaching-tabs { display:flex; gap:8px; margin:24px 0 16px; border-bottom:1px solid #e6e1f0; }
.teaching-tabs button { flex:1; padding:12px 8px; border:0; border-radius:8px 8px 0 0; background:transparent; color:#716881; font:inherit; cursor:pointer; }
.teaching-tabs button[aria-selected=true] { background:#f0edfc; color:#58449c; box-shadow:inset 0 -2px #8470ce; }
.teaching-tabs span { margin-left:6px; font-variant-numeric:tabular-nums; }
details[data-testid] { padding:0; background:#fff; overflow:hidden; }
details[data-testid]>summary { cursor:pointer; padding:16px 18px; font-weight:600; line-height:1.6; }
.record-body { padding:0 20px 20px; border-top:1px solid #ece8f3; }
.record-body> :first-child { margin-top:16px; }
.pending { display:inline-block; margin-left:10px; padding:2px 7px; border-radius:5px; font-size:13px; background:#fff3dd; color:#825626; }
.evidence-policy { margin-top:24px; padding-top:14px; border-top:1px solid #e8e3f1; color:#777082; font-size:15px; }
.evidence-policy>summary { cursor:pointer; }
button:focus-visible, summary:focus-visible { outline:2px solid #8973cf; outline-offset:3px; }
</style>
