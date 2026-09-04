<template>
  <div
    v-if="anchor.visible && !composerOpen"
    ref="root"
    class="text-selection-ai"
    :class="{ 'is-busy': busy }"
    :style="{ left: `${anchor.x}px`, top: `${anchor.y}px` }"
  >
    <button
      ref="actionButton"
      type="button"
      class="text-selection-ai__trigger"
      :aria-label="label"
      :title="label"
      @pointerdown.prevent
      @click="openComposer"
    >
      <Sparkles :size="14" />
      <span>{{ label }}</span>
    </button>
  </div>

  <Teleport v-if="composerOpen && inlineHost" :to="inlineHost">
    <form
      ref="composerRoot"
      class="text-selection-ai__composer"
      :aria-busy="busy"
      @submit.prevent="submit"
      @keydown.esc.stop.prevent="closeComposer"
    >
      <header>
        <span><Sparkles :size="15" /></span>
        <div>
          <strong>{{
            submitted && candidatePending && !busy
              ? candidateTitle
              : composerTitle
          }}</strong>
          <small>{{ contextLabel }}</small>
        </div>
        <button
          type="button"
          class="text-selection-ai__close"
          :disabled="busy || candidatePending"
          :aria-label="cancelLabel"
          :title="cancelLabel"
          @click="closeComposer()"
        >
          <X :size="15" />
        </button>
      </header>

      <blockquote v-if="anchor.text">{{ anchor.text }}</blockquote>

      <template v-if="submitted && busy">
        <p class="text-selection-ai__status" role="status" aria-live="polite">
          <LoaderCircle :size="14" />
          <span>{{ progressLabel || workingLabel }}</span>
        </p>
      </template>

      <template v-else-if="submitted && candidatePending">
        <p class="text-selection-ai__candidate" role="status">
          {{ candidateHint }}
        </p>
        <footer>
          <button type="button" @click="emit('resolve', false)">
            {{ discardLabel }}
          </button>
          <button class="primary" type="button" @click="emit('resolve', true)">
            <Check :size="14" />{{ applyLabel }}
          </button>
        </footer>
      </template>

      <template v-else>
        <textarea
          ref="composer"
          v-model="instruction"
          rows="3"
          maxlength="3000"
          :placeholder="placeholder"
          :aria-label="placeholder"
          @keydown.enter.exact.prevent="submit"
        />

        <p v-if="errorMessage" class="text-selection-ai__error" role="alert">
          {{ errorMessage }}
        </p>
        <p v-else class="text-selection-ai__hint">{{ boundaryLabel }}</p>

        <footer>
          <button type="button" @click="closeComposer()">
            {{ cancelLabel }}
          </button>
          <button class="primary" type="submit" :disabled="!instruction.trim()">
            <Sparkles :size="14" />{{ submitLabel }}
          </button>
        </footer>
      </template>
    </form>
  </Teleport>
</template>

<script setup lang="ts">
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { Check, LoaderCircle, Sparkles, X } from "lucide-vue-next";

export type TeacherInlineAiSource = "selection" | "block" | "document";
export type TeacherInlineAiRequest = {
  text: string;
  instruction: string;
  source: TeacherInlineAiSource;
  target?: TeacherInlineAiTarget;
};
export type TeacherInlineAiTarget = {
  sectionNodeId?: string;
  field?: string;
  itemId?: string;
  label?: string;
};

const props = withDefaults(
  defineProps<{
    container: HTMLElement | null;
    disabled?: boolean;
    busy?: boolean;
    label?: string;
    composerTitle?: string;
    placeholder?: string;
    submitLabel?: string;
    cancelLabel?: string;
    workingLabel?: string;
    selectionLabel?: string;
    blockLabel?: string;
    documentLabel?: string;
    boundaryLabel?: string;
    targetSelector?: string;
    candidatePending?: boolean;
    candidateTitle?: string;
    candidateHint?: string;
    applyLabel?: string;
    discardLabel?: string;
    progressLabel?: string;
    errorMessage?: string;
  }>(),
  {
    disabled: false,
    busy: false,
    label: "AI 修改",
    composerTitle: "告诉 AI 怎么改",
    placeholder: "直接描述你希望这段内容怎样修改…",
    submitLabel: "生成修改",
    cancelLabel: "取消",
    workingLabel: "正在生成候选…",
    selectionLabel: "修改选中内容",
    blockLabel: "修改当前段落",
    documentLabel: "修改当前内容",
    boundaryLabel: "AI 只生成候选，采用后才会写入正式内容。",
    targetSelector:
      "p, li, blockquote, h2, h3, h4, h5, td, th, [data-node-body], .document-section, .script-module",
    candidatePending: false,
    candidateTitle: "修改候选已生成",
    candidateHint: "候选已经显示在原文位置，采用后才会写入正式内容。",
    applyLabel: "采用修改",
    discardLabel: "保留原文",
    progressLabel: "",
    errorMessage: "",
  },
);

