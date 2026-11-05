<template>
  <section class="handout-paths" :aria-label="c('paths')">
    <ReadingAidToolbar v-model:scope="scope" v-model:query="query" :placeholder="c('pathSearch')" />
    <div class="reading-aid-results">
      <section v-for="section in visible" :key="section.id" class="path-section">
        <h3><MathText :content="section.title" /></h3>
        <p v-if="section.state !== 'ready'" role="status">{{ c(section.state === 'stale' ? 'readingStale' : 'pathsMissing') }}</p>
        <article v-for="path in section.paths" :key="path.id" class="learning-path">
          <h4><span>{{ c(path.kind === 'derivation' ? 'pathDerivation' : path.kind === 'method' ? 'referenceMethod' : 'pathExample') }}</span><MathText :content="path.title" /></h4>
          <HandoutPathDiagram :path="path" :selected="selected[path.id] || ''" @select="selected[path.id] = selected[path.id] === $event ? '' : $event" />
          <div v-if="selectedStep(path)" class="path-detail">
            <MathText v-if="selectedStep(path)?.reason" tag="p" class="path-reason" :content="selectedStep(path)!.reason" />
            <div class="path-sources"><button v-for="source in selectedStep(path)!.sources" :key="source.blockId" @click="emit('jump', source.blockId)"><MathText :content="source.title" /><span aria-hidden="true"> ↗</span><span class="sr-only">{{ c('referenceJump') }}</span></button></div>
          </div>
        </article>
        <p v-if="section.state === 'ready' && !section.paths.length">{{ c(query.trim() ? 'referenceNoMatches' : 'pathsEmpty') }}</p>
        <details v-if="section.passages.length" class="path-passages">
          <summary>{{ c('pathPassages') }}</summary>
          <button v-for="passage in section.passages" :key="passage.blockId" @click="emit('jump', passage.blockId)"><MathText :content="passage.title" /> ↗</button>
        </details>
      </section>
      <p v-if="!visible.length">{{ c('referenceNoMatches') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import ReadingAidToolbar from './ReadingAidToolbar.vue'
import { computed, ref } from 'vue'
import MathText from './MathText.vue'
import HandoutPathDiagram from './HandoutPathDiagram.vue'
import { studyCopy as c } from '../shared/study-copy'
import { type LearningPath, type LearningPathSection } from '../utils/handout-paths'
const props = defineProps<{ sections: LearningPathSection[]; currentSection: string }>()
const emit = defineEmits<{ jump: [blockId: string] }>()
const scope = ref<'current' | 'all'>('current'), query = ref('')
const selected = ref<Record<string, string>>({})
const selectedStep = (path: LearningPath) => path.steps.find(step => step.id === selected.value[path.id])
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return props.sections.filter(s => scope.value === 'all' || s.id === (props.currentSection || props.sections[0]?.id))
    .map(s => ({ ...s, paths: s.paths.filter(p => !needle || [s.title, p.title, ...p.steps.flatMap(step => [step.text, step.reason, step.condition])].join(' ').toLocaleLowerCase().includes(needle)) }))
})
</script>

<style scoped>
@import '../styles/reading-aids.css';
.handout-paths { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; }
.path-section h3 { font-size:14px; color:#4b4264; margin:12px 0; }
.learning-path { margin:0 0 24px; }.learning-path h4 { margin:12px 0; font-size:14px; }.learning-path h4>span:first-child { display:inline-block; margin-right:6px; color:#817391; font-size:12px; margin-bottom:4px; font-weight:500; }
.path-detail { margin:12px 0; padding:10px 12px; border:1px solid #e3dceb; border-radius:7px; background:#fff; font-size:14px; }
.path-reason { margin:0 0 6px; line-height:1.65; }
.path-sources button,.path-passages button { display:block; border:0; background:transparent; padding:6px 0; text-align:left; color:#705492; cursor:pointer; font:inherit; font-size:13px; line-height:1.6; }
.path-passages { border-top:1px solid #e5e0eb; padding-top:10px; font-size:13px; }
.path-passages summary { cursor:pointer; color:#6e6480; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
</style>
