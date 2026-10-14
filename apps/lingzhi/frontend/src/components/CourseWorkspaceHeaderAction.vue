<template>
  <button
    type="button"
    class="workspace-header-action"
    :class="{ 'is-primary': primary, 'is-icon-only': iconOnly }"
    :aria-label="label"
    :title="hint || label"
  >
    <slot />
    <span class="workspace-header-action__label">{{ displayLabel || label }}</span>
  </button>
</template>

<script setup lang="ts">
defineProps<{ label: string; displayLabel?: string; hint?: string; primary?: boolean; iconOnly?: boolean }>()
</script>

<style scoped>
.workspace-header-action {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 11px;
  border: 1px solid var(--lz-border, #dce1ed);
  border-radius: 8px;
  background: #fff;
  color: var(--lz-text-secondary, #475569);
  font: 700 15px/1.4 var(--lz-font-sans, sans-serif);
  white-space: nowrap;
  cursor: pointer;
}
.workspace-header-action :deep(svg) { flex: none; }
.workspace-header-action:hover { border-color: #aaa7f2; color: #5148dc; background: #f8f8ff; }
.workspace-header-action.is-primary { color: var(--lz-brand-strong, #6551c7); border-color: var(--lz-brand-border, #aaa7f2); }
.workspace-header-action:focus-visible { outline: 3px solid #9385ed; outline-offset: 3px; }
.workspace-header-action.is-icon-only { width: 38px; padding: 0; }
.workspace-header-action.is-icon-only .workspace-header-action__label { display: none; }
@container course-workspace-header (max-width: 1480px) {
  .workspace-header-action { width: 38px; padding: 0; }
  .workspace-header-action__label { display: none; }
}
</style>
