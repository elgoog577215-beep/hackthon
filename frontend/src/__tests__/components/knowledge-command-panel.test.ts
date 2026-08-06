import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeCommandPanel from '@/components/KnowledgeCommandPanel.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/utils/http', () => ({ default: httpMock }))
vi.mock('@/utils/logger', () => ({ default: { error: vi.fn() } }))

interface PanelPoint {
  knowledge_id: string
  name: string
  statement?: string
}

const POINT: PanelPoint = {
  knowledge_id: 'ckp_capacity',
  name: '容量耗尽判定',
  statement: '当元素数量等于当前容量时，下一次插入必须先扩容。',
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    candidate_id: 'ckc_1',
    operation: 'revise_knowledge_point',
    confirmable: true,
    blocking_issues: [],
    impact_report: {
      needs_regeneration: [{ type: 'section_content', id: 'block-1' }],
      stale: [
        { type: 'section_content', id: 'block-2' },
        { type: 'practice', id: 'q-1' },
      ],
      blocked: [],
      dependent_knowledge_ids: ['ckp_grow'],
    },
    ...overrides,
  }
}

async function mountPanel(point: PanelPoint | null = POINT) {
  const wrapper = mount(KnowledgeCommandPanel, {
    props: { courseId: 'course-1', point },
  })
  await flushPromises()
  return wrapper
}

async function fillAndPreview(wrapper: any, reason = '补充扩容触发条件的精确表述') {
  await wrapper.findAll('textarea')[1]!.setValue(reason)
  await wrapper.get('.knowledge-command-actions button').trigger('click')
  await flushPromises()
}

describe('知识维护面板', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    httpMock.post.mockResolvedValue({ data: { candidate: candidate() } })
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  it('未选中知识点时提示先选择，不展示表单', async () => {
    const wrapper = await mountPanel(null)

    expect(wrapper.text()).toContain('选择一个知识点后可发起维护')
    expect(wrapper.findAll('textarea')).toHaveLength(0)
  })

  it('选中知识点后用当前陈述预填，缺理由时不能预览', async () => {
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('容量耗尽判定')
    expect((wrapper.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe(
      POINT.statement,
    )
    // 没写理由 -> 预览按钮禁用。理由是审阅的前提，不能省。
    expect(wrapper.get('.knowledge-command-actions button').attributes('disabled')).toBeDefined()
  })

  it('预览调用定向编辑接口，只发送编辑描述而不是整个知识库', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    const [url, body] = httpMock.post.mock.calls[0]!
    expect(url).toBe('/api/courses/course-1/knowledge-library/points/preview-edit')
    expect(body).toMatchObject({
      knowledge_id: 'ckp_capacity',
      operation: 'revise_knowledge_point',
      reason: '补充扩容触发条件的精确表述',
    })
    // 关键：请求里不得出现整份知识库负载。
    expect(body).not.toHaveProperty('proposed_knowledge_base')
  })

  it('预览后展示影响面并明确说明尚未生效', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    expect(wrapper.text()).toContain('待确认候选')
    expect(wrapper.text()).toContain('当前知识库尚未改变，确认后才会生效。')
    const impact = wrapper.findAll('.knowledge-command-impact strong').map(n => n.text())
    expect(impact).toEqual(['1', '2', '0'])
    expect(wrapper.text()).toContain('经知识关系受影响的知识点')
  })

  it('确认前不会发出写入请求，确认后才调用 confirm-edit', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    // 预览之后仍然只有一次请求：候选没有被自动应用。
    expect(httpMock.post).toHaveBeenCalledTimes(1)

    const confirmButton = wrapper.get('.knowledge-command-candidate .is-primary')
    await confirmButton.trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledTimes(2)
    const [url, body] = httpMock.post.mock.calls[1]!
    expect(url).toBe('/api/courses/course-1/knowledge-library/points/confirm-edit')
    expect(body.command_id).toBe('kc-ckc_1')
    expect(body.knowledge_id).toBe('ckp_capacity')
    expect(wrapper.emitted('applied')).toHaveLength(1)
    expect(wrapper.text()).toContain('知识修订已生效')
  })

  it('不可确认的候选禁用确认按钮并展示阻断原因', async () => {
    httpMock.post.mockResolvedValue({
      data: {
        candidate: candidate({
          confirmable: false,
          blocking_issues: [{ message: '知识点缺少条件或边界' }],
        }),
      },
    })
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    expect(wrapper.text()).toContain('不可确认')
    expect(wrapper.get('.knowledge-command-candidate .is-primary').attributes('disabled'))
      .toBeDefined()
    expect(wrapper.text()).toContain('知识点缺少条件或边界')
  })

  it('放弃候选后回到未预览状态，不发出任何写入', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    const buttons = wrapper.findAll('.knowledge-command-candidate button')
    await buttons[buttons.length - 1]!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(false)
    expect(httpMock.post).toHaveBeenCalledTimes(1)
  })

  it('确认失败时说明知识库保持原修订', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    httpMock.post.mockRejectedValueOnce({
      response: { data: { detail: { message: '知识库在确认前已发生变化，请刷新后重试' } } },
    })

    await wrapper.get('.knowledge-command-candidate .is-primary').trigger('click')
    await flushPromises()

    expect(wrapper.get('.knowledge-command-error').text()).toContain('知识库在确认前已发生变化')
    expect(wrapper.emitted('applied')).toBeUndefined()
  })

  it('切换到重命名时改用名称字段并重置候选', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(true)

    await wrapper.get('select').setValue('rename_knowledge_point')
    await flushPromises()

    expect(wrapper.text()).toContain('新名称')
    expect((wrapper.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe(POINT.name)
    // 操作变了，旧候选必须失效，否则确认会应用到另一种语义上。
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(false)
  })

  it('英文模式下文案全部走 i18n，无中文残留', async () => {
    await setLocale('en')
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper, 'Sharpen the trigger condition')

    const text = wrapper.text()
    expect(text).toContain('Knowledge maintenance')
    expect(text).toContain('Candidate awaiting confirmation')
    expect(text).toContain('The knowledge base has not changed yet')
    expect(text).toContain('Confirm and apply')
    // 知识点名称本身是课程内容，可以是中文；界面文案不得有中文残留。
    const chrome = text.replace(POINT.name, '').replace(POINT.statement ?? '', '')
    expect(chrome).not.toMatch(/[一-鿿]/)
    await setLocale('zh')
  })
})

