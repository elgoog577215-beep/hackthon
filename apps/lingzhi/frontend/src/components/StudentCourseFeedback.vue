<template>
  <section class="course-feedback" :aria-label="copy('课程反馈', 'Course feedback')">
    <header><h3>{{ copy('向教师提问', 'Ask your teacher') }}</h3><button type="button" :disabled="busy" @click="load">{{ copy('刷新回复', 'Refresh replies') }}</button></header>
    <p>{{ copy('此处的提问和课程正式作答会送给教师。个人讲义、笔记和个人 AI 对话保留在你的学习空间。', 'Questions here and formal course attempts are shared with your teacher. Personal handouts, notes and AI conversations stay in your study space.') }}</p>
    <form @submit.prevent="send"><label>{{ copy('课程问题', 'Course question') }}<textarea v-model="text" maxlength="6000" required rows="3" :disabled="busy" /></label><button :disabled="busy || !text.trim()">{{ copy('发送给教师', 'Send to teacher') }}</button></form>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <ol><li v-for="item in items" :key="item.feedback_id"><span>{{ item.kind === 'course_question' ? copy('我的提问', 'My question') : copy('正式作答回执', 'Formal attempt receipt') }} · {{ item.status === 'delivered' ? copy('已送达', 'Delivered') : copy('待发送', 'Pending') }}</span><p v-if="item.payload.text">{{ item.payload.text }}</p><p v-if="item.reply" class="teacher-reply"><strong>{{ copy('教师回复', 'Teacher reply') }}</strong><br>{{ item.reply }}</p><button v-if="item.status === 'pending'" :disabled="busy" @click="retry(item.feedback_id)">{{ copy('重新发送', 'Send again') }}</button></li></ol>
  </section>
</template>
<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { studyApi, type CourseFeedback } from '../api/study'
import { activeLocale } from '../shared/i18n'
const props = defineProps<{ courseId: string; revisionId: string }>()
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
const text = ref(''), error = ref(''), notice = ref(''), busy = ref(false), items = ref<CourseFeedback[]>([])
let generation = 0
let submission: { request_id: string; expected_release_id: string; text: string } | null = null
async function load() {
  const current = ++generation; busy.value = true; error.value = ''
  try { const result = await studyApi.courseFeedback(props.courseId); if (current !== generation) return; items.value = result.items; if (result.replies_available === false) notice.value = copy('教师端暂不可达，显示已保存的发送记录。', 'Teacher service unavailable; showing saved delivery records.') }
  catch (cause) { if (current === generation) error.value = cause instanceof Error ? cause.message : copy('读取失败', 'Could not load feedback') }
  finally { if (current === generation) busy.value = false }
}
async function send() {
  const current = ++generation; busy.value = true; error.value = ''; notice.value = ''
  const message = text.value.trim()
  if (!submission || submission.text !== message || submission.expected_release_id !== props.revisionId) submission = { request_id: crypto.randomUUID(), expected_release_id: props.revisionId, text: message }
  try { const result = await studyApi.sendCourseFeedback(props.courseId, submission); if (current !== generation) return; text.value = ''; submission = null; notice.value = result.status === 'delivered' ? copy('教师已收到你的问题。', 'Your question reached your teacher.') : copy('问题已保存，待教师端恢复后可重新发送。', 'Question saved. Send again when the teacher service is available.'); await load() }
  catch (cause) { if (current === generation) error.value = cause instanceof Error ? cause.message : copy('发送失败', 'Could not send feedback') }
  finally { if (current === generation) busy.value = false }
}
async function retry(id: string) {
  const current = ++generation; busy.value = true; error.value = ''
  try { await studyApi.retryCourseFeedback(props.courseId, id); if (current === generation) await load() }
  catch (cause) { if (current === generation) error.value = cause instanceof Error ? cause.message : copy('发送失败', 'Could not send feedback') }
  finally { if (current === generation) busy.value = false }
}
watch([() => props.courseId, () => props.revisionId], () => { generation++; text.value = ''; submission = null; items.value = []; notice.value = ''; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>
<style scoped>
.course-feedback{margin-top:22px;padding:22px;border:1px solid #e0dded;border-radius:14px;background:#faf9fe;color:#263449;font-size:15px}.course-feedback header{display:flex;align-items:center;justify-content:space-between;gap:18px}h3{font-size:19px;margin:0}p{line-height:1.7;color:#64718a;white-space:pre-wrap}label{display:flex;flex-direction:column;gap:8px}textarea{font:inherit;border:1px solid #d7deeb;border-radius:8px;padding:10px;resize:vertical;width:100%;box-sizing:border-box}button{font:inherit;border:1px solid #d9ddeb;background:white;border-radius:8px;padding:8px 14px;cursor:pointer}form>button{background:#6551c7;color:white;margin-top:12px}ol{list-style:none;padding:0}li{padding:18px 0;border-top:1px solid #e0dded}li>span{color:#7669a2}.teacher-reply{border-left:3px solid #8d7cce;padding:10px 14px;background:#f0ecfa}button:disabled{opacity:.55;cursor:default}:is(button,textarea):focus-visible{outline:3px solid #9385ed;outline-offset:3px}
</style>
