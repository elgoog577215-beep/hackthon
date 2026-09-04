<template>
  <section class="answer-renderer" :data-mode="mode">
    <div v-if="stepwiseOffered" class="stepwise-switch">
      <!-- Stepwise is an offer, never a requirement: the student can always go
           back to writing one whole answer, and switching keeps what they wrote. -->
      <button
        type="button"
        class="stepwise-toggle"
        :class="{ active: stepwiseActive }"
        :disabled="disabled"
        :aria-pressed="stepwiseActive"
        data-testid="stepwise-toggle"
        @click="toggleStepwise"
      >
        {{ stepwiseActive ? t('courseWorkspace.practice.stepwiseOff', '改为整体作答') : t('courseWorkspace.practice.stepwiseOn', '分步作答') }}
      </button>
      <span class="stepwise-note">
        {{ t('courseWorkspace.practice.stepwiseNote', '分步只是表达方式，不影响掌握判定；你也可以直接整体作答。') }}
      </span>
    </div>

    <div v-if="stepwiseActive" class="stepwise-editor" data-testid="stepwise-editor">
      <div v-for="(step, index) in stepDrafts" :key="index" class="stepwise-step">
        <label>
          <span class="step-label">
            {{ t('courseWorkspace.practice.stepLabel', '第 {index} 步').replace('{index}', String(index + 1)) }}
          </span>
          <textarea
            class="step-input"
            :value="step.text"
            :disabled="disabled"
            :placeholder="t('courseWorkspace.practice.stepPlaceholder', '写下这一步做了什么，以及依据')"
            @input="updateStep(index, $event)"
          />
        </label>
        <button
          v-if="stepDrafts.length > 1"
          type="button"
          class="step-remove"
          :disabled="disabled"
          :aria-label="t('courseWorkspace.practice.removeStep', '删除这一步')"
          @click="removeStep(index)"
        >
          ×
        </button>
      </div>
      <button
        type="button"
        class="step-add"
        :disabled="disabled || stepDrafts.length >= maxSteps"
        data-testid="stepwise-add"
        @click="addStep"
      >
        {{ t('courseWorkspace.practice.addStep', '添加一步') }}
      </button>
    </div>

    <div v-if="mode === 'choice' && normalizedOptions.length" class="choice-list">
      <label
        v-for="option in normalizedOptions"
        :key="optionId(option)"
        :class="{ selected: isOptionSelected(option) }"
      >
        <input
          :checked="isOptionSelected(option)"
          :type="multipleChoice ? 'checkbox' : 'radio'"
          :value="optionId(option)"
          :disabled="disabled"
          @change="selectOption(option, $event)"
        >
        <strong class="option-id">{{ optionId(option) }}</strong>
        <MathText :content="optionLabel(option)" />
      </label>
    </div>

    <div v-else-if="mode === 'numeric_unit'" class="field-grid numeric-grid">
      <label v-for="field in fields" :key="field.field_id">
        <span><MathText :content="field.label" /></span>
        <textarea
          v-if="field.kind === 'rich_text'"
          :value="draft[field.field_id] || ''"
          :disabled="disabled"
          @input="setFromEvent(field.field_id, $event)"
        />
        <input
          v-else
          :type="field.kind === 'number' ? 'number' : 'text'"
          :value="draft[field.field_id] ?? ''"
          :disabled="disabled"
          @input="setFromEvent(field.field_id, $event)"
        >
      </label>
    </div>

    <div v-else-if="mode === 'code'" class="code-answer">
      <label>
        <span>{{ t('courseWorkspace.practice.codeLanguage', '编程语言') }}</span>
        <select
          :value="draft.language || contract?.language || allowedLanguages[0]"
          :disabled="disabled"
          @change="setFromEvent('language', $event)"
        >
          <option v-for="language in allowedLanguages" :key="language" :value="language">
            {{ language }}
          </option>
        </select>
      </label>
      <label>
        <span>{{ t('courseWorkspace.practice.codeAnswer', '代码') }}</span>
        <textarea
          class="code-editor"
          spellcheck="false"
          :value="draft.code || ''"
          :disabled="disabled"
          @input="setFromEvent('code', $event)"
        />
      </label>
      <button type="button" class="run-command" :disabled="disabled || running || !draft.code" @click="runPreview">
        {{ running ? t('courseWorkspace.practice.codeRunning', '运行中…') : t('courseWorkspace.practice.codeRun', '运行代码') }}
      </button>
      <pre v-if="runOutput" class="run-output">{{ runOutput }}</pre>
      <label v-if="fields.some(field => field.field_id === 'test_evidence')">
        <span>{{ t('courseWorkspace.practice.codeTestEvidence', '测试说明') }}</span>
        <textarea
          :value="draft.test_evidence || ''"
          :disabled="disabled"
          @input="setFromEvent('test_evidence', $event)"
        />
      </label>
    </div>

    <div v-else-if="mode === 'structured_fields'" class="field-grid">
      <label v-for="field in fields" :key="field.field_id">
        <span><MathText :content="field.label" /><b v-if="field.required" v-bind:aria-label="t('courseWorkspace.practice.requiredField', '必填')">*</b></span>
        <textarea
          v-if="field.kind === 'rich_text' || field.kind === 'code'"
          :class="{ 'code-editor': field.kind === 'code' }"
          :value="draft[field.field_id] || ''"
          :disabled="disabled"
          @input="setFromEvent(field.field_id, $event)"
        />
        <input
          v-else
          :type="field.kind === 'number' ? 'number' : 'text'"
          :value="draft[field.field_id] ?? ''"
          :disabled="disabled"
          @input="setFromEvent(field.field_id, $event)"
        >
      </label>
    </div>

    <textarea
      v-else
      class="answer-editor"
      :value="draft.text || ''"
      :disabled="disabled"
      :rows="mode === 'short_text' ? 4 : 10"
      :placeholder="placeholder"
      @input="setFromEvent('text', $event)"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MathText from './MathText.vue'
