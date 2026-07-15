<template>
  <li v-if="visible" class="navigator-node">
    <button
      type="button"
      :class="['node-button', `level-${node.node_level}`, { active: activeId === node.node_id }]"
      :style="{ '--node-depth': String(depth) }"
      @click="emit('select', node)"
    >
      <ChevronRight v-if="hasChildren" :size="13" :class="{ open: expanded }" @click.stop="expanded = !expanded" />
      <span v-else class="node-spacer"></span>
      <span v-if="isChapter" class="node-kind chapter-kind"><BookOpenText :size="14" /></span>
      <span v-else class="node-kind leaf-kind" :class="[{ active: activeId === node.node_id, learned: isLearned }, generationState]"></span>
      <span class="node-label">{{ node.node_name }}</span>
      <component v-if="isGenerationPreview && generationIcon" :is="generationIcon" :size="13" class="status generation" :class="[generationState, { spinning: generationState === 'generating' }]" />
      <CheckCircle2 v-else-if="progress?.mastery_status === 'mastered'" :size="13" class="status mastered" />
      <CircleDot v-else-if="activeId === node.node_id" :size="13" class="status current" />
      <span v-else-if="progress?.reading_status === 'learned'" class="read-dot"></span>
    </button>
    <ul v-if="hasChildren && expanded">
      <CourseNavigatorNode
        v-for="child in node.children"
        :key="child.node_id"
        :node="child"
        :active-id="activeId"
        :query="query"
        :depth="depth + 1"
        @select="emit('select', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BookOpenText, CheckCircle2, ChevronRight, CircleDot, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { Node } from '../stores/types'
import { useLearningProgressStore } from '../stores/learningProgress'
import { useCourseStore } from '../stores/course'

defineOptions({ name: 'CourseNavigatorNode' })
const props = withDefaults(defineProps<{ node: Node; activeId?: string; query?: string; depth?: number }>(), { activeId: '', query: '', depth: 0 })
const emit = defineEmits<{ (event: 'select', node: Node): void }>()
const progressStore = useLearningProgressStore()
const courseStore = useCourseStore()
const expanded = ref(props.depth < 2)
const hasChildren = computed(() => Boolean(props.node.children?.length))
const progress = computed(() => progressStore.nodeProgress(props.node.node_id))
const isChapter = computed(() => props.depth === 0 || props.node.node_level === 1)
const isLearned = computed(() => progress.value?.reading_status === 'learned' || progress.value?.mastery_status === 'mastered')
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const generationState = computed(() => {
  if (!isGenerationPreview.value) return ''
  const status = String(props.node.generation_status || '')
  if (status === 'generating') return 'generating'
  if (status === 'completed' || props.node.content_state === 'finalized') return 'finalized'
  if (status === 'error' || props.node.content_state === 'failed') return 'failed'
  if (props.node.content_state === 'draft' || Boolean(props.node.node_content)) return 'draft'
  return 'waiting'
})
const generationIcon = computed(() => {
  if (generationState.value === 'generating') return LoaderCircle
  if (generationState.value === 'finalized') return CheckCircle2
  if (generationState.value === 'failed') return TriangleAlert
  return null
})
const normalizedQuery = computed(() => props.query.trim().toLocaleLowerCase())
const visible = computed(() => {
  if (!normalizedQuery.value) return true
  if (props.node.node_name.toLocaleLowerCase().includes(normalizedQuery.value)) return true
  return props.node.children?.some(child => child.node_name.toLocaleLowerCase().includes(normalizedQuery.value)) || false
})
watch(normalizedQuery, value => { if (value) expanded.value = true })
</script>

<style scoped>
.navigator-node, .navigator-node ul { margin: 0; padding: 0; list-style: none; }
.navigator-node ul { position:relative; margin:1px 0 4px 19px; padding:1px 0 2px 12px; border-left:1px dashed rgba(167,180,214,.72); transition:border-color .18s ease; }
.navigator-node ul:hover { border-left-color:rgba(139,92,246,.52); }
.navigator-node ul::before { content:""; position:absolute; top:0; left:-1px; width:8px; height:1px; background:rgba(165,180,252,.48); }
.node-button { position:relative; width:100%; min-height:38px; display:grid; grid-template-columns:13px 24px minmax(0,1fr) auto; align-items:center; gap:7px; overflow:hidden; padding:5px 8px; border:1px solid transparent; border-radius:11px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease,box-shadow .16s ease; }
.node-button::before { content:""; position:absolute; left:0; top:50%; width:3px; height:0; border-radius:0 4px 4px 0; background:linear-gradient(180deg,#818cf8,#7c3aed); transform:translateY(-50%); transition:height .18s ease; }
.node-button:hover { transform:translateX(1px); color:var(--lz-text-strong); background:rgba(255,255,255,.7); }
.node-button.active { border-color:rgba(255,255,255,.9); color:var(--lz-brand-strong); background:linear-gradient(90deg,rgba(255,255,255,.96),rgba(238,242,255,.84)); box-shadow:0 7px 18px rgba(99,102,241,.11),inset 0 1px 0 #fff; font-weight:700; }
.node-button.active::before { height:28px; }
.node-button.level-1 { min-height:42px; margin-top:6px; color:var(--lz-text-strong); font-weight:750; }
.node-button.level-2 { font-weight: 600; }
.node-button > svg:first-child { color:var(--lz-text-muted); transition:transform .16s ease,color .16s ease; }
.node-button > svg:first-child.open { color:#7c3aed; transform:rotate(90deg); }
.node-spacer { width: 13px; }
.node-kind { width:24px; height:24px; display:grid; place-items:center; }
.chapter-kind { border:1px solid rgba(224,231,255,.88); border-radius:8px; color:#6366f1; background:linear-gradient(135deg,#eef2ff,#faf5ff); box-shadow:0 3px 8px rgba(99,102,241,.08); }
.leaf-kind { width:8px; height:8px; margin-left:8px; border:1.5px solid #cbd5e1; border-radius:50%; background:#fff; }
.leaf-kind.learned { border-color:#34d399; background:#d1fae5; }
.leaf-kind.active { border-color:#6366f1; background:#818cf8; box-shadow:0 0 0 3px rgba(129,140,248,.13); }
.leaf-kind.generating { border-color:#6366f1; background:#c7d2fe; }
.leaf-kind.finalized { border-color:#10b981; background:#a7f3d0; }
.leaf-kind.draft { border-color:#8b5cf6; background:#ddd6fe; }
.leaf-kind.failed { border-color:#ef4444; background:#fecaca; }
.node-label { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; letter-spacing:0; }
.status { flex: 0 0 auto; }
.status.mastered { color: var(--lz-success); }
.status.current { color: var(--lz-brand); }
.status.generation.generating { color:#4f46e5; }
.status.generation.finalized { color:#059669; }
.status.generation.failed { color:#dc2626; }
.status.spinning { animation:navigator-generation-spin .9s linear infinite; }
.read-dot { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; }
@keyframes navigator-generation-spin { to { transform:rotate(360deg); } }
</style>
