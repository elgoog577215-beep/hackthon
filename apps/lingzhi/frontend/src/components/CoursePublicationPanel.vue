<template>
  <CourseWorkspaceHeaderAction :label="copy('发布与学生反馈', 'Publish & student feedback')" :display-label="copy('发布与反馈', 'Publish')" @click="open = true"><Send :size="16" /></CourseWorkspaceHeaderAction>
  <Teleport to="body"><div v-if="open" class="publication-backdrop" @click.self="open = false"><section class="publication-panel" role="dialog" aria-modal="true" :aria-label="copy('发布与学生反馈', 'Publish & student feedback')" @keydown.esc="open = false">
    <header class="publication-heading"><span class="publication-heading-mark" aria-hidden="true"><Send :size="18" /></span><h2>{{ t('courseWorkspaceFlow.deliveryTitle') }}</h2><button type="button" @click="open = false">{{ copy('关闭', 'Close') }}</button></header>
    <p>{{ copy('每次发布固定一个课程版本。已授权学生可刷新课程列表获取更新；教师草稿不会自动进入学生讲义。', 'Each publication freezes a course version. Authorized students can refresh their library for updates; drafts stay in the teacher workspace.') }}</p>
    <nav class="delivery-tabs" :aria-label="t('courseWorkspaceFlow.deliveryTitle')"><button v-for="tab in deliveryTabs" :key="tab.id" type="button" :aria-pressed="deliveryTab === tab.id" :class="{ selected: deliveryTab === tab.id }" @click="deliveryTab = tab.id">{{ tab.label }}</button></nav>
    <p class="delivery-flow">{{ t('courseWorkspaceFlow.publicationHelp') }}</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <section v-if="deliveryTab === 'publication'" class="delivery-section">
    <p>{{ t('courseWorkspaceFlow.grantBeforePublish') }} <button type="button" class="inline-access" @click="deliveryTab = 'access'">{{ t('courseWorkspaceFlow.access') }}</button></p>
    <p>{{ t('courseWorkspaceFlow.previewHelp') }}</p>
    <p v-if="status && !status.enabled">{{ copy('尚未配置师生互通。请按项目 README 为两个服务设置发布方、学习方和服务凭据。', 'Exchange is not configured. Follow the project README to configure the publishing and learning services and their credentials.') }}</p>
    <div v-if="status?.enabled" class="publication-actions"><strong>{{ status.status === 'published' ? copy('已有发布版本', 'A published version is available') : copy('当前未发布', 'Not currently published') }}</strong><button :disabled="busy || readingAvailable !== true" @click="publish">{{ copy('发布当前课程版本', 'Publish current course version') }}</button><button v-if="status.status === 'published'" :disabled="busy" @click="withdraw">{{ copy('停止学生访问', 'Withdraw publication') }}</button></div>
    <p v-if="status?.enabled && readingAvailable !== true" role="status">{{ t(readingAvailable === false ? 'courseWorkspaceFlow.handoutBeforePublish' : 'courseWorkspaceFlow.readingUnverified') }}</p>
    <fieldset v-if="status?.enabled && status.ppt_options?.length"><legend>{{ copy('本次同时发布的 PPT', 'PPTs to include in this publication') }}</legend><label v-for="ppt in status.ppt_options" :key="ppt.project_id" class="ppt-choice"><input v-model="selectedPpts" type="checkbox" :value="ppt.project_id" :disabled="busy">{{ ppt.title }}</label><p>{{ copy('仅列出已确认且引用公开讲义的成品。发布副本不含演讲者备注和批注。', 'Only confirmed exports based on public handouts are listed. Published copies exclude speaker notes and comments.') }}</p></fieldset>
    </section>
    <CourseLearningAccessPanel v-else-if="deliveryTab === 'access'" :course-id="courseId" embedded />
    <section v-else class="delivery-section">
    <p>{{ copy('学生的正式作答与主动课程提问显示在下面。个人讲义、笔记和个人 AI 对话由学生自己保管。', 'Formal attempts and questions students explicitly send appear below. Personal handouts, notes and personal AI conversations remain with the student.') }}</p>
    <header><h3>{{ copy('学生反馈', 'Student feedback') }} · {{ feedback.length }}</h3><button :disabled="busy" @click="load">{{ copy('刷新', 'Refresh') }}</button></header>
    <p v-if="!feedback.length && !busy">{{ copy('还没有收到学生反馈。', 'No student feedback yet.') }}</p>
    <article v-for="item in feedback" :key="item.feedback_id"><div class="feedback-meta"><strong>{{ item.kind === 'course_question' ? copy('课程提问', 'Course question') : copy('正式作答', 'Formal attempt') }}</strong><span>{{ item.actor_id }}</span></div><p v-if="item.payload.text">{{ item.payload.text }}</p><p v-if="item.assessment">{{ copy('练习结果', 'Practice result') }} · {{ item.assessment.result.passed === true ? copy('通过', 'Passed') : item.assessment.result.passed === false ? copy('需要再练', 'Needs practice') : copy('待评阅', 'Pending review') }}<span v-if="typeof item.assessment.result.score === 'number'"> · {{ item.assessment.result.score }}</span></p><div v-if="item.assessment" class="attempt-evidence"><p v-if="item.assessment.task?.prompt">{{ item.assessment.task.prompt }}</p><strong>{{ copy('学生作答', 'Student answer') }}</strong><pre>{{ answerSummary(item.assessment) }}</pre></div><p v-if="item.reply" class="saved-reply">{{ copy('已回复', 'Replied') }}：{{ item.reply }}</p><form @submit.prevent="reply(item)"><label>{{ copy('回复学生', 'Reply to student') }}<textarea v-model="drafts[item.feedback_id]" rows="2" maxlength="6000" required :disabled="busy" /></label><button :disabled="busy || !drafts[item.feedback_id]?.trim()">{{ copy('发送回复', 'Send reply') }}</button></form></article>
    </section>
  </section></div></Teleport>
