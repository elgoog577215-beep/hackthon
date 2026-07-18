<template>
  <Teleport to="body">
    <div v-if="modelValue" class="generation-dialog-layer" @keydown.esc="close">
      <button
        type="button"
        class="generation-dialog-backdrop"
        :aria-label="t('common.cancel', '取消')"
        @click="close"
      />
      <section
        ref="dialogRef"
        class="generation-dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="generation-dialog__header">
          <div class="generation-dialog__heading">
            <span class="generation-dialog__mark"><Sparkles :size="18" /></span>
            <div>
              <p>{{ t('courseGeneration.dialog.eyebrow', '创建学习课程') }}</p>
              <h2 :id="titleId">{{ t('courseGeneration.dialog.title', 'AI 智能课程生成') }}</h2>
            </div>
          </div>
          <button type="button" class="icon-button" :title="t('common.cancel', '取消')" @click="close">
            <X :size="18" />
          </button>
        </header>

        <form class="generation-dialog__body" @submit.prevent="submit">
          <section class="form-section form-section--lead">
            <label class="field-label" for="course-subject">
              {{ t('courseGeneration.form.topic', '课程主题') }}
            </label>
            <input
              id="course-subject"
              v-model="form.subject"
              class="text-input text-input--large"
              type="text"
              autocomplete="off"
              :placeholder="t('courseGeneration.form.topicPlaceholder', '例如：线性代数基础')"
              :disabled="busy"
              autofocus
            />
            <p class="field-help">{{ t('courseGeneration.dialog.topicHelp', '写清楚学习对象；难度、结构和资料边界在下方单独控制。') }}</p>
          </section>

          <section class="form-section teaching-settings">
            <div class="teaching-settings__core">
              <fieldset class="choice-group difficulty-group">
                <legend class="choice-group__title">
                  <span class="field-icon field-icon--amber"><Trophy :size="14" /></span>
                  {{ t('courseGeneration.form.difficulty', '难度等级') }}
                </legend>
                <div class="difficulty-options">
                <button
                  v-for="item in difficultyOptions"
                  :key="item.value"
                  type="button"
                  class="difficulty-option"
                  :class="{ active: form.difficulty === item.value }"
                  :data-tone="item.tone"
                  :aria-pressed="form.difficulty === item.value"
                  :disabled="busy"
                  @click="form.difficulty = item.value"
                >
                  <span class="difficulty-option__rail" />
                  <span class="difficulty-option__copy">
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.detail }}</small>
                  </span>
                  <span class="difficulty-option__check"><Check :size="12" /></span>
                </button>
                </div>
              </fieldset>

              <fieldset class="choice-group composition-group">
                <legend class="choice-group__title">
                  <span class="field-icon field-icon--rose"><WandSparkles :size="14" /></span>
                  <span>
                    {{ t('courseGeneration.form.compositionStyle', '课程编排偏好') }}
                    <small>{{ t('courseGeneration.form.compositionStyleHelp', '决定案例、推演、应用与项目块怎样分布') }}</small>
                  </span>
                </legend>
                <div class="composition-options">
                  <button
                    v-for="item in compositionOptions"
                    :key="item.value"
                    type="button"
                    class="composition-option"
                    :class="{ active: form.compositionStyle === item.value, 'composition-option--wide': item.value === 'balanced' }"
                    :aria-pressed="form.compositionStyle === item.value"
                    :disabled="busy"
                    @click="form.compositionStyle = item.value"
                  >
                    <span class="composition-option__icon"><component :is="item.icon" :size="19" /></span>
                    <span class="composition-option__copy">
                      <strong>{{ item.label }}</strong>
                      <small>{{ item.detail }}</small>
                    </span>
                    <span class="composition-option__check"><Check :size="11" /></span>
                  </button>
                </div>
              </fieldset>
            </div>

            <div class="strategy-settings">
              <div class="strategy-settings__heading">
                <strong>{{ t('courseGeneration.form.strategy', '课程策略') }}</strong>
                <span>{{ t('courseGeneration.form.strategyHelp', '进一步控制课程如何组织，以及资料在生成中的作用。') }}</span>
              </div>
              <div class="compact-grid">
              <label>
                <span class="field-label"><Route :size="13" />{{ t('courseGeneration.pedagogy.label', '教学结构') }}</span>
                <select v-model="form.pedagogyMode" class="select-input" :disabled="busy">
                  <option v-for="item in pedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
              </label>
              <label>
                <span class="field-label"><Target :size="13" />{{ t('courseGeneration.form.coursePurpose', '课程目的') }}</span>
                <select v-model="form.coursePurpose" class="select-input" :disabled="busy">
                  <option v-for="item in purposeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
              </label>
              <label>
                <span class="field-label"><BookMarked :size="13" />{{ t('courseGeneration.grounding.label', '资料使用边界') }}</span>
                <select v-model="form.groundingStrategy" class="select-input" :disabled="busy">
                  <option value="material_first">{{ t('courseGeneration.grounding.materialFirst', '资料优先') }}</option>
                  <option value="strict_grounded">{{ t('courseGeneration.grounding.strict', '仅依据资料') }}</option>
                  <option value="general_assisted">{{ t('courseGeneration.grounding.general', '资料与通用知识结合') }}</option>
                </select>
              </label>
              </div>
            </div>
          </section>

          <section class="form-section guided-intro">
            <div class="guided-intro__heading">
              <strong>{{ t('courseGeneration.guided.title', '分六步完成课程') }}</strong>
              <span>{{ t('courseGeneration.guided.help', '系统每完成一步都会停下来给你看，确认后才继续。') }}</span>
            </div>
            <ol class="guided-intro__steps">
              <li v-for="(label, index) in guidedStepLabels" :key="label">
                <span>{{ index + 1 }}</span>
                <strong>{{ label }}</strong>
              </li>
            </ol>
          </section>

          <section class="form-section web-enrichment-setting">
            <label class="web-enrichment-setting__control">
              <input
                v-model="form.webQuestionEnrichment"
                data-testid="web-question-enrichment"
                type="checkbox"
                :disabled="busy"
              />
              <span>
                <strong>{{ t('courseGeneration.webQuestions.label', '资料不足时联网补充') }}</strong>
                <small>{{ t('courseGeneration.webQuestions.help', '仅对题库覆盖缺口检索可信来源；不会发送学生画像、作答或个人记录。') }}</small>
              </span>
            </label>
          </section>

          <section class="form-section">
            <label class="field-label" for="course-requirements">{{ t('courseGeneration.form.requirements', '额外要求') }}</label>
            <textarea
              id="course-requirements"
              v-model="form.requirements"
              class="textarea-input"
              :disabled="busy"
              :placeholder="t('courseGeneration.form.requirementsPlaceholder', '例如：多一些推导过程，并给出可独立完成的练习')"
            />
          </section>

          <section class="form-section material-section">
            <MaterialInputPanel ref="materialInputRef" v-model="materials" :disabled="busy" />
          </section>
        </form>

        <footer class="generation-dialog__footer">
          <div>
            <Library :size="15" />
            <span>{{ t('courseGeneration.progressVaries', '耗时取决于资料数量与解析复杂度') }}</span>
          </div>
          <div class="footer-actions">
            <button type="button" class="secondary-button" :disabled="busy" @click="close">
              {{ t('common.cancel', '取消') }}
            </button>
            <button type="button" class="primary-button" :disabled="busy || !form.subject.trim()" @click="submit">
              <LoaderCircle v-if="busy" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              {{ busy ? t('courseGeneration.actions.submitting', '正在提交') : t('courseGeneration.actions.confirmRequirements', '确认需求，生成目录') }}
            </button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  BookMarked,
  Check,
  GraduationCap,
  Library,
  LoaderCircle,
  MessageCircleQuestion,
  Route,
  Sparkles,
  Target,
  Trophy,
  WandSparkles,
  Wrench,
  X,
} from 'lucide-vue-next'
import MaterialInputPanel from './MaterialInputPanel.vue'
import { t } from '@/shared/i18n'
import {
  PEDAGOGY_MODE_OPTIONS,
  type CourseGenerationOptions,
  type CourseCompositionStyle,
  type CourseMaterialDraft,
  type DifficultyLevel,
  type PedagogyModeSelection,
} from '@/shared/prompt-config'

