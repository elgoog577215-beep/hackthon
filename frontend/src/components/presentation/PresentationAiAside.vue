<script setup lang="ts">
import { computed, ref } from 'vue'
import PresentationPatchProposal from './PresentationPatchProposal.vue'
import PresentationQualityPanel from './PresentationQualityPanel.vue'
import type {
  PresentationProposal,
  PresentationQualityIssue,
  PresentationSlide,
  PresentationStudioPhase,
  PresentationTemplateId,
} from '@/types/presentation'

const props = defineProps<{
  phase: PresentationStudioPhase
  scopeType: 'chapter' | 'course'
  templateId: PresentationTemplateId
  purpose: 'teaching' | 'self_study'
  pageBudget: number
  requirements: string
  selectedSlide: PresentationSlide | null
  proposal: PresentationProposal | null
  quality: { status: 'passed' | 'blocked' | 'advisory'; issues: PresentationQualityIssue[] } | null
  error: string | null
  progress: { completed: number; total: number; message: string }
  generating?: boolean
  proposing?: boolean
  applying?: boolean
  finalizing?: boolean
  canUndo?: boolean
}>()

const emit = defineEmits<{
  'update:scopeType': [value: 'chapter' | 'course']
  'update:templateId': [value: PresentationTemplateId]
  'update:purpose': [value: 'teaching' | 'self_study']
  'update:pageBudget': [value: number]
  'update:requirements': [value: string]
  generate: []
  prompt: [value: string]
  apply: []
  cancelProposal: []
  undo: []
  finalize: []
  viewSource: []
}>()

const prompt = ref('')
const compareOpen = ref(false)

const RETRYABLE_GENERATION_CODES = new Set([
  'model_unavailable',
  'invalid_model_payload',
  'slide_generation_failed',
])

const editingTarget = computed(() => props.selectedSlide
  ? `正在修改：第 ${props.selectedSlide.position + 1} 页 · ${props.selectedSlide.title || '未命名页'}`
  : '作用范围：整套课件')
const isConfiguring = computed(() => props.phase === 'configuring' || props.phase === 'booting')
const canPrompt = computed(() => !props.proposing && (!props.selectedSlide || props.selectedSlide.status === 'ready'))
const canRetryGeneration = computed(() => {
  if (isConfiguring.value || !props.quality) return false
  const codes = new Set(props.quality.issues.map(issue => issue.code))
  const hasRetryableFailure = [...codes].some(code => RETRYABLE_GENERATION_CODES.has(code))
  const isLegacyFailedDeck = codes.has('slide_not_ready') && codes.has('layout_required_slot_missing')
  return hasRetryableFailure || isLegacyFailedDeck
})
const retryGenerationLabel = computed(() => {
  if (!props.generating) return '重新生成课件'
  if (props.progress.total > 0) {
    return `正在重新生成课件… ${props.progress.completed} / ${props.progress.total}`
  }
  return '正在重新生成课件…'
})

function sendPrompt(value = prompt.value) {
  const normalized = value.trim()
  if (!normalized || !canPrompt.value) return
  emit('prompt', normalized)
  prompt.value = ''
}

const quickPrompt = (value: string) => sendPrompt(value)
</script>

