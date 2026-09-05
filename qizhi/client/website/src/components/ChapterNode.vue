<template>
  <div
    class="chapter-card"
    :class="[
      node.kind === 'chapter' ? 'chapter-card--chapter' : 'chapter-card--section',
      { 'chapter-card--draggable': enableDrag },
      {
        'is-dragging': draggingUnitId === node.id,
        'drag-over-above': dragOverUnitId === node.id && dragOverPosition === 'above' && draggingUnitId !== node.id,
        'drag-over-below': dragOverUnitId === node.id && dragOverPosition === 'below' && draggingUnitId !== node.id,
      },
    ]"
    :style="indentStyle"
    @click="onSelect"
    :data-selected="isSelected ? '1' : '0'"
    @dragover="onCardDragOver"
    @dragleave="onCardDragLeave"
    @drop="onCardDrop"
  >
    <div v-if="enableDrag" class="chapter-card-rail">
      <span
        class="drag-handle"
        draggable="true"
        aria-label="拖动排序"
        title="拖动调整顺序"
        @mousedown.stop
        @click.stop
        @dragstart="onHandleDragStart"
        @dragend="onHandleDragEnd"
      >⋮⋮</span>
    </div>

    <div class="chapter-card-top">
      <button
        class="chapter-collapse-btn"
        type="button"
        @click="onToggle"
        :aria-label="node.collapsed ? '展开' : '收起'"
      >
        <svg v-if="node.collapsed" width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path
            d="M9 6l6 6-6 6"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path
            d="M6 9l6 6 6-6"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <span class="chapter-pill" :class="pillClass">{{ pillText }}</span>

      <input
        class="chapter-title-input"
        type="text"
        :value="node.title"
        placeholder="请输入标题"
        @input="onTitleInput"
        :readonly="readOnly"
      />

      <div class="chapter-menu-wrapper">
        <button
          v-if="showMenu"
          class="chapter-menu-btn"
          type="button"
          @click.stop="isMenuOpen ? onCloseMenu() : onOpenMenu()"
          aria-label="菜单"
        >
          <svg class="dots-icon" width="22" height="22" viewBox="0 0 24 24" fill="none">
            <circle cx="6.5" cy="12" r="1.8" fill="currentColor" />
            <circle cx="12" cy="12" r="1.8" fill="currentColor" />
            <circle cx="17.5" cy="12" r="1.8" fill="currentColor" />
          </svg>
        </button>

        <div v-if="isMenuOpen && showMenu" class="chapter-menu" @click.stop>
          <div v-if="showRename" class="chapter-menu-item" @click="onRename">
            <svg class="menu-item-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 20h9"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path
                d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>重命名</span>
          </div>
          <div
            class="chapter-menu-item"
            :class="{ disabled: !canAddChild }"
            :aria-disabled="!canAddChild"
            @click="canAddChild && onAddChild()"
          >
            <svg class="menu-item-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span>添加子章节</span>
          </div>
          <div class="chapter-menu-item danger" @click="onDelete">
            <svg class="menu-item-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span>删除此章节</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showDescription" class="chapter-card-desc">
      <div class="chapter-desc-spacer" aria-hidden="true"></div>
      <div class="chapter-desc-spacer" aria-hidden="true"></div>
      <textarea
        class="chapter-desc-input"
        :value="node.description"
        placeholder="请输入章节描述（选填）…"
        rows="2"
        @input="onDescInput"
        :readonly="readOnly"
      ></textarea>
      <div class="chapter-desc-spacer" aria-hidden="true"></div>
    </div>

    <div v-if="!node.collapsed && node.children && node.children.length" class="chapter-children">
      <ChapterNode
        v-for="(child, idx) in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :ordinal="idx + 1"
        :activeMenuId="activeMenuId"
        :maxDepth="maxDepth"
        :readOnly="readOnly"
        :showMenu="showMenu"
        :showDescription="showDescription"
        :showRename="showRename"
        :selectedId="selectedId"
        :enableDrag="enableDrag"
        :draggingUnitId="draggingUnitId"
        :dragOverUnitId="dragOverUnitId"
        :dragOverPosition="dragOverPosition"
        @toggle="$emit('toggle', $event)"
        @openMenu="$emit('openMenu', $event)"
        @closeMenu="$emit('closeMenu')"
        @addChild="$emit('addChild', $event)"
        @delete="$emit('delete', $event)"
        @updateTitle="(id, title) => $emit('updateTitle', id, title)"
        @updateDesc="(id, desc) => $emit('updateDesc', id, desc)"
        @select="$emit('select', $event)"
        @rename="$emit('rename', $event)"
        @dragStart="$emit('dragStart', $event)"
        @dragOver="(id, e) => $emit('dragOver', id, e)"
        @dragLeave="(id, e) => $emit('dragLeave', id, e)"
        @drop="(id, e) => $emit('drop', id, e)"
        @dragEnd="$emit('dragEnd')"
        @dragOverTail="(parentId, e) => $emit('dragOverTail', parentId, e)"
        @dragLeaveTail="(parentId, e) => $emit('dragLeaveTail', parentId, e)"
        @dropTail="(parentId, e) => $emit('dropTail', parentId, e)"
      />
      <div
        v-if="enableDrag"
        class="chapter-drop-tail"
        @dragover.prevent.stop="onChildrenTailDragOver"
        @dragleave.stop="onChildrenTailDragLeave"
        @drop.prevent.stop="onChildrenTailDrop"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type ChapterKind = 'chapter' | 'section'
