<template>
  <nav class="workflow-steps" :aria-label="label">
    <button v-for="step in steps" :key="step.value" type="button"
      :class="{ active: modelValue === step.value, complete: step.complete }"
      :aria-current="modelValue === step.value ? 'step' : undefined"
      :disabled="step.disabled" @click="emit('select', step.value)">
      <span>{{ step.value }}</span><strong>{{ step.label }}</strong>
      <Check v-if="step.complete" :size="14" aria-hidden="true" />
    </button>
  </nav>
</template>

<script setup lang="ts">
import { Check } from 'lucide-vue-next'
defineProps<{ label: string; modelValue: number; steps: Array<{ value: number; label: string; complete?: boolean; disabled?: boolean }> }>()
const emit = defineEmits<{ select: [value: number] }>()
</script>

<style scoped>
.workflow-steps{display:flex;gap:4px;min-width:0;padding:3px;border:1px solid #dfe4ed;border-radius:11px;background:#eef1f6}
.workflow-steps button{flex:1;min-width:0;min-height:42px;display:flex;align-items:center;gap:8px;padding:8px 12px;border:0;border-radius:8px;color:#526076;background:transparent;text-align:left;cursor:pointer}
.workflow-steps button>span{width:22px;height:22px;flex-shrink:0;display:grid;place-items:center;border:1px solid #aeb9c9;border-radius:50%;font-size:13px;font-weight:700}
.workflow-steps button>strong{min-width:0;font-size:15px;line-height:1.4;font-weight:600}
.workflow-steps button>svg{flex-shrink:0;color:#168044;margin-left:auto}
.workflow-steps button:hover:not(:disabled){color:#37348c;background:rgba(255,255,255,.7)}
.workflow-steps button.active{color:#312e81;background:#fff;box-shadow:0 2px 8px rgba(30,41,59,.08)}
.workflow-steps button.active>span{border-color:#6965d8;color:#fff;background:#6965d8}
.workflow-steps button.complete>span{border-color:#a7d9ba;color:#168044;background:#edf9f1}
.workflow-steps button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.workflow-steps button:disabled{opacity:.55;cursor:not-allowed}
</style>
