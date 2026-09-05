<template>
  <div ref="rootRef" class="more-options-menu">
    <button
      type="button"
      class="more-options-trigger"
      :class="{ 'is-open': open }"
      :disabled="disabled"
      title="更多操作"
      aria-label="更多操作"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click.stop="toggle"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <circle cx="12" cy="5" r="1.5" stroke="currentColor" stroke-width="2"/>
        <circle cx="12" cy="12" r="1.5" stroke="currentColor" stroke-width="2"/>
        <circle cx="12" cy="18" r="1.5" stroke="currentColor" stroke-width="2"/>
      </svg>
    </button>
    <div v-if="open" class="more-options-dropdown" role="menu" @click="onMenuClick">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(
  defineProps<{
    disabled?: boolean
  }>(),
  { disabled: false },
)

const rootRef = ref<HTMLElement | null>(null)

function toggle() {
  if (props.disabled) return
  open.value = !open.value
}

function onDocumentClick(event: MouseEvent) {
  if (!open.value) return
  const target = event.target as Node
  if (rootRef.value && !rootRef.value.contains(target)) {
    open.value = false
  }
}

function onMenuClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (target.closest('button[disabled]')) return
  if (target.closest('button, a, [role="menuitem"]')) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})

function close() {
  open.value = false
}

defineExpose({ close })
</script>

<style scoped>
.more-options-menu {
  position: relative;
  flex-shrink: 0;
}

.more-options-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 36px;
  padding: 0;
  background-color: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  color: #666;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s, color 0.2s;
}

.more-options-trigger:hover:not(:disabled) {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
  color: #333;
}

.more-options-trigger.is-open:not(:disabled) {
  border-color: #c5d9ff;
  background-color: #f8f9ff;
  color: #333;
}

.more-options-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.more-options-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 148px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 30;
  padding: 6px;
  overflow: hidden;
}

.more-options-dropdown :slotted(button) {
  display: block;
  width: 100%;
  padding: 10px 14px;
  border: none;
  background: transparent;
  text-align: left;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.more-options-dropdown :slotted(button:hover:not(:disabled)) {
  background: #f5f5f5;
}

.more-options-dropdown :slotted(button:disabled) {
  opacity: 0.5;
  cursor: not-allowed;
}

.more-options-dropdown :slotted(.is-danger) {
  color: #d32f2f;
}

.more-options-dropdown :slotted(.is-danger:hover:not(:disabled)) {
  background: #ffebee;
}
</style>