const props = withDefaults(defineProps<{ modelValue: boolean; busy?: boolean }>(), { busy: false })
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  generate: [payload: { subject: string; options: CourseGenerationOptions }]
  error: [message: string]
}>()

const titleId = `course-generation-title-${Math.random().toString(36).slice(2)}`
const dialogRef = ref<HTMLElement | null>(null)
const materialInputRef = ref<InstanceType<typeof MaterialInputPanel> | null>(null)
const materials = ref<CourseMaterialDraft[]>([])
const uploading = ref(false)
const submissionRequestId = ref('')
const submissionIdentity = ref('')
const busy = computed(() => props.busy || uploading.value)
const form = reactive({
  subject: '',
  difficulty: 'intermediate' as DifficultyLevel,
  compositionStyle: 'balanced' as CourseCompositionStyle,
  pedagogyMode: 'auto' as PedagogyModeSelection,
  coursePurpose: 'systematic' as 'systematic' | 'exam_sprint' | 'material_organization' | 'personalized_remedial',
  groundingStrategy: 'material_first' as 'material_first' | 'strict_grounded' | 'general_assisted',
  webQuestionEnrichment: false,
  requirements: '',
})

const difficultyOptions = computed(() => ([
  { value: 'beginner' as const, tone: 'emerald', label: t('courseGeneration.difficulty.beginner.label', '入门'), detail: t('courseGeneration.difficulty.beginner.detail', '明确支架 · 标准任务') },
  { value: 'intermediate' as const, tone: 'blue', label: t('courseGeneration.difficulty.intermediate.label', '进阶'), detail: t('courseGeneration.difficulty.intermediate.detail', '独立分析 · 典型问题') },
  { value: 'advanced' as const, tone: 'violet', label: t('courseGeneration.difficulty.advanced.label', '高阶'), detail: t('courseGeneration.difficulty.advanced.detail', '开放约束 · 权衡迁移') },
]))
const compositionOptions = computed(() => ([
  {
    value: 'balanced' as const,
    icon: WandSparkles,
    label: t('courseGeneration.compositionStyles.balanced.label', '智能均衡'),
    detail: t('courseGeneration.compositionStyles.balanced.detail', '讲解、示例、行动与反馈均衡推进'),
  },
  {
    value: 'theory_driven' as const,
    icon: GraduationCap,
    label: t('courseGeneration.compositionStyles.theoryDriven.label', '理论推导'),
    detail: t('courseGeneration.compositionStyles.theoryDriven.detail', '更多推演、条件边界与反例块'),
  },
  {
    value: 'example_driven' as const,
    icon: Wrench,
    label: t('courseGeneration.compositionStyles.exampleDriven.label', '案例实战'),
    detail: t('courseGeneration.compositionStyles.exampleDriven.detail', '更多典型案例与真实场景块'),
  },
  {
    value: 'project_driven' as const,
    icon: Target,
    label: t('courseGeneration.compositionStyles.projectDriven.label', '项目驱动'),
    detail: t('courseGeneration.compositionStyles.projectDriven.detail', '沿课程进程增加项目任务与成果块'),
  },
  {
    value: 'inquiry_driven' as const,
    icon: MessageCircleQuestion,
    label: t('courseGeneration.compositionStyles.inquiryDriven.label', '问题探究'),
    detail: t('courseGeneration.compositionStyles.inquiryDriven.detail', '用问题、假设、推演与检验组织块'),
  },
]))
const pedagogyOptions = computed(() => PEDAGOGY_MODE_OPTIONS.map(item => ({ value: item.value, label: t(item.labelKey, item.value) })))
const purposeOptions = computed(() => ([
  { value: 'systematic' as const, label: t('courseWorkspace.purpose.systematic', '系统学习') },
  { value: 'exam_sprint' as const, label: t('courseWorkspace.purpose.exam_sprint', '备考冲刺') },
  { value: 'material_organization' as const, label: t('courseWorkspace.purpose.material_organization', '资料整理') },
  { value: 'personalized_remedial' as const, label: t('courseWorkspace.purpose.personalized_remedial', '个性补弱') },
]))
const guidedStepLabels = computed(() => [
  t('courseGeneration.guided.requirements', '需求'),
  t('courseGeneration.guided.outline', '目录'),
  t('courseGeneration.guided.knowledge', '知识蓝图'),
  t('courseGeneration.guided.teaching', '教学方案'),
  t('courseGeneration.guided.content', '课程内容'),
  t('courseGeneration.guided.release', '质量与发布'),
])