const emit = defineEmits<{
  invoke: [payload: TeacherInlineAiRequest];
  resolve: [accept: boolean];
}>();

const root = ref<HTMLElement | null>(null);
const composerRoot = ref<HTMLFormElement | null>(null);
const actionButton = ref<HTMLButtonElement | null>(null);
const composer = ref<HTMLTextAreaElement | null>(null);
const inlineHost = ref<HTMLElement | null>(null);
const anchorTarget = ref<HTMLElement | null>(null);
const composerOpen = ref(false);
const instruction = ref("");
const submitted = ref(false);
const anchorRect = ref<Pick<
  DOMRect,
  "left" | "right" | "top" | "height"
> | null>(null);
const anchor = reactive({
  visible: false,
  x: 0,
  y: 0,
  text: "",
  source: "block" as TeacherInlineAiSource,
});
const contextLabel = ref(props.blockLabel);

function compactText(value: unknown) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1200);
}

function selectionElement(node: Node | null) {
  return node instanceof Element ? node : node?.parentElement || null;
}

function positionForRect(
  rect: Pick<DOMRect, "left" | "right" | "top" | "height">,
  source: TeacherInlineAiSource,
) {
  const container = props.container;
  if (!container) return;
  anchorRect.value = rect;
  const containerRect = container.getBoundingClientRect();
  const panelWidth = composerOpen.value ? 360 : 92;
  const desiredX = rect.right - containerRect.left + container.scrollLeft + 12;
  anchor.x = Math.max(
    panelWidth / 2 + 8,
    Math.min(container.clientWidth - panelWidth / 2 - 8, desiredX),
  );
  anchor.y = Math.max(
    24,
    rect.top -
      containerRect.top +
      container.scrollTop +
      Math.min(rect.height / 2, 28),
  );
  anchor.source = source;
}

function targetFromEvent(event: Event) {
  const element = event.target instanceof Element ? event.target : null;
  if (!element || root.value?.contains(element)) return null;
  if (element.closest('button, textarea, input, select, a, [role="button"]'))
    return null;
  const target = element.closest<HTMLElement>(props.targetSelector);
  return target && props.container?.contains(target) ? target : null;
}

function requestTarget(
  target: HTMLElement | null,
): TeacherInlineAiTarget | undefined {
  if (!target) return undefined;
  const semanticTarget =
    target.closest<HTMLElement>("[data-ai-field]") || target;
  const section = semanticTarget.closest<HTMLElement>("[data-ai-section-id]");
  const value = {
    sectionNodeId: String(section?.dataset.aiSectionId || ""),
    field: String(semanticTarget.dataset.aiField || ""),
    itemId: String(semanticTarget.dataset.aiItemId || ""),
    label: String(semanticTarget.dataset.aiLabel || ""),
  };
  return Object.values(value).some(Boolean) ? value : undefined;
}

function removeInlineHost() {
  inlineHost.value?.remove();
  inlineHost.value = null;
}

function insertionTarget(target: HTMLElement) {
  return target.closest<HTMLElement>("[data-ai-inline-anchor]") || target;
}

function createInlineHost(target: HTMLElement) {
  removeInlineHost();
  const insertion = insertionTarget(target);
  const host = document.createElement(insertion.matches("li") ? "li" : "div");
  host.className = "text-selection-ai-host";
  host.dataset.aiInlineHost = "true";
  if (insertion.matches("li") || !insertion.matches("[data-ai-field]")) {
    insertion.insertAdjacentElement("afterend", host);
  } else {
    insertion.appendChild(host);
  }
  inlineHost.value = host;
}

function showBlockTarget(target: HTMLElement) {
  if (props.disabled || composerOpen.value) return;
  const text = compactText(target.textContent);
  if (text.length < 2) return;
  anchor.text = text;
  anchorTarget.value = target;
  anchor.visible = true;
  contextLabel.value = props.blockLabel;
  positionForRect(target.getBoundingClientRect(), "block");
}

