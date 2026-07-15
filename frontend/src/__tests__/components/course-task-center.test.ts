import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useGenerationStore } from '@/stores/generation'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: { template: '<div />' } },
    { path: '/course/:courseId/learn', name: 'learning', component: { template: '<div />' } },
  ],
})

const mountCenter = () => mount(CourseTaskCenter, {
  props: { modelValue: true, courseId: 'course-1' },
  global: { plugins: [router], stubs: { Teleport: true } },
})

describe('CourseTaskCenter', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await router.push('/courses')
    await router.isReady()
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(generation, 'fetchGlobalTasks').mockResolvedValue(undefined)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    courses.courseList = [{ course_id: 'course-1', course_name: '线性代数', node_count: 4 }]
  })

  it('对运行任务提供暂停，并保留进入课程的直接入口', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-1', course_id: 'course-1', course_name: '线性代数', status: 'running',
      progress: 42, current_phase: 'content_generation', message: '正在生成第二章',
    }]
    const pause = vi.spyOn(generation, 'pauseTask').mockResolvedValue(undefined)
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('线性代数')
    expect(wrapper.text()).toContain('42%')
    await wrapper.find('.task-actions .secondary-button').trigger('click')
    await flushPromises()
    expect(pause).toHaveBeenCalledWith('course-1')

    await wrapper.find('.task-actions__open').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-1')
  })

  it('在等待审阅时读取、保存并确认同一份蓝图', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    generation.globalTasks = [{
      id: 'task-2', course_id: 'course-1', course_name: '线性代数', status: 'waiting_for_review',
      progress: 28, current_phase: 'blueprint_ready',
    }]
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      draft: {
        base_blueprint_revision_id: 'bp-1', course_name: '线性代数', course_purpose: 'systematic',
        course_blueprint: {}, learning_asset_plan: {}, nodes: [{ node_id: 'n1', node_name: '向量空间', learning_objective: '判断子空间' }],
      },
    })
    const save = vi.spyOn(workspace, 'saveBlueprint').mockResolvedValue({ draft: {} })
    const confirm = vi.spyOn(workspace, 'confirmBlueprint').mockResolvedValue({ status: 'running' })
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('确认课程蓝图')
    await wrapper.find('.blueprint-nodes input').setValue('向量空间与线性映射')
    await wrapper.find('.task-actions .primary-button').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      base_blueprint_revision_id: 'bp-1',
      nodes: [expect.objectContaining({ node_name: '向量空间与线性映射' })],
    }))
    expect(confirm).toHaveBeenCalledWith('course-1')
  })

  it('把终态阶段翻译为用户文案，并隐藏无效的取消操作', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-3', course_id: 'course-1', course_name: '线性代数', status: 'completed_with_warnings',
      progress: 100, current_phase: 'quality_failed', message: '',
      recovery: {
        state: 'quality_blocked', can_resume: false, reason_code: 'quality_gate_failed', reason: 'quality failed',
        checkpoint: { phase: 'quality_failed', completed_nodes: 4, total_nodes: 4, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
      },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('质量检查未通过')
    expect(wrapper.text()).not.toContain('quality_failed')
    expect(wrapper.find('.danger-button').exists()).toBe(false)
    expect(wrapper.find('.task-actions .primary-button').exists()).toBe(false)
    expect(wrapper.find('.task-actions__open').exists()).toBe(true)
  })

  it('展示阻断质量项及达到发布标准的修复说明', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-quality', course_id: 'course-1', course_name: 'C语言', status: 'completed_with_warnings',
      progress: 100, current_phase: 'quality_failed', publication_allowed: false,
      quality_report: {
        publication_allowed: false,
        blocking_issues: [{ gate: 'structure', severity: 'critical', asset_type: 'misconceptions', message: '必选资产为空' }],
        warnings: [{ gate: 'coverage', severity: 'major', asset_type: 'course_knowledge_map', message: '仍有 12 个课程局部知识待归一' }],
      },
      quality_repair: { eligible: true, attempts: 0, reason: '可自动补齐缺失的常见误区并重新检查；不会重写课程正文。' },
      recovery: { state: 'quality_blocked', can_resume: false, reason_code: 'quality_gate_failed', reason: 'quality failed', checkpoint: { phase: 'quality_failed', completed_nodes: 4, total_nodes: 4, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] } },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('尚未达到发布标准')
    expect(wrapper.text()).toContain('常见误区')
    expect(wrapper.text()).toContain('必选资产为空')
    expect(wrapper.text()).toContain('怎样达到标准')
    expect(wrapper.text()).toContain('优化建议（不阻止发布）')
    expect(wrapper.text()).toContain('自动补齐并重新检查')
  })

  it('只在后端确认有检查点时提供继续，并显示已保留内容', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-4', course_id: 'course-1', course_name: '线性代数', status: 'failed',
      progress: 55, current_phase: 'content_generation', message: '模型连接中断',
      recovery: {
        state: 'manual_resume', can_resume: true, reason_code: 'checkpoint_available', reason: 'checkpoint available',
        checkpoint: {
          phase: 'content_generation', completed_nodes: 2, total_nodes: 5,
          draft_node_ids: ['n3'], failed_node_ids: ['n3'], interrupted_node_ids: [],
        },
      },
    }]
    const resume = vi.spyOn(generation, 'resumeTask').mockResolvedValue(undefined)
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('已保留 2/5 个内容块和 1 份草稿')
    expect(wrapper.text()).toContain('从保存点继续')
    await wrapper.get('.task-actions .primary-button').trigger('click')
    await flushPromises()
    expect(resume).toHaveBeenCalledWith('course-1')
  })

  it('把已发布警告显示为可学习建议，而不是失败任务', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-5', course_id: 'course-1', course_name: '线性代数', status: 'completed_with_warnings',
      progress: 100, current_phase: 'completed', publication_allowed: true,
      recovery: {
        state: 'completed', can_resume: false, reason_code: 'already_published', reason: 'done',
        checkpoint: { phase: 'completed', completed_nodes: 4, total_nodes: 4, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
      },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('可以学习，有优化建议')
    expect(wrapper.text()).toContain('课程已经发布，仍有优化建议')
    expect(wrapper.text()).not.toContain('可以继续补齐失败节点')
    expect(wrapper.find('.task-actions__open').exists()).toBe(true)
    expect(wrapper.find('.task-actions .primary-button').exists()).toBe(false)
  })
})
