<template>
  <div class="ppt-teaching-editor">
    <div v-if="readonly" class="ppt-teaching-reading">
      <PptTeachingElement v-for="element in readingElements" :key="element.element_id" :element="element" />
      <table v-if="page.teaching.expression.kind === 'comparison'">
        <thead><tr><th>{{ t('pptWorkspace.comparisonDimension') }}</th><th v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><PptTeachingElement :element="elementById(subject.label_element_id)" /></th></tr></thead>
        <tbody><tr v-for="dimension in page.teaching.expression.dimensions" :key="dimension.dimension_id"><th><PptTeachingElement :element="elementById(dimension.label_element_id)" /></th><td v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><PptTeachingElement v-for="element in cellElements(subject.subject_id, dimension.dimension_id)" :key="element.element_id" :element="element" /></td></tr></tbody>
      </table>
      <table v-else-if="page.teaching.expression.kind === 'chart'" data-testid="ppt-reading-chart">
        <thead><tr><th>{{ t('pptWorkspace.editor.chartObject') }}</th><th>{{ t('pptWorkspace.editor.chartValue') }} · <MathText :content="elementText(page.teaching.expression.unit_element_id)" /></th></tr></thead>
        <tbody><tr v-for="point in page.teaching.expression.points" :key="point.label_element_id"><th><PptTeachingElement :element="elementById(point.label_element_id)" /></th><td><PptTeachingElement :element="elementById(point.value_element_id)" /></td></tr></tbody>
      </table>
      <div v-for="edge in page.teaching.expression.relations || []" :key="edge.relation_id" class="ppt-teaching-reading__relation">
        <PptTeachingElement :element="elementById(edge.source_id)" />
        <span>{{ relationSymbol(edge.kind) }} {{ edge.label || t(`pptWorkspace.editor.relations.${edge.kind}`) }}</span>
        <PptTeachingElement :element="elementById(edge.target_id)" />
        <div v-if="edge.condition_element_ids?.length" class="ppt-teaching-reading__conditions">
          <strong>{{ t('pptWorkspace.editor.relationConditions') }}</strong>
          <PptTeachingElement v-for="id in edge.condition_element_ids" :key="id" :element="elementById(id)" />
        </div>
      </div>
    </div>
    <template v-else>
    <template v-if="section === 'layout'">
    <label v-if="compatibleLayouts.length"><span>{{ t('pptWorkspace.pageLayout') }}</span><select v-model="page.layout_id" :disabled="disabled || compatibleLayouts.length < 2" data-testid="ppt-page-layout"><option v-for="layout in compatibleLayouts" :key="layout.id" :value="layout.id">{{ t(`pptWorkspace.layoutNames.${layout.slug}`, layout.slug) }}</option></select></label>
    <label><span>{{ t('pptWorkspace.presentationMode') }}</span>
      <select :value="page.teaching.presentation?.mode || 'legacy'" :disabled="disabled" data-testid="ppt-presentation-mode" @change="setPresentationMode($event)">
        <option v-if="!page.teaching.presentation" value="legacy">{{ t('pptWorkspace.presentationLegacy') }}</option>
        <option value="complete" :disabled="hasAnswers">{{ t('pptWorkspace.presentationComplete') }}</option>
        <option value="question_answer" :disabled="!hasAnswers">{{ t('pptWorkspace.presentationQuestionAnswer') }}</option>
        <option value="key_steps">{{ t('pptWorkspace.presentationKeySteps') }}</option>
      </select>
    </label>
    <div v-if="page.teaching.presentation?.mode === 'key_steps'" class="ppt-teaching-editor__checkpoints">
      <label v-for="(state, index) in page.teaching.states" :key="state.state_id">
        <span class="ppt-teaching-editor__checkpoint"><input type="checkbox" :checked="!!checkpoint(state.state_id)" :disabled="disabled" @change="toggleCheckpoint(state.state_id)">{{ index + 1 }} · {{ state.teaching_note }}</span>
        <input v-if="checkpoint(state.state_id)" v-model="checkpoint(state.state_id).reason" :disabled="disabled" :aria-label="t('pptWorkspace.presentationStopReason')" :placeholder="t('pptWorkspace.presentationStopReason')">
      </label>
    </div>
    <p v-if="page.split_reason">{{ t('pptWorkspace.presentationSplitReason') }}：{{ page.split_reason }}</p>
    </template>
    <template v-if="section === 'content'">
    <p v-if="page.teaching.adopted_diagram">{{ t('pptWorkspace.adoptedDiagramFrozen') }}</p>
    <label v-for="element in standaloneElements" :key="element.element_id">
      <span>{{ elementLabel(element) }}</span>
      <textarea v-model="element.text" :aria-label="elementLabel(element)" :disabled="disabled || !!page.teaching.adopted_diagram" rows="2" />
    </label>
    <table v-if="page.teaching.expression.kind === 'comparison'">
      <thead><tr><th>{{ t('pptWorkspace.comparisonDimension') }}</th><th v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><input v-model="elementById(subject.label_element_id).text" :disabled="disabled" :aria-label="t('pptWorkspace.comparisonSubject')"></th></tr></thead>
      <tbody><tr v-for="dimension in page.teaching.expression.dimensions" :key="dimension.dimension_id"><th><input v-model="elementById(dimension.label_element_id).text" :disabled="disabled" :aria-label="t('pptWorkspace.comparisonDimension')"></th><td v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><textarea v-for="element in cellElements(subject.subject_id, dimension.dimension_id)" :key="element.element_id" v-model="element.text" :disabled="disabled || !!page.teaching.adopted_diagram" rows="2" :aria-label="`${elementText(subject.label_element_id)} · ${elementText(dimension.label_element_id)}`" /></td></tr></tbody>
    </table>
    <fieldset v-if="page.teaching.expression.relations?.length"><legend>{{ t('pptWorkspace.teachingRelations') }}</legend>
      <div v-for="edge in page.teaching.expression.relations" :key="edge.relation_id" class="ppt-teaching-editor__relation">
        <select v-model="edge.source_id" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationSource')"><option v-for="element in relationElements" :key="element.element_id" :value="element.element_id">{{ element.text }}</option></select>
        <span>{{ relationSymbol(edge.kind) }}</span>
        <select v-model="edge.target_id" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationTarget')"><option v-for="element in relationElements" :key="element.element_id" :value="element.element_id">{{ element.text }}</option></select>
        <input v-model="edge.label" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationMeaning')">
      </div>
    </fieldset>
    </template>
    <details v-if="section === 'layout'"><summary>{{ t('pptWorkspace.narrationDetails') }}</summary>
    <fieldset v-for="(state, index) in page.teaching.states" :key="state.state_id">
      <legend>{{ t('pptWorkspace.teachingRevealState') }} {{ index + 1 }}</legend>
      <input v-model="state.teaching_note" :disabled="disabled" :aria-label="t('pptWorkspace.teachingRevealState')">
      <label v-for="element in page.teaching.elements" :key="element.element_id" class="ppt-teaching-editor__choice"><input v-model="state.visible_element_ids" type="checkbox" :value="element.element_id" :disabled="disabled">{{ element.text }}</label>
    </fieldset>
    </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import MathText from './MathText.vue'
