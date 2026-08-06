<template>
  <fieldset
    class="assessment-generation-profile"
    :class="{ 'assessment-generation-profile--compact': compact }"
    data-testid="assessment-generation-profile-selector"
  >
    <legend>{{ label || t('assessmentGeneration.label', '题目生成方式') }}</legend>
    <div class="assessment-generation-profile__options">
      <button
        type="button"
        data-testid="assessment-profile-fast"
        :class="{ active: modelValue === 'fast' }"
        :aria-pressed="modelValue === 'fast'"
        :disabled="disabled"
        @click="choose('fast')"
      >
        <strong>{{ t('assessmentGeneration.fastLabel', '快速版') }}</strong>
        <small v-if="!compact">{{ t('assessmentGeneration.fastHelp', '批量生成与独立求解；复杂题和关键修复仍会保留必要思考') }}</small>
      </button>
      <button
        type="button"
        data-testid="assessment-profile-deliberate"
        :class="{ active: modelValue === 'deliberate' }"
        :aria-pressed="modelValue === 'deliberate'"
        :disabled="disabled"
        @click="choose('deliberate')"
      >
        <strong>{{ t('assessmentGeneration.deliberateLabel', '思考版') }}</strong>
        <small v-if="!compact">{{ t('assessmentGeneration.deliberateHelp', '完整逐题独立求解，并保留更多质量修复轮次') }}</small>
      </button>
    </div>
    <small v-if="hint" class="assessment-generation-profile__hint">{{ hint }}</small>
  </fieldset>
</template>

<script setup lang="ts">
import type { AssessmentGenerationProfile } from '@/utils/question-bank-rebuild'
import { t } from '@/shared/i18n'

const props = withDefaults(defineProps<{
  modelValue: AssessmentGenerationProfile
  disabled?: boolean
  compact?: boolean
  label?: string
  hint?: string
}>(), {
  disabled: false,
  compact: false,
  label: '',
  hint: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: AssessmentGenerationProfile]
}>()

function choose(value: AssessmentGenerationProfile) {
  if (!props.disabled) emit('update:modelValue', value)
}
</script>

<style scoped>
.assessment-generation-profile { min-width:0; margin:0; padding:0; border:0; }
.assessment-generation-profile legend { margin-bottom:8px; color:var(--lz-text, #334155); font-size:12px; font-weight:700; }
.assessment-generation-profile__options { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
.assessment-generation-profile__options button { min-width:0; display:grid; gap:3px; padding:11px 12px; border:1px solid var(--lz-border, #e2e8f0); border-radius:9px; color:var(--lz-text-secondary, #475569); background:#fff; text-align:left; cursor:pointer; }
.assessment-generation-profile__options button.active { border-color:var(--lz-brand, #6366f1); color:var(--lz-brand-strong, #4338ca); background:var(--lz-brand-soft, #eef2ff); box-shadow:inset 0 0 0 1px rgba(99,102,241,.08); }
.assessment-generation-profile__options button:disabled { cursor:not-allowed; opacity:.62; }
.assessment-generation-profile__options strong { font-size:12px; }
.assessment-generation-profile__options small,.assessment-generation-profile__hint { color:var(--lz-text-muted, #64748b); font-size:10px; line-height:1.45; }
.assessment-generation-profile__hint { display:block; margin-top:6px; }
.assessment-generation-profile--compact legend { margin-bottom:5px; font-size:10px; }
.assessment-generation-profile--compact .assessment-generation-profile__options { display:flex; gap:5px; }
.assessment-generation-profile--compact .assessment-generation-profile__options button { display:block; padding:6px 9px; text-align:center; }
@media (max-width: 520px) { .assessment-generation-profile__options { grid-template-columns:1fr; } }
</style>