watch(() => props.modelValue, async open => {
  if (!open) {
    submissionRequestId.value = ''
    submissionIdentity.value = ''
    return
  }
  await nextTick()
  dialogRef.value?.focus()
})

function close() {
  if (!busy.value) emit('update:modelValue', false)
}

async function submit() {
  const subject = form.subject.trim()
  if (!subject || busy.value) return
  uploading.value = true
  try {
    const materialBindings = materials.value.length
      ? await materialInputRef.value?.ensureUploaded()
      : []
    const options: CourseGenerationOptions = {
      difficulty: form.difficulty,
      composition_style: form.compositionStyle,
      pedagogy_mode: form.pedagogyMode,
      generation_mode: 'review_blueprint',
      course_purpose: form.coursePurpose,
      grounding_strategy: form.groundingStrategy,
      requirements: form.requirements.trim(),
      material_bindings: materialBindings || [],
      web_question_enrichment: { enabled: form.webQuestionEnrichment },
    }
    const identity = JSON.stringify({ subject, options })
    if (!submissionRequestId.value || submissionIdentity.value !== identity) {
      submissionRequestId.value = crypto.randomUUID()
      submissionIdentity.value = identity
    }
    emit('generate', {
      subject,
      options: { ...options, request_id: submissionRequestId.value },
    })
  } catch (error: any) {
    emit('error', error?.message || t('courseGeneration.materials.uploadFailed', '资料上传失败'))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.generation-dialog-layer { position: fixed; inset: 0; z-index: 520; display: grid; place-items: center; padding: 20px; }
.generation-dialog-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30, 41, 59, .34); backdrop-filter: blur(5px); cursor: default; }
.generation-dialog { position: relative; width: min(920px, 100%); max-height: min(860px, calc(100vh - 40px)); display: grid; grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; border: 1px solid rgba(255,255,255,.92); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: rgba(255,255,255,.98); box-shadow: var(--lz-shadow-overlay); outline: none; }
.generation-dialog__header { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 18px 0 22px; border-bottom: 1px solid var(--lz-border); }
.generation-dialog__heading { min-width: 0; display: flex; align-items: center; gap: 11px; }
.generation-dialog__mark { width: 36px; height: 36px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 10px; color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.generation-dialog__heading p { margin: 0 0 2px; color: var(--lz-text-muted); font-size: 10px; font-weight: 700; }
.generation-dialog__heading h2 { margin: 0; color: var(--lz-text-strong); font-size: 17px; line-height: 1.25; }
.icon-button { width: 34px; height: 34px; display: grid; place-items: center; border: 0; border-radius: 7px; color: var(--lz-text-secondary); background: transparent; cursor: pointer; }
.icon-button:hover { color: var(--lz-text-strong); background: var(--lz-surface-muted); }
.generation-dialog__body { min-height: 0; overflow: auto; padding: 4px 24px 24px; }
.form-section { padding: 20px 0; border-bottom: 1px solid rgba(226,232,240,.78); }
.form-section:last-child { border-bottom: 0; }
.form-section--lead { padding-top: 22px; }
.web-enrichment-setting__control { display: flex; align-items: flex-start; gap: 11px; cursor: pointer; }
.web-enrichment-setting__control input { margin-top: 3px; accent-color: var(--lz-brand-strong); }
.web-enrichment-setting__control span { display: grid; gap: 4px; }
.web-enrichment-setting__control strong { color: var(--lz-text-strong); font-size: 13px; }
.web-enrichment-setting__control small { color: var(--lz-text-muted); font-size: 11px; line-height: 1.55; }
.guided-intro { display:grid; gap:14px; }
.guided-intro__heading { display:flex; align-items:baseline; justify-content:space-between; gap:18px; }
.guided-intro__heading strong { color:var(--lz-text-strong); font-size:12px; }
.guided-intro__heading span { color:var(--lz-text-muted); font-size:10px; text-align:right; }
.guided-intro__steps { margin:0; padding:0; display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); list-style:none; }
.guided-intro__steps li { position:relative; min-width:0; display:grid; justify-items:center; gap:6px; color:var(--lz-text-secondary); font-size:10px; text-align:center; }
.guided-intro__steps li:not(:last-child)::after { content:""; position:absolute; top:12px; left:calc(50% + 16px); right:calc(-50% + 16px); height:1px; background:var(--lz-border); }
.guided-intro__steps span { position:relative; z-index:1; width:25px; height:25px; display:grid; place-items:center; border:1px solid rgba(99,102,241,.24); border-radius:50%; color:var(--lz-brand-strong); background:#fff; font-family:ui-monospace,monospace; font-weight:750; }
.guided-intro__steps strong { overflow:hidden; max-width:100%; text-overflow:ellipsis; white-space:nowrap; }
.teaching-settings { display: grid; gap: 22px; }
.teaching-settings__core { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; }
.choice-group { min-width: 0; margin: 0; padding: 0; border: 0; }
.choice-group__title { width: 100%; display: flex; align-items: center; gap: 8px; margin: 0 0 11px; padding: 0; color: var(--lz-text); font-size: 12px; font-weight: 750; }
.choice-group__title > span:last-child { display:grid; gap:2px; }
.choice-group__title small { color:var(--lz-text-muted); font-size:9px; font-weight:500; line-height:1.35; }
.field-icon { width: 25px; height: 25px; display: grid; place-items: center; border: 1px solid; border-radius: 8px; box-shadow: 0 2px 7px rgba(15,23,42,.04); }
.field-icon--amber { border-color: #fde7b0; color: #d97706; background: #fffbeb; }
.field-icon--rose { border-color: #fbcfe8; color: #db2777; background: #fdf2f8; }
.difficulty-options { display: grid; gap: 9px; }
.difficulty-option { --choice-accent: #60a5fa; min-width: 0; min-height: 58px; display: grid; grid-template-columns: 5px minmax(0, 1fr) 20px; align-items: center; gap: 11px; padding: 9px 11px; border: 1px solid rgba(226,232,240,.92); border-radius: 12px; color: var(--lz-text-secondary); background: #fff; text-align: left; box-shadow: 0 2px 8px rgba(15,23,42,.025); cursor: pointer; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease, background .16s ease; }
.difficulty-option[data-tone="emerald"] { --choice-accent: #34d399; }
.difficulty-option[data-tone="blue"] { --choice-accent: #60a5fa; }
.difficulty-option[data-tone="violet"] { --choice-accent: #a78bfa; }
.difficulty-option:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(165,180,252,.72); box-shadow: 0 7px 16px rgba(79,70,229,.07); }
.difficulty-option.active { border-color: var(--lz-brand); background: linear-gradient(135deg,#fff,rgba(238,242,255,.72)); box-shadow: 0 8px 18px rgba(79,70,229,.09), inset 0 0 0 1px rgba(99,102,241,.08); }
.difficulty-option__rail { width: 5px; height: 34px; border-radius: 4px; background: #e2e8f0; transition: background .16s ease; }
.difficulty-option.active .difficulty-option__rail { background: var(--choice-accent); }
.difficulty-option__copy { min-width: 0; display: block; }
.difficulty-option__copy strong { display: block; color: var(--lz-text); font-size: 12px; }
.difficulty-option__copy small { display: block; margin-top: 2px; overflow: hidden; color: var(--lz-text-muted); font-size: 10px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.difficulty-option__check,.composition-option__check { display: grid; place-items: center; border: 1px solid var(--lz-border); border-radius: 50%; color: transparent; background: var(--lz-surface-muted); transition: color .16s ease, border-color .16s ease, background .16s ease, transform .16s ease; }
.difficulty-option__check { width: 20px; height: 20px; }
.difficulty-option.active .difficulty-option__check,.composition-option.active .composition-option__check { border-color: var(--lz-brand); color: #fff; background: var(--lz-brand); transform: scale(1.06); }
.composition-options { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }
.composition-option { position: relative; min-width: 0; min-height: 72px; display: grid; grid-template-columns:30px minmax(0,1fr) 17px; align-items:center; gap:8px; padding:10px; border: 1px solid rgba(226,232,240,.92); border-radius: 12px; color: var(--lz-text-secondary); background: #fff; text-align:left; box-shadow: 0 2px 8px rgba(15,23,42,.025); cursor: pointer; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease, background .16s ease; }
.composition-option--wide { grid-column:1 / -1; min-height:64px; }
.composition-option:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(165,180,252,.72); box-shadow: 0 7px 16px rgba(79,70,229,.07); }
.composition-option.active { border-color: var(--lz-brand); color: var(--lz-brand-strong); background: linear-gradient(145deg,#fff,rgba(245,243,255,.82)); box-shadow: 0 8px 18px rgba(79,70,229,.09), inset 0 0 0 1px rgba(99,102,241,.08); }
.composition-option__icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; color: var(--lz-brand); background: var(--lz-brand-soft); transition: transform .16s ease, color .16s ease, background .16s ease; }
.composition-option.active .composition-option__icon { transform: scale(1.05); color: #fff; background: var(--lz-brand); }
.composition-option__copy { min-width:0; display:block; }
.composition-option__copy strong { display:block; color: inherit; font-size: 11px; }
.composition-option__copy small { display:block; margin-top:2px; color:var(--lz-text-muted); font-size:9px; line-height:1.35; }
.composition-option__check { width: 17px; height: 17px; }
.difficulty-option:disabled,.composition-option:disabled { cursor: not-allowed; opacity: .6; }
.strategy-settings { padding-top: 18px; border-top: 1px dashed rgba(203,213,225,.72); }
.strategy-settings__heading { display: flex; align-items: baseline; gap: 9px; margin-bottom: 11px; }
.strategy-settings__heading strong { color: var(--lz-text); font-size: 12px; }
.strategy-settings__heading span { color: var(--lz-text-muted); font-size: 10px; }
.compact-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.field-label { display: block; margin-bottom: 8px; color: var(--lz-text); font-size: 12px; font-weight: 700; }
.compact-grid .field-label { display: flex; align-items: center; gap: 6px; color: var(--lz-text-secondary); font-size: 10px; }
.text-input,.select-input,.textarea-input { width: 100%; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-strong); background: #fff; outline: none; transition: border-color .16s ease, box-shadow .16s ease; }
.text-input:focus,.select-input:focus,.textarea-input:focus { border-color: var(--lz-brand); box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.text-input:disabled,.select-input:disabled,.textarea-input:disabled { cursor: not-allowed; opacity: .6; }
.text-input { height: 42px; padding: 0 12px; }
.text-input--large { height: 48px; font-size: 15px; }
.select-input { height: 38px; padding: 0 9px; font-size: 12px; }
.textarea-input { min-height: 82px; padding: 10px 12px; resize: vertical; line-height: 1.6; font-size: 12px; }
.field-help { margin: 7px 0 0; color: var(--lz-text-muted); font-size: 11px; line-height: 1.5; }
.segmented-options { display: grid; gap: 8px; }
.segmented-options--three { grid-template-columns: repeat(3, 1fr); }
.segmented-options--two { grid-template-columns: repeat(2, 1fr); }
.segmented-options button { min-width: 0; min-height: 66px; display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: #fff; text-align: left; cursor: pointer; }
.segmented-options button:hover { border-color: rgba(99,102,241,.46); }
.segmented-options button.active { border-color: var(--lz-brand); color: var(--lz-brand-strong); background: var(--lz-brand-soft); box-shadow: inset 0 0 0 1px rgba(99,102,241,.1); }
.segmented-options button:disabled { cursor: not-allowed; opacity: .6; }
.segmented-options strong { display: block; color: inherit; font-size: 12px; }
.segmented-options span { min-width: 0; display: block; color: var(--lz-text-muted); font-size: 10px; line-height: 1.45; }
.segmented-options span strong { margin-bottom: 2px; }
.material-section :deep(section) { margin: 0; }
.generation-dialog__footer { min-height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 10px 18px 10px 24px; border-top: 1px solid var(--lz-border); background: rgba(248,250,252,.84); }
.generation-dialog__footer > div:first-child { min-width: 0; display: flex; align-items: center; gap: 7px; color: var(--lz-text-muted); font-size: 10px; }
.footer-actions { display: flex; gap: 8px; flex: 0 0 auto; }
.primary-button,.secondary-button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; }
.primary-button { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.secondary-button { border: 1px solid var(--lz-border); color: var(--lz-text-secondary); background: #fff; }
.primary-button:disabled,.secondary-button:disabled { cursor: not-allowed; opacity: .55; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .generation-dialog-layer { align-items: end; padding: 0; }
  .generation-dialog { width: 100%; max-height: calc(100vh - 56px); border-radius: 14px 14px 0 0; }
  .generation-dialog__body { padding-inline: 16px; }
  .teaching-settings__core { grid-template-columns: 1fr; gap: 22px; }
  .compact-grid { grid-template-columns: 1fr 1fr; }
  .composition-options { grid-template-columns:1fr; }
  .composition-option--wide { grid-column:auto; }
  .generation-dialog__footer { align-items: stretch; flex-direction: column; padding: 10px 16px 14px; }
  .footer-actions,.footer-actions button { width: 100%; }
  .footer-actions button { flex: 1; }
}
@media (max-width: 520px) {
  .guided-intro__steps { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: 12px; }
  .guided-intro__steps li:nth-child(3n)::after { display: none; }
  .segmented-options--three,.segmented-options--two,.compact-grid { grid-template-columns: 1fr; }
  .segmented-options button { min-height: 52px; }
  .strategy-settings__heading { align-items: flex-start; flex-direction: column; gap: 3px; }
}
</style>