export type ChapterNodeModel = {
  id: string
  kind: ChapterKind
  title: string
  description: string
  collapsed: boolean
  children: ChapterNodeModel[]
}

const props = withDefaults(
  defineProps<{
    node: ChapterNodeModel
    depth: number
    /** 同层级序号（1-based），用于胶囊显示：章1/节1... */
    ordinal?: number
    activeMenuId: string | null
    /** 最大层级数（含根层），默认 3：章-节-节 */
    maxDepth?: number
    /** 只读展示（用于课程详情页） */
    readOnly?: boolean
    /** 是否显示三点菜单（只读时会自动隐藏） */
    showMenu?: boolean
    /** 是否展示描述输入框 */
    showDescription?: boolean
    /** 是否展示重命名入口（用于课程详情页） */
    showRename?: boolean
    /** 当前选中节点 id（用于高亮） */
    selectedId?: string | null
    /** 是否允许拖拽排序 */
    enableDrag?: boolean
    draggingUnitId?: string | null
    dragOverUnitId?: string | null
    dragOverPosition?: 'above' | 'below'
  }>(),
  {
    ordinal: 1,
    maxDepth: 3,
    readOnly: false,
    showMenu: true,
    showDescription: true,
    showRename: false,
    selectedId: null,
    enableDrag: false,
    draggingUnitId: null,
    dragOverUnitId: null,
    dragOverPosition: 'above',
  }
)

const emit = defineEmits<{
  (e: 'toggle', id: string): void
  (e: 'openMenu', id: string): void
  (e: 'closeMenu'): void
  (e: 'addChild', parentId: string): void
  (e: 'delete', id: string): void
  (e: 'updateTitle', id: string, title: string): void
  (e: 'updateDesc', id: string, desc: string): void
  (e: 'select', id: string): void
  (e: 'rename', id: string): void
  (e: 'dragStart', id: string): void
  (e: 'dragOver', id: string, event: DragEvent): void
  (e: 'dragLeave', id: string, event: DragEvent): void
  (e: 'drop', id: string, event: DragEvent): void
  (e: 'dragEnd'): void
  (e: 'dragOverTail', parentUnitId: string | null, event: DragEvent): void
  (e: 'dragLeaveTail', parentUnitId: string | null, event: DragEvent): void
  (e: 'dropTail', parentUnitId: string | null, event: DragEvent): void
}>()

const indentStyle = computed(() => ({
  marginLeft: `${props.depth * 16}px`,
}))

const isMenuOpen = computed(() => props.activeMenuId === props.node.id)
const pillText = computed(() => `${props.node.kind === 'chapter' ? '章' : '节'}${props.ordinal ?? 1}`)
const pillClass = computed(() => (props.node.kind === 'chapter' ? 'pill-blue' : 'pill-green'))
const canAddChild = computed(() => props.depth < (props.maxDepth ?? 3) - 1)
const isSelected = computed(() => !!props.selectedId && props.selectedId === props.node.id)

function onToggle() {
  emit('toggle', props.node.id)
}
function onOpenMenu() {
  emit('openMenu', props.node.id)
}
function onCloseMenu() {
  emit('closeMenu')
}
function onAddChild() {
  emit('addChild', props.node.id)
  onCloseMenu()
}
function onDelete() {
  emit('delete', props.node.id)
  onCloseMenu()
}
function onRename() {
  emit('rename', props.node.id)
  onCloseMenu()
}
function onTitleInput(e: Event) {
  emit('updateTitle', props.node.id, (e.target as HTMLInputElement).value)
}
function onDescInput(e: Event) {
  emit('updateDesc', props.node.id, (e.target as HTMLTextAreaElement).value)
}
function onSelect() {
  emit('select', props.node.id)
}

