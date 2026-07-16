import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeLibrary from '@/components/KnowledgeLibrary.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/utils/http', () => ({ default: httpMock }))
vi.mock('@/utils/logger', () => ({ default: { error: vi.fn() } }))

function node(overrides: Record<string, unknown>) {
  return {
    knowledge_id: 'math',
    code: 'MATH',
    parent_id: null,
    node_type: 'subject',
    name: '数学',
    description: '',
    depth: 0,
    sort_order: 0,
    path_ids: ['math'],
    path_names: ['数学'],
    aliases: [],
    learning_actions: [],
    typical_problems: [],
    section_ids: [],
    block_ids: [],
    objective_ids: [],
    criterion_ids: [],
    question_ids: [],
    misconception_ids: [],
    skill_unit_ids: [],
    mistake_point_ids: [],
    improvement_ids: [],
    covered_by_course: false,
    source_status: 'curated',
    status: 'active',
    revision_id: 'knr-math',
    ...overrides,
  }
}

const libraryView = {
  schema_version: 'knowledge_library_view_v3',
  asset_id: 'view-1',
  library_id: 'math.linear_algebra.v1',
  subject_id: 'math.linear_algebra',
  library_version: '1.0.0',
  root_node_id: 'math',
  status: 'active',
  lifecycle_status: 'candidate',
  origin: 'model_generated',
  binding_revision_id: 'sklr-1',
  quality_report: {
    passed: true,
    score: 92,
    metrics: { mapped_ratio: 1, relation_coverage: 0.75, cross_skill_ratio: 0.4 },
    issues: [],
    blocking_issues: [],
  },
  generation_audit: {
    generation_calls: 1,
    review_calls: 1,
    repair_calls: 0,
    sources: ['course_source', 'model_inferred'],
    provider_failure: null,
  },
  source_summary: { course_source: 4, model_inferred: 8 },
  revision_id: 'viewr-1',
  course_map_revision_id: 'mapr-1',
  coverage: { formal_knowledge_count: 1, mapped_count: 1, unmapped_count: 0, mapped_ratio: 1, status: 'mapped' },
  unresolved_mappings: [],
  nodes: [
    node({ covered_by_course: true, section_ids: ['L2-1-1'] }),
    node({
      knowledge_id: 'linear-algebra', parent_id: 'math', node_type: 'domain', name: '线性代数', depth: 1,
      path_ids: ['math', 'linear-algebra'], path_names: ['数学', '线性代数'], covered_by_course: true, section_ids: ['L2-1-1'],
    }),
    node({
      knowledge_id: 'vectors', parent_id: 'linear-algebra', node_type: 'topic', name: '向量、线性组合与张成', depth: 2,
      path_ids: ['math', 'linear-algebra', 'vectors'], path_names: ['数学', '线性代数', '向量、线性组合与张成'], covered_by_course: true, section_ids: ['L2-1-1'],
    }),
    node({
      knowledge_id: 'linear-combination', parent_id: 'vectors', node_type: 'concept', name: '线性组合', depth: 3,
      path_ids: ['math', 'linear-algebra', 'vectors', 'linear-combination'], path_names: ['数学', '线性代数', '向量、线性组合与张成', '线性组合'], covered_by_course: true, section_ids: ['L2-1-1'],
    }),
    node({
      knowledge_id: 'linear-combination-definition', parent_id: 'linear-combination', node_type: 'knowledge_point',
      name: '线性组合的形式定义', description: '有限个向量与标量系数构成的和。', depth: 4,
      path_ids: ['math', 'linear-algebra', 'vectors', 'linear-combination', 'linear-combination-definition'],
      path_names: ['数学', '线性代数', '向量、线性组合与张成', '线性组合', '线性组合的形式定义'],
      covered_by_course: true, section_ids: ['L2-1-1'], block_ids: ['block-1'],
      learning_actions: ['写出并解释线性组合'], question_ids: ['question-1'], criterion_ids: ['criterion-1'],
      misconception_ids: ['mis-1'], skill_unit_ids: ['skill-1'], mistake_point_ids: [], improvement_ids: [],
    }),
    node({
      knowledge_id: 'span', parent_id: 'vectors', node_type: 'concept', name: '张成空间与维数', depth: 3, sort_order: 1,
      path_ids: ['math', 'linear-algebra', 'vectors', 'span'], path_names: ['数学', '线性代数', '向量、线性组合与张成', '张成空间与维数'],
    }),
  ],
  relations: [],
  skill_units: [{
    skill_unit_id: 'skill-1', name: '识别线性组合', learning_goal: '判断向量是否可由给定向量组线性表示',
    primary_knowledge_id: 'linear-combination-definition', knowledge_ids: ['linear-combination-definition'],
  }],
  mistake_points: [{
    mistake_point_id: 'mistake-1', skill_unit_id: 'skill-1', name: '遗漏系数的数域',
    repair_strategy: '先确认系数所属数域', knowledge_ids: ['linear-combination-definition'],
  }],
  improvement_points: [{
    improvement_point_id: 'improve-1', skill_unit_id: 'skill-1', name: '从表示推进到方程化',
    practice_strategy: '把成员关系改写为线性方程组', knowledge_ids: ['linear-combination-definition'],
  }],
  usage_policy: { ai_must_judge_independently: true, allowed_fit: ['hit', 'partial', 'miss'], may_invent_formal_ids: false },
}

