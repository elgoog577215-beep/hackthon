import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import MarkdownDocumentEditor from '@/components/MarkdownDocumentEditor.vue'
import type { Node as CourseNode } from '@/stores/types'

const node: CourseNode = {
  node_id: 'node-1',
  parent_node_id: 'root',
  node_name: '测试节点',
  node_level: 2,
  node_content: '这是一段可以提问的内容。',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}

describe('MarkdownDocumentEditor', () => {
  const mountEditor = (content = node.node_content, isStreaming = false) => {
    const pinia = createPinia()
    setActivePinia(pinia)

    return mount(MarkdownDocumentEditor, {
      props: {
        node,
        content,
        isStreaming,
      },
      global: {
        plugins: [pinia],
        stubs: {
          MarkdownRenderer: {
            props: ['content'],
            template: '<div class="markdown-renderer"><p>{{ content }}</p></div>',
          },
        },
      },
    })
  }

  it('渲染并响应正文内容更新', async () => {
    const wrapper = mountEditor()
    expect(wrapper.find('.markdown-renderer').text()).toBe(node.node_content)

    await wrapper.setProps({ content: '更新后的课程正文。' })
    expect(wrapper.find('.markdown-renderer').text()).toBe('更新后的课程正文。')
  })

  it('只呈现流式状态，不再维护组件内选区 AI 面板', () => {
    const wrapper = mountEditor(node.node_content, true)

    expect(wrapper.find('.animate-blink').exists()).toBe(true)
    expect(wrapper.find('.selection-ai-toolbar').exists()).toBe(false)
    expect(wrapper.find('.selection-ai-panel').exists()).toBe(false)
  })
})
