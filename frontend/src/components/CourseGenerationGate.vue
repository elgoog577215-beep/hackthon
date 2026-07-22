<template>
  <aside v-if="visible" class="generation-gate" :data-step="reviewStep">
    <span class="generation-gate__icon">
      <Rocket v-if="reviewStep === 'release'" :size="17" />
      <CircleCheckBig v-else :size="17" />
    </span>
    <div class="generation-gate__copy">
      <span>{{ gateEyebrow }}</span>
      <strong>{{ gateTitle }}</strong>
      <p>{{ gateHelp }}</p>
      <small v-if="readinessLabel">{{ readinessLabel }}</small>
      <p v-if="error" class="generation-gate__error">{{ error }}</p>
    </div>
    <button
      type="button"
      :disabled="acting || loading || !canConfirm"
      @click="confirmStep"
    >
      <LoaderCircle v-if="acting || loading" :size="15" />
      <Rocket v-else :size="15" />
      {{ primaryLabel }}
    </button>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CircleCheckBig, LoaderCircle, Rocket } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import type { GuidedGenerationStepKey, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'

const props = defineProps<{
  courseId: string
  task?: Task
}>()

const emit = defineEmits<{
  (event: 'confirmed', step: Exclude<GuidedGenerationStepKey, 'requirements' | 'outline'>): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const loading = ref(false)
const acting = ref(false)
const error = ref('')
const generationReview = ref<any>(null)

const reviewStep = computed<'content' | 'release' | null>(() => {
  const step = props.task?.guidedWorkflow?.review_step
  return step === 'content' || step === 'release' ? step : null
})
const visible = computed(() => (
  props.task?.status === 'waiting_for_review'
  && Boolean(reviewStep.value)
))
const reviewArtifact = computed(() => generationReview.value?.artifact || {})
const blockingIssues = computed<any[]>(() => [
  ...(reviewArtifact.value?.blocking_issues || []),
  ...(reviewArtifact.value?.source_chain?.issues || []),
])
const canConfirm = computed(() => Boolean(generationReview.value?.can_confirm))
const gateEyebrow = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseEyebrow', '最后一步')
  : t('courseGeneration.gate.legacyEyebrow', '旧任务衔接'))
const gateTitle = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseTitle', '课程已经长成，可以确认发布')
  : t('courseGeneration.gate.legacyTitle', '正文已完成，继续准备发布'))
const gateHelp = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseHelp', '发布后练习、笔记和 AI 老师正式开放；当前生成页会原地切换为学习页。')
  : t('courseGeneration.gate.legacyHelp', '这是旧任务留下的确认点；继续后不会重新生成正文。'))
const primaryLabel = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.publish', '确认并发布')
  : t('courseGeneration.gate.continue', '继续准备发布'))
const readinessLabel = computed(() => {
  const completed = Number(
    reviewArtifact.value?.completed_count
    ?? props.task?.completedNodes
    ?? props.task?.recovery?.checkpoint?.completed_nodes
    ?? 0,
  )
  const total = Number(
    reviewArtifact.value?.section_count
    ?? props.task?.totalNodes
    ?? props.task?.recovery?.checkpoint?.total_nodes
    ?? 0,
  )
  if (reviewStep.value === 'release') {
    return t('courseGeneration.gate.releaseReadiness', '正文 {completed}/{total} · 阻断项 {blockers}')
      .replace('{completed}', String(completed))
      .replace('{total}', String(total))
      .replace('{blockers}', String(blockingIssues.value.length))
  }
  if (total) {
    return t('courseGeneration.gate.contentReadiness', '正文 {completed}/{total} 已完成')
      .replace('{completed}', String(completed))
      .replace('{total}', String(total))
  }
  return ''
})

watch(
  () => [visible.value, reviewStep.value, props.courseId],
  ([isVisible]) => {
    if (isVisible) void loadReview()
  },
  { immediate: true },
)

