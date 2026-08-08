import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
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
  await wrapper.get('.knowledge-command-actions button.is-preview').trigger('click')
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
    expect(wrapper.get('button.is-preview').attributes('disabled')).toBeDefined()
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

describe('影响面明细与修订历史', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    httpMock.post.mockResolvedValue({ data: { candidate: candidate() } })
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  const detailPayload = {
    detail: {
      counts: { needs_regeneration: 1, stale: 2 },
      truncated: { needs_regeneration: false, stale: false },
      groups: {
        needs_regeneration: [{
          type: 'section_content', id: 'block-1', type_label: '正文块',
          title: '线性表与动态数组', location: '线性表与动态数组',
          excerpt: '根据长度与容量识别扩容触发时机。',
        }],
        stale: [
          { type: 'practice', id: 'q-1', type_label: '练习题', title: '判断是否触发扩容', location: '第一节', excerpt: '' },
          { type: 'slide_deck', id: 'deck-1', type_label: '课件', title: 'deck-1', location: '', excerpt: '' },
        ],
      },
    },
  }

  it('点开计数后展示具体对象的标题、位置和摘要', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    httpMock.post.mockResolvedValueOnce({ data: detailPayload })

    await wrapper.findAll('.knowledge-command-impact button')[0]!.trigger('click')
    await flushPromises()

    const url = httpMock.post.mock.calls[1]![0]
    expect(url).toBe('/api/courses/course-1/knowledge-library/points/impact-detail')
    const text = wrapper.get('.knowledge-command-detail').text()
    expect(text).toContain('正文块')
    expect(text).toContain('线性表与动态数组')
    expect(text).toContain('根据长度与容量识别扩容触发时机')
  })

  it('明细只在展开时才请求，预览阶段不拉取', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    // 预览之后只有 1 次请求：明细没有被顺带拉下来。
    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.knowledge-command-detail').exists()).toBe(false)
  })

  it('再次点击同一分组会收起', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)
    httpMock.post.mockResolvedValueOnce({ data: detailPayload })
    const button = wrapper.findAll('.knowledge-command-impact button')[0]!

    await button.trigger('click')
    await flushPromises()
    expect(wrapper.find('.knowledge-command-detail').exists()).toBe(true)

    await button.trigger('click')
    await flushPromises()
    expect(wrapper.find('.knowledge-command-detail').exists()).toBe(false)
  })

  it('修订历史按最近在前展示操作、作者和理由', async () => {
    const wrapper = await mountPanel()
    httpMock.get.mockResolvedValue({
      data: {
        revisions: [
          { command_id: 'c1', operation: 'revise_knowledge_point', actor: 'teacher-1', reason: '较早的修改' },
          { command_id: 'c2', operation: 'rename_knowledge_point', actor: 'teacher-2', reason: '最近的修改' },
        ],
      },
    })

    await wrapper.get('.knowledge-command-history > button').trigger('click')
    await flushPromises()

    expect(httpMock.get).toHaveBeenCalledWith(
      '/api/courses/course-1/knowledge-library/revisions',
      { silentError: true },
    )
    const items = wrapper.findAll('.knowledge-command-history-list li')
    expect(items).toHaveLength(2)
    // 倒序：最近的在最前。
    expect(items[0]!.text()).toContain('最近的修改')
    expect(items[0]!.text()).toContain('teacher-2')
    expect(items[1]!.text()).toContain('较早的修改')
  })

  it('没有修订记录时给出明确空状态', async () => {
    const wrapper = await mountPanel()
    httpMock.get.mockResolvedValue({ data: { revisions: [] } })

    await wrapper.get('.knowledge-command-history > button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('还没有知识修订记录')
  })
})

describe('下游重建入口', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  async function confirmed(wrapper: any) {
    await fillAndPreview(wrapper)
    await wrapper.get('.knowledge-command-candidate .is-primary').trigger('click')
    await flushPromises()
  }

  it('知识修订生效前不显示重建入口', async () => {
    httpMock.post.mockResolvedValue({ data: { candidate: candidate() } })
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    expect(wrapper.find('.knowledge-command-rebuild').exists()).toBe(false)
  })

  it('重建执行后逐对象展示回执，成功与仍待重建都说清楚', async () => {
    httpMock.post
      .mockResolvedValueOnce({ data: { candidate: candidate() } })
      .mockResolvedValueOnce({ data: { receipt: { command_id: 'c1' } } })
      .mockResolvedValueOnce({
        data: {
          rebuild: {
            status: 'executed',
            summary: { content_changed: 1, stale: 1 },
            receipts: [
              { type: 'slide_deck', id: 'deck-1', outcome: 'content_changed', detail: '' },
              { type: 'section_content', id: 'block-1', outcome: 'stale', detail: '正文暂无定向重建入口' },
            ],
            targets: [{ type: 'section_content', id: 'block-1', owner: 'course_content' }],
            counts: { targets: 2 },
          },
        },
      })
    const wrapper = await mountPanel()
    await confirmed(wrapper)

    await wrapper.get('.knowledge-command-rebuild button').trigger('click')
    await flushPromises()

    const [url, payload] = httpMock.post.mock.calls[2]!
    expect(url).toBe('/api/courses/course-1/knowledge-library/points/rebuild-downstream')
    // 重建针对已确认的修订，只需 request_id，不重发编辑内容。
    expect(payload).toHaveProperty('request_id')
    expect(payload).not.toHaveProperty('value')
    const text = wrapper.get('.knowledge-command-rebuild').text()
    expect(text).toContain('重建完成')
    expect(text).toContain('1 个已更新')
    expect(text).toContain('1 个仍待重建')
    // 逐对象回执可见，失败原因不被吞掉。
    expect(text).toContain('已更新')
    expect(text).toContain('正文暂无定向重建入口')
  })

  it('没有可重建对象时如实说明，不假装执行过', async () => {
    httpMock.post
      .mockResolvedValueOnce({ data: { candidate: candidate() } })
      .mockResolvedValueOnce({ data: { receipt: { command_id: 'c1' } } })
      .mockResolvedValueOnce({
        data: { rebuild: { status: 'nothing_to_rebuild', targets: [], counts: { targets: 0 } } },
      })
    const wrapper = await mountPanel()
    await confirmed(wrapper)

    await wrapper.get('.knowledge-command-rebuild button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.knowledge-command-rebuild').text()).toContain('没有需要重建')
  })
})