</template>
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import http, { teacherRequestConfig } from '../utils/http'
import { activeLocale, t } from '../shared/i18n'
import { Send } from 'lucide-vue-next'
import CourseWorkspaceHeaderAction from './CourseWorkspaceHeaderAction.vue'
import CourseLearningAccessPanel from './CourseLearningAccessPanel.vue'
const props = defineProps<{ courseId: string }>()
const deliveryTab = ref<'publication' | 'access' | 'feedback'>('publication')
const deliveryTabs = computed(() => (['publication', 'access', 'feedback'] as const).map(id => ({ id, label: t(`courseWorkspaceFlow.${id}`) })))
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
interface ExchangeStatus { enabled: boolean; current_revision: string; published_release_id: string; status: string; feedback_count: number; ppt_options?: { project_id: string; title: string }[] }
interface Feedback { feedback_id: string; actor_id: string; kind: string; payload: { text?: string }; revision: number; reply: string; assessment?: { task_revision_id: string; result: { passed: boolean | null; score?: number }; answer_payload?: Record<string, unknown>; task?: { prompt?: string; options?: { id: string; text: string }[] } } }
const open = ref(false), busy = ref(false), error = ref(''), notice = ref(''), status = ref<ExchangeStatus | null>(null), feedback = ref<Feedback[]>([]), drafts = ref<Record<string, string>>({})
const selectedPpts = ref<string[]>([])
const readingAvailable = ref<boolean | null>(null)
function answerSummary(assessment: NonNullable<Feedback['assessment']>) {
  const answer = assessment.answer_payload || {}
  const selected = answer.selected_option_id
  if (selected) { const option = assessment.task?.options?.find(item => item.id === selected); return option ? `${option.id}. ${option.text}` : String(selected) }
  return String(answer.code ?? answer.text ?? answer.answer ?? answer.value ?? JSON.stringify(answer, null, 2))
}
const endpoint = () => `/api/teacher/courses/${encodeURIComponent(props.courseId)}/exchange`
let generation = 0
async function load() {
  const current = ++generation; busy.value = true; error.value = ''; const url = endpoint()
  try { const [state, rows, preview] = await Promise.all([http.get<ExchangeStatus>(url, teacherRequestConfig()), http.get<{ items: Feedback[] }>(url + '/feedback', teacherRequestConfig()), http.get(url.replace(/\/exchange$/, '/preview'), teacherRequestConfig({ silentError: true })).catch(() => null)]); if (current === generation) { status.value = state.data; feedback.value = rows.data.items || []; readingAvailable.value = typeof preview?.data?.availability?.reading === 'boolean' ? preview.data.availability.reading : null } }
  catch (cause) { if (current === generation) error.value = cause instanceof Error ? cause.message : copy('读取失败', 'Could not load publication') }
  finally { if (current === generation) busy.value = false }
}
async function mutate(action: () => Promise<unknown>, message: string) {
  const current = ++generation; busy.value = true; error.value = ''; notice.value = ''
  try { await action(); if (current !== generation) return; notice.value = message; await load() }
  catch (cause) { if (current === generation) error.value = cause instanceof Error ? cause.message : copy('操作失败', 'Action failed') }
  finally { if (current === generation) busy.value = false }
}
function publish() { if (!status.value || readingAvailable.value !== true) return; const url = endpoint(), revision = status.value.current_revision, ppt_project_ids = [...selectedPpts.value]; return mutate(() => http.post(url + '/publish', { expected_revision: revision, ppt_project_ids }, teacherRequestConfig()), copy('课程版本已发布，学生刷新课程列表后可获取。', 'Course version published. Students can refresh their library to receive it.')) }
function withdraw() { const url = endpoint(); return mutate(() => http.delete(url + '/publication', teacherRequestConfig()), copy('已停止新的课程访问，学生已有作答和笔记保留。', 'New course access has stopped. Existing student attempts and notes are retained.')) }
function reply(item: Feedback) { const url = endpoint(); const message = drafts.value[item.feedback_id]?.trim(); if (!message) return; return mutate(async () => { await http.post(`${url}/feedback/${encodeURIComponent(item.feedback_id)}/reply`, { expected_revision: item.revision, text: message }, teacherRequestConfig()) }, copy('回复已保存，学生刷新反馈后可查看。', 'Reply saved. The student can refresh feedback to read it.')) }
watch([open, () => props.courseId], () => { generation++; status.value = null; feedback.value = []; drafts.value = {}; selectedPpts.value = []; readingAvailable.value = null; notice.value = ''; error.value = ''; if (open.value) void load() })
onBeforeUnmount(() => { generation++ })
</script>
<style scoped>
button, textarea { font: inherit; font-size: 15px; }
button { min-height: 40px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 8px 14px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text); background: #fff; line-height: 1.4; font-weight: 600; cursor: pointer; }
button:hover { color: var(--lz-brand-strong); border-color: var(--lz-brand); }
.publication-backdrop { position: fixed; inset: 0; z-index: 2100; display: grid; place-items: center; padding: 24px; background: rgba(30, 41, 59, .42); }
.publication-panel { width: min(840px, 100%); max-height: calc(100dvh - 48px); overflow: auto; padding: 24px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: #fff; box-shadow: var(--lz-shadow-overlay); font: inherit; font-size: 15px; line-height: 1.6; }
header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.publication-heading { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid var(--lz-border); }
.publication-heading-mark { width: 40px; height: 40px; display: grid; place-items: center; border-radius: var(--lz-radius-control); color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
h2, h3 { font-family: inherit; line-height: 1.4; color: var(--lz-text-strong); }
h2 { margin: 0; font-size: 20px; font-weight: 700; }
h3 { font-size: 17px; font-weight: 600; }
p { color: var(--lz-text-secondary); white-space: pre-wrap; }
.delivery-tabs { display: flex; gap: 4px; margin-top: 20px; padding: 3px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-control); background: var(--lz-surface-subtle); }
.delivery-tabs button { flex: 1; min-width: 0; border: 0; background: transparent; }
.delivery-tabs button.selected { color: var(--lz-brand-strong); background: #fff; box-shadow: 0 2px 7px rgba(15, 23, 42, .08); }
.delivery-flow { margin: 0; padding: 16px 0; border-bottom: 1px solid var(--lz-border); font-size: 15px; line-height: 1.6; }
.inline-access { min-height: 0; padding: 0 4px; border: 0; color: var(--lz-brand-strong); background: transparent; }
.publication-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 16px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-control); background: var(--lz-surface-subtle); }
.publication-actions strong { flex: 1; min-width: 180px; font-weight: 600; }
.publication-actions button:first-of-type, form button { border-color: var(--lz-brand); color: #fff; background: var(--lz-brand); }
.publication-actions button:first-of-type:hover, form button:hover { border-color: var(--lz-brand-strong); background: var(--lz-brand-strong); }
article { margin-top: 20px; padding: 20px 0; border-top: 1px solid var(--lz-border); }
.feedback-meta { display: flex; align-items: start; justify-content: space-between; gap: 16px; overflow-wrap: anywhere; }
.feedback-meta span { color: var(--lz-text-secondary); }
.saved-reply { padding: 10px 14px; border-left: 3px solid var(--lz-brand); background: var(--lz-surface-subtle); }
label { display: flex; flex-direction: column; gap: 7px; color: var(--lz-text); }
textarea { min-width: 0; padding: 10px 11px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-strong); background: #fff; resize: vertical; line-height: 1.6; }
form button { margin-top: 12px; }
fieldset { margin: 20px 0 0; padding: 16px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-control); }
.ppt-choice { display: flex; flex-direction: row; align-items: center; gap: 10px; margin: 8px 0; }
.ppt-choice input { width: 18px; height: 18px; accent-color: var(--lz-brand); }
.attempt-evidence { padding: 16px; border-radius: 8px; background: var(--lz-surface-subtle); }
.attempt-evidence pre { font: inherit; font-size: 15px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
button:disabled { opacity: .55; cursor: not-allowed; }
:is(textarea, button):focus-visible { outline: 2px solid var(--lz-brand); outline-offset: 2px; }
@media (max-width: 680px) { .publication-backdrop { padding: 12px; } .publication-panel { max-height: calc(100dvh - 24px); padding: 16px; } }
</style>
