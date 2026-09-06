<template>
  <div
    class="ui-segmented-control"
    :class="`ui-segmented-control--${size}`"
    role="group"
    :aria-label="accessibilityLabel"
    :style="indicatorStyle"
  >
    <span class="ui-segmented-control__indicator" aria-hidden="true" />
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :disabled="option.disabled"
      :aria-pressed="option.value === modelValue"
      :title="option.title || option.label"
      @click="selectOption(option)"
    >
      <component :is="option.icon" v-if="option.icon" :size="iconSize" aria-hidden="true" />
      <span>{{ option.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'

export interface UiSegmentedOption {
  value: string
  label: string
  title?: string
  icon?: Component
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  modelValue: string
  options: UiSegmentedOption[]
  accessibilityLabel: string
  size?: 'compact' | 'regular'
}>(), {
  size: 'regular',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const activeIndex = computed(() => {
  const index = props.options.findIndex(option => option.value === props.modelValue)
  return Math.max(0, index)
})
const indicatorStyle = computed(() => ({
  '--ui-segment-count': String(Math.max(1, props.options.length)),
  '--ui-segment-index': String(activeIndex.value),
}))
const iconSize = computed(() => props.size === 'compact' ? 14 : 16)

function selectOption(option: UiSegmentedOption) {
  if (option.disabled || option.value === props.modelValue) return
  emit('update:modelValue', option.value)
}
</script>

<style scoped>
.ui-segmented-control {
  --ui-segment-padding:4px;
  position:relative;
  isolation:isolate;
  min-width:0;
  height:42px;
  display:grid;
  grid-template-columns:repeat(var(--ui-segment-count),minmax(0,1fr));
  padding:var(--ui-segment-padding);
  border:1px solid #dbe2ee;
  border-radius:12px;
  background:#f8fafc;
}
.ui-segmented-control__indicator {
  position:absolute;
  z-index:-1;
  top:var(--ui-segment-padding);
  bottom:var(--ui-segment-padding);
  left:var(--ui-segment-padding);
  width:calc((100% - (var(--ui-segment-padding) * 2)) / var(--ui-segment-count));
  border-radius:8px;
  background:#fff;
  box-shadow:0 4px 12px rgba(51,65,85,.1),0 1px 2px rgba(51,65,85,.06);
  transform:translateX(calc(var(--ui-segment-index) * 100%));
  transition:transform .24s cubic-bezier(.16,1,.3,1),box-shadow .18s ease-out;
}
.ui-segmented-control button {
  min-width:0;
  height:32px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 10px;
  border:0;
  border-radius:8px;
  color:#64748b;
  background:transparent;
  font:inherit;
  font-size:12px;
  font-weight:700;
  white-space:nowrap;
  cursor:pointer;
  transition:color .18s ease-out,transform .12s ease-out;
}
.ui-segmented-control button:hover:not(:disabled) { color:#475569; }
.ui-segmented-control button[aria-pressed='true'] { color:var(--lz-brand-strong,#4f46e5); }
.ui-segmented-control button[aria-pressed='true'] svg { transform:scale(1.06); }
.ui-segmented-control button:active:not(:disabled) { transform:translateY(1px) scale(.985); }
.ui-segmented-control button:focus-visible { outline:3px solid rgba(99,102,241,.2); outline-offset:-2px; }
.ui-segmented-control button:disabled { opacity:.45; cursor:not-allowed; }
.ui-segmented-control button svg { flex:0 0 auto; transition:transform .18s cubic-bezier(.16,1,.3,1); }
.ui-segmented-control--compact {
  --ui-segment-padding:3px;
  height:34px;
  border-radius:9px;
}
.ui-segmented-control--compact .ui-segmented-control__indicator { border-radius:6px; box-shadow:0 2px 7px rgba(51,65,85,.09); }
.ui-segmented-control--compact button { height:26px; padding:0 8px; border-radius:6px; font-size:11px; }
@media (prefers-reduced-motion:reduce) {
  .ui-segmented-control__indicator,.ui-segmented-control button,.ui-segmented-control button svg { transition:none; }
}
</style>
