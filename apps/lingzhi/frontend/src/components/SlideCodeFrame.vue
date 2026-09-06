<template>
  <div class="slide-code-frame">
    <header v-if="headerLabel" class="slide-code-frame__header">{{ headerLabel }}</header>
    <div class="slide-code-frame__body">
      <ol class="slide-code-frame__lines" aria-hidden="true">
        <li v-for="line in lineNumbers" :key="line">{{ line }}</li>
      </ol>
      <pre><code>{{ code }}</code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  code: string
  metadata?: Record<string, any>
  continuationIndex?: number
  continuationCount?: number
}>(), {
  metadata: () => ({}),
  continuationIndex: 1,
  continuationCount: 1,
})

const languageLabel = computed(() => {
  const language = String(props.metadata?.code_language || '').trim().toLowerCase()
  return ({
    csharp: 'C#',
    python: 'Python',
    javascript: 'JavaScript',
    typescript: 'TypeScript',
    java: 'Java',
    cpp: 'C++',
    'c++': 'C++',
    sql: 'SQL',
    bash: 'Bash',
  } as Record<string, string>)[language] || (language ? language.toUpperCase() : '')
})

const headerLabel = computed(() => [
  languageLabel.value,
  Number(props.metadata?.code_chunk_count || props.continuationCount) > 1
    ? `${Number(props.metadata?.code_chunk_index || props.continuationIndex)}/${Number(props.metadata?.code_chunk_count || props.continuationCount)}`
    : '',
].filter(Boolean).join(' · '))

const lineNumbers = computed(() => {
  const start = Math.max(1, Number(props.metadata?.code_start_line || 1))
  return String(props.code || '').split('\n').map((_line, index) => start + index)
})
</script>

<style scoped>
.slide-code-frame {
  display:grid;
  grid-template-rows:auto minmax(0,1fr);
  gap:.62cqw;
  width:100%;
  height:100%;
  min-height:0;
  color:#f5f7fb;
}
.slide-code-frame__header {
  color:#aeb6d0;
  font:800 .82cqw/1 "Aptos Mono","SFMono-Regular",monospace;
  letter-spacing:.04em;
}
.slide-code-frame__body {
  display:grid;
  grid-template-columns:3.1cqw minmax(0,1fr);
  min-height:0;
}
.slide-code-frame__lines {
  min-height:0;
  margin:0;
  padding:0 .72cqw 0 0;
  border-right:1px solid #34465c;
  color:#73839b;
  list-style:none;
  text-align:right;
  font:1.02cqw/1.5 "Aptos Mono","SFMono-Regular",monospace;
}
.slide-code-frame__body pre {
  width:auto;
  min-height:0;
  height:100%;
  margin:0;
  overflow:hidden;
  padding:0 0 0 1cqw;
  white-space:pre-wrap;
}
.slide-code-frame__body code {
  color:#f5f7fb;
  font:1.02cqw/1.5 "Aptos Mono","SFMono-Regular",monospace;
}
</style>
