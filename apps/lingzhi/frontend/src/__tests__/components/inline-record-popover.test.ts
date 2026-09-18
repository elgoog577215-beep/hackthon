import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InlineRecordPopover from '@/components/InlineRecordPopover.vue'
import type { Note } from '@/stores/types'

const note: Note = {
  id: 'note-1',
  nodeId: 'node-1',
  highlightId: 'highlight-1',
  quote: '线性相关',
  content: '这里需要再看一次定义。',
  color: '#fef3c7',
  createdAt: Date.now(),
  sourceType: 'user',
  recordType: 'note',
  status: 'active',
}

describe('InlineRecordPopover', () => {
  it('新建记录保存后提供无需二次确认的立即撤销入口', async () => {
    const wrapper = mount(InlineRecordPopover, {
      props: {
        visible: true,
        note,
        x: 120,
        y: 180,
        interactive: true,
        initialEdit: true,
        saveState: 'saved',
      },
      global: { stubs: { Teleport: true, Transition: false } },
    })

    const undo = wrapper.findAll('footer button').find(button => button.text().includes('撤销'))
    expect(undo).toBeTruthy()
    await undo!.trigger('click')
    expect(wrapper.emitted('undo')?.[0]).toEqual([note])
  })
  it('关闭或切换记录前保存最后输入，保存仍绑定原笔记', async () => {
    const wrapper = mount(InlineRecordPopover, {
      props: { visible: true, note: { ...note }, x: 120, y: 180, interactive: true },
      global: { stubs: { Teleport: true, Transition: false } },
    })
    await wrapper.get('textarea').setValue('刚写下的想法')
    await wrapper.setProps({ note: { ...note, id: 'note-2', content: '第二条' } })
    expect(wrapper.emitted('save')?.[0]).toEqual([{ note: expect.objectContaining({ id: 'note-1' }), content: '刚写下的想法' }])
    await wrapper.get('textarea').setValue('第二条最后输入')
    await wrapper.get('header button').trigger('click')
    expect(wrapper.emitted('save')?.[1]).toEqual([{ note: expect.objectContaining({ id: 'note-2' }), content: '第二条最后输入' }])
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('取消待保存内容后卸载不会再次发出保存', async () => {
    const wrapper = mount(InlineRecordPopover, {
      props: { visible: true, note: { ...note }, x: 120, y: 180, interactive: true },
      global: { stubs: { Teleport: true, Transition: false } },
    })
    await wrapper.get('textarea').setValue('即将删除的草稿')
    ;(wrapper.vm as unknown as { cancelSave: () => void }).cancelSave()
    wrapper.unmount()
    expect(wrapper.emitted('save')).toBeUndefined()
  })
  it('问 AI 使用最后输入的内容并立即保存', async () => {
    const wrapper = mount(InlineRecordPopover, {
      props: { visible: true, note: { ...note, quote: '' }, x: 120, y: 180, interactive: true },
      global: { stubs: { Teleport: true, Transition: false } },
    })
    await wrapper.get('textarea').setValue('最后输入的问题')
    await wrapper.findAll('footer button')[0]!.trigger('click')
    expect(wrapper.emitted('askAi')?.[0]).toEqual([expect.objectContaining({ content: '最后输入的问题' })])
    expect(wrapper.emitted('save')).toHaveLength(1)
    wrapper.unmount()
  })

  it('已有笔记允许清空正文，历史笔记仍可编辑', async () => {
    const wrapper = mount(InlineRecordPopover, {
      props: { visible: true, note: { ...note, revision: 1, recordType: undefined }, x: 120, y: 180, interactive: true },
      global: { stubs: { Teleport: true, Transition: false } },
    })
    await wrapper.get('textarea').setValue('')
    await wrapper.get('header button').trigger('click')
    expect(wrapper.emitted('save')?.[0]).toEqual([{ note: expect.objectContaining({ id: 'note-1' }), content: '' }])
    wrapper.unmount()
  })

})
