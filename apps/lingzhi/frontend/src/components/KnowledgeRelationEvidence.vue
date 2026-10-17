<template>
  <div class="relation-evidence">
    <p v-if="edge.context"><strong>{{ t('knowledgeFirst.relationContext') }}</strong> · {{ edge.context }}</p>
    <p v-if="edge.type === 'prerequisite' && edge.necessity">{{ t(`knowledgeFirst.necessity_${edge.necessity}`) }}</p>
    <p v-if="edge.strength !== undefined">{{ t('knowledgeFirst.relationStrength') }} · {{ t(`knowledgeFirst.strength_${edge.strength_level || (edge.strength === 1 ? 'strong' : edge.strength === .6 ? 'medium' : edge.strength === .3 ? 'weak' : 'unknown')}`) }}</p>
    <ol v-if="edge.derivation_steps?.length"><li v-for="(step,index) in edge.derivation_steps" :key="index">{{ step }}</li></ol>
    <details v-if="edge.evidence_refs?.length"><summary>{{ t('knowledgeFirst.relationEvidence') }}</summary>
      <p>{{ t('knowledgeFirst.relationEvidenceHint') }}</p>
      <blockquote v-for="(e,index) in edge.evidence_refs" :key="index">{{ e.quote }}<small>{{ e.revision_id }}</small></blockquote>
    </details>
  </div>
</template>
<script setup lang="ts">
import {t} from '../shared/i18n'
defineProps<{edge:any}>()
</script>
<style scoped>
.relation-evidence{font-size:15px;line-height:1.8;overflow-wrap:anywhere}.relation-evidence p{margin:8px 0}.relation-evidence ol{padding-left:24px}.relation-evidence summary{cursor:pointer}.relation-evidence blockquote{margin:10px 0;padding:10px 14px;background:#f6f3fb;border-left:3px solid #b4a1d0}.relation-evidence small{display:block;color:#857392;font-size:15px}.relation-evidence summary:focus-visible{outline:3px solid #b4a1d0;outline-offset:3px}
</style>