<template>
  <aside class="presentation-ai-aside" aria-label="课件 AI">
    <header class="ai-heading">
      <h2>✦　课件 AI</h2>
      <span v-if="!isConfiguring" class="scope-pill">{{ editingTarget }}</span>
      <p v-else>选好依据和课件表达，灵知会先规划页序，再逐页生成。</p>
    </header>

    <div v-if="error" class="error-notice" role="alert">{{ error }}</div>

    <div class="settings">
      <label class="setting-row">
        <span>依据</span>
        <select :value="scopeType" :disabled="generating || !isConfiguring" @change="$emit('update:scopeType', ($event.target as HTMLSelectElement).value as 'chapter' | 'course')">
          <option value="chapter">当前章节</option><option value="course">整门课程</option>
        </select>
      </label>
      <label class="setting-row">
        <span>模板</span>
        <select :value="templateId" :disabled="generating || !isConfiguring" @change="$emit('update:templateId', ($event.target as HTMLSelectElement).value as PresentationTemplateId)">
          <option value="lingzhi-classroom">灵知课堂</option><option value="lingzhi-engineering">理工推演</option><option value="lingzhi-academic">学术答辩</option>
        </select>
      </label>
      <label class="setting-row">
        <span>用途</span>
        <select :value="purpose" :disabled="generating || !isConfiguring" @change="$emit('update:purpose', ($event.target as HTMLSelectElement).value as 'teaching' | 'self_study')">
          <option value="teaching">教师授课</option><option value="self_study">学生自学</option>
        </select>
      </label>
    </div>

    <template v-if="isConfiguring">
      <label class="field-label">
        <span>页数预算</span>
        <input type="number" min="3" max="30" :value="pageBudget" @input="$emit('update:pageBudget', Number(($event.target as HTMLInputElement).value))">
      </label>
      <label class="field-label requirements-field">
        <span>额外要求</span>
        <textarea :value="requirements" placeholder="例如：保留指针代码推演，增加课堂练习…" @input="$emit('update:requirements', ($event.target as HTMLTextAreaElement).value)" />
      </label>
      <button class="primary-action" type="button" :disabled="generating" @click="$emit('generate')">
        {{ generating ? '正在生成课件…' : '开始生成课件' }}
      </button>
    </template>

    <template v-else>
      <div v-if="generating" class="generation-progress">
        <div><strong>{{ progress.message || '正在逐页生成' }}</strong><span>{{ progress.completed }} / {{ progress.total || '—' }}</span></div>
        <progress :max="progress.total || 1" :value="progress.completed" />
      </div>

      <div class="quick-actions">
        <button type="button" :disabled="!canPrompt" @click="quickPrompt('为当前页补一个容易讲清的例子')">＋ 补一个例子</button>
        <button type="button" :disabled="!canPrompt" @click="quickPrompt('把相关常见误区补到当前页')">！ 加入易错点</button>
        <button type="button" :disabled="!canPrompt" @click="quickPrompt('把当前页改成可以当场作答的课堂练习')">▤ 变课堂练习</button>
        <button type="button" :disabled="!canPrompt" @click="quickPrompt('精简当前页，保留核心教学信息')">✎ 精简本页</button>
      </div>

      <PresentationPatchProposal
        v-if="proposal"
        :proposal="proposal"
        :applying="applying"
        @apply="$emit('apply')"
        @cancel="$emit('cancelProposal')"
        @compare="compareOpen = !compareOpen"
      />
      <div v-if="compareOpen && proposal" class="comparison-note">对比已展开；只有点击“应用修改”才会创建新修订。</div>

      <button
        v-if="canRetryGeneration"
        class="primary-action"
        type="button"
        :disabled="generating"
        @click="$emit('generate')"
      >
        {{ retryGenerationLabel }}
      </button>

      <PresentationQualityPanel v-if="quality" :status="quality.status" :issues="quality.issues" />

      <div class="secondary-actions">
        <button type="button" :disabled="!selectedSlide" @click="$emit('viewSource')">查看来源</button>
        <button type="button" :disabled="!canUndo || applying" @click="$emit('undo')">撤销上次修改</button>
        <button class="finish" type="button" :disabled="generating || finalizing || !selectedSlide" @click="$emit('finalize')">
          {{ finalizing ? '正在质检与渲染…' : '完成课件' }}
        </button>
      </div>

      <form class="composer" @submit.prevent="sendPrompt()">
        <span aria-hidden="true">✦</span>
        <textarea v-model="prompt" :disabled="!canPrompt" rows="1" placeholder="告诉我想怎样改这一页…" />
        <button class="send" type="submit" :disabled="!prompt.trim() || !canPrompt" aria-label="发送修改要求">➜</button>
      </form>
    </template>
  </aside>
