<template>
  <main class="teacher-trial">
    <header class="trial-toolbar">
      <button type="button" @click="exit"><ArrowLeft :size="17" />{{ t('teacherTrial.back') }}</button>
      <strong>{{ snapshot?.document.title || t('teacherTrial.title') }}</strong>
      <span>{{ t('teacherTrial.sessionOnly') }}</span>
      <button type="button" :disabled="loading" @click="load">{{ t('teacherTrial.refresh') }}</button>
    </header>
    <p v-if="error" class="trial-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="trial-status" role="status">{{ t('teacherTrial.loading') }}</p>
    <div v-else-if="snapshot" class="trial-body">
      <nav :aria-label="t('teacherTrial.chapters')">
        <button v-for="section in snapshot.document.sections" :key="section.section_id" type="button"
          :class="{ active: selected === section.section_id, chapter: section.level === 1 }"
          :aria-current="selected === section.section_id ? 'page' : undefined" @click="selected = section.section_id">{{ section.title }}</button>
      </nav>
      <article class="trial-reading">
        <h1>{{ currentSection?.title }}</h1>
        <p v-if="!blocks.length" class="trial-empty">{{ t('teacherTrial.noHandout') }}</p>
        <section v-for="block in blocks" :key="block.block_id" :id="`trial-${block.block_id}`" :data-content-block-id="block.block_id">
          <h2 v-if="block.payload.title">{{ block.payload.title }}</h2>
          <MarkdownRenderer :content="block.payload.markdown || ''" />
        </section>
        <section class="trial-practice">
          <h2>{{ t('teacherTrial.practice') }}</h2>
          <p v-if="!questions.length" class="trial-empty">{{ t('teacherTrial.noQuestions') }}</p>
          <article v-for="question in questions" :key="question.revision_id" class="trial-question">
            <MathText :content="question.prompt || ''" />
            <PracticeAnswerRenderer :model-value="answers[question.revision_id] || {}" :contract="question.input_contract"
              :question-type="question.question_type" :options="question.options" :disabled="busy || stale"
              @update:model-value="answers[question.revision_id] = $event" />
            <button type="button" :disabled="busy || stale || !answers[question.revision_id]" @click="grade(question)">{{ t('teacherTrial.check') }}</button>
            <div v-if="feedback[question.revision_id]" role="status" class="trial-feedback">
              <strong>{{ feedback[question.revision_id].passed ? t('teacherTrial.passed') : t('teacherTrial.feedback') }}</strong>
              <MathText :content="feedbackText(feedback[question.revision_id])" />
            </div>
          </article>
        </section>
      </article>
      <aside class="trial-ai">
        <h2>{{ t('teacherTrial.ask') }}</h2>
        <div v-for="(message, index) in messages" :key="index" class="trial-message" :class="message.role">
          <small>{{ message.role === 'user' ? t('teacherTrial.you') : 'AI' }}</small><MarkdownRenderer :content="message.content" />
        </div>
        <ul v-if="sources.length" class="trial-sources"><li v-for="source in sources" :key="source.block_id"><button type="button" @click="showSource(source.block_id)">{{ source.title }}</button></li></ul>
        <form @submit.prevent="ask"><label for="trial-question">{{ t('teacherTrial.questionLabel') }}</label>
          <textarea id="trial-question" v-model="questionText" rows="4" maxlength="4000" :disabled="busy || stale" />
          <button type="submit" :disabled="busy || stale || !questionText.trim()">{{ busy ? t('teacherTrial.working') : t('teacherTrial.send') }}</button>
        </form>
      </aside>
    </div>
  </main>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import http, { identityRequestConfig } from '../utils/http'
