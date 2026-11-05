<template>
  <section class="handout-knowledge" :aria-label="c('concepts')">
    <ReadingAidToolbar v-model:scope="scope" v-model:query="query" :placeholder="c('mapSearch')" />
    <div class="reading-aid-results">
      <template v-if="scope === 'all'">
        <button v-if="focused" class="map-reset" @click="focused = ''">← {{ c('mapOverview') }}</button>
        <div v-else class="map-overview">
          <section v-for="section in matches" :key="section.id" class="map-lecture">
            <h3><MathText :content="section.title" /></h3>
            <button v-for="node in section.nodes" :key="node.id" @click="focused = node.id"><MathText :content="node.name" /><span aria-hidden="true"> ↗</span></button>
          </section>
        </div>
      </template>
      <HandoutConceptMap v-if="graph?.nodes.length" :key="`${scope}:${graph.id}`" :sections="[graph]" :navigate="navigate" :origin-label="c('conceptOrigin')" embedded />
      <p v-else-if="scope === 'current' || !matches.length" class="map-empty">{{ c(query.trim() ? 'referenceNoMatches' : 'mapEmpty') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import ReadingAidToolbar from './ReadingAidToolbar.vue'
import { computed, ref, watch } from 'vue'
import HandoutConceptMap from './HandoutConceptMap.vue'
import MathText from './MathText.vue'
import { studyCopy as c } from '../shared/study-copy'
import { conceptNeighborhood, type HandoutConceptSection } from '../utils/handout-concepts'
const props = defineProps<{ sections: HandoutConceptSection[]; currentSection: string; navigate: (anchor: string) => void }>()
const scope = ref<'current' | 'all'>('current'), query = ref(''), focused = ref('')
const matches = computed(() => props.sections.map(s => ({ ...s, nodes: s.nodes.filter(n => !n.external && `${s.title} ${n.name} ${n.statement}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())) })).filter(s => s.nodes.length))
const graph = computed(() => {
  if (scope.value === 'all') return focused.value ? conceptNeighborhood(props.sections, new Set([focused.value]), c('mapNeighborhood')) : undefined
  const current = props.sections.find(s => s.id === (props.currentSection || props.sections[0]?.id))
  if (!current || !query.value.trim()) return current
  const ids = new Set(current.nodes.filter(n => `${n.name} ${n.statement}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())).map(n => n.id))
  return conceptNeighborhood([current], ids, current.title)
})
watch([query, scope], () => { focused.value = '' })
</script>

<style scoped>
@import '../styles/reading-aids.css';
.handout-knowledge { display:flex; flex-direction:column; flex:1; min-width:0; min-height:0; }.handout-knowledge .reading-aid-results { padding:0 0 24px; }
.map-overview { padding:4px 16px; }.map-lecture { padding:12px 0 16px; border-bottom:1px solid #e6e1ec; }.map-lecture h3 { margin:0 0 10px; font-size:15px; font-weight:650; }.map-lecture button { display:inline-block; max-width:100%; padding:7px 10px; margin:0 6px 7px 0; border:1px solid #ded4ea; border-radius:6px; color:#644884; background:#fff; cursor:pointer; font:inherit; font-size:14px; text-align:left; overflow-wrap:anywhere; }.map-reset { border:0; padding:12px 16px; color:#72558e; background:transparent; cursor:pointer; font:inherit; font-size:14px; }.map-empty { margin:16px; }
.handout-knowledge :deep(.handout-concept-map) { border:0; background:transparent; }
@media(max-width:760px) { .map-lecture button,.map-reset { min-height:44px; } }
</style>
