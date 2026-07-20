<template>
  <template v-if="visible">
    <aside class="generation-gate" :data-step="reviewStep">
      <div>
        <span>{{ gateEyebrow }}</span>
        <strong>{{ gateTitle }}</strong>
        <p>{{ gateHelp }}</p>
        <p v-if="error" class="generation-gate__error">{{ error }}</p>
      </div>
      <button
        type="button"
        :disabled="acting || loading || (reviewStep === 'release' && !canConfirm)"
        @click="handlePrimary"
      >
        <LoaderCircle v-if="acting || loading" :size="15" />
        <ListChecks v-else-if="reviewStep === 'outline'" :size="15" />
        <Rocket v-else :size="15" />
        {{ primaryLabel }}
      </button>
    </aside>

    <Teleport to="body">
      <Transition name="gate-dialog">
        <section
          v-if="editorOpen"
          class="generation-outline-dialog"
          role="dialog"
          aria-modal="true"
          :aria-label="t('courseGeneration.gate.outlineTitle', '检查并确认课程目录')"
          @keydown.esc="editorOpen = false"
        >
          <button class="generation-outline-dialog__backdrop" type="button" :aria-label="t('common.close', '关闭')" @click="editorOpen = false" />
          <div class="generation-outline-dialog__card">
            <header>
              <div>
                <span>{{ t('courseGeneration.gate.outlineEyebrow', '生成关卡 02') }}</span>
                <h2>{{ t('courseGeneration.gate.outlineTitle', '检查并确认课程目录') }}</h2>
                <p>{{ t('courseGeneration.gate.outlineHelp', '这里确认讲什么；确认后系统先冻结全课知识职责，再按预算生成详细教案与正文。') }}</p>
              </div>
              <button type="button" :aria-label="t('common.close', '关闭')" @click="editorOpen = false"><X :size="18" /></button>
            </header>

            <main>
              <label class="generation-outline-dialog__name">
                <span>{{ t('courseWorkspace.blueprint.courseName', '课程名称') }}</span>
                <input v-model="blueprintDraft.course_name" type="text" />
              </label>
              <div class="generation-outline-dialog__nodes">
                <article v-for="(node, index) in blueprintNodes" :key="node.node_id || index">
                  <span>{{ String(index + 1).padStart(2, '0') }}</span>
                  <div>
                    <input v-model="node.node_name" type="text" :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')" />
                    <textarea
                      v-if="'learning_objective' in node"
                      v-model="node.learning_objective"
                      :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                    />
                  </div>
                </article>
              </div>
            </main>

            <footer>
              <p>{{ t('courseGeneration.gate.outlineGuard', '确认前可修改名称和目标；确认后教案、知识绑定与正文将以此目录为准。') }}</p>
              <div>
                <button type="button" class="secondary" :disabled="acting" @click="editorOpen = false">{{ t('common.cancel', '取消') }}</button>
                <button type="button" class="primary" :disabled="acting || !blueprintNodes.length" @click="confirmOutline">
                  <LoaderCircle v-if="acting" :size="15" />
                  <CircleCheck v-else :size="15" />
                  {{ t('courseGeneration.gate.confirmOutline', '确认目录并继续') }}
                </button>
              </div>
            </footer>
          </div>
        </section>
      </Transition>
    </Teleport>
  </template>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CircleCheck, ListChecks, LoaderCircle, Rocket, X } from 'lucide-vue-next'
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
  (event: 'confirmed', step: Exclude<GuidedGenerationStepKey, 'requirements'>): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const editorOpen = ref(false)
const loading = ref(false)
const acting = ref(false)
const error = ref('')
const blueprintDraft = ref<any>({})
const generationReview = ref<any>(null)

const reviewStep = computed(() => (
  props.task?.guidedWorkflow?.review_step || null
))
const visible = computed(() => (
  props.task?.status === 'waiting_for_review'
  && ['outline', 'content', 'release'].includes(String(reviewStep.value || ''))
))
const blueprintNodes = computed<any[]>(() => Array.isArray(blueprintDraft.value?.nodes)
  ? blueprintDraft.value.nodes
  : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes)
    ? blueprintDraft.value.course_blueprint.nodes
    : [])
const canConfirm = computed(() => (
  reviewStep.value === 'outline'
    ? Boolean(blueprintDraft.value)
    : Boolean(generationReview.value?.can_confirm)
))
const gateEyebrow = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseEyebrow', '最后一步')
  : reviewStep.value === 'content'
    ? t('courseGeneration.gate.legacyEyebrow', '旧任务衔接')
    : t('courseGeneration.gate.outlineEyebrow', '生成关卡 02'))
