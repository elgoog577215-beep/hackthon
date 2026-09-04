import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import TextSelectionAiAction from '../../components/TextSelectionAiAction.vue'

function selectionFixture(text: string) {
  const host = document.createElement('section')
  const paragraph = document.createElement('p')
  paragraph.textContent = text
  host.appendChild(paragraph)
  document.body.appendChild(host)
  Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
  host.getBoundingClientRect = () => ({
    x: 100, y: 100, left: 100, top: 100, right: 740, bottom: 500, width: 640, height: 400,
    toJSON: () => ({}),
  })
  paragraph.getBoundingClientRect = () => ({
    x: 180, y: 220, left: 180, top: 220, right: 620, bottom: 280, width: 440, height: 60,
    toJSON: () => ({}),
  })
  const range = {
    startContainer: paragraph.firstChild,
    endContainer: paragraph.firstChild,
    getBoundingClientRect: () => ({
      x: 180, y: 220, left: 180, top: 220, right: 420, bottom: 242, width: 240, height: 22,
      toJSON: () => ({}),
    }),
  } as unknown as Range
  return { host, range }
}

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('文中选区 AI 快捷操作', () => {
  it('仅在当前文档选中有效文字后浮出入口，并就地收集修改要求', async () => {
    const { host, range } = selectionFixture('理解函数模型并确定定义域')
    const removeAllRanges = vi.fn()
    vi.spyOn(window, 'getSelection').mockReturnValue({
      toString: () => '理解函数模型并确定定义域',
      rangeCount: 1,
      getRangeAt: () => range,
      removeAllRanges,
    } as unknown as Selection)
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, label: 'AI 修改' },
    })

    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()

    expect(wrapper.get('button').text()).toContain('AI 修改')
    expect(wrapper.get('.text-selection-ai').attributes('style')).toContain('left: 320px')
    expect(wrapper.get('.text-selection-ai').attributes('style')).toContain('top: 124px')
    await wrapper.get('button').trigger('click')
    expect(host.querySelector('blockquote')?.textContent).toContain('理解函数模型并确定定义域')
    const textarea = host.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '改成可观察、可检查的学习行为'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await nextTick()
    expect(wrapper.emitted('invoke')).toEqual([[
      {
        text: '理解函数模型并确定定义域',
        instruction: '改成可观察、可检查的学习行为',
        source: 'selection',
      },
    ]])
    expect(removeAllRanges).not.toHaveBeenCalled()
  })

  it('短选区不打断用户', async () => {
    const { host, range } = selectionFixture('函')
    vi.spyOn(window, 'getSelection').mockReturnValue({
      toString: () => '函',
      rangeCount: 1,
      getRangeAt: () => range,
    } as unknown as Selection)
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host },
    })

    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()

    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('悬停段落时提供同一个嵌入式修改入口', async () => {
    const { host } = selectionFixture('以真实任务理解函数模型')
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, label: 'AI 修改' },
    })

    host.querySelector('p')!.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()

    expect(wrapper.get('.text-selection-ai__trigger').text()).toContain('AI 修改')
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(host.querySelector('blockquote')?.textContent).toContain('以真实任务理解函数模型')
    expect(host.querySelector('.text-selection-ai__composer')?.textContent).toContain('修改当前段落')
  })

  it('把精确对象身份随请求发送，并把输入框追加在对象下方', async () => {
    const host = document.createElement('section')
    const section = document.createElement('section')
    section.dataset.aiSectionId = 'section-1'
    const inlineAnchor = document.createElement('div')
    inlineAnchor.dataset.aiInlineAnchor = 'true'
    const field = document.createElement('p')
    field.dataset.aiField = 'teacher_activity'
    field.dataset.aiItemId = 'module-1'
    field.dataset.aiLabel = '教师活动'
    field.textContent = '教师演示转换过程'
    inlineAnchor.appendChild(field)
    section.appendChild(inlineAnchor)
    host.appendChild(section)
    document.body.appendChild(host)
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
    host.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 400, width: 640, height: 400,
      toJSON: () => ({}),
    })
    field.getBoundingClientRect = () => ({
      x: 20, y: 40, left: 20, top: 40, right: 420, bottom: 80, width: 400, height: 40,
      toJSON: () => ({}),
    })
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: { container: host, targetSelector: '[data-ai-field]' },
    })

    field.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(inlineAnchor.nextElementSibling?.classList.contains('text-selection-ai-host')).toBe(true)
    expect(field.querySelector('.text-selection-ai-host')).toBeNull()
    expect(section.textContent).toContain('教师活动 · 修改当前段落')

    const textarea = section.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '增加学生预测'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    section.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await nextTick()

    expect(wrapper.emitted('invoke')).toEqual([[
      {
        text: '教师演示转换过程',
        instruction: '增加学生预测',
        source: 'block',
        target: {
          sectionNodeId: 'section-1',
          field: 'teacher_activity',
          itemId: 'module-1',
          label: '教师活动',
        },
      },
    ]])
  })

  it('三栏目标共用大容器右侧入口，进入选择模式后锁定当前栏', async () => {
    const host = document.createElement('section')
    const section = document.createElement('section')
    section.dataset.aiSectionId = 'section-1'
    const objectiveGrid = document.createElement('div')
    objectiveGrid.dataset.aiInlineAnchor = 'true'
    objectiveGrid.getBoundingClientRect = () => ({
      x: 20, y: 32, left: 20, top: 32, right: 600, bottom: 136, width: 580, height: 104,
      toJSON: () => ({}),
    })
    const fields = [
      ['knowledge_objectives', '知识目标', 20, 200],
      ['ability_objectives', '能力目标', 220, 400],
      ['education_objectives', '育人目标', 420, 600],
    ] as const
    for (const [fieldName, label, left, right] of fields) {
      const field = document.createElement('div')
      field.dataset.aiField = fieldName
      field.dataset.aiLabel = label
      field.textContent = `${label}内容`
      field.getBoundingClientRect = () => ({
        x: left, y: 40, left, top: 40, right, bottom: 120, width: right - left, height: 80,
        toJSON: () => ({}),
      })
      objectiveGrid.appendChild(field)
    }
    section.appendChild(objectiveGrid)
    host.appendChild(section)
    document.body.appendChild(host)
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
    host.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 400, width: 640, height: 400,
      toJSON: () => ({}),
    })
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: {
        container: host,
        targetSelector: '[data-ai-field]',
        groupSelector: '[data-ai-inline-anchor]',
        selectTargetLabel: '选择要修改的内容',
      },
    })

    const knowledgeField = objectiveGrid.children[0] as HTMLElement
    const abilityField = objectiveGrid.children[1] as HTMLElement
    knowledgeField.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()

    expect(wrapper.get('.text-selection-ai').attributes('style')).toContain('left: 600px')
    abilityField.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    expect(wrapper.get('.text-selection-ai').attributes('style')).toContain('left: 600px')

    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(wrapper.get('.text-selection-ai__trigger').text()).toContain('选择要修改的内容')
    expect(wrapper.get('.text-selection-ai__trigger').attributes('aria-pressed')).toBe('true')

    knowledgeField.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    expect(knowledgeField.classList.contains('text-selection-ai-target-preview')).toBe(true)
    knowledgeField.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    await nextTick()
    expect(knowledgeField.classList.contains('text-selection-ai-target-preview')).toBe(false)

    const textarea = section.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '改成可检查的知识目标'
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    section.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await nextTick()

    expect(wrapper.emitted('invoke')?.[0]?.[0]).toMatchObject({
      text: '知识目标内容',
      target: {
        sectionNodeId: 'section-1',
        field: 'knowledge_objectives',
        label: '知识目标',
      },
    })
  })

  it('整块选择模式可用 Esc 退出且不会打开修改框', async () => {
    const host = document.createElement('section')
    const group = document.createElement('div')
    group.dataset.aiInlineAnchor = 'true'
    group.getBoundingClientRect = () => ({
      x: 20, y: 40, left: 20, top: 40, right: 420, bottom: 140, width: 400, height: 100,
      toJSON: () => ({}),
    })
    const field = document.createElement('p')
    field.dataset.aiField = 'class_summary'
    field.textContent = '本讲总结'
    group.appendChild(field)
    host.appendChild(group)
    document.body.appendChild(host)
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
    host.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 400, width: 640, height: 400,
      toJSON: () => ({}),
    })
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: {
        container: host,
        targetSelector: '[data-ai-field]',
        groupSelector: '[data-ai-inline-anchor]',
      },
    })

    field.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()

    expect(wrapper.find('.text-selection-ai__trigger').exists()).toBe(false)
    expect(group.classList.contains('text-selection-ai-group-selecting')).toBe(false)
    expect(host.querySelector('.text-selection-ai__composer')).toBeNull()
  })

  it('手动划词会退出整块选择模式，并只保留选中文字', async () => {
    const host = document.createElement('section')
    const group = document.createElement('div')
    group.dataset.aiInlineAnchor = 'true'
    group.getBoundingClientRect = () => ({
      x: 20, y: 40, left: 20, top: 40, right: 420, bottom: 140, width: 400, height: 100,
      toJSON: () => ({}),
    })
    const field = document.createElement('p')
    field.dataset.aiField = 'teacher_activity'
    field.dataset.aiLabel = '教师活动'
    field.textContent = '教师先提问，再讲解四步流程'
    group.appendChild(field)
    host.appendChild(group)
    document.body.appendChild(host)
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 640 })
    host.getBoundingClientRect = () => ({
      x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 400, width: 640, height: 400,
      toJSON: () => ({}),
    })
    const range = {
      startContainer: field.firstChild,
      endContainer: field.firstChild,
      getBoundingClientRect: () => ({
        x: 64, y: 72, left: 64, top: 72, right: 152, bottom: 94, width: 88, height: 22,
        toJSON: () => ({}),
      }),
    } as unknown as Range
    const wrapper = mount(TextSelectionAiAction, {
      attachTo: host,
      props: {
        container: host,
        targetSelector: '[data-ai-field]',
        groupSelector: '[data-ai-inline-anchor]',
      },
    })

    field.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    vi.spyOn(window, 'getSelection').mockReturnValue({
      toString: () => '先提问',
      rangeCount: 1,
      getRangeAt: () => range,
      removeAllRanges: vi.fn(),
    } as unknown as Selection)
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()

    expect(group.classList.contains('text-selection-ai-group-selecting')).toBe(false)
    expect(wrapper.get('.text-selection-ai__trigger').text()).toContain('AI 修改')
    host.dispatchEvent(new Event('pointerleave'))
    await nextTick()
    field.dispatchEvent(new Event('pointerover', { bubbles: true }))
    await nextTick()
    await wrapper.get('.text-selection-ai__trigger').trigger('click')
    expect(host.querySelector('blockquote')?.textContent).toBe('先提问')
    expect(host.querySelector('.text-selection-ai__composer')?.textContent).toContain('教师活动 · 修改选中内容')
  })
})