function captureSelection() {
  if (props.disabled || !props.container || composerOpen.value) return;
  const selected = window.getSelection();
  const text = compactText(selected?.toString());
  if (!selected || selected.rangeCount === 0 || text.length < 2) return;
  const range = selected.getRangeAt(0);
  const start = selectionElement(range.startContainer);
  const end = selectionElement(range.endContainer);
  if (
    !start ||
    !end ||
    !props.container.contains(start) ||
    !props.container.contains(end)
  )
    return;
  const startTarget = start.closest<HTMLElement>(props.targetSelector);
  const endTarget = end.closest<HTMLElement>(props.targetSelector);
  if (!startTarget || !endTarget || startTarget !== endTarget) return;
  anchor.text = text;
  anchor.visible = true;
  contextLabel.value = props.selectionLabel;
  anchorTarget.value = endTarget;
  positionForRect(
    endTarget.getBoundingClientRect() || range.getBoundingClientRect(),
    "selection",
  );
}

function handlePointerOver(event: PointerEvent) {
  const target = targetFromEvent(event);
  if (target) showBlockTarget(target);
}

function handlePointerLeave(event: PointerEvent) {
  if (composerOpen.value || root.value?.contains(event.relatedTarget as Node))
    return;
  anchor.visible = false;
}

function openComposer() {
  if (props.disabled || !anchorTarget.value) return;
  createInlineHost(anchorTarget.value);
  const target = requestTarget(anchorTarget.value);
  const scopeLabel =
    anchor.source === "selection"
      ? props.selectionLabel
      : anchor.source === "document"
        ? props.documentLabel
        : props.blockLabel;
  contextLabel.value = target?.label
    ? `${target.label} · ${scopeLabel}`
    : scopeLabel;
  composerOpen.value = true;
  anchor.visible = false;
  instruction.value = "";
  submitted.value = false;
  nextTick(() => {
    composer.value?.focus();
    inlineHost.value?.scrollIntoView?.({
      behavior: "smooth",
      block: "nearest",
    });
  });
}

function openForDocument(text = "") {
  if (props.disabled || !props.container) return;
  const target =
    props.container.querySelector<HTMLElement>("[data-ai-document-anchor]") ||
    (props.container.firstElementChild as HTMLElement | null);
  if (!target) return;
  anchor.text = compactText(text);
  anchor.visible = true;
  anchor.source = "document";
  anchorTarget.value = target;
  contextLabel.value = props.documentLabel;
  openComposer();
}

function closeComposer() {
  if (props.busy || props.candidatePending) return;
  composerOpen.value = false;
  instruction.value = "";
  submitted.value = false;
  anchor.visible = false;
  anchorRect.value = null;
  anchorTarget.value = null;
  removeInlineHost();
  window.getSelection()?.removeAllRanges();
}

function submit() {
  const value = instruction.value.trim();
  if (!value || props.disabled || props.busy) return;
  submitted.value = true;
  emit("invoke", {
    text: anchor.text,
    instruction: value,
    source: anchor.source,
    target: requestTarget(anchorTarget.value),
  });
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (
    root.value?.contains(event.target as Node) ||
    composerRoot.value?.contains(event.target as Node)
  )
    return;
  if (composerOpen.value) closeComposer();
}

onMounted(() => {
  props.container?.addEventListener("pointerover", handlePointerOver);
  props.container?.addEventListener("pointerleave", handlePointerLeave);
  document.addEventListener("mouseup", captureSelection);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
});

onBeforeUnmount(() => {
  props.container?.removeEventListener("pointerover", handlePointerOver);
  props.container?.removeEventListener("pointerleave", handlePointerLeave);
  document.removeEventListener("mouseup", captureSelection);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  removeInlineHost();
});

watch(
  () => props.container,
  (next, previous) => {
    previous?.removeEventListener("pointerover", handlePointerOver);
    previous?.removeEventListener("pointerleave", handlePointerLeave);
    next?.addEventListener("pointerover", handlePointerOver);
    next?.addEventListener("pointerleave", handlePointerLeave);
  },
);
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled && !props.busy) closeComposer();
  },
);
watch(
  () => [props.candidatePending, props.busy] as const,
  ([candidatePending, busy], [previousCandidate]) => {
    if (previousCandidate && !candidatePending && !busy && submitted.value)
      closeComposer();
  },
);

