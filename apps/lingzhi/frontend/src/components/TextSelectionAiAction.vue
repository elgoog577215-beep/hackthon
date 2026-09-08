<template>
  <Teleport to="body">
    <nav
      v-if="hoverTarget && !opened && !disabled && !busy"
      ref="actionMenu"
      class="block-ai-menu"
      :style="triggerStyle"
      role="menu"
      :aria-label="t('courseWorkspace.inlineAi.menu')"
      @pointerdown.prevent
      @keydown="menuKeydown"
    >
      <button
        v-for="action in actions"
        :key="action.key"
        type="button"
        role="menuitem"
        :data-action="action.key"
        @click="chooseAction(action.key)"
      >
        <component :is="action.icon" :size="15" /><span>{{
          action.label
        }}</span>
      </button>
    </nav>
  </Teleport>
  <Teleport v-if="opened && inlineHost" :to="inlineHost">
    <section
      ref="panel"
      class="text-selection-ai__composer"
      :class="{ 'is-comparison-stacked': comparisonLayout === 'stacked' }"
      :aria-label="composerTitle"
      :aria-busy="busy"
      @keydown.esc.stop.prevent="collapseOrClose"
    >
      <header>
        <strong><Sparkles :size="16" />{{ t('courseWorkspace.inlineAi.aiPrefix') }} · {{ actionLabel }}</strong>
        <span>{{ contextLabel }}</span>
        <div
          v-if="changes.length && !collapsed"
          class="inline-edit-comparison-tools"
        >
          <div
            class="inline-edit-layout-switch"
            role="group"
            :aria-label="tr('compareLayout')"
            @keydown="comparisonLayoutKeydown"
          >
            <button
              ref="sideBySideButton"
              type="button"
              :aria-pressed="comparisonLayout === 'side-by-side'"
              :disabled="!sideBySideAvailable"
              :title="!sideBySideAvailable ? tr('sideBySideUnavailable') : undefined"
              @click="setComparisonLayout('side-by-side')"
            >
              {{ tr('compareSideBySide') }}
            </button>
            <button
              ref="stackedButton"
              type="button"
              :aria-pressed="comparisonLayout === 'stacked'"
              @click="setComparisonLayout('stacked')"
            >
              {{ tr('compareStacked') }}
            </button>
          </div>
          <button
            ref="focusCompareTrigger"
            class="inline-edit-focus-trigger"
            type="button"
            @click="openFocusCompare"
          >
            <Maximize2 :size="14" />{{ tr('focusCompare') }}
          </button>
        </div>
        <button
          type="button"
          :aria-label="collapsed ? tr('expand') : tr('collapse')"
          @click="collapsed = !collapsed"
        >
          <ChevronDown v-if="collapsed" :size="16" /><ChevronUp
            v-else
            :size="16"
          />
        </button>
        <button
          v-if="!busy && !candidatePending"
          type="button"
          :aria-label="cancelLabel"
          @click="closeComposer"
        >
          <X :size="16" />
        </button>
      </header>
      <template v-if="!collapsed">
        <p v-if="stale" class="inline-edit-error" role="alert">
          {{ tr('sourceChanged') }}
        </p>
        <div v-if="changes.length" class="inline-edit-diff">
          <article v-for="(change, index) in changes" :key="index">
            <strong v-if="change.label">{{ change.label }}</strong>
            <div>
              <section>
                <small>{{ tr('before') }}</small>
                <MarkdownRenderer
                  :content="change.before || tr('empty')"
                  :enable-code-run="false"
                />
              </section>
              <section>
                <small>{{ tr('after') }}</small>
                <MarkdownRenderer
                  :content="change.after || tr('empty')"
                  :enable-code-run="false"
                />
              </section>
            </div>
          </article>
        </div>
        <blockquote v-else-if="sourceText">
          <MarkdownRenderer :content="sourceText" :enable-code-run="false" />
        </blockquote>
        <p
          v-if="busy"
          class="text-selection-ai__status"
          role="status"
          aria-live="polite"
        >
          <LoaderCircle :size="15" class="spin" />{{
            progressLabel || workingLabel
          }}
        </p>
        <p
          v-if="errorMessage || localError"
          class="inline-edit-error"
          role="alert"
        >
          {{ errorMessage || localError }}
        </p>
        <div v-if="candidatePending" class="inline-edit-decisions">
          <span>{{ candidateHint }}</span>
          <button type="button" :disabled="busy" @click="resolve(false)">
            {{ discardLabel }}
          </button>
          <button
            class="primary"
            type="button"
            :disabled="busy || stale || !canApply"
            @click="resolve(true)"
          >
            <Check :size="15" />{{ applyLabel }}
          </button>
        </div>
        <footer
          v-if="candidatePending && !composerVisible"
          class="inline-edit-followups"
        >
          <button type="button" :disabled="busy || stale" @click="openFollowUp">
            <MessageCircleMore :size="15" />{{ tr('iterate') }}
          </button>
          <button
            type="button"
            :disabled="busy || stale || !history.length"
            @click="redo"
          >
            <RefreshCw :size="15" />{{ t('courseWorkspace.inlineAi.redo') }}
          </button>
        </footer>
        <form v-if="composerVisible" @submit.prevent="submit">
          <label class="sr-only" :for="inputId">{{ placeholder }}</label>
          <textarea
            :id="inputId"
            ref="input"
            v-model="instruction"
            rows="2"
            maxlength="2000"
            :placeholder="
              candidatePending ? tr('iteratePlaceholder') : placeholder
            "
            :disabled="busy || stale"
            @keydown="inputKeydown"
          />
          <footer>
            <span>{{
              candidatePending ? tr('iterateHint') : boundaryLabel
            }}</span
            ><button
              type="button"
              :disabled="busy"
              @click="
                candidatePending ? (composerVisible = false) : closeComposer()
              "
            >
              {{ cancelLabel }}</button
            ><button
              class="primary"
              type="submit"
              :disabled="busy || stale || !instruction.trim()"
            >
              <RefreshCw v-if="errorMessage" :size="15" /><ArrowUp
                v-else
                :size="15"
              />{{
                candidatePending
                  ? tr('iterate')
                  : errorMessage
                    ? tr('retry')
                    : submitLabel
              }}
            </button>
          </footer>
        </form>
      </template>
      <p v-else class="inline-edit-collapsed" role="status">
        {{
          busy
            ? progressLabel || workingLabel
            : candidatePending
              ? candidateTitle
              : tr('draftKept')
        }}
      </p>
      <p class="sr-only" role="status" aria-live="polite">
        {{ comparisonAnnouncement }}
      </p>
    </section>
  </Teleport>
  <Teleport v-if="opened && changes.length" to="body">
    <dialog
      ref="focusDialog"
      class="inline-edit-focus-dialog"
      :class="{ 'is-comparison-stacked': focusComparisonLayout === 'stacked' }"
      :aria-labelledby="focusDialogTitleId"
      @close="restoreFocusCompareTrigger"
    >
      <header>
        <div>
          <strong :id="focusDialogTitleId">{{ candidateTitle }}</strong>
          <span>{{ contextLabel }}</span>
        </div>
        <button
          type="button"
          :aria-label="tr('closeFocusCompare')"
          @click="closeFocusCompare"
        >
          <X :size="18" />
        </button>
      </header>
      <div class="inline-edit-focus-content">
        <article v-for="(change, index) in changes" :key="index">
          <strong v-if="change.label">{{ change.label }}</strong>
          <div>
            <section>
              <small>{{ tr('before') }}</small>
              <MarkdownRenderer
                :content="change.before || tr('empty')"
                :enable-code-run="false"
              />
            </section>
            <section>
              <small>{{ tr('after') }}</small>
              <MarkdownRenderer
                :content="change.after || tr('empty')"
                :enable-code-run="false"
              />
            </section>
          </div>
        </article>
      </div>
    </dialog>
  </Teleport>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlignLeft,
  CircleHelp,
  Lightbulb,
  MessageCircleMore,
  MessageSquareText,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronUp,
  LoaderCircle,
  Maximize2,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { createUuid } from '../utils/client-id'
