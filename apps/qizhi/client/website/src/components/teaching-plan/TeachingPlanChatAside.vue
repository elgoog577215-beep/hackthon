<template>
  <div class="tp-chat">
    <div ref="outlinePickerRef" class="tp-chat__outline glass-panel">
      <button
        type="button"
        class="tp-chat__outline-btn"
        :class="{ 'is-warning': !selectedOutlineId, 'is-open': outlineMenuOpen }"
        aria-haspopup="listbox"
        :aria-expanded="outlineMenuOpen"
        @click.stop="toggleOutlineMenu"
      >
        <span class="tp-chat__outline-label">
          <span class="material-symbols-outlined tp-chat__file-icon" aria-hidden="true">description</span>
          <span class="tp-chat__outline-text">{{ selectedLabel }}</span>
        </span>
        <span
          class="material-symbols-outlined tp-chat__chevron"
          :class="{ 'is-open': outlineMenuOpen }"
          aria-hidden="true"
        >keyboard_arrow_down</span>
      </button>
    </div>

    <Teleport to="body">
      <div
        v-if="outlineMenuOpen"
        ref="dropdownRef"
        class="tp-chat__dropdown-portal"
        :style="dropdownStyle"
        role="listbox"
        @click.stop
        @mousedown.stop
      >
        <button
          v-for="outline in outlineList"
          :key="outline.id"
          type="button"
          class="tp-chat__dropdown-item"
          role="option"
          @click.stop="selectOutlineItem(outline)"
        >
          {{ outline.name }}
        </button>
        <p v-if="loadingOutlines" class="tp-chat__dropdown-empty">加载中...</p>
        <p v-else-if="outlineList.length === 0" class="tp-chat__dropdown-empty">暂无教学大纲</p>
      </div>
    </Teleport>

    <div class="tp-chat__prompts">
      <button
        v-for="(hint, idx) in promptHints"
        :key="idx"
        type="button"
        class="tp-chat__prompt-chip"
        :title="hint"
        :disabled="generating"
        @click="emit('apply-prompt', hint)"
      >
        {{ hint }}
      </button>
    </div>

    <div class="tp-chat__composer glass-panel inset-shadow">
      <textarea
        ref="textareaRef"
        :value="userInput"
        class="tp-chat__input"
        rows="4"
        placeholder="请输入生成教案的章节与要求（必填）"
        :disabled="disabled"
        @input="onInput"
      />
      <div v-if="!selectedOutlineId" class="tp-chat__hint tp-chat__hint--error">请选择教学大纲</div>

      <div class="tp-chat__actions">
        <button type="button" class="tp-chat__icon-btn" title="附件" :disabled="disabled" @click="emit('attach')">
          <span class="material-symbols-outlined" aria-hidden="true">attach_file</span>
        </button>
        <button
          type="button"
          class="tp-chat__send-btn"
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
import type { ResourceResponse } from '../../api/types'
import { buildTeachingPlanPromptSuggestions } from '../../lib/teachingPlanPrompts'

const props = withDefaults(
  defineProps<{
    outlineList: ResourceResponse[]
    selectedOutlineId: string | null
    selectedLabel: string
    loadingOutlines: boolean
    userInput: string
    generating: boolean
    disabled?: boolean
  }>(),
  { disabled: false },
)

const emit = defineEmits<{
  (e: 'select-outline', outline: ResourceResponse): void
  (e: 'apply-prompt', text: string): void
  (e: 'attach'): void
  (e: 'send'): void
  (e: 'update:userInput', value: string): void
}>()

const outlinePickerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const outlineMenuOpen = ref(false)
const dropdownStyle = ref<CSSProperties>({})

const promptHints = computed(() => {
  const selected = props.outlineList.find((o) => o.id === props.selectedOutlineId) ?? null
  return buildTeachingPlanPromptSuggestions(selected)
})

