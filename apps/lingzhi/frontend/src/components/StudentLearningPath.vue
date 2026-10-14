<template>
  <section class="learning-path"><h2>{{ title }} · {{ copy('我的学习路径', 'My learning path') }}</h2><p>{{ copy('根据已保存的学习位置、阅读、练习和待处理问题更新。没有检查证据时保持未评估。', 'Updated from your saved position, reading, attempts and open issues. Unchecked knowledge remains unassessed.') }}</p><p v-if="error" role="alert">{{ error }}</p><template v-if="path"><div class="next-step"><strong>{{ copy('建议下一步', 'Suggested next step') }}：{{ actionLabel(path.next_action.action_type) }}</strong><span>{{ path.chapter.chapter_name }} · {{ path.attempt_count }} {{ copy('次正式作答', 'saved attempts') }}</span><RouterLink :to="link(path.next_action.node_id || path.chapter.chapter_id, path.next_action.action_type)">{{ copy('继续学习', 'Continue learning') }} →</RouterLink></div><ol><li v-for="step in path.steps" :key="step.chapter_id"><div><strong>{{ step.title }}</strong><span>{{ actionLabel(step.action.action_type) }}</span></div><RouterLink :to="link(step.action.node_id || step.chapter_id, step.action.action_type)">{{ copy('进入', 'Open') }}</RouterLink></li></ol></template></section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { studyApi, type StudyLearningPath } from '../api/study'
import { activeLocale } from '../shared/i18n'
import { learningActionLabel } from '../utils/learning-action'
const props = defineProps<{ courseId: string; title: string }>()
const path = ref<StudyLearningPath | null>(null), error = ref('')
const copy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
const actionLabel = learningActionLabel
const link = (node: string, actionType = '') => ({
  path: `/course/${props.courseId}/learn/${encodeURIComponent(node || '')}`,
  query: { returnTo: '/study?view=courses', ...(actionType ? { learningAction: actionType } : {}) },
})
let sequence = 0
watch(() => props.courseId, async id => { const current = ++sequence; path.value = null; error.value = ''; try { const result = await studyApi.path(id); if (current === sequence) path.value = result } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : copy('读取失败', 'Could not load path') } }, { immediate: true })
onBeforeUnmount(() => { sequence++ })
</script>
<style scoped>
.learning-path{margin-top:30px;padding:25px;background:white;border:1px solid #e1e5ef;border-radius:16px;font-size:15px}.learning-path h2{font-size:21px}.learning-path p,.learning-path span{color:#748096}.next-step{display:flex;flex-wrap:wrap;align-items:center;gap:14px;background:#f3effc;padding:18px;border-radius:10px}.next-step a{margin-left:auto}ol{padding-left:22px}li{padding:14px 0;border-bottom:1px solid #edf0f6;display:flex;justify-content:space-between;gap:15px}li span{display:block;margin-top:4px}a{color:#6551c7;text-decoration:none}a:focus-visible{outline:3px solid #9385ed;outline-offset:3px}
</style>
