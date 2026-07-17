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
    knowledge_id: 'course-path:course-1',
    code: 'course-path:course-1',
    parent_id: null,
    node_type: 'course',
    name: '线性代数课程',
    description: '',
    depth: 0,
    sort_order: 0,
    path_ids: ['course-path:course-1'],
    path_names: ['线性代数课程'],
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
    mastery_criterion_ids: [],
    covered_by_course: true,
    source_status: 'course_path',
    status: 'active',
    revision_id: 'knr-math',
    ...overrides,
  }
}

const libraryView = {
  schema_version: 'knowledge_library_view_v3',
  asset_id: 'view-1',
  library_id: 'ckb-course-1',
  subject_id: 'course-1',
  library_version: 'ckbr-1',
  root_node_id: 'course-path:course-1',
  status: 'active',
  lifecycle_status: 'accepted',
  origin: 'course_and_domain_generated',
  binding_revision_id: 'ckbr-1',
  quality_report: {
    passed: true,
    score: 92,
    metrics: { mapped_ratio: 1, relation_coverage: 0.5 },
    issues: [],
    blocking_issues: [],
  },
  generation_audit: { invalid_relation_candidates: [], unresolved_relation_candidates: [], title_fallback_used: false },
  source_summary: { course_source: 2 },
  revision_id: 'viewr-1',
  course_map_revision_id: 'mapr-1',
  coverage: { formal_knowledge_count: 0, mapped_count: 2, unmapped_count: 0, mapped_ratio: 1, status: 'course_local' },
  unresolved_mappings: [],
  nodes: [
    node({ section_ids: ['L2-1-1'] }),
    node({
      knowledge_id: 'course-path:chapter:L1-1', parent_id: 'course-path:course-1', node_type: 'chapter', name: '向量基础', depth: 1,
      path_ids: ['course-path:course-1', 'course-path:chapter:L1-1'], path_names: ['线性代数课程', '向量基础'], section_ids: ['L1-1'],
    }),
    node({
      knowledge_id: 'course-path:section:L2-1-1', parent_id: 'course-path:chapter:L1-1', node_type: 'section', name: '线性组合与数域', depth: 2,
      path_ids: ['course-path:course-1', 'course-path:chapter:L1-1', 'course-path:section:L2-1-1'],
      path_names: ['线性代数课程', '向量基础', '线性组合与数域'], section_ids: ['L2-1-1'],
    }),
    node({
      knowledge_id: 'group-linear-combination', parent_id: 'course-path:section:L2-1-1', node_type: 'concept_group', name: '线性表示机制', depth: 3,
      path_ids: ['course-path:course-1', 'course-path:chapter:L1-1', 'course-path:section:L2-1-1', 'group-linear-combination'],
      path_names: ['线性代数课程', '向量基础', '线性组合与数域', '线性表示机制'], section_ids: ['L2-1-1'],
    }),
    node({
      knowledge_id: 'linear-combination-definition', parent_id: 'group-linear-combination', node_type: 'knowledge_point',
      name: '线性组合的形式定义', description: '有限个向量分别乘以标量后相加所得的向量。', statement: '有限个向量分别乘以标量后相加所得的向量称为这些向量的线性组合。', depth: 4,
      conditions: ['系数属于指定数域'], boundaries: ['向量必须属于同一向量空间'],
      path_ids: ['course-path:course-1', 'course-path:chapter:L1-1', 'course-path:section:L2-1-1', 'group-linear-combination', 'linear-combination-definition'],
      path_names: ['线性代数课程', '向量基础', '线性组合与数域', '线性表示机制', '线性组合的形式定义'],
      covered_by_course: true, section_ids: ['L2-1-1'], block_ids: ['block-1'],
      learning_actions: ['写出并解释线性组合'], question_ids: ['question-1'], criterion_ids: ['criterion-1'],
      misconception_ids: ['mis-1'], skill_unit_ids: ['skill-1'], mistake_point_ids: ['mistake-1'], mastery_criterion_ids: ['mastery-1'], improvement_ids: [],
    }),
    node({
      knowledge_id: 'coefficient-domain-boundary', parent_id: 'group-linear-combination', node_type: 'knowledge_point',
      name: '系数数域的约束', description: '线性组合中的系数必须来自当前向量空间的标量域。', depth: 4, sort_order: 1,
      path_ids: ['course-path:course-1', 'course-path:chapter:L1-1', 'course-path:section:L2-1-1', 'group-linear-combination', 'coefficient-domain-boundary'],
      path_names: ['线性代数课程', '向量基础', '线性组合与数域', '线性表示机制', '系数数域的约束'],
      covered_by_course: true, section_ids: ['L2-1-1'], learning_actions: ['判断系数是否属于指定数域'],
    }),
  ],
  relations: [{
    relation_id: 'relation-1', source_knowledge_id: 'coefficient-domain-boundary',
    target_knowledge_id: 'linear-combination-definition', relation_type: 'prerequisite',
    source_status: 'course_source', status: 'accepted',
    reason: '先确定允许使用的标量域，才能正确解释线性组合的形式定义', revision_id: 'relr-1',
  }],
  skill_units: [{
    skill_unit_id: 'skill-1', name: '识别线性组合', learning_goal: '判断向量是否可由给定向量组线性表示',
    primary_knowledge_id: 'linear-combination-definition', knowledge_ids: ['linear-combination-definition'],
  }],
  mistake_points: [{
    mistake_point_id: 'mistake-1', skill_unit_id: 'skill-1', name: '遗漏系数的数域',
    error_pattern: '默认系数可以来自任意集合', discrimination: '先确认向量空间的标量域',
    repair_strategy: '先确认系数所属数域', knowledge_ids: ['linear-combination-definition'],
  }],
  mastery_criteria: [{
    criterion_id: 'mastery-1', name: '线性组合定义掌握', observable_performance: '独立写出线性组合并说明系数数域',
    knowledge_ids: ['linear-combination-definition'], skill_ids: ['skill-1'], verification_method: '完成正反例辨析',
  }],
  improvement_points: [],
  usage_policy: {
    ai_must_judge_independently: true, allowed_fit: ['hit', 'partial', 'miss'], may_invent_formal_ids: false,
    identity_scope: 'course_only', personal_state_can_modify_library: false,
  },
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

describe('Course knowledge library', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    httpMock.get.mockResolvedValue(response())
    httpMock.post.mockResolvedValue({ data: { library: libraryView } })
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  it('只展示当前课程的路径结构与原子知识点', async () => {
    const { wrapper } = await mountLibrary()

    expect(httpMock.get).toHaveBeenCalledWith('/api/courses/course-1/learning-assets')
    expect(wrapper.text()).toContain('本课覆盖 2 / 2')
    expect(wrapper.text()).toContain('线性代数课程')
    expect(wrapper.text()).toContain('向量基础')
    expect(wrapper.text()).toContain('线性组合与数域')
    expect(wrapper.text()).toContain('线性表示机制')
    expect(wrapper.findAll('.knowledge-tree-scope button')).toHaveLength(1)
    expect(wrapper.get('.knowledge-tree-scope button').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(6)
    expect(wrapper.text()).toContain('线性组合的形式定义')
    expect(wrapper.text()).toContain('系数数域的约束')
  })

  it('知识详情汇合能力、练习、易错、掌握标准、关系理由和正文位置', async () => {
    const { wrapper, courseStore } = await mountLibrary()
    const scrollSpy = vi.spyOn(courseStore, 'scrollToNode')
    await wrapper.get('.knowledge-tree-row.is-knowledge_point .knowledge-tree-node').trigger('click')

    expect(wrapper.get('.knowledge-tree-detail h2').text()).toBe('线性组合的形式定义')
    expect(wrapper.text()).toContain('识别线性组合')
    expect(wrapper.text()).toContain('独立写出线性组合')
    expect(wrapper.text()).toContain('遗漏系数的数域')
    expect(wrapper.text()).toContain('完成正反例辨析')
    expect(wrapper.text()).toContain('先确定允许使用的标量域')
    expect(wrapper.findAll('.knowledge-tree-skill-group')).toHaveLength(1)
    expect(wrapper.get('.knowledge-tree-skill-group').text()).toContain('易错点')
    expect(wrapper.text()).toContain('掌握标准')
    expect(wrapper.text()).not.toContain('提升点')
    expect(wrapper.text()).toContain('回到对应正文')

    await wrapper.get('.knowledge-tree-detail-footer button').trigger('click')
    expect(courseStore.showKnowledgeLibrary).toBe(false)
    await new Promise(resolve => setTimeout(resolve, 170))
    expect(scrollSpy).toHaveBeenCalledWith('L2-1-1')
  })

  it('搜索原子知识时保留课程、章节、小节和概念组祖先路径', async () => {
    const { wrapper } = await mountLibrary()
    const input = wrapper.get('.knowledge-tree-search input')
    await input.setValue('系数数域')
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(5)
    expect(wrapper.get('.knowledge-tree-detail h2').text()).toBe('系数数域的约束')
    expect(wrapper.get('.knowledge-tree-breadcrumb').text()).toContain('线性代数课程')
    expect(wrapper.get('.knowledge-tree-breadcrumb').text()).toContain('线性表示机制')
  })

  it('英文模式呈现课程知识结构且不泄露翻译键', async () => {
    await setLocale('en')
    const { wrapper } = await mountLibrary()
    await wrapper.get('.knowledge-tree-row.is-knowledge_point .knowledge-tree-node').trigger('click')

    expect(wrapper.text()).toContain('Knowledge library')
    expect(wrapper.text()).toContain('Skills and misconceptions')
    expect(wrapper.text()).toContain('Mistake points')
    expect(wrapper.text()).toContain('Mastery criteria')
    expect(wrapper.text()).not.toContain('Improvement points')
    expect(wrapper.text()).not.toContain('knowledgeLibrary.')
  })

  it('展示课程知识库状态、质量摘要和课程来源', async () => {
    const { wrapper } = await mountLibrary()

    expect(wrapper.get('[data-testid="knowledge-lifecycle"]').text()).toContain('课程知识库')
    expect(wrapper.get('[data-testid="knowledge-quality"]').text()).toContain('92')
    expect(wrapper.get('[data-testid="knowledge-quality"]').text()).toContain('路径覆盖 100%')
    expect(wrapper.get('[data-testid="knowledge-source-summary"]').text()).toContain('当前课程知识库 2')
    expect(wrapper.find('[data-testid="knowledge-diff"]').exists()).toBe(false)
  })

  it('课程知识库只提供重新生成，不走学科库接受或退回链路', async () => {
    const { wrapper } = await mountLibrary()
    expect(wrapper.find('[data-testid="knowledge-review-note"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-accept"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-reject"]').exists()).toBe(false)

    await wrapper.get('[data-testid="knowledge-rebuild"]').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/courses/course-1/knowledge-library/rebuild', { force: true })
  })

  it('降级库不把章节索引伪装成知识点，并明确要求重建', async () => {
    const degraded = {
      ...libraryView,
      lifecycle_status: 'degraded',
      origin: 'course_index',
      status: 'unavailable',
      nodes: [],
      relations: [],
      skill_units: [],
      mistake_points: [],
      mastery_criteria: [],
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

    expect(wrapper.get('[data-testid="knowledge-lifecycle"]').text()).toContain('未通过质量门')
    expect(wrapper.find('[data-testid="knowledge-accept"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-reject"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="knowledge-rebuild"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="knowledge-quality-issues"]').text()).toContain('结构仍与章节一一对应')
    expect(wrapper.findAll('.knowledge-tree-row')).toHaveLength(0)
    expect(wrapper.text()).toContain('当前课程还没有通过质量门的知识库')
  })

  it('compacts technical quality failures and hides raw section identifiers', async () => {
    const rawSectionId = '01787b5b-f521-4a1a-97d0-e0755676fda9'
    const degraded = {
      ...libraryView,
      lifecycle_status: 'degraded',
      status: 'unavailable',
      nodes: [],
      coverage: {
        ...libraryView.coverage,
        section_count: 68,
        covered_section_count: 0,
      },
      quality_report: {
        ...libraryView.quality_report,
        passed: false,
        issues: [
          { code: 'knowledge_blueprint_missing', severity: 'critical', message: '知识库缺少有效的知识蓝图' },
          { code: 'missing_section_bindings', severity: 'critical', message: `知识库未覆盖小节：['${rawSectionId}']` },
          { code: 'invalid_concept_group_id', severity: 'critical', message: '概念组 ID 必须非空且唯一' },
          { code: 'invalid_knowledge_id', severity: 'critical', message: '知识点 ID 必须非空且唯一' },
          { code: 'invalid_skill_id', severity: 'critical', message: '能力点 ID 必须非空且唯一' },
        ],
      },
    }
    httpMock.get.mockResolvedValue({
      data: { ...response().data, assets: { ...response().data.assets, knowledge_library: [degraded] } },
    })

    const { wrapper } = await mountLibrary()
    const issueList = wrapper.get('[data-testid="knowledge-quality-issues"]')

    expect(issueList.findAll('li').length).toBeLessThanOrEqual(3)
    expect(issueList.text()).not.toContain(rawSectionId)
    expect(issueList.text()).toContain('68')
    expect(wrapper.find('[data-testid="knowledge-quality-toggle"]').exists()).toBe(true)
  })

  it('重新生成失败时显示后端结构化错误而不是对象字符串', async () => {
    const { wrapper } = await mountLibrary()
    httpMock.post.mockRejectedValueOnce({
      response: { data: { detail: { code: 'knowledge_quality_failed', message: '课程知识结构仍不完整，原版本保持不变', retryable: true } } },
    })

    await wrapper.get('[data-testid="knowledge-rebuild"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('.knowledge-tree-governance-error').text()).toContain('课程知识结构仍不完整')
    expect(wrapper.get('.knowledge-tree-governance-error').text()).not.toContain('[object Object]')
  })
})