const sendDisabled = computed(
  () =>
    props.generating ||
    props.disabled ||
    !props.selectedOutlineId ||
    !props.userInput.trim(),
)

function updateDropdownPosition() {
  const btn = outlinePickerRef.value?.querySelector('.tp-chat__outline-btn') as HTMLElement | null
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

async function toggleOutlineMenu() {
  if (outlineMenuOpen.value) {
    outlineMenuOpen.value = false
    return
  }
  updateDropdownPosition()
  outlineMenuOpen.value = true
  await nextTick()
  updateDropdownPosition()
}

function closeOutlineMenu() {
  outlineMenuOpen.value = false
}

function selectOutlineItem(outline: ResourceResponse) {
  emit('select-outline', outline)
  closeOutlineMenu()
}

function onDocumentPointerDown(e: PointerEvent) {
  if (!outlineMenuOpen.value) return
  const target = e.target as Node
  if (outlinePickerRef.value?.contains(target)) return
  if (dropdownRef.value?.contains(target)) return
  closeOutlineMenu()
}

function onViewportChange() {
  if (outlineMenuOpen.value) updateDropdownPosition()
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
  closeOutlineMenu()
})

defineExpose({ focusInput })
</script>

<style scoped>
.tp-chat {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow: visible;
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

.tp-chat__outline {
  position: relative;
  border-radius: 12px;
  padding: 4px;
  z-index: 2;
}

.tp-chat__outline-btn {
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

.tp-chat__outline-btn.is-warning:not(.is-open) {
  outline: 1px solid rgba(255, 152, 0, 0.5);
}

.tp-chat__outline-label {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.tp-chat__file-icon {
  flex-shrink: 0;
  font-size: 20px;
  color: #4450b7;
}

.tp-chat__outline-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tp-chat__chevron {
  flex-shrink: 0;
  font-size: 22px;
  color: #8a8f98;
  transition: transform 0.2s;
}

.tp-chat__chevron.is-open {
  transform: rotate(180deg);
}

.tp-chat__prompts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  max-height: 112px;
  overflow-y: auto;
  padding-right: 2px;
}

.tp-chat__prompt-chip {
  flex-shrink: 0;
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  line-height: 1.4;
  color: #4a4d53;
  text-align: left;
  cursor: pointer;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition:
    background 0.15s,
    border-color 0.15s;
}

.tp-chat__prompt-chip:hover:not(:disabled) {
  background: #fff;
  border-color: #bdc2ff;
  color: #1b1c1d;
}

.tp-chat__prompt-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tp-chat__composer {
  flex: 1;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  padding: 14px;
}

.tp-chat__input {
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

.tp-chat__input::placeholder {
  color: #8a8f98;
}

.tp-chat__input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.tp-chat__hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8a8f98;
}

.tp-chat__hint--error {
  color: #ba1a1a;
}

.tp-chat__actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.tp-chat__icon-btn {
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

.tp-chat__icon-btn:hover:not(:disabled) {
  background: rgba(68, 80, 183, 0.08);
  color: #4450b7;
}

.tp-chat__icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tp-chat__send-btn {
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

.tp-chat__send-btn:hover:not(:disabled) {
  background: #3a46a8;
}

.tp-chat__send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.tp-chat__icon-btn .material-symbols-outlined,
.tp-chat__send-btn .material-symbols-outlined {
  font-size: 22px;
}
</style>

<!-- Teleport 到 body，下拉层样式需非 scoped -->
<style>
.tp-chat__dropdown-portal {
  max-height: 240px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.tp-chat__dropdown-portal .tp-chat__dropdown-item {
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

.tp-chat__dropdown-portal .tp-chat__dropdown-item:hover {
  background: #f5f3f4;
}

.tp-chat__dropdown-portal .tp-chat__dropdown-empty {
  margin: 0;
  padding: 12px 14px;
  font-size: 13px;
  color: #8a8f98;
}
</style>
