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
})
