<template>
  <nav class="course-workflow-bar" aria-label="启智课程闭环导航">
    <button type="button" class="workflow-brand" title="返回课程闭环总览" @click="openStep('overview')">
      <img src="/qizhi-favicon.svg" alt="" />
      <span><strong>启智课程闭环</strong><small>{{ courseTitle }}</small></span>
    </button>

    <div class="workflow-steps" role="list" aria-label="课程闭环步骤">
      <template v-for="(step, index) in steps" :key="step.key">
        <button
          type="button"
          class="workflow-step"
          :class="{ active: activeStep === step.key, complete: isComplete(step.key) }"
          :aria-current="activeStep === step.key ? 'step' : undefined"
          :title="step.description"
          @click="openStep(step.key)"
        >
          <span class="workflow-step__icon"><component :is="step.icon" :size="14" /></span>
          <span class="workflow-step__copy"><small>0{{ index + 1 }}</small><strong>{{ step.label }}</strong></span>
        </button>
        <ArrowRight v-if="index < steps.length - 1" class="workflow-arrow" :size="13" aria-hidden="true" />
      </template>
    </div>

    <div class="workflow-status" :class="statusTone" :title="statusDescription">
      <Link2 :size="13" /><span>{{ statusLabel }}</span>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, BookOpenText, LayoutDashboard, Link2, Presentation, Sparkles } from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useCourseEvolutionStore } from '../stores/courseEvolution'
import { peekPptSameSourceHighlight, type PptSameSourceHighlightState } from '../utils/ppt-same-source'

type WorkflowStep = 'overview' | 'design' | 'learning' | 'growth'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const evolutionStore = useCourseEvolutionStore()
const syncState = ref<PptSameSourceHighlightState | null>(null)

const steps = computed<Array<{ key: WorkflowStep; label: string; description: string; icon: Component }>>(() => [
  { key: 'overview', label: '统一课程源', description: '查看教师设计、学生学习与课程生长如何衔接', icon: LayoutDashboard },
  { key: 'design', label: '教学设计', description: '编辑 PPT 并分析对教案、正文与练习的影响', icon: Presentation },
  { key: 'learning', label: '学习现场', description: '查看同源修改如何进入学生正在学习的课程', icon: BookOpenText },
  { key: 'growth', label: '课程生长', description: '根据真实学习证据生成并确认个体化课程更新', icon: Sparkles },
])

const courseId = computed(() => String(route.params.courseId || courseStore.currentCourseId || ''))
const courseTitle = computed(() => courseStore.currentCourse?.course_name
  || (courseId.value === 'demo-matrix-growth-v2' ? '矩阵与线性变换' : '当前课程'))
const activeStep = computed<WorkflowStep>(() => {
  if (route.name === 'course-workbench') return 'overview'
  if (route.name === 'ppt-workspace') return 'design'
  if (route.query.surface === 'growth') return 'growth'
  return 'learning'
})
const appliedGrowthCount = computed(() => evolutionStore.courseId === courseId.value ? evolutionStore.appliedPlans.length : 0)
const statusTone = computed(() => appliedGrowthCount.value ? 'is-growth' : syncState.value ? 'is-synced' : 'is-source')
const statusLabel = computed(() => {
  if (appliedGrowthCount.value) return `已应用 ${appliedGrowthCount.value} 个生长方案`
  if (syncState.value) return 'PPT 改动已交接到课程'
  return 'PPT、正文与学习进度同源'
})
const statusDescription = computed(() => {
  if (appliedGrowthCount.value) return '学习证据已形成课程更新，仍可回到任一步查看或继续调整。'
  if (syncState.value) return '修改前后内容和目标位置已保留，可直接进入课程核对。'
  return '所有入口都指向同一个课程文档，不会复制出两套互不相干的数据。'
})

