<template>
  <div class="rai-chat">
    <div
      v-if="showPicker"
      ref="pickerRef"
      class="rai-chat__picker glass-panel"
    >
      <button
        type="button"
        class="rai-chat__picker-btn"
        :class="{ 'is-warning': pickerRequired && !pickerSelectedId, 'is-open': pickerMenuOpen }"
        aria-haspopup="listbox"
        :aria-expanded="pickerMenuOpen"
        @click.stop="togglePickerMenu"
      >
        <span class="rai-chat__picker-label">
          <span class="material-symbols-outlined rai-chat__file-icon" aria-hidden="true">description</span>
          <span class="rai-chat__picker-text">{{ pickerDisplayLabel }}</span>
        </span>
        <span
          class="material-symbols-outlined rai-chat__chevron"
          :class="{ 'is-open': pickerMenuOpen }"
          aria-hidden="true"
        >keyboard_arrow_down</span>
      </button>
    </div>

    <Teleport to="body">
      <div
        v-if="showPicker && pickerMenuOpen"
        ref="dropdownRef"
        class="rai-chat__dropdown-portal"
        :style="dropdownStyle"
        role="listbox"
        @click.stop
        @mousedown.stop
      >
        <button
          v-if="pickerAllowClear"
          type="button"
          class="rai-chat__dropdown-item rai-chat__dropdown-item--muted"
          @click.stop="onClearPicker"
        >
          {{ pickerClearLabel }}
        </button>
        <button
          v-for="item in pickerItems"
          :key="item.id"
          type="button"
          class="rai-chat__dropdown-item"
          role="option"
          @click.stop="onSelectPickerItem(item)"
        >
          {{ item.name }}
        </button>
        <p v-if="pickerLoading" class="rai-chat__dropdown-empty">{{ pickerLoadingText }}</p>
        <p v-else-if="pickerItems.length === 0" class="rai-chat__dropdown-empty">{{ pickerEmptyText }}</p>
      </div>
    </Teleport>

    <div class="rai-chat__composer glass-panel inset-shadow">
      <div v-if="prompts.length && !userInput" class="rai-chat__prompts">
        <button
          v-for="(hint, idx) in prompts"
          :key="idx"
          type="button"
          class="rai-chat__prompt-chip"
          :title="hint"
          :disabled="generating || disabled"
          @click="emit('apply-prompt', hint)"
        >
          <span class="material-symbols-outlined rai-chat__prompt-icon" aria-hidden="true">lightbulb</span>
          {{ hint }}
        </button>
      </div>
      <textarea
        ref="textareaRef"
        :value="userInput"
        class="rai-chat__input"
        rows="4"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="onInput"
      />
      <div
        v-for="(hint, idx) in inputHints"
        :key="idx"
        class="rai-chat__hint"
        :class="{ 'rai-chat__hint--error': hint.error }"
      >
        {{ hint.message }}
      </div>

      <div class="rai-chat__actions">
        <button
          v-if="showAttach"
          type="button"
          class="rai-chat__icon-btn"
          title="附件"
          :disabled="disabled"
          @click="emit('attach')"
        >
          <span class="material-symbols-outlined" aria-hidden="true">attach_file</span>
        </button>
        <button
          type="button"
          class="rai-chat__send-btn"
          title="发送"
          :disabled="sendDisabled"
          @click="emit('send')"
        >
          <span class="material-symbols-outlined" aria-hidden="true">send</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, type CSSProperties } from 'vue'

export interface ResourceAiPickerItem {
  id: string
  name: string
}

export interface ResourceAiInputHint {
  message: string
  error?: boolean
}

const props = withDefaults(
  defineProps<{
    userInput: string
    placeholder: string
    generating?: boolean
    disabled?: boolean
    sendDisabled?: boolean
    prompts?: string[]
    inputHints?: ResourceAiInputHint[]
    showAttach?: boolean
    showPicker?: boolean
    pickerItems?: ResourceAiPickerItem[]
    pickerSelectedId?: string | null
    pickerLabel?: string
    pickerPlaceholder?: string
    pickerRequired?: boolean
    pickerLoading?: boolean
    pickerEmptyText?: string
    pickerLoadingText?: string
    pickerAllowClear?: boolean
    pickerClearLabel?: string
  }>(),
  {
    generating: false,
    disabled: false,
    sendDisabled: false,
    prompts: () => [],
    inputHints: () => [],
    showAttach: true,
    showPicker: false,
    pickerItems: () => [],
    pickerSelectedId: null,
    pickerLabel: '',
    pickerPlaceholder: '请选择……',
    pickerRequired: false,
    pickerLoading: false,
    pickerEmptyText: '暂无可用资源',
    pickerLoadingText: '加载中...',
    pickerAllowClear: false,
    pickerClearLabel: '不选择基础资源',
  },
)

const emit = defineEmits<{
  (e: 'select-picker-item', item: ResourceAiPickerItem): void
  (e: 'clear-picker'): void
  (e: 'apply-prompt', text: string): void
  (e: 'attach'): void
  (e: 'send'): void
  (e: 'update:userInput', value: string): void
}>()

const pickerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const pickerMenuOpen = ref(false)
const dropdownStyle = ref<CSSProperties>({})

const pickerDisplayLabel = computed(
  () => props.pickerLabel || props.pickerPlaceholder,
)

