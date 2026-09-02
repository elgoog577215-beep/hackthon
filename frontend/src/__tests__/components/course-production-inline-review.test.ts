import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationGate from '@/components/CourseGenerationGate.vue'
import CourseOutlineReview from '@/components/CourseOutlineReview.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useGenerationStore } from '@/stores/generation'
import type { Task } from '@/stores/types'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

describe('课程生产内联确认', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => zhMessages,
    })))
    await setLocale('zh')
  })

  it('在课程工作区原位编辑、保存并确认目录', async () => {
    const workspace = useCourseWorkspaceStore()
    const generation = useGenerationStore()
    const course = useCourseStore()
    const draft = {
      base_blueprint_revision_id: 'bp-1',
      course_name: '线性代数',
      course_purpose: 'systematic',
      course_blueprint: {},
      learning_asset_plan: {},
      blueprint_locks: {},
      nodes: [
        {
          node_id: 'n1',
          parent_node_id: '',
          node_level: 2,
          node_name: '向量空间',
          learning_objective: '理解向量空间',
        },
      ],
    }
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({ current: draft } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({
      draft: payload,
    }) as any)
    const confirm = vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({} as any)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(course, 'refreshCourseData').mockResolvedValue(undefined)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'c1',
        courseName: '线性代数',
        task: {
          id: 'job-1',
          courseId: 'c1',
          courseName: '线性代数',
          status: 'waiting_for_review',
          progress: 28,
          currentStep: 'outline',
          logs: [],
          shouldStop: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('.generation-outline-dialog').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('目录节点')
    expect(wrapper.find('.outline-review__header').exists()).toBe(false)
    expect(wrapper.find('.outline-review__course-name').exists()).toBe(false)
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('线性代数')

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    editor.get('h2').element.textContent = '向量与空间'
    await editor.trigger('input')
    const buttons = wrapper.findAll('.outline-review__actions button')
    expect(buttons[0]!.attributes('disabled')).toBeUndefined()
    await buttons[0]!.trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('c1', expect.objectContaining({
      nodes: [expect.objectContaining({ node_name: '向量与空间' })],
    }))

    await buttons[1]!.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('c1', 'outline')
    expect(wrapper.emitted('confirmed')).toHaveLength(1)
  })

  it('按父子关系展示结构，单小节自动折叠且不破坏真实节点', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-grouped',
        course_name: '结构化课程',
        nodes: [
          { node_id: 'chapter-1', parent_node_id: 'root', node_level: 1, node_name: '第一章 基础' },
          { node_id: 'chapter-2', parent_node_id: 'root', node_level: 1, node_name: '第二章 进阶' },
          { node_id: 'section-1', parent_node_id: 'chapter-1', node_level: 2, node_name: '1.1 概念' },
          { node_id: 'section-2', parent_node_id: 'chapter-2', node_level: 2, node_name: '2.1 实践' },
        ],
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-grouped', courseName: '结构化课程' },
    })
    await flushPromises()

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    expect(editor.findAll('h2').map(heading => heading.text())).toEqual(['第一章 基础', '第二章 进阶'])
    const sections = editor.findAll('h3')
    expect(sections.map(heading => heading.text())).toEqual(['1.1 概念', '2.1 实践'])
    expect(sections.every(heading => heading.attributes('data-collapsed-single-section') === 'true')).toBe(true)
    expect(sections.every(heading => heading.attributes('aria-hidden') === 'true')).toBe(true)
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).not.toContain('小节2')
    expect(wrapper.text()).not.toContain('快速定位')
  })

  it('同章有多个小节时保留可见的小节层级', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-multi-section',
        course_name: '结构化课程',
        nodes: [
          { node_id: 'chapter-1', parent_node_id: 'root', node_level: 1, node_name: '第一章 基础' },
          { node_id: 'section-1', parent_node_id: 'chapter-1', node_level: 2, node_name: '1.1 概念' },
          { node_id: 'section-2', parent_node_id: 'chapter-1', node_level: 2, node_name: '1.2 方法' },
        ],
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-multi-section', courseName: '结构化课程' },
    })
    await flushPromises()

    const sections = wrapper.get('[data-testid="outline-rich-editor"]').findAll('h3')
    expect(sections).toHaveLength(2)
    expect(sections.every(heading => heading.attributes('data-collapsed-single-section') === undefined)).toBe(true)
    expect(wrapper.get('[data-testid="formal-outline-document"]').text()).toContain('小节2')
  })

  it('秋学期十六讲按八个教学周自动排课且不编造学时', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-short-term',
        course_name: 'C 语言程序设计',
        authoring_structure_version: 'lecture_v1',
        course_generation_brief: {
          formal_course_profile: {
            active_week_start: 1,
            active_week_end: 16,
            schedule_slots: [],
          },
          teacher_course_brief: {
            academic_term: '2026-2027 秋季学期',
            lecture_count: 16,
          },
        },
        nodes: Array.from({ length: 16 }, (_, index) => ({
          node_id: `lecture-${index + 1}`,
          parent_node_id: '',
          node_level: 2,
          node_name: `第${index + 1}讲 主题${index + 1}`,
          learning_objective: `完成第${index + 1}讲学习`,
        })),
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-short-term', courseName: 'C 语言程序设计' },
    })
    await flushPromises()

    const calendar = wrapper.findAll('.formal-outline__attachments table')[0]!
    const rows = calendar.findAll('tbody tr')
    expect(rows).toHaveLength(16)
    expect(rows.map(row => row.findAll('td')[0]!.text())).toEqual([
      '第1周', '第1周', '第2周', '第2周', '第3周', '第3周', '第4周', '第4周',
      '第5周', '第5周', '第6周', '第6周', '第7周', '第7周', '第8周', '第8周',
    ])
    expect(rows.every(row => row.findAll('td')[6]!.text() === '待确认')).toBe(true)
    expect(wrapper.get('.formal-outline__attachment-heading').text()).toContain('8 个教学周')
  })

  it('教学日历从讲授实践在线分解中汇总正式学时', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-hour-breakdown',
        course_name: '课程设计',
        authoring_structure_version: 'lecture_v1',
        nodes: [{
          node_id: 'lecture-1',
          parent_node_id: '',
          node_level: 2,
          node_name: '第1讲 真实项目启动',
          learning_objective: '能完成项目问题定义',
          hour_breakdown: {
            classroom_lecture: 1,
            classroom_practice: 1,
            online_instruction: 0.5,
          },
        }],
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-hour-breakdown', courseName: '课程设计' },
    })
    await flushPromises()

    const calendar = wrapper.findAll('.formal-outline__attachments table')[0]!
    expect(calendar.get('tbody tr').findAll('td')[6]!.text()).toBe('2.5')
  })

  it('shows source-backed outline changes and retrieval failure without hiding the local blueprint', async () => {
    const workspace = useCourseWorkspaceStore()
    const draft = {
      base_blueprint_revision_id: 'bp-web',
      course_name: 'Current web standards',
      nodes: [{
        node_id: 'n1', parent_node_id: '', node_level: 2,
        node_name: 'Current baseline', learning_objective: 'Verify the current baseline',
      }],
    }
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      draft,
      retrieval: {
        status: 'waiting_for_confirmation',
        proposal: {
          reason: 'A current standard adds a required verification step.',
          retrieval_package_revision: 3,
          diff: {
            before: { chapter_count: 1, section_count: 1 },
            after: { chapter_count: 1, section_count: 2 },
            added: [{ node_id: 'n2', node_name: 'Verification', new_position: '2' }],
          },
          sources: [{
            source_id: 'src-1', title: 'Official standard',
            url: 'https://standards.example.edu/current', domain: 'standards.example.edu',
            trust_tier: 'tier_a', published_date: '2026-08-01',
          }],
        },
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-web', courseName: 'Current web standards' },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="retrieval-outline-proposal"]').text()).toContain('A current standard adds a required verification step.')
    expect(wrapper.get('[data-testid="retrieval-outline-proposal"]').text()).toContain('Verification')
    expect(wrapper.get('.outline-retrieval__source').attributes('href')).toBe('https://standards.example.edu/current')

    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValueOnce({
      current: draft,
      retrieval: {
        status: 'failed',
        notice: '联网核验未完成，可重试或离线继续',
        package: {
          rejected_sources: Array.from({ length: 20 }, (_, index) => ({
            source_id: `rejected-${index}`,
            trust_tier: 'tier_c',
            rejection_reasons: ['low_relevance'],
          })),
          receipt: {
            error_codes: ['no_sources'],
            source_count: 0,
            admitted_count: 0,
            tier_distribution: { tier_c: 20 },
          },
        },
      },
    } as any)
    await (wrapper.vm as any).loadBlueprint()
    await flushPromises()
    expect(wrapper.get('[data-testid="retrieval-outline-notice"]').text()).toContain('联网核验未完成')
    expect(wrapper.get('[data-testid="retrieval-outline-notice"]').text()).toContain(
      zhMessages.courseGeneration.retrieval.errors.no_sources,
    )
    expect(wrapper.get('[data-testid="retrieval-outline-notice"]').text()).toContain('20')
    expect(wrapper.get('[data-testid="retrieval-outline-notice"]').text()).toContain('0')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').findAll('h2')).toHaveLength(1)
  })

  it('发布确认显示必要就绪信息并占据工作区底栏', async () => {
    const workspace = useCourseWorkspaceStore()
    const generation = useGenerationStore()
    const course = useCourseStore()
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      can_confirm: true,
      artifact: {
        publication_allowed: true,
        blocking_issues: [],
        source_chain: { can_publish: true, issues: [] },
      },
    } as any)
    const confirm = vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({} as any)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(course, 'refreshCourseData').mockResolvedValue(undefined)
    const task: Task = {
      id: 'job-2',
      courseId: 'c1',
      courseName: '线性代数',
      status: 'waiting_for_review',
      progress: 98,
      currentStep: 'release',
      completedNodes: 4,
      totalNodes: 4,
      logs: [],
      shouldStop: false,
      guidedWorkflow: {
        schema_version: 'guided_course_generation_v2',
        current_step: 'release',
        review_step: 'release',
        steps: [
          { number: 1, key: 'requirements', status: 'confirmed' },
          { number: 2, key: 'outline', status: 'confirmed' },
          { number: 3, key: 'content', status: 'confirmed' },
          { number: 4, key: 'release', status: 'waiting_for_confirmation' },
        ],
      },
    }

    const wrapper = mount(CourseGenerationGate, {
      props: { courseId: 'c1', task },
    })
    await flushPromises()

    expect(wrapper.find('.generation-outline-dialog').exists()).toBe(false)
    expect(wrapper.text()).toContain('正文 4/4 · 阻断项 0')
    await wrapper.get('.generation-gate > button').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('c1', 'release')
    expect(wrapper.emitted('confirmed')).toEqual([['release']])
  })

  it('发布门的阻断项计数与任务中心的列表一致，重复来源只算一次', async () => {
    // blocking_issues and source_chain.issues routinely report the same blocker.
    // The gate used to count both, so it showed "阻断项 3" above a list of 2.
    const workspace = useCourseWorkspaceStore()
    const generation = useGenerationStore()
    const course = useCourseStore()
    const duplicated = {
      code: 'source_missing',
      message: '缺少来源绑定',
      target_id: 'L2-1-1',
      severity: 'blocker',
    }
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      can_confirm: false,
      artifact: {
        publication_allowed: false,
        blocking_issues: [duplicated],
        source_chain: {
          can_publish: false,
          issues: [duplicated, { ...duplicated, target_id: 'L2-1-2' }],
        },
      },
    } as any)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(course, 'refreshCourseData').mockResolvedValue(undefined)
    const task: Task = {
      id: 'job-dup',
      courseId: 'c1',
      courseName: '线性代数',
      status: 'waiting_for_review',
      progress: 98,
      currentStep: 'release',
      completedNodes: 4,
      totalNodes: 4,
      logs: [],
      shouldStop: false,
      guidedWorkflow: {
        schema_version: 'guided_course_generation_v2',
        current_step: 'release',
        review_step: 'release',
        steps: [
          { number: 1, key: 'requirements', status: 'confirmed' },
          { number: 2, key: 'outline', status: 'confirmed' },
          { number: 3, key: 'content', status: 'confirmed' },
          { number: 4, key: 'release', status: 'waiting_for_confirmation' },
        ],
      },
    }

    const wrapper = mount(CourseGenerationGate, { props: { courseId: 'c1', task } })
    await flushPromises()

    // Three raw entries, two distinct problems.
    expect(wrapper.text()).toContain('阻断项 2')
    expect(wrapper.text()).not.toContain('阻断项 3')
  })

  it('项目目录展示暂定起点、路径角色与生成理由', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-project',
        course_name: '环保保温玻璃杯设计',
        course_purpose: 'systematic',
        course_type: 'project',
        course_intent: {
          schema_version: 'course_intent_v1',
          type: 'project',
          project_goal: '设计一款环保保温玻璃杯',
          expected_deliverable: '产品设计方案与可验证原型',
        },
        learner_starting_profile: {
          status: 'tentative',
          evidence_basis: 'self_reported',
          self_reported_strengths: ['熟悉产品造型与结构'],
          focus_areas: ['玻璃材料与隔热原理'],
        },
        nodes: [{
          node_id: 'project-1',
          parent_node_id: '',
          node_level: 2,
          node_name: '验证材料与隔热方案',
          learning_objective: '完成材料方案比较并给出选择依据',
          learning_path_role: 'focus',
          path_reason: '你熟悉造型，但对玻璃材料与隔热原理不确定。',
        }],
      },
    } as any)
    const save = vi.spyOn(workspace, 'saveBlueprint').mockImplementation(async (_courseId, payload) => ({
      draft: payload,
    }) as any)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'course-project',
        courseName: '环保保温玻璃杯设计',
        task: {
          id: 'job-project',
          courseId: 'course-project',
          courseName: '环保保温玻璃杯设计',
          courseType: 'project',
          status: 'waiting_for_review',
          progress: 28,
          currentStep: 'outline',
          logs: [],
          shouldStop: false,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('项目起点')
    expect(wrapper.text()).toContain('产品设计方案与可验证原型')
    expect(wrapper.text()).toContain('熟悉产品造型与结构')
    expect(wrapper.text()).toContain('玻璃材料与隔热原理')
    expect(wrapper.text()).toContain('重点补充')
    expect(wrapper.get('[data-testid="outline-rich-editor"]').text()).toContain('验证材料与隔热方案')

    const editor = wrapper.get('[data-testid="outline-rich-editor"]')
    editor.get('h2').element.textContent = '比较并验证材料与隔热方案'
    await editor.trigger('input')
    await wrapper.findAll('.outline-review__actions button')[0]!.trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('course-project', expect.objectContaining({
      course_type: 'project',
      course_intent: expect.objectContaining({ expected_deliverable: '产品设计方案与可验证原型' }),
      learner_starting_profile: expect.objectContaining({ status: 'tentative' }),
      nodes: [expect.objectContaining({ learning_path_role: 'focus' })],
    }))
  })

  it('英文模式不泄漏新增界面的中文回退文案或翻译键', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => enMessages,
    })))
    await setLocale('en')
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-en',
        course_name: 'Linear algebra',
        nodes: [{
          node_id: 'n1',
          parent_node_id: '',
          node_level: 2,
          node_name: 'Vector spaces',
          learning_objective: 'Recognize vector-space structure',
        }],
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: { courseId: 'course-en', courseName: 'Linear algebra' },
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('Outline nodes')
    expect(wrapper.find('.outline-review__header').exists()).toBe(false)
    expect(wrapper.find('.outline-review__course-name').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('确认这门课')
    expect(wrapper.text()).not.toContain('courseGeneration.')
  })

  it('D-1：在确认目录时就显示覆盖度判断与不覆盖清单', async () => {
    const workspace = useCourseWorkspaceStore()
    const draft = {
      base_blueprint_revision_id: 'bp-1',
      course_name: '微积分核心概览课',
      course_purpose: 'systematic',
      course_blueprint: {},
      learning_asset_plan: {},
      blueprint_locks: {},
      nodes: [
        {
          node_id: 'n1',
          parent_node_id: '',
          node_level: 2,
          node_name: '函数与极限',
          learning_objective: '理解极限',
        },
      ],
    }
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: draft,
      coverage: {
        available: true,
        status: 'partial',
        scale: 'micro',
        scale_label: '微型课',
        class_hours: 8,
        may_claim_complete_subject: false,
        coverage_promise: '只覆盖一个可检查的核心切面，不承担学科完整覆盖',
        required_positioning: '微积分核心概览课',
        covered_topics: ['函数、极限与连续'],
        uncovered_topics: ['中值定理', '洛必达法则与未定式', '反常积分'],
        uncovered_count: 3,
        advisories: ['建议一：压缩为核心课，只保留最关键的 8 个主题'],
      },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'c1',
        courseName: '微积分',
        task: {
          id: 'job-1',
          courseId: 'c1',
          courseName: '微积分',
          status: 'waiting_for_review',
          progress: 28,
          currentStep: 'outline',
          logs: [],
          shouldStop: false,
        } as unknown as Task,
      },
    })
    await flushPromises()

    const verdict = wrapper.get('[data-testid="outline-coverage-verdict"]')
    expect(verdict.attributes('data-status')).toBe('partial')
    expect(verdict.text()).toContain('微型课')
    expect(verdict.text()).toContain('8 课时')
    // 点名的缺失知识点必须逐条出现在确认页上。
    const uncovered = wrapper.get('[data-testid="outline-coverage-uncovered"]').text()
    expect(uncovered).toContain('中值定理')
    expect(uncovered).toContain('洛必达法则与未定式')
    expect(uncovered).toContain('反常积分')
    expect(verdict.text()).toContain('压缩为核心课')
  })

  it('D-1：后端没有给出判定时保持沉默，不得暗示课程完整', async () => {
    const workspace = useCourseWorkspaceStore()
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      current: {
        base_blueprint_revision_id: 'bp-1',
        course_name: '老课程',
        course_purpose: 'systematic',
        course_blueprint: {},
        learning_asset_plan: {},
        blueprint_locks: {},
        nodes: [],
      },
      coverage: { available: false, status: 'unknown' },
    } as any)

    const wrapper = mount(CourseOutlineReview, {
      props: {
        courseId: 'c1',
        courseName: '老课程',
        task: {
          id: 'job-1',
          courseId: 'c1',
          courseName: '老课程',
          status: 'waiting_for_review',
          progress: 28,
          currentStep: 'outline',
          logs: [],
          shouldStop: false,
        } as unknown as Task,
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="outline-coverage-verdict"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('完整课程')
  })
})
