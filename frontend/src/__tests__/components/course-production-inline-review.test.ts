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
    expect(wrapper.text()).toContain('确认这门课怎样展开')
    expect(wrapper.text()).toContain('1 个目录节点')

    await wrapper.get('.outline-review__nodes input').setValue('向量与空间')
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

    expect(wrapper.text()).toContain('你的项目起点（暂定）')
    expect(wrapper.text()).toContain('产品设计方案与可验证原型')
    expect(wrapper.text()).toContain('熟悉产品造型与结构')
    expect(wrapper.text()).toContain('玻璃材料与隔热原理')
    expect(wrapper.text()).toContain('重点补充')
    expect(wrapper.text()).toContain('你熟悉造型，但对玻璃材料与隔热原理不确定。')

    await wrapper.get('.outline-review__nodes input').setValue('比较并验证材料与隔热方案')
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

    expect(wrapper.text()).toContain('Confirm how this course unfolds')
    expect(wrapper.text()).toContain('Outline nodes · 1')
    expect(wrapper.text()).not.toContain('确认这门课')
    expect(wrapper.text()).not.toContain('courseGeneration.')
  })
})