</template>

<style scoped>
.presentation-ai-aside{min-width:0;min-height:0;display:flex;flex-direction:column;gap:14px;overflow:auto;border:1px solid #e2e8f0;border-radius:13px;padding:18px;background:#fff}.ai-heading h2{margin:0;color:#1e293b;font-size:18px}.ai-heading>p{margin:9px 0 0;color:#64748b;font-size:12px;line-height:1.65}.scope-pill{display:inline-block;margin-top:8px;padding:5px 9px;border-radius:999px;color:#4f46e5;background:#eef2ff;font-size:12px}.error-notice{padding:9px 10px;border-left:3px solid #dc2626;border-radius:0 7px 7px 0;color:#b91c1c;background:#fef2f2;font-size:12px}.settings{overflow:hidden;border:1px solid #e2e8f0;border-radius:9px}.setting-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border-bottom:1px solid #e2e8f0;color:#475569}.setting-row:last-child{border:0}.setting-row select{min-width:145px;border:0;color:#334155;background:transparent;text-align:right;outline:none}.field-label{display:grid;gap:6px;color:#475569;font-size:12px}.field-label input,.field-label textarea{width:100%;border:1px solid #dfe3eb;border-radius:8px;padding:9px 10px;color:#334155;background:#fff;font:inherit;outline:none}.field-label input:focus,.field-label textarea:focus{border-color:#a5b4fc;box-shadow:0 0 0 3px rgba(99,102,241,.08)}.requirements-field textarea{min-height:110px;resize:vertical}.primary-action{min-height:42px;border:1px solid #4f46e5;border-radius:8px;color:#fff;background:#6366f1;font-weight:700}.primary-action:disabled{opacity:.58}.generation-progress{padding:11px;border:1px solid #e0e7ff;border-radius:9px;background:#f8faff}.generation-progress>div{display:flex;justify-content:space-between;color:#475569;font-size:12px}.generation-progress progress{width:100%;height:6px;margin-top:8px;accent-color:#6366f1}.quick-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.quick-actions button{min-height:42px;padding:9px;border:1px solid #e0e4eb;border-radius:8px;color:#475569;background:#fff;text-align:left}.quick-actions button:hover:not(:disabled){border-color:#c7d2fe;color:#4f46e5;background:#fafaff}.quick-actions button:disabled{opacity:.5}.comparison-note{padding:8px 9px;border-radius:7px;color:#4f46e5;background:#eef2ff;font-size:11px}.secondary-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.secondary-actions button{min-height:38px;border:1px solid #dfe3eb;border-radius:8px;color:#475569;background:#fff}.secondary-actions .finish{grid-column:1/-1;border-color:#6366f1;color:#fff;background:#6366f1;font-weight:700}.secondary-actions button:disabled{opacity:.5}.composer{min-height:54px;display:grid;grid-template-columns:auto minmax(0,1fr) 34px;align-items:end;gap:8px;margin-top:auto;padding:9px 8px 8px 11px;border:1px solid #d9dce8;border-radius:10px;color:#94a3b8;background:#fff}.composer:focus-within{border-color:#a5b4fc;box-shadow:0 0 0 3px rgba(99,102,241,.08)}.composer textarea{min-height:32px;max-height:100px;resize:none;border:0;padding:5px 0;color:#334155;background:transparent;font:inherit;font-size:12px;outline:none}.send{width:34px;height:34px;border:0;border-radius:7px;color:#fff;background:#6366f1}.send:disabled{color:#cbd5e1;background:#f1f5f9}@media(max-width:520px){.presentation-ai-aside{padding:14px}.setting-row select{min-width:128px}.quick-actions{grid-template-columns:1fr}.composer{position:sticky;bottom:0}}
</style>