export type TeacherInlineAiSource = 'selection' | 'block' | 'document'
export type TeacherInlineAiTarget = {
  sectionNodeId?: string
  field?: string
  itemId?: string
  label?: string
}
export type TeacherInlineAiRequest = {
  text: string
  instruction: string
  source: TeacherInlineAiSource
  target?: TeacherInlineAiTarget
}
export type TeacherInlineAiChange = {
  label?: string
  before: string
  after: string
}
const props = withDefaults(
  defineProps<{
    container: HTMLElement | null
    disabled?: boolean
    busy?: boolean
    label?: string
    composerTitle?: string
    placeholder?: string
    submitLabel?: string
    cancelLabel?: string
    workingLabel?: string
    selectionLabel?: string
    blockLabel?: string
    documentLabel?: string
    boundaryLabel?: string
    targetSelector?: string
    groupSelector?: string
    selectTargetLabel?: string
    candidatePending?: boolean
    candidateTitle?: string
    candidateHint?: string
    applyLabel?: string
    discardLabel?: string
    progressLabel?: string
    errorMessage?: string
    changes?: TeacherInlineAiChange[]
    canApply?: boolean
    sourceRevision?: string
    getSourceText?: (target: TeacherInlineAiTarget) => string
  }>(),
  {
    disabled: false,
    busy: false,
    label: '',
    composerTitle: '',
    placeholder: '',
    submitLabel: '',
    cancelLabel: '',
    workingLabel: '',
    selectionLabel: '',
    blockLabel: '',
    documentLabel: '',
    boundaryLabel: '',
    targetSelector:
      'p, li, blockquote, h2, h3, h4, h5, td, th, [data-node-body]',
    groupSelector: '',
    selectTargetLabel: '',
    candidatePending: false,
    candidateTitle: '',
    candidateHint: '',
    applyLabel: '',
    discardLabel: '',
    progressLabel: '',
    errorMessage: '',
    changes: () => [],
    canApply: true,
    sourceRevision: '',
  },
)
const emit = defineEmits<{
  invoke: [payload: TeacherInlineAiRequest]
  resolve: [accept: boolean]
  opened: []
  closed: []
}>()
const tr = (key: string) => t(`teacherInlineEdit.${key}`)
const composerTitle = computed(() => props.composerTitle || tr('title'))
const placeholder = computed(() => props.placeholder || tr('placeholder'))
const submitLabel = computed(() => props.submitLabel || tr('generate'))
const cancelLabel = computed(() => props.cancelLabel || tr('cancel'))
const workingLabel = computed(() => props.workingLabel || tr('working'))
const boundaryLabel = computed(() => props.boundaryLabel || tr('boundary'))
const candidateTitle = computed(() => props.candidateTitle || tr('ready'))
const candidateHint = computed(() => props.candidateHint || tr('reviewHint'))
const applyLabel = computed(() => props.applyLabel || tr('apply'))
const discardLabel = computed(() => props.discardLabel || tr('discard'))
type InlineAction = 'explain' | 'example' | 'simplify' | 'ask'
type ComparisonLayout = 'side-by-side' | 'stacked'
const COMPARISON_STACK_BREAKPOINT = 900
const activeAction = ref<InlineAction>('ask')
const composerVisible = ref(true)
const actionMenu = ref<HTMLElement | null>(null)
const actions = computed(() => [
  {
    key: 'explain' as const,
    icon: MessageSquareText,
    label: t('courseWorkspace.inlineAi.explain'),
  },
  {
    key: 'example' as const,
    icon: Lightbulb,
    label: t('courseWorkspace.inlineAi.example'),
  },
  {
    key: 'simplify' as const,
    icon: AlignLeft,
    label: t('courseWorkspace.inlineAi.simplify'),
  },
  {
    key: 'ask' as const,
    icon: CircleHelp,
    label: tr('edit'),
  },
])
const actionLabel = computed(
  () =>
    actions.value.find((action) => action.key === activeAction.value)?.label,
)
async function chooseAction(action: InlineAction) {
  activeAction.value = action
  openTarget()
  if (!opened.value) return
  composerVisible.value = action === 'ask'
  if (action === 'ask') return
  instruction.value = t(`courseWorkspace.inlineAi.${action}Prompt`)
  await nextTick()
  submit()
}
function openFollowUp() {
  composerVisible.value = true
  nextTick(() => input.value?.focus({ preventScroll: true }))
}
function redo() {
  if (props.busy || stale.value || !history.length) return
  const previous = history.pop()!
  instruction.value = previous
  composerVisible.value = false
  submit()
}
function menuKeydown(event: KeyboardEvent) {
  const buttons = Array.from(
    actionMenu.value?.querySelectorAll<HTMLButtonElement>('button') || [],
  )
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (event.key === 'Escape') {
    event.preventDefault()
    hoverTarget.value = null
    selectionText = ''
    return
  }
  let next = -1
  if (event.key === 'ArrowDown') next = (index + 1) % buttons.length
  if (event.key === 'ArrowUp')
    next = (index - 1 + buttons.length) % buttons.length
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = buttons.length - 1
  if (next >= 0) {
    event.preventDefault()
    buttons[next]?.focus({ preventScroll: true })
  }
}
function trackPointer(event: PointerEvent) {
  if (opened.value || !hoverTarget.value || selectionText) return
  const element = event.target instanceof Element ? event.target : null
  if (
    element &&
    (actionMenu.value?.contains(element) || hoverTarget.value.contains(element))
  )
    return
  const targetRect = hoverTarget.value.getBoundingClientRect()
  const menuRect = actionMenu.value?.getBoundingClientRect()
  if (
    menuRect &&
    event.clientX >= Math.min(menuRect.left, targetRect.left) &&
    event.clientX <= Math.max(menuRect.right, targetRect.right) &&
    event.clientY >= Math.min(menuRect.top, targetRect.top) &&
    event.clientY <= Math.max(menuRect.bottom, targetRect.bottom)
  )
    return
  hoverTarget.value = null
}
const inputId = `inline-edit-${createUuid()}`
const focusDialogTitleId = `inline-edit-focus-${createUuid()}`
const hoverTarget = ref<HTMLElement | null>(null),
  target = ref<HTMLElement | null>(null),
  inlineHost = ref<HTMLElement | null>(null),
  panel = ref<HTMLElement | null>(null),
  input = ref<HTMLTextAreaElement | null>(null),
  sideBySideButton = ref<HTMLButtonElement | null>(null),
  stackedButton = ref<HTMLButtonElement | null>(null),
  focusCompareTrigger = ref<HTMLButtonElement | null>(null),
  focusDialog = ref<HTMLDialogElement | null>(null)