function onHandleDragStart(e: DragEvent) {
  if (!props.enableDrag) {
    e.preventDefault()
    return
  }
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', props.node.id)
  }
  emit('dragStart', props.node.id)
}

function onHandleDragEnd() {
  emit('dragEnd')
}

function onCardDragOver(e: DragEvent) {
  if (!props.enableDrag || !props.draggingUnitId || props.draggingUnitId === props.node.id) return
  e.preventDefault()
  e.stopPropagation()
  emit('dragOver', props.node.id, e)
}

function onCardDragLeave(e: DragEvent) {
  if (!props.enableDrag) return
  const current = e.currentTarget as HTMLElement
  const related = e.relatedTarget as Node | null
  if (related && current.contains(related)) return
  e.stopPropagation()
  emit('dragLeave', props.node.id, e)
}

function onCardDrop(e: DragEvent) {
  if (!props.enableDrag) return
  e.preventDefault()
  e.stopPropagation()
  emit('drop', props.node.id, e)
}

function onChildrenTailDragOver(e: DragEvent) {
  if (!props.enableDrag || !props.draggingUnitId) return
  e.preventDefault()
  emit('dragOverTail', props.node.id, e)
}

function onChildrenTailDragLeave(e: DragEvent) {
  if (!props.enableDrag) return
  const current = e.currentTarget as HTMLElement
  const related = e.relatedTarget as Node | null
  if (related && current.contains(related)) return
  emit('dragLeaveTail', props.node.id, e)
}

function onChildrenTailDrop(e: DragEvent) {
  if (!props.enableDrag) return
  emit('dropTail', props.node.id, e)
}
</script>

<style scoped>
.chapter-card {
  position: relative;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 14px;
  padding: 12px 12px 12px 14px;
  box-shadow:
    0 10px 24px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: visible;
}
.chapter-card[data-selected='1'] {
  border-color: rgba(19, 88, 228, 0.35);
  background: rgba(19, 88, 228, 0.06);
  box-shadow:
    0 14px 32px rgba(19, 88, 228, 0.10),
    0 4px 12px rgba(0, 0, 0, 0.04);
}
.chapter-card--section[data-selected='1'] {
  border-color: rgba(27, 138, 90, 0.32);
  background: rgba(27, 138, 90, 0.06);
  box-shadow:
    0 14px 32px rgba(27, 138, 90, 0.10),
    0 4px 12px rgba(0, 0, 0, 0.04);
}

/* 左侧色条：根据章/节变色（可拖拽时由 .chapter-card-rail 接管） */
.chapter-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  border-top-left-radius: 14px;
  border-bottom-left-radius: 14px;
  background: rgba(19, 88, 228, 0.55);
}
.chapter-card--section::before {
  background: rgba(27, 138, 90, 0.55);
}
.chapter-card--draggable::before {
  display: none;
}

.chapter-card--draggable {
  padding-left: 28px;
}

.chapter-card-rail {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-top-left-radius: 14px;
  border-bottom-left-radius: 14px;
  background: rgba(19, 88, 228, 0.55);
  z-index: 1;
  transition: background-color 0.18s, filter 0.18s;
}

.chapter-card--section .chapter-card-rail {
  background: rgba(27, 138, 90, 0.55);
}

.chapter-card--draggable:hover .chapter-card-rail {
  filter: brightness(1.06);
}

.chapter-card--draggable.is-dragging .chapter-card-rail {
  filter: brightness(1.12);
}

.chapter-card.is-dragging {
  opacity: 0.55;
}

.chapter-card.drag-over-above {
  box-shadow:
    inset 0 3px 0 #1358E4,
    0 10px 24px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.04);
}

.chapter-card.drag-over-below {
  box-shadow:
    inset 0 -3px 0 #1358E4,
    0 10px 24px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.04);
}

.chapter-card--section.drag-over-above {
  box-shadow:
    inset 0 3px 0 #1B8A5A,
    0 10px 24px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.04);
}

.chapter-card--section.drag-over-below {
  box-shadow:
    inset 0 -3px 0 #1B8A5A,
    0 10px 24px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.04);
}

.chapter-drop-tail {
  min-height: 20px;
  flex-shrink: 0;
}

.chapter-card-top {
  display: grid;
  grid-template-columns: 32px auto minmax(120px, 1fr) 40px;
  gap: 10px;
  align-items: center;
}

