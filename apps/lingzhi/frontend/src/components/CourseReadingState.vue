<template>
  <section class="course-reading-state" :role="error && !loading ? 'alert' : 'status'" aria-live="polite">
    <template v-if="loading">
      <LoaderCircle class="course-reading-state__spinner" :size="28" aria-hidden="true" />
      <p>{{ t('courseWorkspace.readingState.loading', '正在加载课程内容…') }}</p>
    </template>
    <template v-else-if="error">
      <TriangleAlert :size="30" aria-hidden="true" />
      <h2>{{ t('courseWorkspace.readingState.failed', '课程加载失败') }}</h2>
      <p>{{ error }}</p>
      <div class="course-reading-state__actions">
        <button type="button" class="lz-action-button" @click="emit('retry')">{{ t('courseWorkspace.readingState.retry', '重新加载') }}</button>
        <button v-if="teacherPreview" type="button" class="lz-action-button" @click="emit('returnWorkbench')">{{ t('courseWorkspaceFlow.returnWorkbench', '返回备课工作台') }}</button>
      </div>
    </template>
    <template v-else-if="generationPreview">
      <LoaderCircle class="course-reading-state__spinner" :size="28" aria-hidden="true" />
      <h2>{{ t('courseGeneration.workspace.preparing', '正在准备课程结构') }}</h2>
      <p>{{ t('courseGeneration.workspace.contentWillAppear', '目录与正文会随着真实生成结果逐步出现') }}</p>
    </template>
    <template v-else-if="courseSelected">
      <BookOpen :size="30" aria-hidden="true" />
      <h2>{{ teacherPreview ? t('courseWorkspace.readingState.previewEmpty', '暂无可试读的讲义') : t('courseWorkspace.readingState.empty', '暂无可阅读内容') }}</h2>
      <p>{{ teacherPreview ? t('courseWorkspace.readingState.previewEmptyHelp', '这门课程还没有可试读的讲义内容，请返回备课工作台准备讲义。') : t('courseWorkspace.readingState.emptyHelp', '这门课程目前没有可阅读内容。') }}</p>
      <button v-if="teacherPreview" type="button" class="lz-action-button" @click="emit('returnWorkbench')">{{ t('courseWorkspaceFlow.returnWorkbench', '返回备课工作台') }}</button>
    </template>
    <template v-else>
      <BookOpen :size="30" aria-hidden="true" />
      <h2>{{ t('courseWorkspace.readingState.selectCourse', '开始您的学习之旅') }}</h2>
      <p>{{ t('courseWorkspace.readingState.selectCourseHelp', '请从左侧选择一个课程或章节开始阅读') }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { BookOpen, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import { t } from '@/shared/i18n'

defineProps<{
  loading: boolean
  error: string | null
  courseSelected: boolean
  teacherPreview?: boolean
  generationPreview?: boolean
}>()
const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'returnWorkbench'): void
}>()
</script>

<style scoped>
.course-reading-state { min-height: 280px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 40px 24px; color: #7b88a3; text-align: center; }
.course-reading-state h2 { margin: 0; color: #465575; font-size: 19px; font-weight: 600; }
.course-reading-state p { max-width: 540px; margin: 0; font-size: 15px; line-height: 1.8; }
.course-reading-state__actions { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; }
.course-reading-state .lz-action-button { padding: 10px 18px; font-size: 15px; }
.course-reading-state__spinner { color: #7e79d2; animation: reading-state-spin 1s linear infinite; }
@keyframes reading-state-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .course-reading-state__spinner { animation: none; } }
</style>
