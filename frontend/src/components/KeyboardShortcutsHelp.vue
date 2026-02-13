<template>
  <el-dialog
    v-model="visible"
    title="键盘快捷键"
    width="520px"
    align-center
    class="shortcuts-help-dialog"
    destroy-on-close
  >
    <div class="shortcuts-grid">
      <div
        v-for="(group, index) in shortcutGroups"
        :key="index"
        class="shortcut-group"
      >
        <h4 class="group-title">{{ group.title }}</h4>
        <div class="group-items">
          <div
            v-for="shortcut in group.items"
            :key="shortcut.key"
            class="shortcut-item"
          >
            <div class="shortcut-keys">
              <kbd v-if="shortcut.ctrl" class="key">Ctrl</kbd>
              <kbd v-if="shortcut.shift" class="key">Shift</kbd>
              <kbd v-if="shortcut.alt" class="key">Alt</kbd>
              <kbd class="key">{{ formatKey(shortcut.key) }}</kbd>
            </div>
            <span class="shortcut-desc">{{ shortcut.description }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end">
        <el-button @click="visible = false" class="!rounded-lg">
          关闭
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Shortcut {
  key: string
  description: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
}

interface ShortcutGroup {
  title: string
  items: Shortcut[]
}

const visible = ref(false)

const shortcutGroups = computed<ShortcutGroup[]>(() => [
  {
    title: '通用',
    items: [
      { key: 'k', ctrl: true, description: '全局搜索' },
      { key: '?', description: '显示快捷键帮助' },
      { key: 'f', ctrl: true, shift: true, description: '专注模式' },
    ],
  },
  {
    title: '编辑',
    items: [
      { key: 'n', ctrl: true, description: '新建节点' },
      { key: 's', ctrl: true, description: '保存' },
      { key: 'z', ctrl: true, description: '撤销' },
      { key: 'z', ctrl: true, shift: true, description: '重做' },
    ],
  },
  {
    title: '视图',
    items: [
      { key: 'b', ctrl: true, description: '切换侧边栏' },
      { key: 'g', ctrl: true, description: '知识图谱' },
    ],
  },
  {
    title: '导出',
    items: [
      { key: 'e', ctrl: true, shift: true, description: '导出内容' },
    ],
  },
])

const formatKey = (key: string) => {
  const keyMap: Record<string, string> = {
    'ArrowUp': '↑',
    'ArrowDown': '↓',
    'ArrowLeft': '←',
    'ArrowRight': '→',
    'Enter': '↵',
    'Escape': 'Esc',
    'Delete': 'Del',
    'Backspace': '⌫',
  }
  return keyMap[key] || key.toUpperCase()
}

const open = () => {
  visible.value = true
}

const close = () => {
  visible.value = false
}

defineExpose({
  open,
  close,
})
</script>

<style scoped>
.shortcuts-grid {
  display: grid;
  gap: 1.5rem;
}

.shortcut-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.group-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.group-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f1f5f9;
}

.shortcut-item:last-child {
  border-bottom: none;
}

.shortcut-keys {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.key {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.75rem;
  height: 1.75rem;
  padding: 0 0.375rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 500;
  color: #475569;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #cbd5e1;
  border-radius: 0.375rem;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 1px 2px rgba(0, 0, 0, 0.05);
}

.shortcut-desc {
  font-size: 0.875rem;
  color: #334155;
}


</style>