import http from '../utils/http'
import { t } from '../shared/i18n'

const MAX_STEPS = 20

type AnswerField = {
  field_id: string
  kind: string
  label: string
  required?: boolean
}

const props = defineProps<{
  contract?: Record<string, any>
  options?: Array<Record<string, any>>
  questionType?: string
  modelValue: Record<string, any>
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: Record<string, any>): void
}>()

const running = ref(false)
const runOutput = ref('')
const draft = computed(() => props.modelValue || {})
const normalizedOptions = computed(() => (
  Array.isArray(props.options)
    ? props.options.filter(option => option && optionId(option))
    : []
))
const modernModes = new Set([
  'choice',
  'numeric_unit',
  'code',
  'short_text',
  'rich_text',
  'structured_fields',
])
const questionTypeModes: Record<string, string> = {
  selected_response: 'choice',
  single_choice: 'choice',
  multiple_choice: 'choice',
  output_prediction: 'choice',
  numeric_response: 'numeric_unit',
  implementation_task: 'code',
  debugging_trace: 'structured_fields',
  state_trace_transfer: 'structured_fields',
  symbolic_derivation: 'structured_fields',
  structured_application: 'structured_fields',
  mechanism_evidence: 'structured_fields',
  source_analysis: 'structured_fields',
  language_transformation: 'structured_fields',
  constrained_decision: 'structured_fields',
}
const mode = computed(() => {
  const explicit = String(props.contract?.mode || '')
  if (modernModes.has(explicit)) return explicit
  if (normalizedOptions.value.length >= 2) return 'choice'
  if (explicit === 'code_and_text') return 'code'
  return questionTypeModes[String(props.questionType || '')] || 'rich_text'
})
const fields = computed<AnswerField[]>(() => {
  const supplied = props.contract?.fields
  if (Array.isArray(supplied) && supplied.length) return supplied
  if (mode.value === 'numeric_unit') {
    return [
      { field_id: 'value', kind: 'number', label: t('courseWorkspace.practice.fieldValue', '数值'), required: true },
      { field_id: 'unit', kind: 'short_text', label: t('courseWorkspace.practice.fieldUnit', '单位'), required: true },
      { field_id: 'work', kind: 'rich_text', label: t('courseWorkspace.practice.fieldWork', '计算过程'), required: true },
    ]
  }
  if (mode.value === 'code') {
    return [
      { field_id: 'code', kind: 'code', label: t('courseWorkspace.practice.codeAnswer', '代码'), required: true },
      { field_id: 'test_evidence', kind: 'rich_text', label: t('courseWorkspace.practice.codeTestEvidence', '测试说明') },
    ]
  }
  if (mode.value === 'structured_fields') {
    if (props.questionType === 'debugging_trace') {
      return [
        { field_id: 'trace', kind: 'rich_text', label: t('courseWorkspace.practice.fieldTrace', '执行轨迹'), required: true },
        { field_id: 'diagnosis', kind: 'rich_text', label: t('courseWorkspace.practice.fieldDiagnosis', '问题定位'), required: true },
        { field_id: 'result_check', kind: 'rich_text', label: t('courseWorkspace.practice.fieldResultCheck', '结果检查'), required: true },
      ]
    }
    return [
      { field_id: 'answer', kind: 'rich_text', label: t('courseWorkspace.practice.fieldAnswer', '作答'), required: true },
      { field_id: 'evidence', kind: 'rich_text', label: t('courseWorkspace.practice.fieldEvidence', '依据'), required: true },
      { field_id: 'result_check', kind: 'rich_text', label: t('courseWorkspace.practice.fieldResultCheck', '结果检查'), required: true },
    ]
  }
  return []
})
const multipleChoice = computed(() => (
  Boolean(props.contract?.selection?.multiple)
  || props.questionType === 'multiple_choice'
))
const allowedLanguages = computed<string[]>(() => (
  props.contract?.allowed_languages?.length
    ? props.contract.allowed_languages
    : ['python', 'javascript']
))

