<script setup lang="ts">
import { ref, watch } from 'vue'

/**
 * 可折叠区块（点击标题栏展开/收起）。
 *
 * 用于把课程页「下方资源」（教案版本 / PPT / 课堂视频）提到正文上方后，
 * 仍能一键收起，避免资源多时挤压正文浏览。
 *
 * - 默认展开（defaultOpen），资源即时可见，解决「要拖到最底下」的问题；
 * - 标题栏右侧 actions 插槽用于放操作按钮，点击不会触发折叠。
 */
const props = withDefaults(
  defineProps<{
    title: string
    /** 标题后的数量角标，未传则不显示 */
    count?: number
    /** 初始是否展开，默认展开 */
    defaultOpen?: boolean
  }>(),
  { defaultOpen: true }
)

const open = ref(props.defaultOpen)
// defaultOpen 变化时同步（父组件异步加载后可能调整初始态）
watch(
  () => props.defaultOpen,
  (v) => {
    open.value = v
  }
)

function toggle() {
  open.value = !open.value
}
</script>

<template>
  <section class="collapsible-section" :class="{ 'is-open': open }">
    <button
      type="button"
      class="cs-header"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="cs-titlewrap">
        <svg class="cs-chevron" :class="{ open }" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="cs-title">{{ title }}</span>
        <span v-if="count !== undefined" class="cs-count">{{ count }}</span>
      </span>
      <span v-if="$slots.actions" class="cs-actions" @click.stop>
        <slot name="actions" />
      </span>
    </button>

    <div v-show="open" class="cs-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.collapsible-section {
  background: #fff;
  border: 1px solid #e9edf3;
  border-radius: 14px;
  overflow: hidden;
}

.cs-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}

.cs-header:hover {
  background: #f8fafc;
}

.cs-titlewrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.cs-chevron {
  color: #8a94a6;
  transition: transform 0.18s ease;
  flex: none;
}

.cs-chevron.open {
  transform: rotate(90deg);
}

.cs-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.cs-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.cs-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.cs-body {
  padding: 0 24px 20px;
}
</style>