function refreshSyncState() {
  syncState.value = courseId.value ? peekPptSameSourceHighlight(sessionStorage, courseId.value) : null
}
function isComplete(step: WorkflowStep) {
  if (step === 'overview') return true
  if (step === 'design') return Boolean(syncState.value)
  if (step === 'learning') return Boolean(syncState.value?.animationPlayed || appliedGrowthCount.value)
  return appliedGrowthCount.value > 0
}
function openStep(step: WorkflowStep) {
  const id = courseId.value
  if (!id) return
  if (step === 'overview') {
    void router.push({ name: 'course-workbench', params: { courseId: id } })
    return
  }
  if (step === 'design') {
    void router.push({ name: 'ppt-workspace', params: { courseId: id } })
    return
  }
  const nodeId = syncState.value?.sectionId || String(route.params.nodeId || courseStore.currentNode?.node_id || '')
  void router.push({
    name: 'learning',
    params: { courseId: id, ...(nodeId ? { nodeId } : {}) },
    query: step === 'growth' ? { surface: 'growth' } : {},
  })
}

watch(() => [route.fullPath, courseId.value], refreshSyncState, { immediate: true })
</script>

<style scoped>
.course-workflow-bar { position:relative; z-index:90; min-width:0; height:52px; display:grid; grid-template-columns:minmax(190px,1fr) minmax(470px,auto) minmax(190px,1fr); align-items:center; gap:14px; padding:0 14px; border:1px solid rgba(205,215,229,.92); border-radius:14px; color:#203047; background:rgba(255,255,255,.96); box-shadow:0 8px 24px rgba(33,55,91,.08); backdrop-filter:blur(14px); }
.workflow-brand,.workflow-step { border:0; font:inherit; cursor:pointer; }
.workflow-brand { min-width:0; display:flex; align-items:center; gap:9px; padding:0; color:inherit; background:transparent; text-align:left; }
.workflow-brand img { width:27px; height:27px; flex:0 0 27px; border-radius:8px; box-shadow:0 5px 12px rgba(37,86,216,.18); }
.workflow-brand > span { min-width:0; display:flex; flex-direction:column; }
.workflow-brand strong { color:#17325f; font-size:12px; line-height:1.25; }
.workflow-brand small { overflow:hidden; margin-top:2px; color:#718096; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.workflow-steps { min-width:0; display:flex; align-items:center; justify-content:center; gap:5px; }
.workflow-step { min-width:0; height:38px; display:flex; align-items:center; gap:7px; padding:0 9px; border-radius:9px; color:#66758a; background:transparent; transition:color .18s ease,background .18s ease,transform .18s ease; }
.workflow-step:hover { color:#2556d8; background:#f2f6ff; transform:translateY(-1px); }
.workflow-step.active { color:#173f9d; background:#eaf0ff; box-shadow:inset 0 0 0 1px #cad8ff; }
.workflow-step__icon { width:25px; height:25px; flex:0 0 25px; display:grid; place-items:center; border:1px solid #dce3ed; border-radius:8px; color:#66758a; background:#fff; }
.workflow-step.active .workflow-step__icon { border-color:#9eb7fb; color:#fff; background:#2556d8; }
.workflow-step.complete:not(.active) .workflow-step__icon { border-color:#f0d278; color:#8a5b00; background:#fff9dc; }
.workflow-step__copy { display:flex; flex-direction:column; align-items:flex-start; }
.workflow-step__copy small { font-size:7px; font-weight:800; letter-spacing:.12em; opacity:.58; }
.workflow-step__copy strong { font-size:10px; line-height:1.2; white-space:nowrap; }
.workflow-arrow { flex:0 0 auto; color:#bdc7d5; }
.workflow-status { min-width:0; justify-self:end; display:flex; align-items:center; gap:6px; padding:6px 9px; border-radius:999px; font-size:9px; font-weight:750; white-space:nowrap; }
.workflow-status.is-source { color:#315a95; background:#edf5ff; }
.workflow-status.is-synced { color:#7a5300; background:#fff7d6; }
.workflow-status.is-growth { color:#6d28a8; background:#f6edff; }
@media (max-width:1120px) { .course-workflow-bar { grid-template-columns:38px minmax(0,1fr) auto; gap:8px; } .workflow-brand > span,.workflow-step__copy small { display:none; } }
@media (max-width:760px) { .course-workflow-bar { grid-template-columns:32px minmax(0,1fr); padding:0 8px; border-radius:10px; } .workflow-brand img { width:25px; height:25px; } .workflow-status,.workflow-step__copy,.workflow-arrow { display:none; } .workflow-steps { justify-content:space-between; gap:1px; } .workflow-step { width:25%; justify-content:center; padding:0 3px; } }
</style>
