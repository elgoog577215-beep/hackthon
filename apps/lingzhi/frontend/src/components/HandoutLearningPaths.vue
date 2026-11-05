<template>
  <section class="handout-paths" :aria-label="c('paths')">
    <div class="reading-aid-controls">
      <div class="reading-aid-scope" role="group" :aria-label="c('referenceScope')">
        <button v-for="s in ['current', 'all'] as const" :key="s" :aria-pressed="scope === s" @click="scope = s">{{ c(s === 'current' ? 'referenceCurrent' : 'referenceAllCourse') }}</button>
      </div>
      <input v-model="query" type="search" :placeholder="c('pathSearch')" :aria-label="c('pathSearch')" />
    </div>
    <div class="reading-aid-results">
      <section v-for="section in visible" :key="section.id" class="path-section">
        <h3><MathText :content="section.title" /></h3>
        <p v-if="section.state !== 'ready'" role="status">{{ c(section.state === 'stale' ? 'readingStale' : 'pathsMissing') }}</p>
        <article v-for="path in section.paths" :key="path.id" class="learning-path">
          <h4><span>{{ c(path.kind === 'derivation' ? 'pathDerivation' : path.kind === 'method' ? 'referenceMethod' : 'pathExample') }}</span><MathText :content="path.title" /></h4>
          <ol class="path-tree">
            <li v-for="row in pathRows(path)" :key="row.step.id" :style="{ '--path-depth': Math.min(row.depth, 3) }" :data-stage="row.step.stage">
              <div v-if="row.step.condition" class="path-condition"><MathText :content="row.step.condition" /></div>
              <span class="path-stage">{{ c(stageLabels[row.step.stage]) }}</span>
              <MathText tag="p" :content="row.step.text" />
              <p v-if="row.step.reason" class="path-reason"><b>{{ c('pathReason') }}</b><MathText :content="row.step.reason" /></p>
              <div class="path-sources"><button v-for="source in row.step.sources" :key="source.blockId" @click="emit('jump', source.blockId)">{{ c('referenceJump') }} · <MathText :content="source.title" /><span aria-hidden="true"> ↗</span></button></div>
            </li>
          </ol>
          <p v-if="!path.steps.some(s => s.stage === 'check')" class="path-note">{{ c('pathNoCheck') }}</p>
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
import { computed, ref } from 'vue'
import MathText from './MathText.vue'
import { studyCopy as c } from '../shared/study-copy'
import { pathRows, type LearningPathSection } from '../utils/handout-paths'
const props = defineProps<{ sections: LearningPathSection[]; currentSection: string }>()
const emit = defineEmits<{ jump: [blockId: string] }>()
const scope = ref<'current' | 'all'>('current'), query = ref('')
const stageLabels = { start: 'pathStart', choice: 'pathChoice', step: 'pathStep', result: 'pathResult', check: 'pathCheck' } as const
const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return props.sections.filter(s => scope.value === 'all' || s.id === (props.currentSection || props.sections[0]?.id))
    .map(s => ({ ...s, paths: s.paths.filter(p => !needle || [s.title, p.title, ...p.steps.flatMap(step => [step.text, step.reason, step.condition])].join(' ').toLocaleLowerCase().includes(needle)) }))
})
</script>

<style scoped>
@import '../styles/reading-aids.css';
.handout-paths { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; }
.path-section h3 { font-size:16px; color:#4b4264; margin:14px 0; }
.learning-path { margin:0 0 24px; }.learning-path h4 { margin:12px 0; font-size:16px; }.learning-path h4>span:first-child { display:block; color:#817391; font-size:12px; margin-bottom:4px; font-weight:500; }
.path-tree { list-style:none; margin:0; padding:0; }.path-tree li { position:relative; margin:0 0 12px calc(var(--path-depth) * 10px); padding:12px 12px 10px 15px; border-left:2px solid #d5c9e7; background:#fff; border-radius:0 7px 7px 0; overflow-wrap:anywhere; }.path-tree li:not(:first-child)::before { content:'↓'; position:absolute; top:-16px; left:8px; color:#8d76a6; background:#fafbfe; }
.path-tree p { margin:6px 0; font-size:15px; line-height:1.75; }.path-stage { font-size:12px; color:#725991; font-weight:650; }.path-condition { font-size:14px; color:#286f78; padding:5px 8px; margin:-2px -2px 8px; background:#edf7f7; border-radius:4px; }.path-reason { color:#697287; }.path-reason b { font-weight:500; margin-right:6px; }.path-sources button,.path-passages button { border:0; background:transparent; padding:5px 0; text-align:left; color:#705492; cursor:pointer; font:inherit; font-size:13px; line-height:1.6; }.path-sources button { display:block; }.path-note { font-size:13px; color:#858091; }.path-passages { border-top:1px solid #e5e0eb; padding-top:10px; font-size:14px; }.path-passages summary { cursor:pointer; color:#6e6480; }.path-passages button { display:block; }
@media(max-width:760px) { .path-sources button,.path-passages button,.path-passages summary { min-height:44px; } .path-sources button { width:100%; } }
</style>
