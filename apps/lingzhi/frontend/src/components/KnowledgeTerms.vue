<template>
  <section v-if="point.terms?.length || point.aliases?.length || point.term_candidates?.length" class="knowledge-terms" data-testid="knowledge-terms">
    <h3>{{ t('knowledgeFirst.sourceTerms') }}</h3>
    <p v-if="point.terms?.length" class="term-note">{{ t('knowledgeFirst.sourceTermsHint') }}</p>
    <dl v-for="(term, index) in point.terms || []" :key="index" class="term-record">
      <dt>{{ term.name }}<span v-if="term.english_name" lang="en"> · {{ term.english_name }}</span></dt>
      <dd v-if="term.abbreviations?.length">{{ t('knowledgeFirst.abbreviations') }}：{{ term.abbreviations.join(' / ') }}</dd>
      <dd v-if="term.aliases?.length">{{ t('knowledgeFirst.aliases') }}：{{ term.aliases.join(' / ') }}</dd>
    </dl>
    <p v-if="point.aliases?.length" class="alias-list">{{ t('knowledgeFirst.searchAliases') }}：{{ point.aliases.join(' / ') }}</p>
    <details v-if="point.term_candidates?.length" class="term-candidates">
      <summary>{{ t('knowledgeFirst.unconfirmedTerms') }}</summary>
      <p>{{ t('knowledgeFirst.unconfirmedTermsHint') }}</p>
      <p v-for="(term, index) in point.term_candidates" :key="index">{{ [term.name, term.english_name, ...(term.aliases || [])].filter(Boolean).join(' / ') }}</p>
    </details>
  </section>
</template>
<script setup lang="ts">
import { t } from '../shared/i18n'
import type { KnowledgeTerm } from '../utils/knowledge-terms'
defineProps<{ point: { terms?: KnowledgeTerm[]; aliases?: string[]; term_candidates?: KnowledgeTerm[] } }>()
</script>
<style scoped>
.knowledge-terms{margin:22px 0;font-size:15px;line-height:1.75;overflow-wrap:anywhere}.knowledge-terms h3{font-size:16px;margin:0 0 10px}.term-note{color:#78658b}.term-record{display:block;margin:12px 0;padding:12px 14px;background:#f7f4fb;border-radius:9px}.term-record dt{font-weight:600}.term-record dd{margin:4px 0 0}.alias-list{color:#655777}.term-candidates{padding:12px;border:1px solid #e7dcc7;border-radius:8px;background:#fffaf0}.term-candidates summary{cursor:pointer;font-weight:600}
</style>
