<template>
  <section :id="id" class="handout-type-reference" :data-group="group" :aria-labelledby="`${id}-title`">
    <header>
      <strong :id="`${id}-title`">{{ currentGroup?.label[activeLocale] }}</strong>
      <button type="button" :aria-label="t('courseWorkbench.scriptDocument.typeGuide.close')" @click="emit('close')"><X :size="16" /></button>
    </header>
    <p>{{ currentGroup?.purpose[activeLocale] }}</p>
    <div class="handout-type-reference__list">
      <article v-for="item in types" :key="item.id">
        <h5>{{ item.label[activeLocale] }}</h5>
        <p>{{ item.purpose?.[activeLocale] }}</p>
        <ul><li v-for="point in item.checkpoints?.[activeLocale]" :key="point">{{ point }}</li></ul>
        <p v-if="item.example" class="handout-type-reference__example"><strong>{{ t('courseWorkbench.scriptDocument.typeGuide.example') }}</strong>{{ item.example[activeLocale] }}</p>
      </article>
    </div>
    <footer>{{ t('courseWorkbench.scriptDocument.typeGuide.boundary') }}</footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import { handoutContentGroups, handoutTypesForGroup, type HandoutContentGroup } from '../utils/handout-content'
const props = defineProps<{ group: HandoutContentGroup; id: string }>()
const emit = defineEmits<{ (event: 'close'): void }>()
const currentGroup = computed(() => handoutContentGroups.find(item => item.id === props.group))
const types = computed(() => handoutTypesForGroup(props.group))
</script>

<style scoped>
.handout-type-reference{--type-accent:#315e91;flex-basis:100%;min-width:0;box-sizing:border-box;padding:16px 18px;border:1px solid #dce3ed;border-left:3px solid var(--type-accent);background:#fff;color:#435066;font:15px/1.65 var(--handout-sans)}
.handout-type-reference[data-group="practice"]{--type-accent:#17815a}.handout-type-reference[data-group="question"]{--type-accent:#6e4a9c}
.handout-type-reference>header{display:flex;align-items:center;justify-content:space-between;gap:14px;color:var(--type-accent)}
.handout-type-reference button{display:grid;place-items:center;padding:4px;border:0;background:transparent;color:#657080;cursor:pointer}.handout-type-reference button:focus-visible{outline:2px solid #6366f1;outline-offset:3px}
.handout-type-reference p{margin:8px 0}.handout-type-reference__list{max-height:380px;overflow:auto;overscroll-behavior:contain;padding-right:8px}
.handout-type-reference article{padding:12px 0;border-top:1px solid #e5e9ef}.handout-type-reference h5{margin:0;color:#263147;font-size:16px}
.handout-type-reference ul{margin:7px 0;padding-left:20px}.handout-type-reference__example{padding:9px 12px;background:#f7f8fc}.handout-type-reference__example strong{margin-right:8px;font-weight:650}.handout-type-reference footer{padding-top:10px;border-top:1px solid #e5e9ef;color:#637087}
</style>
