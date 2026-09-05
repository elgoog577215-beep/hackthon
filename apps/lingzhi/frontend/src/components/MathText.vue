<template>
  <component
    :is="tag"
    v-if="hasMath"
    class="math-text"
    data-math-rendered="true"
    v-html="renderedContent"
  />
  <component :is="tag" v-else class="math-text">{{ content }}</component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderInlineMarkdown } from '../utils/markdown'

const props = withDefaults(defineProps<{
  content?: string | number | null
  tag?: string
}>(), {
  content: '',
  tag: 'span',
})

const value = computed(() => String(props.content ?? ''))

const hasInlineDollarMath = (text: string) => Array.from(
  text.matchAll(/(^|[^$])\$([^$\n]+?)\$(?!\$)/g),
).some((match) => {
  const inner = String(match[2] || '').trim()
  if (!inner || /^\d+(?:\.\d+)?$/.test(inner)) return false
  if (/\p{Script=Han}/u.test(inner) && !/[\\=^_{}[\]+\-*/<>]/.test(inner)) return false
  return /\\[A-Za-z]+|[=^_{}[\]+\-*/<>]|^[A-Za-zΑ-Ωα-ω](?:\d+)?$/.test(inner)
})

// Only content fields opt into this component.  Requiring a balanced delimiter
// or an unambiguous mathematical structure keeps ordinary currency and code
// labels as plain text while still recovering delimiter-free legacy formulas.
const hasMath = computed(() => {
  const text = value.value
  const hasDelimitedMath = /\$\$[\s\S]+?\$\$/.test(text)
    || hasInlineDollarMath(text)
    || /\\\([\s\S]+?\\\)/.test(text)
    || /\\\[[\s\S]+?\\\]/.test(text)
    || /\\begin\{(?:align\*?|aligned|array|bmatrix|cases|equation\*?|gather\*?|matrix|pmatrix|smallmatrix|split|vmatrix|Vmatrix)\}/.test(text)
  if (hasDelimitedMath) return true

  const hasLatexCommand = /\\(?:alpha|arccos|arcsin|arctan|beta|cap|cdot|chi|cos|cup|delta|det|epsilon|eta|exists|forall|frac|gamma|geq?|in|infty|int|lambda|leq?|lim|ln|log|mathbb|mathbf|mathrm|mu|nabla|neq|notin|nu|omega|operatorname|partial|phi|pi|prod|psi|rho|sigma|sin|sqrt|subset|sum|supset|tan|tau|text|theta|times|varphi|vec|xi|zeta)\b/.test(text)
  const hasMathStructure = /[=^_{}[\]()+\-*/<>≤≥]|\\(?:left|right)\b/.test(text)
  const hasNakedEquation = /(?:^|[\s：:;,\uff1b])(?:[A-Za-zΑ-ωΑ-Ω]|\\[A-Za-z]+)(?:[\wΑ-ωΑ-Ω{}()[\]\\.^'\s+\-*/]|\u00b7){0,60}=(?!=)/.test(text)
  const hasNakedPowerOrSubscript = /\b[A-Za-zΑ-Ωα-ω][A-Za-zΑ-Ωα-ω0-9]*(?:\^|_)(?:\{[^}\n]+\}|[A-Za-zΑ-Ωα-ω0-9])/.test(text)
  const hasRecoverableDisplayStart = /\$\$(?=\s*(?:\\|[A-Za-zΑ-ωΑ-Ω]).*[=^_{}])/s.test(text)

  return hasLatexCommand || (hasMathStructure && hasNakedPowerOrSubscript) || hasNakedEquation || hasRecoverableDisplayStart
})

const renderedContent = computed(() => renderInlineMarkdown(value.value))
</script>

<style scoped>
.math-text{min-width:0;color:inherit;font:inherit;line-height:inherit;overflow-wrap:inherit;word-break:inherit}
.math-text:deep(.katex){font-size:1em}
.math-text:deep(.katex-display){display:block;max-width:100%;margin:.45em 0;overflow-x:auto;overflow-y:hidden;padding-bottom:.15em;-webkit-overflow-scrolling:touch}
.math-text:deep(.math-fallback){display:inline-block;max-width:100%;overflow-x:auto;border:1px dashed rgba(148,163,184,.7);border-radius:6px;background:rgba(248,250,252,.9);color:#475569;font-size:.88em;line-height:1.55;padding:.12rem .35rem;white-space:pre-wrap;word-break:break-word}
.math-text:deep(p){margin:0}
</style>