const gateTitle = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseTitle', '课程已经长成，可以确认发布')
  : reviewStep.value === 'content'
    ? t('courseGeneration.gate.legacyTitle', '正文已完成，继续准备发布')
    : t('courseGeneration.gate.outlineReadyTitle', '目录已生成，等待你的确认'))
const gateHelp = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.releaseHelp', '发布后练习、笔记和 AI 老师正式开放；当前生成页会原地切换为学习页。')
  : reviewStep.value === 'content'
    ? t('courseGeneration.gate.legacyHelp', '这是旧任务留下的确认点；继续后不会重新生成正文。')
    : t('courseGeneration.gate.outlineReadyHelp', '确认后一次生成整门课教案，并同时编译知识库，再并行生成各节正文。'))
const primaryLabel = computed(() => reviewStep.value === 'release'
  ? t('courseGeneration.gate.publish', '确认并发布')
  : reviewStep.value === 'content'
    ? t('courseGeneration.gate.continue', '继续准备发布')
    : t('courseGeneration.gate.reviewOutline', '检查并确认目录'))

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
    if (reviewStep.value === 'outline') {
      const data = await workspace.loadBlueprint(props.courseId)
      blueprintDraft.value = JSON.parse(JSON.stringify(data.draft || data.current || data))
    }
  } catch {
    error.value = t('courseGeneration.gate.loadFailed', '当前确认内容读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function handlePrimary() {
  if (reviewStep.value === 'outline') {
    editorOpen.value = true
    return
  }
  if (reviewStep.value === 'content' || reviewStep.value === 'release') {
    void confirmStep(reviewStep.value)
  }
}

async function confirmOutline() {
  const draft = blueprintDraft.value
  if (!draft) return
  acting.value = true
  error.value = ''
  try {
    if (draft.base_blueprint_revision_id) {
      await workspace.saveBlueprint(props.courseId, {
        base_blueprint_revision_id: draft.base_blueprint_revision_id,
        course_name: draft.course_name,
        course_purpose: draft.course_purpose,
        course_blueprint: draft.course_blueprint,
        nodes: draft.nodes,
        learning_asset_plan: draft.learning_asset_plan,
        blueprint_locks: draft.blueprint_locks || {},
      })
    }
    await workspace.confirmGenerationStep(props.courseId, 'outline')
    editorOpen.value = false
    await afterConfirmed('outline')
  } catch {
    error.value = t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。')
  } finally {
    acting.value = false
  }
}

async function confirmStep(step: 'content' | 'release') {
  if (!canConfirm.value || acting.value) return
  acting.value = true
  error.value = ''
  try {
    await workspace.confirmGenerationStep(props.courseId, step)
    await afterConfirmed(step)
  } catch {
    error.value = step === 'release'
      ? t('courseGeneration.gate.publishFailed', '发布确认失败，请查看阻断项后重试。')
      : t('courseGeneration.gate.confirmFailed', '确认失败，请稍后重试。')
  } finally {
    acting.value = false
  }
}

async function afterConfirmed(step: 'outline' | 'content' | 'release') {
  generationStore.startGlobalMonitor()
  await courseStore.refreshCourseData(props.courseId)
  ElMessage.success(step === 'release'
    ? t('courseGeneration.gate.publishing', '已确认发布，正在完成最后保存')
    : t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
  emit('confirmed', step)
}
</script>

<style scoped>
.generation-gate { position:absolute; z-index:45; left:18px; right:18px; bottom:16px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:12px 14px 12px 16px; border:1px solid #d9dded; border-radius:12px; background:rgba(255,255,255,.96); box-shadow:0 16px 38px rgba(30,41,59,.16); backdrop-filter:blur(10px); }
.generation-gate > div { min-width:0; display:grid; grid-template-columns:auto 1fr; align-items:baseline; gap:2px 8px; }
.generation-gate span { color:#6268ce; font-size:8px; font-weight:850; letter-spacing:.07em; text-transform:uppercase; }
.generation-gate strong { color:#263144; font-size:12px; }
.generation-gate p { grid-column:1/-1; margin:0; color:#727d8f; font-size:9px; line-height:1.45; }
.generation-gate p.generation-gate__error { color:#b42318; }
.generation-gate > button { min-height:36px; flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 14px; border:1px solid #4f46e5; border-radius:8px; color:#fff; background:#4f46e5; font-size:10px; font-weight:800; cursor:pointer; }
.generation-gate > button:disabled { opacity:.55; cursor:not-allowed; }
.generation-gate > button svg { animation:gate-spin .85s linear infinite; }
.generation-gate > button svg:not(.lucide-loader-circle) { animation:none; }
.generation-outline-dialog { position:fixed; inset:0; z-index:1600; display:grid; place-items:center; padding:24px; }
.generation-outline-dialog__backdrop { position:absolute; inset:0; width:100%; height:100%; border:0; background:rgba(21,29,45,.48); backdrop-filter:blur(6px); }
.generation-outline-dialog__card { position:relative; z-index:1; width:min(780px,calc(100vw - 32px)); max-height:min(86vh,820px); display:grid; grid-template-rows:auto minmax(0,1fr) auto; overflow:hidden; border:1px solid rgba(255,255,255,.8); border-radius:16px; background:#f9fafc; box-shadow:0 30px 80px rgba(15,23,42,.28); }
.generation-outline-dialog__card > header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; padding:20px 22px 17px; border-bottom:1px solid #e2e6ed; background:#fff; }
.generation-outline-dialog__card > header span { color:#5f65cc; font-size:8px; font-weight:850; letter-spacing:.08em; }
.generation-outline-dialog__card > header h2 { margin:4px 0 3px; color:#1f2937; font-size:19px; }
.generation-outline-dialog__card > header p { margin:0; color:#697386; font-size:10px; }
.generation-outline-dialog__card > header button { width:32px; height:32px; display:grid; place-items:center; border:0; border-radius:7px; color:#697386; background:#f4f5f7; cursor:pointer; }
.generation-outline-dialog__card > main { min-height:0; overflow:auto; padding:18px 22px 24px; }
.generation-outline-dialog__name span { display:block; margin-bottom:5px; color:#697386; font-size:9px; }
.generation-outline-dialog__name input,.generation-outline-dialog__nodes input,.generation-outline-dialog__nodes textarea { width:100%; border:1px solid #dce1e9; border-radius:7px; color:#263144; background:#fff; outline:none; }
.generation-outline-dialog__name input { height:38px; padding:0 10px; font-size:12px; font-weight:750; }
.generation-outline-dialog__nodes { display:grid; gap:8px; margin-top:14px; }
.generation-outline-dialog__nodes article { display:grid; grid-template-columns:30px minmax(0,1fr); gap:8px; padding:10px; border:1px solid #e2e6ed; border-radius:9px; background:#fff; }
.generation-outline-dialog__nodes article > span { padding-top:9px; color:#8c95a5; font:700 9px ui-monospace,SFMono-Regular,monospace; }
.generation-outline-dialog__nodes input { height:34px; padding:0 8px; font-size:11px; font-weight:700; }
.generation-outline-dialog__nodes textarea { min-height:52px; margin-top:6px; padding:7px 8px; resize:vertical; font-size:10px; line-height:1.45; }
.generation-outline-dialog__name input:focus,.generation-outline-dialog__nodes input:focus,.generation-outline-dialog__nodes textarea:focus { border-color:#7c83ee; box-shadow:0 0 0 3px rgba(99,102,241,.08); }
.generation-outline-dialog__card > footer { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:13px 18px; border-top:1px solid #e2e6ed; background:#fff; }
.generation-outline-dialog__card > footer p { margin:0; color:#7b8495; font-size:9px; line-height:1.45; }
.generation-outline-dialog__card > footer > div { flex:0 0 auto; display:flex; gap:7px; }
.generation-outline-dialog__card > footer button { min-height:35px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 13px; border-radius:8px; font-size:10px; font-weight:800; cursor:pointer; }
.generation-outline-dialog__card > footer .secondary { border:1px solid #d9dee7; color:#596579; background:#fff; }
.generation-outline-dialog__card > footer .primary { border:1px solid #4f46e5; color:#fff; background:#4f46e5; }
.generation-outline-dialog__card > footer button:disabled { opacity:.55; cursor:not-allowed; }
.gate-dialog-enter-active,.gate-dialog-leave-active { transition:opacity .18s ease; }.gate-dialog-enter-from,.gate-dialog-leave-to { opacity:0; }
@keyframes gate-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .generation-gate { left:8px; right:8px; bottom:8px; align-items:stretch; flex-direction:column; gap:8px; padding:10px; }
  .generation-gate > button { width:100%; }
  .generation-outline-dialog { padding:0; }
  .generation-outline-dialog__card { width:100%; max-height:100dvh; height:100dvh; border:0; border-radius:0; }
  .generation-outline-dialog__card > footer { align-items:stretch; flex-direction:column; }
  .generation-outline-dialog__card > footer > div { display:grid; grid-template-columns:.75fr 1.25fr; }
}
@media (prefers-reduced-motion:reduce) {
  .generation-gate > button svg,.gate-dialog-enter-active,.gate-dialog-leave-active { animation:none; transition:none; }
}
</style>