import PptTeachingElement from './PptTeachingElement.vue'
const props = withDefaults(defineProps<{ page: Record<string, any>; disabled: boolean; readonly?: boolean; section?: string; layouts?: Record<string, any>[] }>(), { layouts: () => [], section: 'layout' })
const compatibleLayouts = computed(() => props.layouts.filter(layout => layout.page_ids?.includes(props.page.page_id)))
const hasAnswers = computed(() => props.page.teaching.elements.some((e: any) => e.role === 'answer'))
function checkpoint(id: string) { return props.page.teaching.presentation?.checkpoints.find((c: any) => c.state_id === id) }
function setPresentationMode(event: Event) {
  const select = event.target as HTMLSelectElement
  const mode = select.value
  if (props.disabled || (mode === 'complete' && hasAnswers.value) || (mode === 'question_answer' && !hasAnswers.value)) {
    select.value = props.page.teaching.presentation?.mode || 'legacy'
    return
  }
  props.page.teaching.presentation = { schema_version: 'page_presentation_v1', mode,
    checkpoints: mode === 'key_steps' ? props.page.teaching.states.map((s: any) => ({ state_id: s.state_id, reason: '' })) : [] }
}
function toggleCheckpoint(id: string) {
  const policy = props.page.teaching.presentation
  policy.checkpoints = checkpoint(id) ? policy.checkpoints.filter((c: any) => c.state_id !== id) : [...policy.checkpoints, { state_id: id, reason: '' }]
  const order = props.page.teaching.states.map((s: any) => s.state_id)
  policy.checkpoints.sort((a: any, b: any) => order.indexOf(a.state_id) - order.indexOf(b.state_id))
}
function elementText(id: string) { return props.page.teaching.elements.find((e: any) => e.element_id === id)?.text || '' }
function elementById(id: string) { return props.page.teaching.elements.find((e: any) => e.element_id === id) }
function elementLabel(element: any) { return t(`pptWorkspace.teachingRoles.${element.role}`) }
function cellElements(subject: string, dimension: string) {
  return props.page.teaching.expression.cells.find((c: any) => c.subject_id === subject && c.dimension_id === dimension)?.element_ids.map(elementById) || []
}
const comparisonCellIds = computed(() => new Set<string>(props.page.teaching.expression.cells?.flatMap((c: any) => c.element_ids) || []))
const relationElements = computed(() => props.page.teaching.elements.filter((e: any) => props.page.teaching.expression.node_element_ids?.includes(e.element_id) || comparisonCellIds.value.has(e.element_id)))
function relationSymbol(kind: string) {
  return kind === 'equivalent' ? '＝' : ['association', 'contrasts'].includes(kind) ? '—' : '→'
}
const readingElements = computed(() => {
  const expression = props.page.teaching.expression
  let elements = standaloneElements.value
  if (expression.ordered_element_ids?.length) {
    elements = expression.ordered_element_ids.map(elementById).filter(Boolean)
  } else if (expression.kind === 'chart') {
    const chartIds = new Set([expression.unit_element_id, ...expression.points.flatMap((point: any) => [point.label_element_id, point.value_element_id])])
    elements = elements.filter((element: any) => !chartIds.has(element.element_id))
  }
  return elements.filter((element: any) => element.text !== props.page.title || !['text', undefined].includes(element.kind))
})
const standaloneElements = computed(() => props.page.teaching.expression.kind === 'comparison'
  ? props.page.teaching.elements.filter((e: any) => !e.subject_id && !e.dimension_id)
  : props.page.teaching.elements)
