<template>
  <div
    ref="rootRef"
    class="ui-select-menu"
    :class="{ 'is-open': open }"
    @keydown.esc.stop.prevent="closeMenu(true)"
  >
    <button
      ref="triggerRef"
      type="button"
      class="ui-select-menu__trigger"
      :aria-label="accessibilityLabel"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="menuId"
      @click="toggleMenu"
      @keydown.down.prevent="openMenu('selected')"
      @keydown.up.prevent="openMenu('last')"
    >
      <span class="ui-select-menu__copy">
        <small>{{ label }}</small>
        <Transition name="ui-select-value" mode="out-in">
          <strong :key="selectedOption?.value || modelValue">{{ selectedOption?.label || modelValue }}</strong>
        </Transition>
      </span>
      <span v-if="selectedOption?.count !== undefined" class="ui-select-menu__count" aria-hidden="true">
        {{ selectedOption.count }}
      </span>
      <ChevronDown class="ui-select-menu__chevron" :size="15" aria-hidden="true" />
    </button>

    <Transition name="ui-select-options">
      <div
        v-if="open"
        :id="menuId"
        class="ui-select-menu__options"
        role="listbox"
        :aria-label="accessibilityLabel"
        @keydown="handleOptionsKeydown"
      >
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          role="option"
          :data-option-value="option.value"
          :aria-selected="option.value === modelValue"
          :disabled="option.disabled"
          tabindex="-1"
          @click="selectOption(option)"
        >
          <Check class="ui-select-menu__check" :class="{ visible: option.value === modelValue }" :size="15" aria-hidden="true" />
          <span class="ui-select-menu__option-copy">
            <strong>{{ option.label }}</strong>
            <small v-if="option.hint">{{ option.hint }}</small>
          </span>
          <span v-if="option.count !== undefined" class="ui-select-menu__option-count">{{ option.count }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'

export interface UiSelectOption {
  value: string
  label: string
  hint?: string
  count?: number
  disabled?: boolean
}

const props = defineProps<{
  modelValue: string
  options: UiSelectOption[]
  label: string
  accessibilityLabel: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const menuId = `ui-select-${Math.random().toString(36).slice(2, 10)}`
const selectedOption = computed(() => props.options.find(option => option.value === props.modelValue))

onMounted(() => document.addEventListener('pointerdown', handleOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', handleOutsidePointer))

function handleOutsidePointer(event: PointerEvent) {
  if (!open.value || rootRef.value?.contains(event.target as Node)) return
  closeMenu(false)
}

function toggleMenu() {
  if (open.value) closeMenu(false)
  else void openMenu('selected')
}

async function openMenu(focus: 'selected' | 'last') {
  open.value = true
  await nextTick()
  const options = optionButtons()
  const target = focus === 'last'
    ? options.at(-1)
    : options.find(option => option.dataset.optionValue === props.modelValue) || options[0]
  target?.focus()
}

function closeMenu(restoreFocus: boolean) {
  if (!open.value) return
  open.value = false
  if (restoreFocus) void nextTick(() => triggerRef.value?.focus())
}

function selectOption(option: UiSelectOption) {
  if (option.disabled) return
  if (option.value !== props.modelValue) emit('update:modelValue', option.value)
  closeMenu(true)
}

function optionButtons() {
  if (!rootRef.value) return []
  return Array.from(rootRef.value.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)'))
}

function handleOptionsKeydown(event: KeyboardEvent) {
  const options = optionButtons()
  if (!options.length) return
  const activeIndex = Math.max(0, options.indexOf(document.activeElement as HTMLButtonElement))
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const direction = event.key === 'ArrowDown' ? 1 : -1
    options[(activeIndex + direction + options.length) % options.length]?.focus()
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault()
    options[event.key === 'Home' ? 0 : options.length - 1]?.focus()
  } else if (event.key === 'Tab') {
    closeMenu(false)
  }
}
</script>

<style scoped>
.ui-select-menu { position:relative; min-width:0; width:100%; }
.ui-select-menu__trigger {
  width:100%;
  height:42px;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto 18px;
  align-items:center;
  gap:7px;
  padding:5px 9px 5px 11px;
  border:1px solid #dbe2ee;
  border-radius:12px;
  color:#475569;
  background:#fff;
  font:inherit;
  text-align:left;
  cursor:pointer;
  transition:border-color .16s ease-out,box-shadow .16s ease-out,background .16s ease-out,transform .12s ease-out;
}
.ui-select-menu__trigger:hover { border-color:#c7d2fe; background:#fefeff; }
.ui-select-menu__trigger:active { transform:scale(.985); }
.ui-select-menu__trigger:focus-visible,.ui-select-menu.is-open .ui-select-menu__trigger {
  border-color:#a5b4fc;
  outline:0;
  box-shadow:0 5px 16px rgba(79,70,229,.09),0 0 0 3px rgba(99,102,241,.1);
}
.ui-select-menu__copy { min-width:0; display:grid; gap:1px; }
.ui-select-menu__copy small { color:#64748b; font-size:9px; font-weight:650; line-height:1; }
.ui-select-menu__copy strong { overflow:hidden; display:block; color:#475569; font-size:12px; font-weight:750; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.ui-select-menu__count { min-width:21px; height:20px; display:grid; place-items:center; padding:0 6px; border-radius:7px; color:#64748b; background:#f1f5f9; font-size:10px; font-weight:800; }
.ui-select-menu__chevron { color:#94a3b8; transition:color .16s ease-out,transform .2s cubic-bezier(.16,1,.3,1); }
.ui-select-menu.is-open .ui-select-menu__chevron { color:var(--lz-brand-strong,#4f46e5); transform:rotate(180deg); }
.ui-select-menu__options {
  position:absolute;
  z-index:120;
  top:calc(100% + 7px);
  left:0;
  min-width:max(100%,220px);
  max-width:min(300px,calc(100vw - 32px));
  display:grid;
  gap:2px;
  padding:5px;
  overflow:hidden;
  border:1px solid rgba(203,213,225,.9);
  border-radius:12px;
  background:#fff;
  box-shadow:0 16px 36px rgba(51,65,85,.17),0 4px 12px rgba(79,70,229,.08);
  transform-origin:top left;
}
.ui-select-menu__options button {
  width:100%;
  min-height:38px;
  display:grid;
  grid-template-columns:18px minmax(0,1fr) auto;
  align-items:center;
  gap:7px;
  padding:6px 8px;
  border:0;
  border-radius:8px;
  color:#475569;
  background:transparent;
  font:inherit;
  text-align:left;
  cursor:pointer;
  transition:color .14s ease-out,background .14s ease-out,transform .12s ease-out;
}
.ui-select-menu__options button:hover,.ui-select-menu__options button:focus-visible { color:var(--lz-brand-strong,#4f46e5); background:#f5f7ff; outline:0; }
.ui-select-menu__options button:active { transform:scale(.987); }
.ui-select-menu__options button[aria-selected='true'] { color:var(--lz-brand-strong,#4f46e5); background:var(--lz-brand-soft,#eef2ff); }
.ui-select-menu__options button:disabled { opacity:.42; cursor:not-allowed; }
.ui-select-menu__check { opacity:0; transform:scale(.65); transition:opacity .14s ease-out,transform .18s cubic-bezier(.16,1,.3,1); }
.ui-select-menu__check.visible { opacity:1; transform:scale(1); }
.ui-select-menu__option-copy { min-width:0; display:grid; gap:2px; }
.ui-select-menu__option-copy strong { overflow:hidden; font-size:12px; font-weight:730; text-overflow:ellipsis; white-space:nowrap; }
.ui-select-menu__option-copy small { color:#64748b; font-size:10px; font-weight:500; line-height:1.35; white-space:normal; }
.ui-select-menu__option-count { min-width:24px; color:#64748b; font-size:10px; font-weight:780; text-align:right; }
.ui-select-options-enter-active,.ui-select-options-leave-active { transition:opacity .16s ease-out,transform .2s cubic-bezier(.16,1,.3,1),filter .16s ease-out; }
.ui-select-options-enter-from,.ui-select-options-leave-to { opacity:0; filter:blur(2px); transform:translateY(-5px) scale(.98); }
.ui-select-value-enter-active { transition:opacity .13s ease-out,transform .16s cubic-bezier(.16,1,.3,1); }
.ui-select-value-enter-from { opacity:0; transform:translateY(3px); }
.ui-select-value-leave-active { display:none; }
@media (prefers-reduced-motion:reduce) {
  .ui-select-menu__trigger,.ui-select-menu__chevron,.ui-select-menu__options button,.ui-select-menu__check,.ui-select-options-enter-active,.ui-select-options-leave-active,.ui-select-value-enter-active { transition:none; }
  .ui-select-options-enter-from,.ui-select-options-leave-to { filter:none; transform:none; }
}
</style>
