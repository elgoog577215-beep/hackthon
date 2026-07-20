<template>
  <aside class="production-notice" :data-state="status" role="status" aria-live="polite">
    <span class="production-notice__icon">
      <CirclePause v-if="status === 'paused'" :size="17" />
      <GitCompareArrows v-else-if="status === 'conflict'" :size="17" />
      <TriangleAlert v-else :size="17" />
    </span>
    <div class="production-notice__copy">
      <div>
        <strong>{{ title }}</strong>
        <span>{{ t('courseGeneration.production.savedContentVisible', '已完成内容仍可查看') }}</span>
      </div>
      <p>{{ friendlyError }} {{ recoveryDetail }}</p>
      <details v-if="technicalError">
        <summary>{{ t('courseGeneration.production.technicalReason', '查看技术原因') }}</summary>
        <code>{{ technicalError }}</code>
      </details>
    </div>
    <button v-if="canResume" type="button" :disabled="acting" @click="emit('resume')">
      <LoaderCircle v-if="acting" :size="15" />
      <RotateCw v-else :size="15" />
      {{ resumeLabel }}
    </button>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CirclePause, GitCompareArrows, LoaderCircle, RotateCw, TriangleAlert } from 'lucide-vue-next'
import type { Task } from '../stores/types'
import { t } from '../shared/i18n'
import { canResumeCourseProduction, courseProductionRecoveryDetail } from '../utils/course-production'

const props = withDefaults(defineProps<{
  task?: Task
  acting?: boolean
}>(), {
  task: undefined,
  acting: false,
})

const emit = defineEmits<{
  (event: 'resume'): void
}>()

const status = computed(() => String(props.task?.status || 'error'))
const canResume = computed(() => canResumeCourseProduction(props.task))
const recoveryDetail = computed(() => courseProductionRecoveryDetail(props.task))
const technicalError = computed(() => String(props.task?.error || '').trim())
const title = computed(() => {
  if (status.value === 'paused') return t('courseGeneration.production.pausedTitle', '课程生产已暂停')
  if (status.value === 'conflict') return t('courseGeneration.production.blockedTitle', '课程生产需要处理冲突')
  return t('courseGeneration.production.interruptedTitle', '课程生产暂时中断')
})
const friendlyError = computed(() => {
  const error = technicalError.value.toLowerCase()
  if (/authentication|credential|api[_ -]?key/.test(error)) {
    return t('courseGeneration.production.authError', 'AI 服务暂时无法完成身份校验。')
  }
  if (/timeout|timed out/.test(error)) {
    return t('courseGeneration.production.timeoutError', 'AI 服务响应超时，本阶段尚未完成。')
  }
  if (/unavailable|connection|network/.test(error)) {
    return t('courseGeneration.production.unavailableError', 'AI 服务暂时不可用，本阶段尚未完成。')
  }
  if (status.value === 'paused') return t('courseGeneration.production.pausedDescription', '当前模型调用已经停止。')
  if (status.value === 'conflict') return t('courseGeneration.production.blockedDescription', '当前产物与课程真源存在冲突。')
  return t('courseGeneration.production.genericError', '本阶段尚未完成。')
})
const resumeLabel = computed(() => status.value === 'paused'
  ? t('courseGeneration.production.continueAction', '继续课程生产')
  : t('courseGeneration.production.retryAction', '重试当前阶段'))
</script>

<style scoped>
.production-notice {
  flex:0 0 auto;
  display:grid;
  grid-template-columns:32px minmax(0,1fr) auto;
  align-items:start;
  gap:11px;
  margin:12px clamp(14px,3vw,38px) 0;
  padding:11px 12px;
  border:1px solid #efd3a8;
  border-radius:10px;
  color:#75431c;
  background:#fffbf3;
}
.production-notice[data-state="paused"] {
  border-color:#d8dde5;
  color:#4b5565;
  background:#f7f8fa;
}
.production-notice[data-state="conflict"] {
  border-color:#e9c8a5;
  background:#fff8ef;
}
.production-notice__icon {
  width:32px;
  height:32px;
  display:grid;
  place-items:center;
  border-radius:8px;
  color:#b54708;
  background:#fff1db;
}
.production-notice[data-state="paused"] .production-notice__icon {
  color:#667085;
  background:#e9ecf1;
}
.production-notice__copy { min-width:0; }
.production-notice__copy > div {
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:7px;
}
.production-notice__copy strong { color:#643713; font-size:10px; }
.production-notice[data-state="paused"] .production-notice__copy strong { color:#344054; }
.production-notice__copy > div span {
  padding:2px 6px;
  border-radius:999px;
  color:#7b5b3e;
  background:rgba(255,255,255,.72);
  font-size:8px;
  font-weight:750;
}
.production-notice__copy p {
  margin:3px 0 0;
  color:#84664c;
  font-size:9px;
  line-height:1.55;
}
.production-notice[data-state="paused"] .production-notice__copy p { color:#697386; }
.production-notice details { margin-top:5px; color:#8a6b4f; font-size:8px; }
.production-notice summary { width:max-content; cursor:pointer; }
.production-notice code {
  display:block;
  max-height:90px;
  margin-top:5px;
  padding:6px 8px;
  overflow:auto;
  border-left:2px solid #d89b43;
  background:rgba(255,255,255,.72);
  white-space:pre-wrap;
}
.production-notice > button {
  min-height:34px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 12px;
  border:1px solid #a85b1a;
  border-radius:7px;
  color:#fff;
  background:#a85b1a;
  font-size:9px;
  font-weight:800;
  cursor:pointer;
}
.production-notice > button:disabled { opacity:.55; cursor:wait; }
.production-notice > button svg.lucide-loader-circle { animation:production-notice-spin .9s linear infinite; }
@keyframes production-notice-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .production-notice {
    grid-template-columns:30px minmax(0,1fr);
    margin:9px 9px 0;
  }
  .production-notice > button {
    grid-column:1/-1;
    width:100%;
  }
}
@media (prefers-reduced-motion:reduce) {
  .production-notice > button svg { animation:none!important; }
}
</style>