// --- Stepwise answering (J3) ------------------------------------------------
// The backend treats a payload with no usable `steps` as a whole answer, so the
// degradation path costs nothing here: dropping the steps key is enough.
const maxSteps = MAX_STEPS
const stepwiseOffered = computed(() => (
  Boolean(props.contract?.stepwise) && mode.value !== 'choice'
))
const submittedSteps = computed<Array<Record<string, any>>>(() => (
  Array.isArray(draft.value.steps) ? draft.value.steps : []
))
// Only the student turns stepwise on/off; never infer it from an empty draft, or
// the editor would collapse the moment they clear their first step.
const stepwiseOptOut = ref(false)
const stepwiseActive = computed(() => (
  stepwiseOffered.value && !stepwiseOptOut.value && submittedSteps.value.length > 0
))
const stepDrafts = computed(() => (
  submittedSteps.value.length
    ? submittedSteps.value.map((step, index) => ({
      text: String(step?.text ?? ''),
      step_index: Number(step?.step_index) || index + 1,
      step_id: String(step?.step_id ?? ''),
    }))
    : [{ text: '', step_index: 1, step_id: '' }]
))

function writeSteps(steps: Array<Record<string, any>>) {
  const next = { ...draft.value }
  if (!steps.length) {
    // No steps at all is exactly the whole-answer shape the backend expects.
    delete next.steps
  } else {
    next.steps = steps.map((step, index) => ({
      ...step,
      step_index: index + 1,
    }))
  }
  emit('update:modelValue', next)
}

function toggleStepwise() {
  if (stepwiseActive.value) {
    // Leaving stepwise must not throw away what the student already wrote: fold
    // the steps into the free-text answer instead of deleting them.
    const written = stepDrafts.value.map(step => step.text.trim()).filter(Boolean)
    const merged = [String(draft.value.text || '').trim(), ...written]
      .filter(Boolean)
      .join('\n')
    stepwiseOptOut.value = true
    const next: Record<string, any> = { ...draft.value, text: merged }
    delete next.steps
    emit('update:modelValue', next)
    return
  }
  stepwiseOptOut.value = false
  writeSteps([{ text: '', step_index: 1, step_id: '' }])
}

function updateStep(index: number, event: Event) {
  const target = event.target as HTMLTextAreaElement
  const steps = stepDrafts.value.map((step, position) => (
    position === index ? { ...step, text: target.value } : step
  ))
  writeSteps(steps)
}

function addStep() {
  if (stepDrafts.value.length >= MAX_STEPS) return
  writeSteps([...stepDrafts.value, { text: '', step_index: 0, step_id: '' }])
}

function removeStep(index: number) {
  const steps = stepDrafts.value.filter((_step, position) => position !== index)
  writeSteps(steps.length ? steps : [{ text: '', step_index: 1, step_id: '' }])
}

function optionId(option: Record<string, any>) {
  return String(
    option.id
    || option.option_id
    || option.key
    || option.value
    || '',
  )
}

function optionLabel(option: Record<string, any>) {
  return String(
    option.label
    || option.text
    || option.option_text
    || option.content
    || option.value
    || '',
  )
}

function isOptionSelected(option: Record<string, any>) {
  const id = optionId(option)
  if (multipleChoice.value) {
    return Array.isArray(draft.value.selected_option_ids)
      && draft.value.selected_option_ids.includes(id)
  }
  return String(draft.value.selected_option_id || '') === id
}

