<template>
  <div class="ppt-teaching-editor">
    <p>{{ t('pptWorkspace.teachingPhysicalPages') }}：{{ page.resolved_scenes?.length || 0 }}</p>
    <p v-if="page.teaching.adopted_diagram">{{ t('pptWorkspace.adoptedDiagramFrozen') }}</p>
    <label v-for="element in standaloneElements" :key="element.element_id">
      <span>{{ elementLabel(element) }}</span>
      <textarea v-model="element.text" :disabled="disabled || !!page.teaching.adopted_diagram" rows="2" />
    </label>
    <table v-if="page.teaching.expression.kind === 'comparison'">
      <thead><tr><th>{{ t('pptWorkspace.comparisonDimension') }}</th><th v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><input v-model="elementById(subject.label_element_id).text" :disabled="disabled" :aria-label="t('pptWorkspace.comparisonSubject')"></th></tr></thead>
      <tbody><tr v-for="dimension in page.teaching.expression.dimensions" :key="dimension.dimension_id"><th><input v-model="elementById(dimension.label_element_id).text" :disabled="disabled" :aria-label="t('pptWorkspace.comparisonDimension')"></th><td v-for="subject in page.teaching.expression.subjects" :key="subject.subject_id"><textarea v-for="element in cellElements(subject.subject_id, dimension.dimension_id)" :key="element.element_id" v-model="element.text" :disabled="disabled || !!page.teaching.adopted_diagram" rows="2" :aria-label="`${elementText(subject.label_element_id)} · ${elementText(dimension.label_element_id)}`" /></td></tr></tbody>
    </table>
    <fieldset v-if="page.teaching.expression.relations?.length"><legend>{{ t('pptWorkspace.teachingRelations') }}</legend>
      <div v-for="edge in page.teaching.expression.relations" :key="edge.relation_id" class="ppt-teaching-editor__relation">
        <select v-model="edge.source_id" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationSource')"><option v-for="element in relationElements" :key="element.element_id" :value="element.element_id">{{ element.text }}</option></select>
        <span>→</span>
        <select v-model="edge.target_id" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationTarget')"><option v-for="element in relationElements" :key="element.element_id" :value="element.element_id">{{ element.text }}</option></select>
        <input v-model="edge.label" :disabled="disabled || !!page.teaching.adopted_diagram" :aria-label="t('pptWorkspace.relationMeaning')">
      </div>
    </fieldset>
    <fieldset v-for="(state, index) in page.teaching.states" :key="state.state_id">
      <legend>{{ t('pptWorkspace.teachingRevealState') }} {{ index + 1 }}</legend>
      <input v-model="state.teaching_note" :disabled="disabled" :aria-label="t('pptWorkspace.teachingRevealState')">
      <label v-for="element in page.teaching.elements" :key="element.element_id" class="ppt-teaching-editor__choice"><input v-model="state.visible_element_ids" type="checkbox" :value="element.element_id" :disabled="disabled">{{ element.text }}</label>
    </fieldset>
    <details><summary>{{ t('pptWorkspace.savedPagePreview') }}</summary><PptSceneCanvas v-for="scene in page.resolved_scenes" :key="scene.state_id" :scene="scene" /></details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import PptSceneCanvas from './PptSceneCanvas.vue'
const props = defineProps<{ page: Record<string, any>; disabled: boolean }>()
function elementText(id: string) { return props.page.teaching.elements.find((e: any) => e.element_id === id)?.text || '' }
function elementById(id: string) { return props.page.teaching.elements.find((e: any) => e.element_id === id) }
function elementLabel(element: any) { return t(`pptWorkspace.teachingRoles.${element.role}`) }
function cellElements(subject: string, dimension: string) {
  return props.page.teaching.expression.cells.find((c: any) => c.subject_id === subject && c.dimension_id === dimension)?.element_ids.map(elementById) || []
}
const comparisonCellIds = computed(() => new Set<string>(props.page.teaching.expression.cells?.flatMap((c: any) => c.element_ids) || []))
const relationElements = computed(() => props.page.teaching.elements.filter((e: any) => props.page.teaching.expression.node_element_ids?.includes(e.element_id) || comparisonCellIds.value.has(e.element_id)))
const standaloneElements = computed(() => props.page.teaching.expression.kind === 'comparison'
  ? props.page.teaching.elements.filter((e: any) => !e.subject_id && !e.dimension_id)
  : props.page.teaching.elements)
</script>

<style scoped>
.ppt-teaching-editor{font-size:16px;line-height:1.6}.ppt-teaching-editor label{display:flex;flex-direction:column;gap:6px;margin:14px 0}.ppt-teaching-editor textarea,.ppt-teaching-editor input:not([type=checkbox]),.ppt-teaching-editor select{font:inherit;padding:8px;border:1px solid #cdd3df;border-radius:5px;background:#fff;width:100%;color:#172033}.ppt-teaching-editor :is(textarea,input,select):focus-visible{outline:2px solid #3857d6;outline-offset:2px}.ppt-teaching-editor table{border-collapse:collapse;width:100%;margin:18px 0}.ppt-teaching-editor td,.ppt-teaching-editor th{padding:10px;border-bottom:1px solid #e1e5ec;text-align:left}.ppt-teaching-editor fieldset{border:0;border-top:1px solid #e1e5ec;padding:16px 0;margin:18px 0}.ppt-teaching-editor legend{font-weight:650}.ppt-teaching-editor__relation{display:grid;grid-template-columns:1fr 24px 1fr 1fr;gap:8px;align-items:center;margin:10px 0}.ppt-teaching-editor label.ppt-teaching-editor__choice{flex-direction:row;align-items:flex-start;gap:9px}.ppt-teaching-editor__choice input{margin-top:7px}.ppt-teaching-editor details{margin-top:18px}.ppt-teaching-editor summary{cursor:pointer}.ppt-teaching-editor :deep(.ppt-scene){margin:14px 0;border:1px solid #e1e5ec}
</style>