import { t } from '../shared/i18n'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import MathText from '../components/MathText.vue'
import PracticeAnswerRenderer from '../components/PracticeAnswerRenderer.vue'
const route = useRoute(), router = useRouter()
const snapshot = ref<any>(null), selected = ref(''), error = ref(''), loading = ref(false), busy = ref(false), stale = ref(false)
const answers = ref<Record<string, any>>({}), feedback = ref<Record<string, any>>({})
const messages = ref<Array<{role: 'user' | 'assistant'; content: string}>>([]), sources = ref<any[]>([]), questionText = ref('')
let controller = new AbortController()
const endpoint = () => `/api/teacher/courses/${encodeURIComponent(String(route.params.courseId))}/preview`
const config = () => identityRequestConfig('teacher', { signal: controller.signal })
const currentSection = computed(() => snapshot.value?.document.sections.find((s: any) => s.section_id === selected.value))
const scope = computed(() => new Set([selected.value, ...(snapshot.value?.document.sections || []).filter((s: any) => s.parent_section_id === selected.value).map((s: any) => s.section_id)]))
const blocks = computed(() => (snapshot.value?.document.blocks || []).filter((b: any) => scope.value.has(b.section_id)))
const questions = computed(() => (snapshot.value?.questions || []).filter((q: any) => scope.value.has(q.node_id) || (q.node_ids || []).some((id: string) => scope.value.has(id))))
function clearTrial() { answers.value = {}; feedback.value = {}; messages.value = []; sources.value = []; questionText.value = '' }
function failure(e: any) { if (e?.code === 'ERR_CANCELED') return; stale.value = e?.response?.status === 409; error.value = stale.value ? t('teacherTrial.stale') : t('teacherTrial.failed') }
async function load() {
  controller.abort(); controller = new AbortController(); clearTrial(); stale.value = false; loading.value = true; error.value = ''
  try { snapshot.value = (await http.get(endpoint(), config())).data; if (!snapshot.value.document.sections.some((s: any) => s.section_id === selected.value)) selected.value = String(route.params.nodeId || snapshot.value.document.sections[0]?.section_id || '') }
  catch (e) { failure(e) } finally { loading.value = false }
}
async function grade(q: any) {
  busy.value = true; error.value = ''
  try { const {data} = await http.post(`${endpoint()}/grade`, { preview_revision: snapshot.value.preview_revision, question_revision_id: q.revision_id, answer_payload: answers.value[q.revision_id] }, config()); feedback.value[q.revision_id] = data.feedback }
  catch (e) { failure(e) } finally { busy.value = false }
}
function feedbackText(result: any): string { return String(result.feedback || result.explanation || result.summary || '') }
async function ask() {
  const text = questionText.value.trim(); if (!text) return
  busy.value = true; error.value = ''
  try { const {data} = await http.post(`${endpoint()}/ask`, { preview_revision: snapshot.value.preview_revision, question: text, section_id: selected.value, messages: messages.value.slice(-12) }, config()); messages.value.push({role:'user', content:text}, {role:'assistant', content:data.answer}); sources.value = data.sources; questionText.value = '' }
  catch (e) { failure(e) } finally { busy.value = false }
}
function showSource(id: string) { const block = snapshot.value?.document.blocks.find((b: any) => b.block_id === id); if (block) selected.value = block.section_id }
function exit() { clearTrial(); const target = String(route.query.returnTo || ''); router.push(target.startsWith('/') && !target.startsWith('//') ? target : {name:'course-workspace', params:{courseId:route.params.courseId, mode:'build'}}) }
watch(() => route.params.courseId, load, {immediate:true})
onBeforeUnmount(() => { controller.abort(); clearTrial() })
</script>
<style scoped>
.teacher-trial{height:100%;display:flex;flex-direction:column;background:var(--bg-primary,#fff);color:var(--text-primary,#222);font-size:14px}.trial-toolbar{min-height:58px;display:flex;align-items:center;gap:20px;padding:10px 24px;border-bottom:1px solid #e5e5e5}.trial-toolbar strong{flex:1}.trial-toolbar span,.trial-empty,.trial-status{color:#666;font-size:13px}.teacher-trial button{display:inline-flex;align-items:center;gap:6px;padding:8px 10px;border:0;border-radius:6px;background:transparent;color:inherit;cursor:pointer}.teacher-trial button:hover:not(:disabled){background:#ededed}.teacher-trial button:focus-visible,.teacher-trial textarea:focus-visible{outline:2px solid #306bd5;outline-offset:2px}.teacher-trial button:disabled{opacity:.45;cursor:default}.trial-body{display:grid;grid-template-columns:210px minmax(360px,1fr) 310px;min-height:0;flex:1}.trial-body>nav{overflow:auto;padding:20px 12px;background:#f7f7f7}.trial-body>nav button{width:100%;text-align:left;font-size:13px;line-height:1.5;margin-bottom:3px;padding-left:22px}.trial-body>nav button.chapter{font-weight:600;padding-left:10px}.trial-body>nav button.active{background:#e9e9e9}.trial-reading{overflow:auto;padding:32px clamp(24px,4vw,72px) 64px}.trial-reading h1{font-size:26px;margin:0 0 32px;font-weight:600}.trial-reading h2{font-size:19px;margin:32px 0 16px}.trial-reading>section{max-width:75ch;margin-inline:auto}.trial-ai{padding:24px 20px;border-left:1px solid #e5e5e5;overflow:auto;background:#fafafa}.trial-ai h2{font-size:15px;margin:0 0 24px}.trial-ai form{display:grid;gap:8px;margin-top:24px}.trial-ai label{font-size:13px;color:#666}.trial-ai textarea{resize:vertical;min-height:90px;border:1px solid #d6d6d6;border-radius:8px;padding:10px;font:inherit;background:#fff}.trial-ai form button,.trial-question>button{background:#252525;color:#fff;justify-content:center}.trial-question{padding:24px 0;border-bottom:1px solid #e5e5e5}.trial-question>button{margin-top:12px}.trial-feedback{padding:16px 0}.trial-message{margin:20px 0;line-height:1.7}.trial-message small{color:#666}.trial-sources{padding-left:16px;font-size:12px}.trial-error{padding:12px 24px;color:#8c3030;background:#fff4f2;margin:0}.trial-status{padding:24px}@media(max-width:1000px){.trial-body{grid-template-columns:170px minmax(0,1fr)}.trial-ai{grid-column:2;border-top:1px solid #ddd}.trial-body>nav{grid-row:1/3}.trial-toolbar span{display:none}}
</style>
