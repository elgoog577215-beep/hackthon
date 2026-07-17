import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InlineCourseBlockAI from '@/components/InlineCourseBlockAI.vue'
import { useAITeacherStore, type AIMessage, type SendAIMessagePayload } from '@/stores/aiTeacher'
import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'
import type { ContentBlock, Node, Note } from '@/stores/types'

const node: Node = {
  node_id: 'node-1',
  parent_node_id: 'chapter-1',
  node_name: '向量空间',
  node_level: 2,
  node_content: '',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}

const block: ContentBlock = {
  block_id: 'block-1',
  block_revision_id: 'block-revision-1',
  type: 'concept',
  title: '向量的定义',
  content: '向量同时具有大小和方向。',
  order: 0,
}

function mountBlockAI(attachToDocument = false, props: { active?: boolean } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const courseStore = useCourseStore()
  courseStore.currentCourseId = 'course-1'
  courseStore.currentCourseVersionId = 'course-version-1'
  const aiStore = useAITeacherStore()
  const noteStore = useNoteStore()
  const persistedNote: Note = {
    id: 'ai-qa-block-1',
    nodeId: 'node-1',
    highlightId: 'hl-ai-qa-block-1',
    quote: '向量的定义\n\n向量同时具有大小和方向。',
    title: '解释 · 向量的定义',
    summary: '回答摘要',
    content: '回答正文',
    color: 'purple',
    createdAt: Date.now(),
    sourceType: 'ai',
    recordType: 'note',
    status: 'active',
    origin: 'assistant_inline_qa',
    syncState: 'saved',
    anchor: { block_id: 'block-1', block_revision_id: 'block-revision-1' },
    metadata: { record_subtype: 'anchored_ai_qa' },
  }
  vi.spyOn(noteStore, 'upsertAnchoredAiNote').mockResolvedValue(persistedNote)
  vi.spyOn(noteStore, 'deleteNote').mockResolvedValue()

  vi.spyOn(aiStore, 'sendMessage').mockImplementation(async (payload: SendAIMessagePayload) => {
    const message: AIMessage = {
      message_id: `message-${Math.random()}`,
      role: 'assistant',
      content: '',
      status: 'streaming',
      context_ref: payload.contextRef,
    }
    payload.onAssistantMessage?.(message)
    message.content = `回答：${payload.question}`
    message.status = 'complete'
  })

  const wrapper = mount(InlineCourseBlockAI, {
    props: { node, block, active: true, ...props },
    ...(attachToDocument ? { attachTo: document.body } : {}),
    global: {
      plugins: [pinia],
      stubs: {
        MarkdownRenderer: { props: ['content'], template: '<div class="markdown-stub">{{ content }}</div>' },
      },
    },
  })
  return { wrapper, aiStore, noteStore }
}

