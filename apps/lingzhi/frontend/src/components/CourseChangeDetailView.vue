<template>
  <section class="course-change-detail" data-testid="course-change-detail" :aria-label="title">
    <header>
      <button ref="backButton" type="button" class="detail-back" data-testid="back-to-impact-list" @click="$emit('back')"><ArrowLeft :size="18" />{{ t('courseEvolution.workspace.backToList') }}</button>
      <div class="detail-heading"><small v-if="subtitle && subtitle !== title">{{ subtitle }}</small><h3>{{ title }}</h3></div>
      <div class="detail-actions"><slot name="actions" /></div>
    </header>
    <div class="detail-content"><slot /></div>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import { t } from '../shared/i18n'
defineProps<{ title: string; subtitle: string }>()
defineEmits<{ back: [] }>()
const backButton = ref<HTMLButtonElement | null>(null)
onMounted(() => backButton.value?.focus())
</script>
<style scoped>
.course-change-detail{display:flex;flex-direction:column;flex:1;min-height:0;background:white;overflow:hidden}
.course-change-detail>header{display:flex;align-items:center;gap:20px;padding:18px 24px;border-bottom:1px solid #e3e7ef;flex-shrink:0}
.detail-back{display:flex;align-items:center;gap:6px;min-height:38px;padding:8px 12px;background:white;border:1px solid #cfd5df;border-radius:8px;color:#344054;font-size:15px;cursor:pointer}
.detail-heading{min-width:0;flex:1}.detail-heading small{font-size:15px;color:#667085}.detail-heading h3{margin:4px 0 0;font-size:22px;color:#172033}
.detail-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.detail-content{min-height:0;overflow:auto;padding:24px;flex:1;font-size:16px;line-height:1.7}
.detail-back:focus-visible{outline:3px solid #b8b2ff;outline-offset:2px}
@media(max-width:900px){.course-change-detail>header{flex-wrap:wrap;gap:12px}.detail-heading{flex-basis:65%}}
</style>