</script>

<style scoped>
.ppt-teaching-reading{font-size:17px;line-height:1.9}.ppt-teaching-reading :deep(p){margin:0 0 16px}.ppt-teaching-reading__relation{display:flex;flex-wrap:wrap;gap:10px}.ppt-teaching-reading__conditions{flex-basis:100%}.ppt-teaching-reading__conditions strong{font-size:15px}.ppt-teaching-reading table{font-size:16px}.ppt-teaching-reading th{font-weight:650;background:#f7f8fb}

.ppt-teaching-editor{font-size:16px;line-height:1.6}.ppt-teaching-editor label{display:flex;flex-direction:column;gap:6px;margin:14px 0}.ppt-teaching-editor textarea,.ppt-teaching-editor input:not([type=checkbox]),.ppt-teaching-editor select{font:inherit;padding:8px;border:1px solid #cdd3df;border-radius:5px;background:#fff;width:100%;color:#172033}.ppt-teaching-editor :is(textarea,input,select):focus-visible{outline:2px solid #3857d6;outline-offset:2px}.ppt-teaching-editor table{border-collapse:collapse;width:100%;margin:18px 0}.ppt-teaching-editor td,.ppt-teaching-editor th{padding:10px;border-bottom:1px solid #e1e5ec;text-align:left}.ppt-teaching-editor fieldset{border:0;border-top:1px solid #e1e5ec;padding:16px 0;margin:18px 0}.ppt-teaching-editor legend{font-weight:650}.ppt-teaching-editor__relation{display:grid;grid-template-columns:1fr 24px 1fr 1fr;gap:8px;align-items:center;margin:10px 0}.ppt-teaching-editor label.ppt-teaching-editor__choice{flex-direction:row;align-items:flex-start;gap:9px}.ppt-teaching-editor__choice input{margin-top:7px}.ppt-teaching-editor__checkpoint{display:flex;align-items:baseline;gap:10px}.ppt-teaching-editor input[type=checkbox]{width:auto}.ppt-teaching-editor details{margin-top:18px}.ppt-teaching-editor summary{cursor:pointer}.ppt-teaching-editor :deep(.ppt-scene){margin:14px 0;border:1px solid #e1e5ec}
</style>