const readPanelSource = () => readFileSync(
  resolve(process.cwd(), 'src/components/KnowledgeCommandPanel.vue'), 'utf-8',
)

describe('移动端与无障碍', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    httpMock.post.mockResolvedValue({ data: { candidate: candidate() } })
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  it('窄视口下影响面计数堆叠为整行，避免三列挤在一起', () => {
    const source = readPanelSource()
    const media = source.slice(source.indexOf('@media (max-width: 720px)'))
    expect(media).toContain('.knowledge-command-impact li { flex:1 1 100%; }')
    // 媒体查询必须在所有基础规则之后，否则会被同优先级规则覆盖。
    expect(source.indexOf('@media (max-width: 720px)')).toBeGreaterThan(
      source.indexOf('.knowledge-command-impact button'),
    )
  })

  it('可点开的计数是真正的 button，键盘和读屏可达', async () => {
    const wrapper = await mountPanel()
    await fillAndPreview(wrapper)

    const buttons = wrapper.findAll('.knowledge-command-impact button')
    expect(buttons).toHaveLength(3)
    for (const button of buttons) {
      expect(button.element.tagName).toBe('BUTTON')
      expect(button.attributes('type')).toBe('button')
    }
  })

  it('触摸目标不小于 30px，窄屏可点中', () => {
    const source = readPanelSource()
    for (const selector of [
      '.knowledge-command-impact button',
      '.knowledge-command-rebuild > button',
      '.knowledge-command-history > button',
    ]) {
      const rule = source.slice(source.indexOf(selector))
      const match = rule.match(/min-height:(\d+)px/)
      expect(match, `${selector} 缺少 min-height`).toBeTruthy()
      expect(Number(match![1])).toBeGreaterThanOrEqual(30)
    }
  })
})

describe('AI 拆分建议', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => (String(input).includes('/en/') ? enMessages : zhMessages),
    })))
    await setLocale('zh')
  })

  const splitButton = (wrapper: any) => wrapper.get('button.is-propose')

  it('AI 建议拆分时进入同一个候选区，仍需教师确认', async () => {
    httpMock.post.mockResolvedValueOnce({
      data: {
        proposal: {
          should_split: true,
          reason: '包含判定条件与扩容动作两个独立命题',
          parts: [
            { knowledge_id: 'ckp_a', name: '容量耗尽的判定条件', statement: '元素数量等于容量即为容量耗尽。' },
            { knowledge_id: 'ckp_b', name: '扩容前置检查', statement: '插入前必须确认是否已达容量上限。' },
          ],
        },
        candidate: candidate({ operation: 'split_knowledge_point' }),
      },
    })
    const wrapper = await mountPanel()

    await splitButton(wrapper).trigger('click')
    await flushPromises()

    expect(httpMock.post.mock.calls[0]![0])
      .toBe('/api/courses/course-1/knowledge-library/points/propose-split')
    // 只传知识点 ID，不由前端决定拆成什么。
    expect(httpMock.post.mock.calls[0]![1]).toEqual({ knowledge_id: 'ckp_capacity' })
    const text = wrapper.text()
    expect(text).toContain('两个独立命题')
    expect(text).toContain('容量耗尽的判定条件')
    // 关键：AI 的建议同样落进候选区，没有自动应用。
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(true)
    expect(wrapper.emitted('applied')).toBeUndefined()
  })

  it('AI 判断无需拆分时如实告知，不产出候选', async () => {
    httpMock.post.mockResolvedValueOnce({
      data: { proposal: { should_split: false, reason: '只表达一个命题' }, candidate: null },
    })
    const wrapper = await mountPanel()

    await splitButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('只表达一个命题')
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(false)
  })

  it('AI 提了拆分但未过质量门时说明原因', async () => {
    httpMock.post.mockResolvedValueOnce({
      data: {
        proposal: { should_split: true, reason: 'x', rejected_reason: 'too_few_valid_parts', parts: [] },
        candidate: null,
      },
    })
    const wrapper = await mountPanel()

    await splitButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('未通过质量门')
    expect(wrapper.find('.knowledge-command-candidate').exists()).toBe(false)
  })
})