describe('确认遇到基线前移时的重定位', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  function staleError() {
    return {
      response: { data: { detail: { code: 'knowledge_base_revision_changed', message: '知识库已变化' } } },
    }
  }

  it('无关改动导致过期时自动重定位并要求再次确认，不作废教师的工作', async () => {
    httpMock.post
      .mockResolvedValueOnce({ data: { candidate: candidate({ base_knowledge_revision_id: 'ckbr_old' }) } })
      .mockRejectedValueOnce(staleError())
      .mockResolvedValueOnce({
        data: {
          relocation: {
            outcome: 'relocated',
            candidate: candidate({ candidate_id: 'ckc_2', base_knowledge_revision_id: 'ckbr_new' }),
          },
        },
      })
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    await wrapper.get('.knowledge-command-candidate .is-primary').trigger('click')
    await flushPromises()

    const [url, body] = httpMock.post.mock.calls[2]!
    expect(url).toBe('/api/courses/course-1/knowledge-library/points/relocate-edit')
    expect(body.base_knowledge_revision_id).toBe('ckbr_old')
    // 候选换成重算后的那个，仍在待确认状态（不是自动应用）。
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(true)
    expect(wrapper.text()).toContain('请再次确认')
    expect(wrapper.emitted('applied')).toBeUndefined()
  })

  it('冲突时清掉候选并说明原因，不假装还能确认', async () => {
    httpMock.post
      .mockResolvedValueOnce({ data: { candidate: candidate({ base_knowledge_revision_id: 'ckbr_old' }) } })
      .mockRejectedValueOnce(staleError())
      .mockResolvedValueOnce({
        data: {
          relocation: {
            outcome: 'conflict',
            reason: 'target_field_changed',
            message: '候选要修改的字段已被他人改动',
            candidate: null,
          },
        },
      })
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    await wrapper.get('.knowledge-command-candidate .is-primary').trigger('click')
    await flushPromises()

    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(false)
    expect(wrapper.get('.knowledge-command-error').text()).toContain('已被他人改动')
    expect(wrapper.emitted('applied')).toBeUndefined()
  })

  it('非过期类失败不触发重定位', async () => {
    httpMock.post
      .mockResolvedValueOnce({ data: { candidate: candidate() } })
      .mockRejectedValueOnce({ response: { data: { detail: { code: 'knowledge_candidate_not_confirmable', message: '未通过质量门' } } } })
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    await wrapper.get('.knowledge-command-candidate .is-primary').trigger('click')
    await flushPromises()

    // 只有 preview + confirm 两次请求，没有第三次重定位。
    expect(httpMock.post).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.knowledge-command-error').text()).toContain('未通过质量门')
  })
})
