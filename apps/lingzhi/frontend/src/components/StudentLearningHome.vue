<template>
  <section class="student-home glass-panel-elevated">
    <header class="student-home-heading">
      <div><h1>{{ t('courseLibrary.title') }}</h1><p>{{ t('studentWorkspace.homeHelp') }}</p></div>
      <button type="button" class="primary" @click="emit('create', 'systematic')"><Plus :size="18" />{{ t('studentWorkspace.newMaterial') }}</button>
    </header>
    <div class="student-home-actions">
      <button type="button" :title="t('studentWorkspace.systematicHelp')" @click="emit('create', 'systematic')"><BookOpen :size="18" /><strong>{{ t('studentWorkspace.systematic') }}</strong><ArrowRight :size="16" /></button>
      <button type="button" :title="t('studentWorkspace.examHelp')" @click="emit('create', 'exam_prep')"><Target :size="18" /><strong>{{ t('studentWorkspace.exam') }}</strong><ArrowRight :size="16" /></button>
    </div>
    <StudentCourseLibrary :user-id="userId" compact @source="emit('source', $event)" />
    <section class="student-home-materials">
      <header><div><h2>{{ t('studentWorkspace.personalMaterials') }}</h2><p>{{ t('studentWorkspace.materialsHelp') }}</p></div><RouterLink to="/study?view=materials">{{ t('studentWorkspace.allMaterials') }}<ArrowRight :size="16" /></RouterLink></header>
      <div v-if="materials.length" class="recent-materials-list"><RouterLink v-for="material in materials.slice(0, 4)" :key="material.id" :to="`/study/${material.id}`"><FileText :size="19" /><span><strong>{{ material.title }}</strong><small>{{ t(material.purpose === 'exam_prep' ? 'studentWorkspace.exam' : 'studentWorkspace.systematic') }}</small></span><ArrowRight :size="16" /></RouterLink></div>
      <p v-else class="home-empty">{{ t('studentWorkspace.noMaterials') }}</p>
    </section>
  </section>
</template>
<script setup lang="ts">
import { ArrowRight, BookOpen, FileText, Plus, Target } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { StudyPurpose, StudySource, StudySummary } from '../api/study'
import StudentCourseLibrary from './StudentCourseLibrary.vue'
defineProps<{ userId: string; materials: StudySummary[] }>()
const emit = defineEmits<{ create: [purpose: StudyPurpose]; source: [source: StudySource] }>()
</script>
<style scoped>
.student-home{max-width:1160px;margin:auto;padding:32px;color:var(--lz-text);font-size:15px}.student-home-heading,.student-home-materials>header{display:flex;align-items:center;justify-content:space-between;gap:20px}.student-home h1{margin:0;font:inherit;font-size:26px;font-weight:700;color:var(--lz-text-strong)}.student-home h2{margin:0;font:inherit;font-size:20px;font-weight:650;color:var(--lz-text-strong)}.student-home p{margin:8px 0 0;color:var(--lz-text-secondary);line-height:1.6}.student-home button{display:flex;align-items:center;gap:9px;padding:10px 14px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:var(--lz-text);font:inherit;cursor:pointer}.student-home button.primary{color:var(--lz-action-text);border-color:var(--lz-action-border);background:var(--lz-action-bg);white-space:nowrap;border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);box-shadow:var(--lz-action-shadow)}.student-home-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:24px 0 30px}.student-home-actions>button{text-align:left;padding:18px;gap:14px}.student-home-actions>button>svg{flex:none;color:var(--lz-brand-strong)}.student-home-actions>button>svg:last-child{margin-left:auto}.student-home-actions strong,.student-home-actions span{display:block}.student-home-actions strong{font-weight:600}.student-home-actions span{margin-top:5px;line-height:1.6;color:var(--lz-text-secondary)}.student-home-materials{margin-top:30px;padding-top:26px;border-top:1px solid var(--lz-border)}.student-home-materials>header>a{display:flex;align-items:center;gap:7px;white-space:nowrap;color:var(--lz-brand-strong);text-decoration:none}.recent-materials-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:18px}.recent-materials-list>a{display:flex;align-items:center;gap:12px;padding:15px;border:1px solid var(--lz-border);border-radius:var(--lz-radius-control);color:var(--lz-text);background:#fff;text-decoration:none}.recent-materials-list>a>svg{flex:none;color:var(--lz-brand-strong)}.recent-materials-list>a>span{flex:1;min-width:0}.recent-materials-list strong{font-weight:600;overflow-wrap:anywhere}.recent-materials-list small{display:block;margin-top:4px;color:var(--lz-text-secondary);font-size:15px}.home-empty{padding:20px;background:var(--lz-surface-subtle);border-radius:8px}.student-home :deep(.student-courses){padding:0;max-width:none}.student-home :is(button,a):focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}@media(max-width:900px){.student-home{padding:24px}.student-home-actions,.recent-materials-list{grid-template-columns:1fr}}
</style>

<style scoped>
.student-home { max-width: 1340px; padding: 26px 32px 38px; border: 0; background: transparent; box-shadow: none; }
.student-home h1 { font-size: 28px; color: #312e81; line-height: 1.3; }
.student-home-actions { display: flex; gap: 10px; margin: 16px 0 26px; flex-wrap: wrap; }
.student-home-actions > button { padding: 9px 13px; gap: 9px; border-color: transparent; background: var(--lz-surface-subtle); color: var(--lz-brand-strong); }
.student-home-materials { margin-top: 26px; padding-top: 22px; }
.recent-materials-list { grid-template-columns: repeat(3,minmax(0,1fr)); }
.recent-materials-list > a { border-radius: 15px; background: rgba(255,255,255,.88); }
@media(max-width:1100px) { .recent-materials-list { grid-template-columns: repeat(2,minmax(0,1fr)); } }
</style>
