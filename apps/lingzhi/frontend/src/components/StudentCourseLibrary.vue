<template>
  <section class="student-courses" :class="{ 'is-compact': compact }">
    <header class="course-library-heading"><div><component :is="compact ? 'h2' : 'h1'">{{ copy('教师授权课程', 'Authorized courses') }}</component><p>{{ t('studentWorkspace.courseHelp') }}</p></div><button type="button" :disabled="loading" @click="load">{{ copy('刷新', 'Refresh') }}</button></header>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="loading" role="status">{{ copy('正在读取课程…', 'Loading courses…') }}</p>
    <div v-if="courses.length" class="course-grid">
      <article v-for="course in courses" :key="course.course_id">
        <div class="course-card-heading"><CourseCover :course-id="course.course_id" :title="course.title" /><div><h2>{{ course.title }}</h2><span class="course-origin">{{ course.exchange_origin ? copy('教师已发布 · 已授权', 'Published by teacher · Access granted') : copy('已获得学习授权', 'Learning access granted') }}</span><p v-if="course.question_count !== undefined">{{ course.question_count }} {{ copy('道课程练习', 'course exercises') }}</p></div></div>
        <template v-if="course.reading_available">
          <div class="course-card-actions"><RouterLink class="course-start" :to="studentCourseLink(course.course_id)">{{ copy('进入学习', 'Start learning') }} →</RouterLink><button type="button" :disabled="loading" @click="derive(course)">{{ copy('生成个人复习讲义', 'Create a personal revision handout') }}</button></div>
          <nav class="course-tools" :aria-label="`${course.title} · ${t('studentWorkspace.courseTools')}`"><RouterLink v-for="tool in tools" :key="tool" :to="studentCourseLink(course.course_id, tool)">{{ t(`studentWorkspace.${tool}`) }}</RouterLink></nav>
          <button type="button" class="course-detail-toggle" :aria-expanded="detailCourseId === course.course_id" @click="detailCourseId = detailCourseId === course.course_id ? '' : course.course_id">{{ t('studentWorkspace.coursePath') }}</button>
          <StudentLearningPath compact v-if="detailCourseId === course.course_id" :key="`${course.course_id}:${course.revision_id}:${pathGeneration}`" :course-id="course.course_id" :title="course.title" />
        </template>
        <p v-else>{{ copy('教师尚未提供讲义', 'The teacher has not provided a handout yet') }}</p>
        <div v-if="course.update_available" class="course-update"><strong>{{ copy('教师发布了新版本', 'Your teacher published an update') }}</strong><p>{{ copy('更新后继续学习，原作答与笔记保留。', 'Continue with the new version; previous attempts and notes are retained.') }}</p><button :disabled="loading" @click="update(course)">{{ copy('使用新版本', 'Use new version') }}</button></div>
        <section v-if="course.published_ppts?.length" class="published-ppts"><h3>{{ copy('教师发布的 PPT', 'Published PPTs') }}</h3><button v-for="ppt in course.published_ppts" :key="ppt.asset_id" :disabled="loading" @click="downloadPpt(course, ppt.asset_id, ppt.filename)">{{ copy('下载', 'Download') }} {{ ppt.filename }}</button></section>
        <button v-if="course.exchange_origin" class="feedback-button" :aria-expanded="feedbackCourse === course.course_id" @click="feedbackCourse = feedbackCourse === course.course_id ? '' : course.course_id">{{ copy('课程提问与教师回复', 'Questions & teacher replies') }}</button><StudentCourseFeedback v-if="course.exchange_origin && feedbackCourse === course.course_id" :course-id="course.course_id" :revision-id="course.revision_id" />
      </article>
    </div>
    <p v-if="!loading && !error && !courses.length" class="course-empty">{{ copy('还没有获授权课程。将你的学生身份提供给教师，教师授权后课程会显示在这里。', 'No authorized courses yet. Give your student identity to your teacher; granted courses will appear here.') }}</p>
    <details class="student-id"><summary>{{ copy('我的学生身份', 'My student identity') }}</summary><code>{{ userId }}</code></details>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { studyApi, type StudyCourse, type StudySource } from '../api/study'
