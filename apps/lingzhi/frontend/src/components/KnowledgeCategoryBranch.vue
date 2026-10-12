<template>
  <details class="knowledge-branch" open>
    <summary>{{ category.name }} <small>{{ pointCount }}</small></summary>
    <div class="branch-children">
      <KnowledgeCategoryBranch v-for="child in children" :key="child.id" :category="child" :categories="categories" :points="points" :selected-id="selectedId" :ancestors="[...ancestors, category.id]" @select="emit('select', $event)" />
      <button v-for="point in leaves" :key="point.knowledge_id" type="button" :class="{ selected: point.knowledge_id === selectedId }" :aria-pressed="point.knowledge_id === selectedId" @click="emit('select', point.knowledge_id)"><span aria-hidden="true" />{{ point.name }}</button>
    </div>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
type Category = { id: string; name: string; parent_id?: string | null }
type Point = { knowledge_id: string; name: string; parent_id: string }
const props = withDefaults(defineProps<{ category: Category; categories: Category[]; points: Point[]; selectedId: string; ancestors?: string[] }>(), { ancestors: () => [] })
const emit = defineEmits<{ (e: 'select', id: string): void }>()
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
</style>