.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-height: 36px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -3px;
  line-height: 1;
  cursor: grab;
  user-select: none;
  transition: color 0.18s;
}

.drag-handle:hover {
  color: #fff;
}

.drag-handle:active {
  cursor: grabbing;
}

.chapter-collapse-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: #1f2328;
  cursor: pointer;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.18s, border-color 0.18s, box-shadow 0.18s, transform 0.12s;
}
.chapter-collapse-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
.chapter-collapse-btn:active {
  transform: translateY(0.5px);
}

.chapter-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.2px;
  user-select: none;
  white-space: nowrap;
}
.pill-blue {
  color: #1358E4;
  background: rgba(19, 88, 228, 0.12);
  border: 1px solid rgba(19, 88, 228, 0.22);
}
.pill-green {
  color: #1B8A5A;
  background: rgba(27, 138, 90, 0.12);
  border: 1px solid rgba(27, 138, 90, 0.22);
}

.chapter-title-input {
  width: 100%;
  height: 36px;
  padding: 0 12px;
  border: 1px solid rgba(0, 0, 0, 0.10);
  border-radius: 999px;
  font-size: 14px;
  color: #111;
  outline: none;
  background: rgba(255, 255, 255, 0.95);
  transition: border-color 0.18s, box-shadow 0.18s, background-color 0.18s;
}
.chapter-title-input[readonly] {
  cursor: pointer;
  background: rgba(255, 255, 255, 0.75);
}
.chapter-title-input:focus {
  border-color: rgba(19, 88, 228, 0.55);
  box-shadow: 0 0 0 4px rgba(19, 88, 228, 0.12);
  background: #ffffff;
}
.chapter-title-input::placeholder {
  color: #8b8f98;
}

.chapter-menu-wrapper {
  position: relative;
  display: flex;
  justify-content: flex-end;
}
.chapter-menu-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  color: #1f2328;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.18s, box-shadow 0.18s, transform 0.12s;
}
.chapter-menu-btn:hover {
  background-color: rgba(0, 0, 0, 0.04);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
.chapter-menu-btn:active {
  transform: translateY(0.5px);
}

.dots-icon {
  color: #30343a;
}

.chapter-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 180px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.10);
  border-radius: 12px;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.16);
  overflow: hidden;
  z-index: 1000;
}

.chapter-menu-item {
  padding: 12px 14px;
  font-size: 14px;
  color: #111;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: background-color 0.18s;
}
.chapter-menu-item:hover {
  background: #f6f7fb;
}
.chapter-menu-item.danger {
  color: #d32f2f;
}
.chapter-menu-item.danger:hover {
  background: rgba(211, 47, 47, 0.08);
}

.menu-item-icon {
  flex: 0 0 auto;
}

.chapter-menu-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}

.chapter-desc-input {
  width: 100%;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  font-size: 14px;
  color: #111;
  outline: none;
  resize: vertical;
  font-family: inherit;
  background: #f7f8fb;
  transition: border-color 0.18s, box-shadow 0.18s, background-color 0.18s;
}
.chapter-desc-input[readonly] {
  cursor: pointer;
}
.chapter-desc-input:focus {
  border-color: rgba(19, 88, 228, 0.45);
  box-shadow: 0 0 0 4px rgba(19, 88, 228, 0.10);
  background: #ffffff;
}
.chapter-desc-input::placeholder {
  color: #8b8f98;
}

.chapter-children {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chapter-card-desc {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 32px auto minmax(120px, 1fr) 40px;
  gap: 10px;
  align-items: start;
}

.chapter-desc-spacer {
  width: 100%;
  height: 1px;
}

/* 小屏：让标题输入更优雅换行 */
@media (max-width: 520px) {
  .chapter-card-top {
    grid-template-columns: 32px auto 1fr 40px;
    grid-auto-rows: auto;
  }
  /* 把折叠按钮 / 胶囊 / 菜单按钮锁在第一行，标题独占第二行铺满。
     之前只给 title 设 1/-1 会让菜单按钮被自动放到第三行 col 1，
     而它的下拉 (right: 0) 又会朝左溢出，看起来"没反应"。 */
  .chapter-collapse-btn {
    grid-row: 1;
    grid-column: 1;
  }
  .chapter-pill {
    grid-row: 1;
    grid-column: 2;
  }
  .chapter-menu-wrapper {
    grid-row: 1;
    grid-column: 4;
  }
  .chapter-title-input {
    grid-row: 2;
    grid-column: 1 / -1;
  }

  .chapter-card-desc {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .chapter-desc-spacer {
    display: none;
  }
}
</style>
