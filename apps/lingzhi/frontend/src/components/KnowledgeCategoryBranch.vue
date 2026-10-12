<template>
  <details class="knowledge-branch" open>
    <summary>{{ category.name }} <small>{{ pointCount }}</small></summary>
    <div class="branch-children">
      <KnowledgeCategoryBranch v-for="child in children" :key="child.id" :category="child" :categories="categories" :points="points" :selected-id="selectedId" :ancestors="[...ancestors, category.id]" :inline-details="inlineDetails" :relations="relations" :related-points="relatedPoints" :current-lesson-id="currentLessonId" :lesson-labels="lessonLabels" @select="emit('select', $event)" @navigate-related="emit('navigate-related', $event)" />
      <template v-for="point in leaves" :key="point.knowledge_id">
        <button type="button" :data-knowledge-id="point.knowledge_id" :class="{ selected: point.knowledge_id === selectedId }" :aria-pressed="point.knowledge_id === selectedId" :aria-expanded="inlineDetails ? point.knowledge_id === selectedId : undefined" @click="emit('select', inlineDetails && point.knowledge_id === selectedId ? '' : point.knowledge_id)"><span aria-hidden="true" />{{ point.name }}</button>
        <div v-if="inlineDetails && point.knowledge_id === selectedId" class="leaf-content"><MarkdownRenderer :content="point.statement || ''" /><ul v-if="point.conditions?.length"><li v-for="condition in point.conditions" :key="condition">{{ condition }}</li></ul>
          <section v-if="crossLinks(point).length" class="cross-lesson-links"><strong>{{ t('knowledgeFirst.crossLessonLinks') }}</strong><div v-for="link in crossLinks(point)" :key="link.key"><button type="button" @click="emit('navigate-related', { lesson_id: link.lessonId, knowledge_id: link.point.knowledge_id })">{{ lessonLabels[link.lessonId] || link.lessonId }} · {{ link.point.name }} <small>{{ link.direction }} {{ t(`knowledgeFirst.relationTypes.${link.edge.type}`, link.edge.type) }}</small></button><p>{{ link.edge.reason }}</p></div></section>
        </div>
      </template>
    </div>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { t } from '../shared/i18n'
type Category = { id: string; name: string; parent_id?: string | null }
type Point = { knowledge_id: string; name: string; parent_id: string; statement?: string; conditions?: string[]; section_refs?: string[]; topic?: string }
const props = withDefaults(defineProps<{ category: Category; categories: Category[]; points: Point[]; selectedId: string; ancestors?: string[]; inlineDetails?: boolean; relations?: any[]; relatedPoints?: Point[]; currentLessonId?: string; lessonLabels?: Record<string, string> }>(), { ancestors: () => [], inlineDetails: false, relations: () => [], relatedPoints: () => [], currentLessonId: '', lessonLabels: () => ({}) })
const emit = defineEmits<{ (e: 'select', id: string): void; (e: 'navigate-related', target: { lesson_id: string; knowledge_id: string }): void }>()
function crossLinks(point: Point) {
  if (!props.currentLessonId) return []
  return props.relations.flatMap(edge => {
    const otherId = edge.source_id === point.knowledge_id ? edge.target_id : edge.target_id === point.knowledge_id ? edge.source_id : ''
    const other = props.relatedPoints.find(p => p.knowledge_id === otherId)
    if (!other) return []
    const refs = other.section_refs || [other.topic || '']
    const lessonId = refs.find(id => id && id !== props.currentLessonId)
    if (!lessonId || (!edge.cross_lesson && refs.includes(props.currentLessonId))) return []
    return [{ key: `${edge.id}:${otherId}`, point: other, lessonId, edge, direction: edge.source_id === point.knowledge_id ? '→' : '←' }]
  })
}
const children = computed(() => props.categories.filter(c => c.parent_id === props.category.id && !props.ancestors.includes(c.id) && c.id !== props.category.id))
const leaves = computed(() => props.points.filter(p => p.parent_id === props.category.id))
const pointCount = computed(() => {
  const ids = new Set([props.category.id])
  for (let i = 0; i < props.categories.length; i++) for (const c of props.categories) if (c.parent_id && ids.has(c.parent_id)) ids.add(c.id)
  return props.points.filter(p => ids.has(p.parent_id)).length
})
</script>
<style scoped>
.knowledge-branch summary{cursor:pointer;padding:11px 4px;color:#465478;font-size:15px;line-height:1.5}.knowledge-branch small{color:#909ab3;font-weight:400;margin-left:8px}.branch-children{border-left:1px solid #e2e6f1;margin-left:6px;padding-left:12px}.branch-children button{display:flex;align-items:center;gap:9px;text-align:left;width:100%;border:0;border-radius:7px;background:transparent;color:#465478;font:inherit;font-size:15px;padding:9px 8px;line-height:1.6;cursor:pointer}.branch-children button span{width:5px;height:5px;border-radius:50%;background:#a0abdb;flex:none}.branch-children button:hover{background:#f5f6fc}.branch-children button.selected{background:#edf0ff;color:#4c5baf}.knowledge-branch summary:focus-visible,.branch-children button:focus-visible{outline:2px solid #5968c4;outline-offset:2px}
.leaf-content{max-width:900px;margin:4px 8px 14px;padding:12px 18px;border-left:2px solid #b7bde3;background:#f8f9fe;border-radius:0 6px 6px 0;color:#53607b;font-size:15px;line-height:1.8}.leaf-content ul{padding-left:20px;margin-bottom:0}
.cross-lesson-links{border-top:1px solid #e5e7f3;margin-top:14px;padding-top:12px}.cross-lesson-links button{color:#5d58a3;padding:8px 0;flex-wrap:wrap}.cross-lesson-links small{font-size:13px;color:#9298ac}.cross-lesson-links p{margin:0 0 8px;color:#8590a4;font-size:14px}
</style>