function selectOption(option: Record<string, any>, event: Event) {
  const id = optionId(option)
  if (!multipleChoice.value) {
    setValue('selected_option_id', id)
    return
  }
  const target = event.target as HTMLInputElement
  const current = Array.isArray(draft.value.selected_option_ids)
    ? [...draft.value.selected_option_ids]
    : []
  const next = target.checked
    ? Array.from(new Set([...current, id]))
    : current.filter(value => value !== id)
  setValue('selected_option_ids', next)
}

function setValue(field: string, value: unknown) {
  emit('update:modelValue', { ...draft.value, [field]: value })
}

function setFromEvent(field: string, event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  setValue(field, target.value)
}

async function runPreview() {
  running.value = true
  runOutput.value = ''
  try {
    const response = await http.post('/api/execute', {
      code: draft.value.code || '',
      language: draft.value.language || props.contract?.language || allowedLanguages.value[0],
      timeout: 10,
    })
    runOutput.value = [response.data?.output, response.data?.error]
      .filter(Boolean)
      .join('\n') || t('courseWorkspace.practice.codeNoOutput', '运行完成，无输出')
    setValue('run_result', {
      status: response.data?.error ? 'failed' : 'completed',
      output: runOutput.value.slice(0, 32768),
    })
  } catch {
    runOutput.value = t('courseWorkspace.practice.codeRunFailed', '运行失败')
    ElMessage.error(t('courseWorkspace.practice.codeRunFailedToast', '代码运行失败'))
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.answer-renderer { display: grid; gap: 14px; }
.stepwise-switch { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.stepwise-toggle { border: 1px solid #94a3b8; border-radius: 8px; padding: 7px 14px; background: #fff; color: #334155; font: inherit; cursor: pointer; }
.stepwise-toggle.active { border-color: #397d76; background: #f0fdfa; color: #397d76; font-weight: 650; }
.stepwise-toggle:disabled { opacity: .55; cursor: not-allowed; }
.stepwise-note { color: #64748b; font-size: .86rem; line-height: 1.5; }
.stepwise-editor { display: grid; gap: 10px; padding: 13px; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; }
.stepwise-step { display: flex; align-items: flex-start; gap: 8px; }
.stepwise-step label { flex: 1; display: grid; gap: 6px; color: #334155; font-weight: 650; }
.step-label { color: #397d76; font-size: .9rem; }
.step-input { min-height: 76px; }
.step-remove { flex: none; margin-top: 26px; width: 32px; height: 32px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; color: #b45309; font-size: 1.1rem; line-height: 1; cursor: pointer; }
.step-add { justify-self: start; border: 1px dashed #94a3b8; border-radius: 8px; padding: 8px 14px; background: #fff; color: #334155; font: inherit; cursor: pointer; }
.step-add:disabled { opacity: .55; cursor: not-allowed; }
.choice-list, .field-grid, .code-answer { display: grid; gap: 12px; }
.choice-list label { display: flex; align-items: flex-start; gap: 10px; padding: 13px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; cursor: pointer; }
.choice-list label.selected { border-color: #397d76; background: #f0fdfa; box-shadow: 0 0 0 1px #397d76; }
.choice-list input { width: auto; margin-top: 3px; }
.option-id { min-width: 1.5rem; color: #397d76; }
.field-grid label, .code-answer label { display: grid; gap: 7px; color: #334155; font-weight: 650; }
.field-grid b { color: #b45309; margin-left: 4px; }
.numeric-grid { grid-template-columns: minmax(140px, 1fr) minmax(140px, 1fr); }
.numeric-grid label:last-child { grid-column: 1 / -1; }
input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 8px; padding: 11px 12px; background: #fff; color: #0f172a; font: inherit; }
textarea { min-height: 120px; resize: vertical; line-height: 1.65; }
.code-editor { min-height: 240px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; tab-size: 4; }
.run-command { justify-self: start; border: 1px solid #94a3b8; border-radius: 8px; padding: 8px 14px; background: #fff; cursor: pointer; }
.run-output { margin: 0; max-height: 220px; overflow: auto; border-radius: 8px; padding: 12px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; }
@media (max-width: 700px) {
  .numeric-grid { grid-template-columns: 1fr; }
  .numeric-grid label:last-child { grid-column: auto; }
  .stepwise-switch { align-items: flex-start; flex-direction: column; gap: 8px; }
  .stepwise-toggle { width: 100%; }
  .stepwise-editor { padding: 10px; }
  .step-remove { margin-top: 24px; }
}
</style>