function response() {
  return {
    data: {
      assets: {
        knowledge_library: [libraryView],
        questions: [{ asset_id: 'question-1', question_id: 'question-1', prompt: '判断是否构成线性组合' }],
        mastery_criteria: [{ asset_id: 'criterion-1', criterion_id: 'criterion-1', observable_performance: '独立写出线性组合' }],
        misconceptions: [{ asset_id: 'mis-1', misconception_id: 'mis-1', error_pattern: '系数只能为正数', discrimination: '系数可以是任意标量' }],
      },
    },
  }
}

function reviewResponse() {
  return {
    data: {
      library: libraryView,
      previous_revision_id: 'sklr-0',
      diff: { added: 4, modified: 2, removed: 1 },
    },
  }
}

async function mountLibrary() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const courseStore = useCourseStore()
  courseStore.currentCourseId = 'course-1'
  const wrapper = mount(KnowledgeLibrary, {
    global: { plugins: [pinia], stubs: { Teleport: true, Transition: false } },
  })
  courseStore.showKnowledgeLibrary = true
  await flushPromises()
  return { wrapper, courseStore }
}

describe('Subject knowledge library', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    httpMock.get.mockImplementation((url: string) => (
      url.endsWith('/review') ? Promise.resolve(reviewResponse()) : Promise.resolve(response())
    ))
    httpMock.post.mockResolvedValue({ data: { library: libraryView } })
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  it('默认聚焦本课覆盖，并可切换到完整学科知识', async () => {
    const { wrapper } = await mountLibrary()

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/learning-assets')
    expect(wrapper.text()).toContain('本课覆盖 1 / 1')
    expect(wrapper.text()).not.toContain('第1章')
    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(5)

    await wrapper.get('.knowledge-tree-scope button:nth-child(2)').trigger('click')
    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(6)
    expect(wrapper.text()).toContain('张成空间与维数')
  })

  it('知识详情汇合能力、练习、易错、提升和正文位置', async () => {
    const { wrapper, courseStore } = await mountLibrary()
    const scrollSpy = vi.spyOn(courseStore, 'scrollToNode')
    await wrapper.get('.knowledge-tree-row.is-knowledge_point .knowledge-tree-node').trigger('click')

    expect(wrapper.get('.knowledge-tree-detail h2').text()).toBe('线性组合的形式定义')
    expect(wrapper.text()).toContain('识别线性组合')
    expect(wrapper.text()).toContain('独立写出线性组合')
    expect(wrapper.text()).toContain('遗漏系数的数域')
    expect(wrapper.text()).toContain('从表示推进到方程化')
    expect(wrapper.findAll('.knowledge-tree-skill-group')).toHaveLength(1)
    expect(wrapper.get('.knowledge-tree-skill-group').text()).toContain('易错点')
    expect(wrapper.get('.knowledge-tree-skill-group').text()).toContain('提升点')
    expect(wrapper.text()).toContain('回到对应正文')

    await wrapper.get('.knowledge-tree-detail-footer button').trigger('click')
    expect(courseStore.showKnowledgeLibrary).toBe(false)
    await new Promise(resolve => setTimeout(resolve, 170))
    expect(scrollSpy).toHaveBeenCalledWith('L2-1-1')
  })

  it('全部知识模式下搜索保留语义祖先路径', async () => {
    const { wrapper } = await mountLibrary()
    await wrapper.get('.knowledge-tree-scope button:nth-child(2)').trigger('click')
    const input = wrapper.get('.knowledge-tree-search input')
    await input.setValue('张成空间')
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(4)
    expect(wrapper.get('.knowledge-tree-detail h2').text()).toBe('张成空间与维数')
  })

  it('英文模式完整呈现统一父子结构且不泄露翻译键', async () => {
    await setLocale('en')
    const { wrapper } = await mountLibrary()
    await wrapper.get('.knowledge-tree-row.is-knowledge_point .knowledge-tree-node').trigger('click')

    expect(wrapper.text()).toContain('Knowledge library')
    expect(wrapper.text()).toContain('Skills, mistakes, and improvements')
    expect(wrapper.text()).toContain('Mistake points')
    expect(wrapper.text()).toContain('Improvement points')
    expect(wrapper.text()).not.toContain('knowledgeLibrary.')
  })

  it('展示候选状态、质量摘要和版本差异', async () => {
    const { wrapper } = await mountLibrary()

    expect(wrapper.get('[data-testid="knowledge-lifecycle"]').text()).toContain('候选知识库')
    expect(wrapper.get('[data-testid="knowledge-quality"]').text()).toContain('92')
    expect(wrapper.get('[data-testid="knowledge-quality"]').text()).toContain('映射率 100%')
    expect(wrapper.get('[data-testid="knowledge-source-summary"]').text()).toContain('课程来源 4')
    expect(wrapper.get('[data-testid="knowledge-source-summary"]').text()).toContain('模型推断 8')
    expect(wrapper.get('[data-testid="knowledge-diff"]').text()).toContain('新增 4')
    expect(wrapper.get('[data-testid="knowledge-diff"]').text()).toContain('修改 2')
    expect(wrapper.get('[data-testid="knowledge-diff"]').text()).toContain('删除 1')
  })

  it('可以接受、退回或重新生成整个候选版本', async () => {
    const { wrapper } = await mountLibrary()
    const note = wrapper.get('[data-testid="knowledge-review-note"]')
    await note.setValue('关系结构需要复核')

    await wrapper.get('[data-testid="knowledge-accept"]').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/course-1/knowledge-library/review', {
      revision_id: 'sklr-1', decision: 'accept', note: '关系结构需要复核',
    })

    await wrapper.get('[data-testid="knowledge-reject"]').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/course-1/knowledge-library/review', {
      revision_id: 'sklr-1', decision: 'reject', note: '关系结构需要复核',
    })

    await wrapper.get('[data-testid="knowledge-rebuild"]').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/course-1/knowledge-library/rebuild', { force: true })
  })

  it('降级库明确显示为课程索引且不提供审核晋升按钮', async () => {
    const degraded = {
      ...libraryView,
      lifecycle_status: 'degraded',
      origin: 'course_index',
      status: 'degraded',
      relations: [{
        relation_id: 'candidate-relation', source_knowledge_id: 'linear-combination-definition',
        target_knowledge_id: 'span', relation_type: 'related', source_status: 'model_inferred',
        status: 'candidate', reason: '候选关系', revision_id: 'rel-1',
      }],
      quality_report: {
        ...libraryView.quality_report,
        passed: false,
        score: 35,
        issues: [{ code: 'course_outline_mirror', severity: 'critical', message: '结构仍与章节一一对应' }],
        blocking_issues: [{ code: 'course_outline_mirror', severity: 'critical', message: '结构仍与章节一一对应' }],
      },
    }
    httpMock.get.mockResolvedValue({
      data: { ...response().data, assets: { ...response().data.assets, knowledge_library: [degraded] } },
    })

    const { wrapper } = await mountLibrary()

    expect(wrapper.get('[data-testid="knowledge-lifecycle"]').text()).toContain('课程索引')
    expect(wrapper.find('[data-testid="knowledge-accept"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-reject"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-rebuild"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="knowledge-quality-issues"]').text()).toContain('结构仍与章节一一对应')
    expect(wrapper.get('[data-testid="knowledge-candidate-relations"]').text()).toContain('1')
  })

  it('重新生成失败时显示后端结构化错误而不是对象字符串', async () => {
    const { wrapper } = await mountLibrary()
    httpMock.post.mockRejectedValueOnce({
      response: { data: { detail: { code: 'insufficient_quota', message: 'AI 服务额度不足，原版本保持不变', retryable: true } } },
    })

    await wrapper.get('[data-testid="knowledge-rebuild"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('.knowledge-tree-governance-error').text()).toContain('AI 服务额度不足')
    expect(wrapper.get('.knowledge-tree-governance-error').text()).not.toContain('[object Object]')
  })
})