describe('InlineCourseBlockAI', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('固定提供解释、举例、简化和提问四个块级动作', () => {
    const { wrapper } = mountBlockAI()

    expect(wrapper.findAll('.block-ai-menu button').map(button => button.text())).toEqual(['解释', '举例', '简化', '提问'])
  })

  it('菜单保持稳定挂载，不再因悬停反复插入和删除 DOM', async () => {
    const { wrapper } = mountBlockAI(false, { active: false })
    const menu = wrapper.get('.block-ai-menu')
    expect(menu.classes()).not.toContain('is-active')

    await wrapper.setProps({ active: true })
    expect(wrapper.get('.block-ai-menu').element).toBe(menu.element)
    expect(wrapper.get('.block-ai-menu').classes()).toContain('is-active')
  })

  it('打开菜单后用方向键移动焦点，Escape 关闭并返回入口', async () => {
    const { wrapper } = mountBlockAI(true)
    await flushPromises()

    const menuButtons = wrapper.findAll('.block-ai-menu button')
    expect(document.activeElement).toBe(menuButtons[0]!.element)

    await wrapper.get('.block-ai-menu').trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(menuButtons[1]!.element)

    await wrapper.get('.block-ai-menu').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(wrapper.emitted('activate')).toEqual([['']])
    expect(document.activeElement).toBe(wrapper.get('.block-ai-handle').element)
    wrapper.unmount()
  })

  it('点击当前内容块之外会关闭操作菜单', () => {
    const { wrapper } = mountBlockAI()

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))

    expect(wrapper.emitted('activate')).toEqual([['']])
    wrapper.unmount()
  })

  it('学生块级菜单不混入正式课程编辑动作', () => {
    const { wrapper } = mountBlockAI()

    expect(wrapper.findAll('.block-ai-menu button').map(button => button.text())).toEqual(['解释', '举例', '简化', '提问'])
    expect(wrapper.text()).not.toContain('改进正式正文')
  })

  it('解释动作使用稳定块上下文并在原位显示结果', async () => {
    const { wrapper, aiStore, noteStore } = mountBlockAI()

    await wrapper.findAll('.block-ai-menu button')[0]!.trigger('click')
    await flushPromises()

    expect(aiStore.sendMessage).toHaveBeenCalledWith(expect.objectContaining({
      courseId: 'course-1',
      nodeId: 'node-1',
      entrypoint: 'block',
      selection: '向量的定义\n\n向量同时具有大小和方向。',
      contextRef: expect.objectContaining({
        content_anchor: expect.objectContaining({ block_id: 'block-1', block_revision_id: 'block-revision-1' }),
      }),
    }))
    expect(wrapper.findAll('.inline-ai-result')).toHaveLength(1)
    expect(wrapper.get('.markdown-stub').text()).toContain('回答：')
    expect(wrapper.get('.inline-ai-result__header').text()).toContain('来源：向量的定义')
    expect(noteStore.upsertAnchoredAiNote).toHaveBeenCalledWith(expect.objectContaining({
      nodeId: 'node-1',
      prompt: '请只基于当前课程内容块，用更容易理解的方式解释它。',
      content: expect.stringContaining('### AI 讲解'),
      anchor: expect.objectContaining({ block_id: 'block-1', block_revision_id: 'block-revision-1' }),
    }))
    expect(wrapper.emitted('recordPersisted')).toEqual([['ai-qa-block-1']])
    expect(wrapper.text()).toContain('已沉淀到正文')
  })

  it('完整回答只收集显式效果反馈，不自动触发下一步或额外问答', async () => {
    const { wrapper, aiStore } = mountBlockAI()
    const feedback = vi.spyOn(aiStore, 'submitAnswerFeedback').mockResolvedValue({
      status: 'recorded', event_id: 'event-1', feedback: 'unclear',
    })

    await wrapper.findAll('.block-ai-menu button')[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('.inline-ai-feedback').text()).toContain('这次回答解决你的问题了吗？')

    await wrapper.findAll('.inline-ai-feedback button')[1]!.trigger('click')
    await flushPromises()

    expect(feedback).toHaveBeenCalledWith(
      expect.objectContaining({ role: 'assistant', status: 'complete' }),
      'unclear',
      expect.objectContaining({
        action: 'explain',
        contentAnchor: expect.objectContaining({ block_id: 'block-1', block_revision_id: 'block-revision-1' }),
      }),
    )
    expect(aiStore.sendMessage).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.inline-ai-feedback button')[1]!.classes()).toContain('active')
  })

  it('提问与继续追问始终复用同一个行内结果块', async () => {
    const { wrapper, aiStore } = mountBlockAI()

    await wrapper.findAll('.block-ai-menu button')[3]!.trigger('click')
    await wrapper.get('.inline-ai-composer textarea').setValue('它和标量有什么区别？')
    await wrapper.get('.inline-ai-composer').trigger('submit')
    await flushPromises()
    await wrapper.get('.inline-ai-result__actions button').trigger('click')
    await wrapper.get('.inline-ai-composer textarea').setValue('能再短一点吗？')
    await wrapper.get('.inline-ai-composer').trigger('submit')
    await flushPromises()

    expect(aiStore.sendMessage).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.inline-ai-result')).toHaveLength(1)
    expect(wrapper.get('.markdown-stub').text()).toContain('能再短一点吗？')
  })

  it('可取消未发送的提问，不留下空结果块', async () => {
    const { wrapper } = mountBlockAI()

    await wrapper.findAll('.block-ai-menu button')[3]!.trigger('click')
    expect(wrapper.find('.inline-ai-composer').exists()).toBe(true)

    await wrapper.get('.cancel-composer-action').trigger('click')
    expect(wrapper.find('.inline-ai-result').exists()).toBe(false)
  })

  it('生成中明确显示停止操作并取消当前请求', async () => {
    const { wrapper, aiStore } = mountBlockAI()
    vi.spyOn(aiStore, 'cancel')
    vi.spyOn(aiStore, 'sendMessage').mockImplementation((payload: SendAIMessagePayload) => {
      payload.onAssistantMessage?.({
        message_id: 'streaming-message',
        role: 'assistant',
        content: '',
        status: 'streaming',
        context_ref: payload.contextRef,
      })
      return new Promise<void>(() => {})
    })

    await wrapper.findAll('.block-ai-menu button')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.inline-ai-result__loading span')).toHaveLength(3)
    expect(wrapper.get('.remove-action').text()).toContain('停止生成')

    await wrapper.get('.remove-action').trigger('click')
    expect(aiStore.cancel).toHaveBeenCalledOnce()
    expect(wrapper.find('.inline-ai-result').exists()).toBe(false)
  })

  it('回答自动进入正文，重做更新同一条记录，删除同时归档记录', async () => {
    const { wrapper, aiStore, noteStore } = mountBlockAI()
    await wrapper.findAll('.block-ai-menu button')[1]!.trigger('click')
    await flushPromises()
    expect(noteStore.upsertAnchoredAiNote).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已沉淀到正文')

    await wrapper.findAll('.inline-ai-result__actions button')[1]!.trigger('click')
    await flushPromises()
    expect(aiStore.sendMessage).toHaveBeenCalledTimes(2)
    expect(noteStore.upsertAnchoredAiNote).toHaveBeenCalledTimes(2)
    expect(noteStore.upsertAnchoredAiNote).toHaveBeenLastCalledWith(expect.objectContaining({
      action: 'example',
      anchor: expect.objectContaining({ block_id: 'block-1' }),
    }))

    await wrapper.findAll('.inline-ai-result__actions button').at(-1)!.trigger('click')
    await flushPromises()
    expect(noteStore.deleteNote).toHaveBeenCalledWith('ai-qa-block-1')
    expect(wrapper.emitted('recordReleased')).toContainEqual(['ai-qa-block-1'])
    expect(wrapper.find('.inline-ai-result').exists()).toBe(false)
  })
})