import { activeLocale, t } from '../shared/i18n'
import StudentLearningPath from './StudentLearningPath.vue'
import CourseCover from './CourseCover.vue'
import { studentCourseLink, type StudentWorkspaceTool } from '../shared/student-workspace'
import StudentCourseFeedback from './StudentCourseFeedback.vue'
withDefaults(defineProps<{ userId: string; compact?: boolean }>(), { compact: false })
const detailCourseId = ref('')
const tools: StudentWorkspaceTool[] = ['practice', 'mistakes', 'knowledge', 'overview']
const emit = defineEmits<{ source: [source: StudySource] }>()
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
const courses = ref<StudyCourse[]>([]), loading = ref(false), error = ref('')
const feedbackCourse = ref(''), pathGeneration = ref(0)
let sequence = 0
async function load() { const current = ++sequence; loading.value = true; error.value = ''; try { const result = await studyApi.courses(); if (current === sequence) { courses.value = result; if (!result.some(c => c.course_id === detailCourseId.value)) detailCourseId.value = ''; pathGeneration.value++ } } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : copy('课程读取失败', 'Could not load courses') } finally { if (current === sequence) loading.value = false } }
onMounted(load)
defineExpose({ reload: load })
async function derive(course: StudyCourse) { const current = ++sequence; loading.value = true; error.value = ''; try { const source = await studyApi.courseSource(course.course_id, course.revision_id); if (current === sequence) emit('source', source) } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : copy('资料选择失败', 'Could not select course sources') } finally { if (current === sequence) loading.value = false } }
async function update(course: StudyCourse) { const current = ++sequence; loading.value = true; error.value = ''; try { await studyApi.updateCourse(course.course_id, course.revision_id); if (current === sequence) await load() } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : copy('课程更新失败', 'Could not update course') } finally { if (current === sequence) loading.value = false } }
async function downloadPpt(course: StudyCourse, assetId: string, filename: string) { const current = ++sequence; loading.value = true; error.value = ''; try { const blob = await studyApi.coursePpt(course.course_id, assetId, course.revision_id); if (current !== sequence) return; const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url) } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : copy('PPT 下载失败', 'Could not download PPT') } finally { if (current === sequence) loading.value = false } }
onBeforeUnmount(() => { sequence++ })
</script>
<style scoped>
.student-courses{max-width:1160px;margin:auto;padding:32px;color:var(--lz-text);font-size:15px}.course-library-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.course-library-heading h1,.course-library-heading h2{margin:0;color:var(--lz-text-strong);font:inherit;font-size:26px;font-weight:700}.is-compact .course-library-heading h2{font-size:20px;font-weight:650}.student-courses p{margin:8px 0 0;color:var(--lz-text-secondary);line-height:1.6}.student-courses button{min-height:38px;display:inline-flex;align-items:center;justify-content:center;padding:8px 13px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text);background:#fff;cursor:pointer;font:inherit;font-size:15px;line-height:1.4}.course-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:20px;align-items:start}.course-grid>article{min-width:0;background:#fff;border:1px solid var(--lz-border);border-radius:var(--lz-radius-control);padding:20px}.course-card-heading h2{margin:10px 0 0;font:inherit;font-size:20px;font-weight:650;color:var(--lz-text-strong);overflow-wrap:anywhere}.course-origin{font-size:15px;color:var(--lz-success)}.course-card-actions{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin-top:18px}.course-card-actions>a{display:inline-flex;align-items:center;justify-content:center;min-height:38px;padding:8px 14px;background:var(--lz-action-bg);color:var(--lz-action-text);border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);text-decoration:none;line-height:1.4;box-shadow:var(--lz-action-shadow)}.course-tools{display:flex;flex-wrap:wrap;gap:8px 16px;padding:16px 0 12px;border-bottom:1px solid var(--lz-border)}.course-tools a{font-size:15px;color:var(--lz-brand-strong);text-decoration:none}.course-detail-toggle,.feedback-button{margin-top:12px}.course-detail-toggle{width:100%;justify-content:flex-start!important;background:var(--lz-surface-subtle)!important}.course-empty{padding:24px;background:var(--lz-surface-subtle);border:1px dashed var(--lz-border);border-radius:var(--lz-radius-control);margin-top:20px!important}.student-id{margin-top:20px;color:var(--lz-text-secondary);font-size:15px;overflow-wrap:anywhere}.student-id summary{cursor:pointer}.student-id code{display:block;margin-top:8px;font-size:15px}.course-update{margin-top:16px;padding:14px;border-left:3px solid var(--lz-brand);background:var(--lz-brand-soft)}.course-update button{margin-top:10px}.published-ppts{margin-top:16px;padding-top:14px;border-top:1px solid var(--lz-border)}.published-ppts h3{margin:0;font:inherit;font-size:16px;font-weight:600}.published-ppts button{margin-top:8px}.student-courses :deep(.learning-path){margin-top:12px;padding:16px;border-radius:8px;background:var(--lz-surface-subtle)}.student-courses :deep(.learning-path h2){font-size:17px}.student-courses :deep(.next-step){padding:0;background:transparent;gap:8px}.student-courses :deep(.next-step>a){margin-left:0}.student-courses :deep(.learning-path ol:empty){display:none}a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}button:disabled{opacity:.55;cursor:not-allowed}@media(max-width:900px){.student-courses{padding:24px}.course-grid{grid-template-columns:1fr}}
</style>

<style scoped>
.student-courses { max-width: 1340px; }
.course-grid { grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; align-items: start; }
.course-grid > article { padding: 18px; border-radius: 15px; border-color: rgba(203,213,225,.74); background: rgba(255,255,255,.88); box-shadow: 0 4px 14px rgba(79,70,229,.04),inset 0 1px 0 rgba(255,255,255,.94); }
.course-card-heading { display: grid; grid-template-columns: 72px minmax(0,1fr); align-items: center; gap: 14px; min-height: 110px; --course-cover-width: 72px; }
.course-card-heading h2 { margin: 0 0 7px; font-size: 19px; color: #312e81; line-height: 1.5; }
.course-card-actions { margin-top: 12px; }
.course-card-actions .course-start { padding-left: 0; padding-right: 0; background: transparent; color: var(--lz-brand-strong); font-weight: 650; border-color: transparent; }
@media(max-width:1100px) { .course-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
</style>
