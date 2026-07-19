<template>
  <section class="answer-renderer" :data-mode="mode">
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
        <span>{{ optionLabel(option) }}</span>
      </label>
    </div>

    <div v-else-if="mode === 'numeric_unit'" class="field-grid numeric-grid">
      <label v-for="field in fields" :key="field.field_id">
        <span>{{ field.label }}</span>
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
        <span>编程语言</span>
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
        <span>代码</span>
        <textarea
          class="code-editor"
          spellcheck="false"
          :value="draft.code || ''"
          :disabled="disabled"
          @input="setFromEvent('code', $event)"
        />
      </label>
      <button type="button" class="run-command" :disabled="disabled || running || !draft.code" @click="runPreview">
        {{ running ? '运行中…' : '运行代码' }}
      </button>
      <pre v-if="runOutput" class="run-output">{{ runOutput }}</pre>
      <label v-if="fields.some(field => field.field_id === 'test_evidence')">
        <span>测试说明</span>
        <textarea
          :value="draft.test_evidence || ''"
          :disabled="disabled"
          @input="setFromEvent('test_evidence', $event)"
        />
      </label>
    </div>

    <div v-else-if="mode === 'structured_fields'" class="field-grid">
      <label v-for="field in fields" :key="field.field_id">
        <span>{{ field.label }}<b v-if="field.required" aria-label="必填">*</b></span>
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
import http from '../utils/http'

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
      { field_id: 'value', kind: 'number', label: '数值', required: true },
      { field_id: 'unit', kind: 'short_text', label: '单位', required: true },
      { field_id: 'work', kind: 'rich_text', label: '计算过程', required: true },
    ]
  }
  if (mode.value === 'code') {
    return [
      { field_id: 'code', kind: 'code', label: '代码', required: true },
      { field_id: 'test_evidence', kind: 'rich_text', label: '测试说明' },
    ]
  }
  if (mode.value === 'structured_fields') {
    if (props.questionType === 'debugging_trace') {
      return [
        { field_id: 'trace', kind: 'rich_text', label: '执行轨迹', required: true },
        { field_id: 'diagnosis', kind: 'rich_text', label: '问题定位', required: true },
        { field_id: 'result_check', kind: 'rich_text', label: '结果检查', required: true },
      ]
    }
    return [
      { field_id: 'answer', kind: 'rich_text', label: '作答', required: true },
      { field_id: 'evidence', kind: 'rich_text', label: '依据', required: true },
      { field_id: 'result_check', kind: 'rich_text', label: '结果检查', required: true },
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
      .join('\n') || '运行完成，无输出'
    setValue('run_result', {
      status: response.data?.error ? 'failed' : 'completed',
      output: runOutput.value.slice(0, 32768),
    })
  } catch {
    runOutput.value = '运行失败'
    ElMessage.error('代码运行失败')
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.answer-renderer { display: grid; gap: 14px; }
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
}
</style>