function updateDropdownPosition() {
  const btn = pickerRef.value?.querySelector('.rai-chat__picker-btn') as HTMLElement | null
  if (!btn) return
  const rect = btn.getBoundingClientRect()
  dropdownStyle.value = {
    position: 'fixed',
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    zIndex: 1300,
  }
}

async function togglePickerMenu() {
  if (pickerMenuOpen.value) {
    pickerMenuOpen.value = false
    return
  }
  updateDropdownPosition()
  pickerMenuOpen.value = true
  await nextTick()
  updateDropdownPosition()
}

function closePickerMenu() {
  pickerMenuOpen.value = false
}

function onSelectPickerItem(item: ResourceAiPickerItem) {
  emit('select-picker-item', item)
  closePickerMenu()
}

function onClearPicker() {
  emit('clear-picker')
  closePickerMenu()
}

function onDocumentPointerDown(e: PointerEvent) {
  if (!pickerMenuOpen.value) return
  const target = e.target as Node
  if (pickerRef.value?.contains(target)) return
  if (dropdownRef.value?.contains(target)) return
  closePickerMenu()
}

function onViewportChange() {
  if (pickerMenuOpen.value) updateDropdownPosition()
}

function onInput(e: Event) {
  emit('update:userInput', (e.target as HTMLTextAreaElement).value)
}

function focusInput() {
  textareaRef.value?.focus()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown, true)
  window.addEventListener('resize', onViewportChange)
  window.addEventListener('scroll', onViewportChange, true)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
  closePickerMenu()
})

defineExpose({ focusInput })
</script>

<style scoped>
.rai-chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.04),
    0 1px 2px rgba(0, 0, 0, 0.02);
}

.inset-shadow {
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.03);
}

.rai-chat__picker {
  position: relative;
  border-radius: 12px;
  padding: 4px;
  z-index: 2;
}

.rai-chat__picker-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 10px;
  font-size: 14px;
  color: #1b1c1d;
  text-align: left;
}

.rai-chat__picker-btn.is-warning:not(.is-open) {
  outline: 1px solid rgba(255, 152, 0, 0.5);
}

.rai-chat__picker-label {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.rai-chat__file-icon {
  flex-shrink: 0;
  font-size: 20px;
  color: #4450b7;
}

.rai-chat__picker-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rai-chat__chevron {
  flex-shrink: 0;
  font-size: 22px;
  color: #8a8f98;
  transition: transform 0.2s;
}

.rai-chat__chevron.is-open {
  transform: rotate(180deg);
}

.rai-chat__prompts {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
  max-height: 106px;
  overflow-y: auto;
  padding: 0 0 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.rai-chat__prompt-chip {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid rgba(68, 80, 183, 0.1);
  border-radius: 8px;
  background: rgba(68, 80, 183, 0.04);
  font-size: 12px;
  line-height: 1.4;
  color: #4a4d53;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    background 0.15s,
    border-color 0.15s;
}

.rai-chat__prompt-icon {
  flex-shrink: 0;
  font-size: 14px;
  color: #4450b7;
  opacity: 0.7;
}

.rai-chat__prompt-chip:hover:not(:disabled) {
  background: rgba(68, 80, 183, 0.08);
  border-color: #bdc2ff;
  color: #1b1c1d;
}

.rai-chat__prompt-chip:hover:not(:disabled) .rai-chat__prompt-icon {
  opacity: 1;
}

.rai-chat__prompt-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rai-chat__composer {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  padding: 14px;
}

.rai-chat__input {
  flex: 1;
  width: 100%;
  min-height: 100px;
  border: none;
  background: transparent;
  resize: none;
  outline: none;
  font-size: 15px;
  line-height: 1.55;
  color: #08090a;
  font-family: inherit;
}

.rai-chat__input::placeholder {
  color: #8a8f98;
}

.rai-chat__input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.rai-chat__hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8a8f98;
}

.rai-chat__hint--error {
  color: #ba1a1a;
}

.rai-chat__actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-shrink: 0;
}

.rai-chat__icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #767684;
  cursor: pointer;
}

.rai-chat__icon-btn:hover:not(:disabled) {
  background: rgba(68, 80, 183, 0.08);
  color: #4450b7;
}

.rai-chat__icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.rai-chat__send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 12px;
  background: #4450b7;
  color: #fff;
  cursor: pointer;
  transition: background 0.2s;
}

.rai-chat__send-btn:hover:not(:disabled) {
  background: #3a46a8;
}

.rai-chat__send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.rai-chat__icon-btn .material-symbols-outlined,
.rai-chat__send-btn .material-symbols-outlined {
  font-size: 22px;
}
</style>

<style>
.rai-chat__dropdown-portal {
  max-height: 240px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.rai-chat__dropdown-portal .rai-chat__dropdown-item {
  display: block;
  width: 100%;
  padding: 12px 14px;
  border: none;
  background: none;
  text-align: left;
  font-size: 14px;
  color: #1b1c1d;
  cursor: pointer;
}

.rai-chat__dropdown-portal .rai-chat__dropdown-item:hover {
  background: #f5f3f4;
}

.rai-chat__dropdown-portal .rai-chat__dropdown-item--muted {
  color: #8a8f98;
}

.rai-chat__dropdown-portal .rai-chat__dropdown-empty {
  margin: 0;
  padding: 12px 14px;
  font-size: 13px;
  color: #8a8f98;
}
</style>