const opened = ref(false),
  collapsed = ref(false),
  stale = ref(false),
  instruction = ref(''),
  sourceText = ref(''),
  localError = ref(''),
  comparisonWidth = ref(0),
  comparisonPreference = ref<ComparisonLayout | null>(null),
  comparisonAnnouncement = ref('')
const source = ref<TeacherInlineAiSource>('block'),
  triggerPosition = ref({ left: 0, top: 0 }),
  identity = ref<TeacherInlineAiTarget | undefined>()
let selectionText = '',
  sourceVersion = '',
  resolving = false,
  history: string[] = [],
  pendingInstruction = ''
let panelResizeObserver: ResizeObserver | null = null
const sideBySideAvailable = computed(
  () => comparisonWidth.value >= COMPARISON_STACK_BREAKPOINT,
)
const comparisonLayout = computed<ComparisonLayout>(() =>
  sideBySideAvailable.value
    ? comparisonPreference.value || 'side-by-side'
    : 'stacked',
)
const focusComparisonLayout = computed<ComparisonLayout>(
  () => comparisonPreference.value || 'side-by-side',
)
const triggerStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${triggerPosition.value.left}px`,
  top: `${triggerPosition.value.top}px`,
}))
const contextLabel = computed(() =>
  [
    identity.value?.label,
    source.value === 'selection'
      ? props.selectionLabel || tr('selection')
      : source.value === 'document'
        ? props.documentLabel || tr('document')
        : props.blockLabel || tr('paragraph'),
  ]
    .filter(Boolean)
    .join(' · '),
)
function updateComparisonWidth(width?: number) {
  const measured = width ?? panel.value?.getBoundingClientRect().width ?? 0
  comparisonWidth.value = Math.max(0, measured)
}
function observeComparisonPanel(element: HTMLElement | null) {
  panelResizeObserver?.disconnect()
  panelResizeObserver = null
  if (!element) return
  updateComparisonWidth(element.getBoundingClientRect().width)
  if (typeof ResizeObserver === 'undefined') return
  panelResizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (entry) updateComparisonWidth(entry.contentRect.width)
  })
  panelResizeObserver.observe(element)
}
function setComparisonLayout(layout: ComparisonLayout) {
  if (layout === 'side-by-side' && !sideBySideAvailable.value) return
  comparisonPreference.value = layout
  comparisonAnnouncement.value =
    layout === 'side-by-side'
      ? tr('sideBySideSelected')
      : tr('stackedSelected')
}
function comparisonLayoutKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'ArrowLeft' && sideBySideAvailable.value) {
    setComparisonLayout('side-by-side')
    nextTick(() => sideBySideButton.value?.focus({ preventScroll: true }))
    return
  }
  setComparisonLayout('stacked')
  nextTick(() => stackedButton.value?.focus({ preventScroll: true }))
}
function openFocusCompare() {
  const dialog = focusDialog.value
  if (!dialog) return
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else dialog.setAttribute('open', '')
}
function restoreFocusCompareTrigger() {
  nextTick(() => focusCompareTrigger.value?.focus({ preventScroll: true }))
}
function closeFocusCompare() {
  const dialog = focusDialog.value
  if (!dialog) return
  if (typeof dialog.close === 'function') dialog.close()
  else {
    dialog.removeAttribute('open')
    restoreFocusCompareTrigger()
  }
}
function contentText(element: HTMLElement) {
  if (element.dataset.aiSource) return element.dataset.aiSource
  const clone = element.cloneNode(true) as HTMLElement
  clone
    .querySelectorAll('[data-ai-inline-host],button,select,.ai-change-marker')
    .forEach((item) => item.remove())
  return (clone.textContent || '').trim()
}
function metadata(element: HTMLElement): TeacherInlineAiTarget | undefined {
  const field = element.closest<HTMLElement>('[data-ai-field]')
  const node = element.closest<HTMLElement>(
    '[data-ai-section-id], [data-node-id], [data-node-body]',
  )
  const value = {
    sectionNodeId:
      node?.dataset.aiSectionId ||
      node?.dataset.nodeId ||
      node?.dataset.nodeBody ||
      '',
    field: field?.dataset.aiField || '',
    itemId: field?.dataset.aiItemId || '',
    label: field?.dataset.aiLabel || '',
  }
  return Object.values(value).some(Boolean) ? value : undefined
}
function eventTarget(event: Event) {
  const el = event.target instanceof Element ? event.target : null
  if (!el || el.closest('button,textarea,input,select,[data-ai-inline-host]'))
    return null
  const found = el.closest<HTMLElement>(props.targetSelector)
  return found && props.container?.contains(found) ? found : null
}
function positionTrigger() {
  if (!hoverTarget.value?.isConnected) {
    hoverTarget.value = null
    return
  }
  const r = hoverTarget.value.getBoundingClientRect()
  if (r.bottom < 0 || r.top > window.innerHeight) {
    hoverTarget.value = null
    return
  }
  triggerPosition.value = {
    left:
      r.left >= 128
        ? r.left - 120
        : Math.max(8, Math.min(r.right + 8, window.innerWidth - 120)),
    top: Math.max(8, Math.min(r.top, window.innerHeight - 152)),
  }
}
function hover(event: Event) {
  if (opened.value || props.disabled || props.busy || selectionText) return
  const el = eventTarget(event)
  if (!el || contentText(el).length < 2) return
  hoverTarget.value = el
  positionTrigger()
}
function captureSelection() {
  if (opened.value || props.disabled || props.busy) return
  const sel = window.getSelection()
  if (!sel || !sel.rangeCount || sel.isCollapsed) return
  const range = sel.getRangeAt(0)
  const start =
    range.startContainer instanceof Element
      ? range.startContainer
      : range.startContainer.parentElement
  const end =
    range.endContainer instanceof Element
      ? range.endContainer
      : range.endContainer.parentElement
  if (
    !start ||
    !end ||
    !props.container?.contains(start) ||
    !props.container.contains(end) ||
    start.closest('[data-ai-inline-host]')
  )
    return
  const first = start.closest<HTMLElement>(props.targetSelector),
    last = end.closest<HTMLElement>(props.targetSelector)
  if (!first || first !== last) {
    hoverTarget.value = null
    selectionText = ''
    return
  }
  const text = sel.toString().trim()
  if (text.length < 2) return
  const visibleText = (first.textContent || '').replace(/\s+/g, ' ').trim()
  selectionText =
    first.dataset.aiSource && visibleText === text.replace(/\s+/g, ' ').trim()
      ? first.dataset.aiSource
      : text
  hoverTarget.value = first
  positionTrigger()
}
function removeHost() {
  inlineHost.value?.remove()
  inlineHost.value = null
}
function insertHost(el: HTMLElement) {
  removeHost()
  let host: HTMLElement
  if (el.matches('td,th')) {
    const row = el.closest('tr')!
    host = document.createElement('tr')
    const cell = document.createElement('td')
    cell.colSpan = Array.from(row.cells).reduce((sum, c) => sum + c.colSpan, 0)
    host.appendChild(cell)
    row.after(host)
    host.dataset.aiInlineHost = 'true'
    inlineHost.value = cell
  } else {
    host = document.createElement(el.matches('li') ? 'li' : 'div')
    el.after(host)
    inlineHost.value = host
  }
  host.className = 'text-selection-ai-host'
  host.dataset.aiInlineHost = 'true'
  host.contentEditable = 'false'
}
function openTarget() {
  const el = hoverTarget.value
  if (!el || props.disabled || props.busy) return
  target.value = el
  identity.value = metadata(el)
  source.value = selectionText ? 'selection' : 'block'
  sourceText.value =
    selectionText ||
    (identity.value && props.getSourceText
      ? props.getSourceText(identity.value)
      : contentText(el))
  sourceVersion = props.sourceRevision
  history = []
  instruction.value = ''
  composerVisible.value = true
  pendingInstruction = ''
  localError.value = ''
  stale.value = false
  collapsed.value = false
  comparisonPreference.value = null
  comparisonAnnouncement.value = ''
  insertHost(el)
  opened.value = true
  hoverTarget.value = null
  selectionText = ''
  window.getSelection()?.removeAllRanges()
  emit('opened')
  nextTick(() => input.value?.focus({ preventScroll: true }))
}
function openForDocument(_text = '') {
  if (props.disabled || props.busy || !props.container) return
  if (opened.value) {
    collapsed.value = false
    nextTick(() => input.value?.focus({ preventScroll: true }))
    return
  }
  const candidates = Array.from(
    props.container.querySelectorAll<HTMLElement>(props.targetSelector),
  )
  const visible = candidates.find((el) => {
    const r = el.getBoundingClientRect()
    return (
      r.top >= 64 &&
      r.bottom <= window.innerHeight &&
      contentText(el).length > 1
    )
  })
  hoverTarget.value =
    visible ||
    candidates[0] ||
    props.container.querySelector<HTMLElement>('[data-ai-document-anchor]')
  selectionText = ''
  activeAction.value = 'ask'
  openTarget()
  if (opened.value) source.value = 'block'
}
function closeComposer() {
  if (props.busy || props.candidatePending) {
    collapsed.value = true
    return
  }
  opened.value = false
  target.value = null
  instruction.value = ''
  history = []
  selectionText = ''
  hoverTarget.value = null
  removeHost()
  emit('closed')
}
function collapseOrClose() {
  if (instruction.value.trim() || props.busy || props.candidatePending)
    collapsed.value = true
  else closeComposer()
}
function inputKeydown(event: KeyboardEvent) {
  if (
    event.key === 'Enter' &&
    !event.shiftKey &&
    !event.isComposing &&
    event.keyCode !== 229
  ) {
    event.preventDefault()
    submit()
  }
}
function submit() {
  if (!instruction.value.trim() || props.busy || props.disabled || stale.value)
    return
  if (props.sourceRevision !== sourceVersion || !target.value?.isConnected) {
    stale.value = true
    return
  }
  pendingInstruction = instruction.value.trim()
  localError.value = ''
  emit('invoke', {
    text: sourceText.value,
    instruction: [...history, pendingInstruction].join('\n'),
    source: source.value,
    target: identity.value,
  })
}
function resolve(accept: boolean) {
  if (props.busy || (accept && (stale.value || !props.canApply))) return
  resolving = true
  emit('resolve', accept)
}
function outside(event: PointerEvent) {
  const el = event.target instanceof Element ? event.target : null
  if (el?.closest('.block-ai-menu,[data-ai-inline-host]')) return
  if (!opened.value) {
    selectionText = ''
    hoverTarget.value = null
  }
}
watch(
  panel,
  (element) => observeComparisonPanel(element),
  { flush: 'post' },
)
watch(
  () => props.busy,
  (busy, previous) => {
    if (previous && !busy) {
      if (resolving) {
        resolving = false
        if (!props.candidatePending) closeComposer()
      } else if (
        props.candidatePending &&
        !props.errorMessage &&
        pendingInstruction
      ) {
        history.push(pendingInstruction)
        pendingInstruction = ''
        instruction.value = ''
        composerVisible.value = false
      } else if (props.errorMessage) {
        composerVisible.value = true
      }
    }
  },
)
watch(
  () => props.candidatePending,
  (pending, previous) => {
    if (previous && !pending && resolving && !props.busy) {
      resolving = false
      closeComposer()
    }
  },
)
watch(
  () => props.sourceRevision,
  (version) => {
    if (opened.value && version !== sourceVersion && !resolving)
      stale.value = true
  },
)
watch(
  () => props.container,
  (next, previous) => {
    previous?.removeEventListener('pointerover', hover)
    next?.addEventListener('pointerover', hover)
    if (previous && opened.value) {
      opened.value = false
      removeHost()
      emit('closed')
    }
  },
  { flush: 'post' },
)
onMounted(() => {
  props.container?.addEventListener('pointerover', hover)
  document.addEventListener('mouseup', captureSelection)
  document.addEventListener('keyup', captureSelection)
  document.addEventListener('pointerdown', outside)
  document.addEventListener('pointermove', trackPointer)
  document.addEventListener('scroll', positionTrigger, true)
  window.addEventListener('resize', positionTrigger)
})
onBeforeUnmount(() => {
  panelResizeObserver?.disconnect()
  panelResizeObserver = null
  props.container?.removeEventListener('pointerover', hover)
  document.removeEventListener('mouseup', captureSelection)
  document.removeEventListener('keyup', captureSelection)
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('pointermove', trackPointer)
  document.removeEventListener('scroll', positionTrigger, true)
  window.removeEventListener('resize', positionTrigger)
  removeHost()
})
defineExpose({ openForDocument, closeComposer })
</script>
<style scoped>
.block-ai-menu {
  z-index: 610;
  width: 112px;
  padding: 3px;
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 7px 18px rgba(15, 23, 42, 0.07),
    0 1px 2px rgba(15, 23, 42, 0.035);
}
.block-ai-menu button {
  width: 100%;
  min-height: 34px;
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: #64748b;
  background: transparent;
  text-align: left;
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}
.block-ai-menu button:hover,
.block-ai-menu button:focus-visible {
  color: var(--lz-brand-strong, #5148b6);
  background: rgba(238, 242, 255, 0.9);
  outline: 2px solid transparent;
}
.block-ai-menu button:focus-visible {
  outline-color: var(--lz-brand-strong, #5148b6);
  outline-offset: -2px;
}
.inline-edit-followups {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--lz-border, #d5d9e2);
}
:global(.text-selection-ai-host) {
  display: block;
  grid-column: 1/-1;
  min-width: 0;
  margin: 12px 0;
  list-style: none;
}
:global(tr.text-selection-ai-host) {
  display: table-row;
}
.text-selection-ai__composer {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  container-name: ai-suggestion;
  container-type: inline-size;
  padding: 16px;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 8px;
  background: var(--lz-surface, #fff);
  color: var(--lz-text-primary, #273247);
  font-size: 15px;
  line-height: 1.6;
  text-align: left;
  white-space: normal;
}
.text-selection-ai__composer > header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}
.text-selection-ai__composer > header strong {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 15px;
}
.text-selection-ai__composer > header > span {
  flex: 1;
  min-width: 0;
  color: var(--lz-text-secondary, #536078);
  font-size: 13px;
}
.text-selection-ai__composer > header > button {
  width: 32px;
  min-height: 32px;
  padding: 0;
  display: grid;
  place-items: center;
}
.inline-edit-comparison-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}
.inline-edit-layout-switch {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 8px;
  background: #f3f4f8;
}
.text-selection-ai__composer .inline-edit-layout-switch button {
  min-height: 30px;
  padding: 3px 10px;
  border-color: transparent;
  background: transparent;
  color: var(--lz-text-secondary, #536078);
}
.text-selection-ai__composer .inline-edit-layout-switch button[aria-pressed='true'] {
  border-color: #d9d8ee;
  background: var(--lz-surface, #fff);
  color: var(--lz-brand-strong, #5148b6);
  box-shadow: 0 1px 3px rgba(30, 41, 59, 0.08);
}
.text-selection-ai__composer .inline-edit-focus-trigger {
  min-height: 36px;
  white-space: nowrap;
}
.text-selection-ai__composer button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 6px;
  background: var(--lz-surface, #fff);
  color: var(--lz-text-primary, #273247);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}
.text-selection-ai__composer button.primary {
  border-color: var(--lz-brand-strong, #5148b6);
  background: var(--lz-brand-strong, #5148b6);
  color: #fff;
}
.text-selection-ai__composer button:hover:not(:disabled) {
  filter: brightness(0.95);
}
.text-selection-ai__composer button:disabled,
.text-selection-ai__composer textarea:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.text-selection-ai__composer :is(button, textarea):focus-visible {
  outline: 2px solid var(--lz-brand-strong, #5148b6);
  outline-offset: 2px;
}
.text-selection-ai__composer blockquote {
  max-height: 144px;
  overflow: auto;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 0;
  background: var(--lz-bg-page, #f5f6f9);
  color: var(--lz-text-secondary, #536078);
  font-size: 14px;
  white-space: pre-wrap;
}
.text-selection-ai__composer form {
  display: grid;
  gap: 8px;
}
.text-selection-ai__composer textarea {
  width: 100%;
  min-height: 76px;
  max-height: 220px;
  padding: 10px 12px;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 6px;
  background: var(--lz-surface, #fff);
  color: inherit;
  font: inherit;
  resize: vertical;
}
.text-selection-ai__composer textarea::placeholder {
  color: #626e80;
}
.text-selection-ai__composer footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.text-selection-ai__composer footer > span {
  flex: 1;
  color: var(--lz-text-secondary, #536078);
  font-size: 13px;
}
.inline-edit-diff {
  min-width: 0;
  max-width: 100%;
  max-height: 380px;
  overflow: auto;
  margin-bottom: 12px;
}
.inline-edit-diff article + article {
  margin-top: 16px;
}
.inline-edit-diff article > strong {
  font-size: 14px;
}
.inline-edit-diff article > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
.inline-edit-diff section {
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  padding: 10px;
  background: var(--lz-bg-page, #f5f6f9);
}
.inline-edit-diff section + section {
  background: #f0f7f2;
}
.inline-edit-diff small {
  color: #536078;
  font-size: 13px;
}
.inline-edit-diff :deep(.markdown-renderer),
.inline-edit-focus-content :deep(.markdown-renderer) {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.inline-edit-diff :deep(pre),
.inline-edit-focus-content :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  margin: 6px 0 0;
  font: inherit;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.text-selection-ai__composer.is-comparison-stacked .inline-edit-diff {
  max-height: none;
  overflow: visible;
}
.text-selection-ai__composer.is-comparison-stacked .inline-edit-diff article > div {
  grid-template-columns: minmax(0, 1fr);
}
.inline-edit-focus-dialog {
  width: min(1120px, calc(100vw - 96px));
  max-width: none;
  max-height: min(88vh, 900px);
  box-sizing: border-box;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 12px;
  background: var(--lz-surface, #fff);
  color: var(--lz-text-primary, #273247);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.2);
}
.inline-edit-focus-dialog::backdrop {
  background: rgba(20, 27, 42, 0.32);
}
.inline-edit-focus-dialog > header {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--lz-border, #d5d9e2);
}
.inline-edit-focus-dialog > header > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.inline-edit-focus-dialog > header strong {
  color: var(--lz-text-primary, #273247);
  font-size: 16px;
}
.inline-edit-focus-dialog > header span {
  overflow: hidden;
  color: var(--lz-text-secondary, #536078);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inline-edit-focus-dialog button {
  min-width: 36px;
  min-height: 36px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--lz-border, #d5d9e2);
  border-radius: 7px;
  background: var(--lz-surface, #fff);
  color: var(--lz-text-primary, #273247);
  cursor: pointer;
}
.inline-edit-focus-dialog button:focus-visible {
  outline: 2px solid var(--lz-brand-strong, #5148b6);
  outline-offset: 2px;
}
.inline-edit-focus-content {
  max-height: calc(min(88vh, 900px) - 65px);
  overflow: auto;
  padding: 18px;
}
.inline-edit-focus-content article + article {
  margin-top: 18px;
}
.inline-edit-focus-content article > strong {
  display: block;
  margin-bottom: 8px;
  font-size: 15px;
}
.inline-edit-focus-content article > div {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.inline-edit-focus-content section {
  min-width: 0;
  box-sizing: border-box;
  padding: 16px;
  background: var(--lz-bg-page, #f5f6f9);
}
.inline-edit-focus-content section + section {
  background: #f0f7f2;
}
.inline-edit-focus-content small {
  color: #536078;
  font-size: 13px;
}
.inline-edit-focus-dialog.is-comparison-stacked .inline-edit-focus-content article > div {
  grid-template-columns: minmax(0, 1fr);
}
@container ai-suggestion (max-width: 899px) {
  .inline-edit-diff {
    max-height: none;
    overflow: visible;
  }
  .inline-edit-diff article > div {
    grid-template-columns: minmax(0, 1fr);
  }
}
@container ai-suggestion (max-width: 639px) {
  .text-selection-ai__composer > header > span {
    flex-basis: 40%;
  }
  .inline-edit-comparison-tools {
    order: 4;
    width: 100%;
  }
}
.inline-edit-decisions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}
.inline-edit-decisions > span {
  flex: 1;
  color: var(--lz-text-secondary, #536078);
  font-size: 13px;
}
.text-selection-ai__status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
  color: var(--lz-brand-strong, #5148b6);
}
.inline-edit-error {
  margin: 10px 0;
  color: #a12630;
  white-space: pre-wrap;
}
.inline-edit-collapsed {
  margin: 0;
  color: var(--lz-text-secondary, #536078);
  font-size: 14px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
.spin {
  animation: inline-edit-spin 1s linear infinite;
}
@keyframes inline-edit-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}
</style>
