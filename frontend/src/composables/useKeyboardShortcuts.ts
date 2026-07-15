import { onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export interface ShortcutConfig {
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  meta?: boolean
  handler: () => void
  description?: string
  preventDefault?: boolean
}

export function useKeyboardShortcuts(
  shortcuts: ShortcutConfig[],
  enabled: Ref<boolean> | boolean = true
) {
  const isEnabled = () => {
    if (typeof enabled === 'boolean') return enabled
    return enabled.value
  }

  const handleKeydown = (event: KeyboardEvent) => {
    if (!isEnabled()) return

    // Ignore shortcuts when user is typing in input/textarea
    const target = event.target as HTMLElement
    if (
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable
    ) {
      return
    }

    for (const shortcut of shortcuts) {
      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
      const ctrlMatch = !!shortcut.ctrl === (event.ctrlKey || event.metaKey)
      const shiftMatch = !!shortcut.shift === event.shiftKey
      const altMatch = !!shortcut.alt === event.altKey

      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        if (shortcut.preventDefault !== false) {
          event.preventDefault()
        }
        shortcut.handler()
        break
      }
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
  })

  return {
    handleKeydown,
  }
}

// Common shortcuts presets
export const createCommonShortcuts = (options: {
  onSearch?: () => void
  onNewNode?: () => void
  onSave?: () => void
  onFocusMode?: () => void
  onToggleSidebar?: () => void
  onExport?: () => void
  onUndo?: () => void
  onRedo?: () => void
  onHelp?: () => void
}): ShortcutConfig[] => {
  const shortcuts: ShortcutConfig[] = []

  if (options.onSearch) {
    shortcuts.push({
      key: 'k',
      ctrl: true,
      handler: options.onSearch,
      description: '全局搜索',
      preventDefault: true,
    })
  }

  if (options.onNewNode) {
    shortcuts.push({
      key: 'n',
      ctrl: true,
      handler: options.onNewNode,
      description: '新建节点',
      preventDefault: true,
    })
  }

  if (options.onSave) {
    shortcuts.push({
      key: 's',
      ctrl: true,
      handler: options.onSave,
      description: '保存',
      preventDefault: true,
    })
  }

  if (options.onFocusMode) {
    shortcuts.push({
      key: 'f',
      ctrl: true,
      shift: true,
      handler: options.onFocusMode,
      description: '专注模式',
      preventDefault: true,
    })
  }

  if (options.onToggleSidebar) {
    shortcuts.push({
      key: 'b',
      ctrl: true,
      handler: options.onToggleSidebar,
      description: '切换侧边栏',
      preventDefault: true,
    })
  }

  if (options.onExport) {
    shortcuts.push({
      key: 'e',
      ctrl: true,
      shift: true,
      handler: options.onExport,
      description: '导出',
      preventDefault: true,
    })
  }

  if (options.onUndo) {
    shortcuts.push({
      key: 'z',
      ctrl: true,
      handler: options.onUndo,
      description: '撤销',
      preventDefault: true,
    })
  }

  if (options.onRedo) {
    shortcuts.push({
      key: 'z',
      ctrl: true,
      shift: true,
      handler: options.onRedo,
      description: '重做',
      preventDefault: true,
    })
  }

  if (options.onHelp) {
    shortcuts.push({
      key: '?',
      handler: options.onHelp,
      description: '显示快捷键帮助',
      preventDefault: true,
    })
  }

  return shortcuts
}