async function loadReview() {
  if (!props.courseId || !reviewStep.value) return
  loading.value = true
  error.value = ''
  try {
    generationReview.value = await workspace.loadGenerationReview(props.courseId)
  } catch {
    error.value = t('courseGeneration.gate.loadFailed', '当前确认内容读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function confirmStep() {
  const step = reviewStep.value
  if (!step || !canConfirm.value || acting.value) return
  acting.value = true
  error.value = ''
  try {
    await workspace.confirmGenerationStep(props.courseId, step)
    generationStore.startGlobalMonitor()
    await courseStore.refreshCourseData(props.courseId)
    ElMessage.success(step === 'release'
      ? t('courseGeneration.gate.publishing', '已确认发布，正在完成最后保存')
      : t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
    emit('confirmed', step)
  } catch {
    error.value = step === 'release'
      ? t('courseGeneration.gate.publishFailed', '发布确认失败，请查看阻断项后重试。')
      : t('courseGeneration.gate.confirmFailed', '确认失败，请稍后重试。')
  } finally {
    acting.value = false
  }
}
</script>

<style scoped>
.generation-gate {
  position:relative;
  z-index:4;
  flex:0 0 auto;
  display:grid;
  grid-template-columns:42px minmax(0,1fr) auto;
  align-items:center;
  gap:15px;
  margin:0;
  padding:14px clamp(18px,3vw,42px) 15px;
  border-top:1px solid #dce3e2;
  background:linear-gradient(90deg,rgba(247,251,249,.98),rgba(252,253,253,.98) 58%,#fff);
  box-shadow:0 -12px 30px rgba(30,41,59,.065);
}
.generation-gate__icon {
  width:42px;
  height:42px;
  display:grid;
  place-items:center;
  border:1px solid #cde2da;
  border-radius:12px;
  color:#087a5b;
  background:#eef8f4;
}
.generation-gate__copy {
  min-width:0;
  display:grid;
  grid-template-columns:auto minmax(0,1fr);
  align-items:baseline;
  gap:3px 10px;
}
.generation-gate__copy > span {
  color:#26715d;
  font-size:11px;
  font-weight:850;
  letter-spacing:.07em;
}
.generation-gate__copy strong {
  overflow:hidden;
  color:#263144;
  font-size:15px;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.generation-gate__copy p {
  grid-column:1/-1;
  margin:0;
  color:#727d8f;
  font-size:12px;
  line-height:1.5;
}
.generation-gate__copy small {
  grid-column:1/-1;
  width:max-content;
  margin-top:5px;
  padding:4px 8px;
  border-radius:999px;
  color:#346b5b;
  background:#edf7f3;
  font-size:11px;
  font-weight:750;
}
.generation-gate__copy p.generation-gate__error { color:#b42318; }
.generation-gate > button {
  min-height:44px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 18px;
  border:1px solid #087a5b;
  border-radius:10px;
  color:#fff;
  background:linear-gradient(135deg,#0a8061,#2e8c70);
  box-shadow:0 8px 20px rgba(8,122,91,.2);
  font-size:13px;
  font-weight:800;
  cursor:pointer;
}
.generation-gate > button:disabled { opacity:.5; box-shadow:none; cursor:not-allowed; }
.generation-gate > button:not(:disabled):hover { transform:translateY(-1px); box-shadow:0 10px 24px rgba(8,122,91,.24); }
.generation-gate > button svg.lucide-loader-circle { animation:gate-spin .85s linear infinite; }
@keyframes gate-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .generation-gate {
    grid-template-columns:36px minmax(0,1fr);
    align-items:start;
    gap:10px;
    padding:12px 10px calc(12px + env(safe-area-inset-bottom,0px));
  }
  .generation-gate__icon { width:36px; height:36px; border-radius:10px; }
  .generation-gate__copy { grid-template-columns:1fr; gap:2px; }
  .generation-gate__copy strong,.generation-gate__copy p,.generation-gate__copy small { grid-column:1; }
  .generation-gate__copy strong { white-space:normal; }
  .generation-gate > button { grid-column:1/-1; width:100%; }
}
@media (prefers-reduced-motion:reduce) {
  .generation-gate > button svg { animation:none!important; }
}
</style>