defineExpose({ openForDocument, closeComposer });
</script>

<style scoped>
.text-selection-ai {
  position: absolute;
  z-index: 30;
  transform: translate(-50%, -50%);
  pointer-events: auto;
}
.text-selection-ai__trigger {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid #cbc8f5;
  border-radius: 8px;
  color: #4d46cf;
  background: #fff;
  box-shadow: 0 8px 22px rgba(45, 42, 130, 0.16);
  font-size: 12px;
  font-weight: 760;
  cursor: pointer;
  white-space: nowrap;
}
.text-selection-ai__trigger:hover {
  border-color: #8e88e9;
  color: #fff;
  background: #514bdc;
}
.text-selection-ai__trigger:focus-visible,
.text-selection-ai__composer button:focus-visible,
.text-selection-ai__composer textarea:focus-visible {
  outline: 3px solid rgba(91, 84, 232, 0.22);
  outline-offset: 2px;
}
:global(.text-selection-ai-host) {
  display: block;
  min-width: 0;
  margin: 10px 0 4px;
  list-style: none;
}
.text-selection-ai__composer {
  width: 100%;
  display: grid;
  gap: 10px;
  padding: 13px 14px;
  border: 1px solid #cfccf4;
  border-radius: 12px;
  color: #344054;
  background: #fafaff;
  box-shadow: 0 8px 20px rgba(31, 33, 84, 0.07);
  box-sizing: border-box;
}
.text-selection-ai__composer header {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 28px;
  align-items: center;
  gap: 8px;
}
.text-selection-ai__composer header > span {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #514bdc;
  background: #efeeff;
}
.text-selection-ai__composer header div {
  min-width: 0;
  display: grid;
  gap: 1px;
}
.text-selection-ai__composer strong {
  color: #20283a;
  font-size: 13px;
}
.text-selection-ai__composer small {
  color: #667085;
  font-size: 11px;
}
.text-selection-ai__close {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 7px;
  color: #667085;
  background: transparent;
  cursor: pointer;
}
.text-selection-ai__close:hover:not(:disabled) {
  color: #344054;
  background: #f2f4f7;
}
.text-selection-ai__composer blockquote {
  max-height: 72px;
  overflow: auto;
  margin: 0;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  color: #596579;
  background: #f1f3f8;
  font-size: 11px;
  line-height: 1.55;
}
.text-selection-ai__composer textarea {
  width: 100%;
  min-height: 64px;
  padding: 10px 11px;
  border: 1px solid #b8c0cd;
  border-radius: 9px;
  color: #172033;
  background: #fff;
  font: 500 13px/1.55 inherit;
  resize: vertical;
  box-sizing: border-box;
}
.text-selection-ai__composer textarea::placeholder {
  color: #747f91;
}
.text-selection-ai__hint,
.text-selection-ai__status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #667085;
  font-size: 10px;
  line-height: 1.45;
}
.text-selection-ai__status {
  color: #5148dc;
}
.text-selection-ai__status svg {
  animation: inline-ai-spin 0.8s linear infinite;
}
.text-selection-ai__composer footer {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
}
.text-selection-ai__composer footer button {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 11px;
  border: 1px solid #d2d7e0;
  border-radius: 8px;
  color: #475467;
  background: #fff;
  font-size: 11px;
  font-weight: 750;
  cursor: pointer;
}
.text-selection-ai__composer footer button.primary {
  border-color: #5148dc;
  color: #fff;
  background: #5148dc;
}
.text-selection-ai__composer footer button:hover:not(:disabled) {
  border-color: #a8a4eb;
  color: #4d46cf;
  background: #f7f6ff;
}
.text-selection-ai__composer footer button.primary:hover:not(:disabled) {
  border-color: #433bc4;
  color: #fff;
  background: #433bc4;
}
.text-selection-ai__composer button:disabled,
.text-selection-ai__composer textarea:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
@keyframes inline-ai-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .text-selection-ai__status svg {
    animation: none;
  }
}
.text-selection-ai__hint,
.text-selection-ai__status,
.text-selection-ai__candidate,
.text-selection-ai__error {
  font-size: 11px;
  line-height: 1.5;
}
.text-selection-ai__status {
  min-height: 42px;
}
.text-selection-ai__candidate {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #475467;
}
.text-selection-ai__error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #b42318;
}
.text-selection-ai__candidate + footer .primary svg {
  animation: none;
}
</style>
