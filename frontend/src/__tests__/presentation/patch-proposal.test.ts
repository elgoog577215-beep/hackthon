import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PresentationPatchProposal from '@/components/presentation/PresentationPatchProposal.vue'
import type { PresentationProposal } from '@/types/presentation'

const proposal: PresentationProposal = {
  proposal_id: 'proposal-1',
  request_id: 'request-1',
  deck_id: 'deck-1',
  base_revision_id: 'rev-1',
  scope: 'slide',
  slide_ids: ['slide-4'],
  prompt: '补一个例子',
  patches: [{
    slide_id: 'slide-4',
    changes: {
      blocks: [
        { block_id: 'existing', type: 'callout', title: '课程要点', content: '指针保存地址。', items: [], metadata: {} },
        { block_id: 'new', type: 'callout', title: '补充例子', content: '用门牌号解释地址。', items: [], metadata: {} },
      ],
    },
  }],
  summary: '建议修改 1 页；课程来源锚点保持不变。',
  risks: [],
  status: 'proposed',
  created_at: '2026-07-15T00:00:00Z',
}

describe('PresentationPatchProposal', () => {
  it('把结构化页面 patch 摘要成人类可读对比，不泄露内部字段', () => {
    const wrapper = mount(PresentationPatchProposal, { props: { proposal } })
    const text = wrapper.text()
    expect(text).toContain('课程要点：指针保存地址。')
    expect(text).toContain('补充例子：用门牌号解释地址。')
    expect(text).not.toContain('block_id')
    expect(text).not.toContain('metadata')
  })
})
