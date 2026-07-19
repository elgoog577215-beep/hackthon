import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useGenerationStore } from '@/stores/generation'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

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
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
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
    expect(wrapper.text()).toContain('暂停并保留草稿')
    await wrapper.find('.task-actions .secondary-button').trigger('click')
    await flushPromises()
    expect(pause).toHaveBeenCalledWith('course-1', 'task-1')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.find('.task-actions .secondary-button').text()).toContain('Pause and keep draft')

    await wrapper.find('.task-actions__open').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.courseId).toBe('course-1')
  })

  it('排队任务同样可以暂停，并明确提供取消删除', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-pending', course_id: 'course-1', course_name: '线性代数', status: 'pending',
      progress: 8, current_phase: 'requirement_analysis', message: '等待生成',
    }]
    const pause = vi.spyOn(generation, 'pauseTask').mockResolvedValue(undefined)
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('取消并删除')
    expect(wrapper.text()).toContain('停止本步并保留检查点')
    await wrapper.get('.task-actions .secondary-button:not(.task-actions__open)').trigger('click')
    await flushPromises()
    expect(pause).toHaveBeenCalledWith('course-1', 'task-pending')
  })

  it('用中英文产品文案显示全课教案规划与正文生成阶段', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-plan', course_id: 'course-1', course_name: '线性代数', status: 'running',
      progress: 35, current_phase: 'course_teaching_plan', message: '正在规划全课小节教案',
    }, {
      id: 'task-content', course_id: 'course-2', course_name: '微积分', status: 'running',
      progress: 55, current_phase: 'content_generation', message: '各节正文并行生成',
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('规划并汇编全课小节教案')
    const rows = wrapper.findAll('.task-row')
    await rows[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('生成课程内容')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.text()).toContain('Generating course content')
    await rows[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Planning and assembling all section lesson plans')
  })

  it('同一课程的多次生成分别成行，并按所选任务 ID 执行控制', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [
      {
        id: 'task-old', course_id: 'course-1', course_name: '线性代数', status: 'completed',
        progress: 100, current_phase: 'completed', message: '旧任务已完成',
        updated_at: '2026-07-18T10:00:00Z',
      },
      {
        id: 'task-new', course_id: 'course-1', course_name: '线性代数', status: 'running',
        progress: 42, current_phase: 'content_generation', message: '新任务正在生成',
        updated_at: '2026-07-19T10:00:00Z',
      },
    ]
    const pause = vi.spyOn(generation, 'pauseTask').mockResolvedValue(undefined)
    const deleteTask = vi.spyOn(generation, 'deleteTask').mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const wrapper = mountCenter()
    await flushPromises()

    const rows = wrapper.findAll('.task-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('42%')
    expect(rows[1]!.text()).toContain('100%')

    await wrapper.get('.task-actions .secondary-button:not(.task-actions__open)').trigger('click')
    await flushPromises()
    expect(pause).toHaveBeenCalledWith('course-1', 'task-new')

    await rows[1]!.trigger('click')
    await flushPromises()
    await wrapper.get('.task-actions .danger-button').trigger('click')
    await flushPromises()
    expect(deleteTask).toHaveBeenCalledWith('course-1', 'task-old')
  })

  it('失败任务可以删除未发布现场', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-failed', course_id: 'course-1', course_name: '线性代数', status: 'failed',
      progress: 38, current_phase: 'blueprint_generation', message: '生成中断',
      recovery: {
        state: 'manual_resume', can_resume: true, reason_code: 'checkpoint_available', reason: 'checkpoint available',
        checkpoint: { phase: 'blueprint_generation', completed_nodes: 0, total_nodes: 4, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
      },
    }]
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const deleteTask = vi.spyOn(generation, 'deleteTask').mockResolvedValue(undefined)
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('删除任务')
    await wrapper.get('.task-actions .danger-button').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('删除未发布课程'),
      '删除任务',
      expect.any(Object),
    )
    expect(deleteTask).toHaveBeenCalledWith('course-1', 'task-failed')
  })

  it('清理已发布任务时明确保留正式课程', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-completed', course_id: 'course-1', course_name: '线性代数', status: 'completed',
      progress: 100, current_phase: 'completed', message: '课程生成完成',
    }]
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const deleteTask = vi.spyOn(generation, 'deleteTask').mockResolvedValue(undefined)
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('清除任务记录')
    await wrapper.get('.task-actions .danger-button').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('正式课程仍会保留'),
      '清除任务记录',
      expect.any(Object),
    )
    expect(deleteTask).toHaveBeenCalledWith('course-1', 'task-completed')
  })

  it('在等待审阅时读取、保存并确认同一份蓝图', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    generation.globalTasks = [{
      id: 'task-2', course_id: 'course-1', course_name: '线性代数', status: 'waiting_for_review',
      progress: 35, current_phase: 'outline_ready',
      phase_detail: { artifact_type: 'course_outline', completed_items: 1, total_items: 1 },
      guided_workflow: {
        schema_version: 'guided_course_generation_v2', current_step: 'outline', review_step: 'outline',
        steps: [
          { number: 1, key: 'requirements', status: 'confirmed' },
          { number: 2, key: 'outline', status: 'waiting_for_confirmation' },
          { number: 3, key: 'content', status: 'locked' },
          { number: 4, key: 'release', status: 'locked' },
        ],
      },
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'outline', can_confirm: true,
      guided_workflow: generation.globalTasks[0].guided_workflow,
      artifact: {},
    })
    vi.spyOn(workspace, 'loadBlueprint').mockResolvedValue({
      draft: {
        base_blueprint_revision_id: 'bp-1', course_name: '线性代数', course_purpose: 'systematic',
        course_blueprint: {}, learning_asset_plan: {}, nodes: [{ node_id: 'n1', node_name: '向量空间', learning_objective: '判断子空间' }],
      },
    })
    const save = vi.spyOn(workspace, 'saveBlueprint').mockResolvedValue({ draft: {} })
    const confirm = vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({ status: 'running' })
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('确认课程目录')
    expect(wrapper.text()).toContain('确认后会冻结全课知识职责')
    expect(wrapper.text()).toContain('确认发布')
    expect(wrapper.text()).toContain('目录小节')
    await wrapper.find('.blueprint-nodes input').setValue('向量空间与线性映射')
    await wrapper.find('.task-actions .primary-button').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith('course-1', expect.objectContaining({
      base_blueprint_revision_id: 'bp-1',
      nodes: [expect.objectContaining({ node_name: '向量空间与线性映射' })],
    }))
    expect(confirm).toHaveBeenCalledWith('course-1', 'outline')
  })

  it('内容确认步骤展示每道题为什么存在、实际考什么和同源命中结果', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v2', current_step: 'content', review_step: 'content',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'content', status: 'waiting_for_confirmation' },
        { number: 4, key: 'release', status: 'locked' },
      ],
    }
    generation.globalTasks = [{
      id: 'task-content', course_id: 'course-1', course_name: '线性代数',
      status: 'waiting_for_review', progress: 88, current_phase: 'content_ready',
      guided_workflow: workflow,
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'content',
      can_confirm: true,
      guided_workflow: workflow,
      artifact: {
        quality_status: 'passed',
        asset_quality_passed: true,
        manual_review_count: 0,
        asset_counts: { questions: 3 },
        question_review: {
          total: 3,
          passed: 3,
          blocked: 0,
          samples: [{
            question_id: 'q1',
            practice_level: 'objective_practice',
            prompt: '判断两个向量是否相同并说明依据。',
            status: 'passed',
            task_goal: '同时比较大小和方向',
            why_this_question: '检查能否迁移向量相同的判断条件。',
            library_fit: 'HIT',
            target_skills: [{ id: 's1', name: '比较向量' }],
            target_misconceptions: [{ id: 'm1', name: '只比较大小' }],
            issues: [],
          }],
        },
        sections: [],
      },
    })

    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.findAll('.guided-workflow__step')).toHaveLength(4)
    expect(wrapper.text()).toContain('小节教案、知识库与关系图已由同一计划编译')
    expect(wrapper.text()).toContain('题目合同与可判定性')
    expect(wrapper.text()).toContain('为什么出这道题')
    expect(wrapper.text()).toContain('它实际在考什么')
    expect(wrapper.text()).toContain('同时比较大小和方向')
    expect(wrapper.text()).toContain('只比较大小')
    expect(wrapper.text()).toContain('3 / 3')
  })

  it('英文模式完整显示四步和当前确认动作，不泄漏翻译键或中文', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v2', current_step: 'content', review_step: 'content',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'content', status: 'waiting_for_confirmation' },
        { number: 4, key: 'release', status: 'locked' },
      ],
    }
    generation.globalTasks = [{
      id: 'task-content-en', course_id: 'course-1', course_name: 'Linear Algebra',
      status: 'waiting_for_review', progress: 88, current_phase: 'content_ready',
      guided_workflow: workflow,
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'content',
      can_confirm: true,
      guided_workflow: workflow,
      artifact: {
        quality_status: 'passed',
        asset_quality_passed: true,
        manual_review_count: 0,
        asset_counts: {},
        question_review: { total: 0, passed: 0, blocked: 0, samples: [] },
        sections: [],
      },
    })
    vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({ status: 'running' })
    await setLocale('en')

    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.findAll('.guided-workflow__step')).toHaveLength(4)
    expect(wrapper.text()).toContain('Review course content')
    expect(wrapper.text()).toContain('Course generation')
    expect(wrapper.text()).toContain('Confirm publication')
    expect(wrapper.text()).not.toContain('courseTasks.')
    expect(wrapper.text()).not.toContain('确认课程内容')
  })

  it('把结构阻断翻译为用户文案，并提供删除而非继续操作', async () => {
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

    expect(wrapper.text()).toContain('结构检查未通过')
    expect(wrapper.text()).not.toContain('quality_failed')
    expect(wrapper.find('.danger-button').exists()).toBe(true)
    expect(wrapper.find('.danger-button').text()).toContain('删除任务')
    expect(wrapper.find('.task-actions .primary-button').exists()).toBe(false)
    expect(wrapper.find('.task-actions__open').exists()).toBe(true)
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
    expect(resume).toHaveBeenCalledWith('course-1', 'task-4')
  })

  it('显示详细教案批次的真实恢复位置', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-plan-batch', course_id: 'course-1', course_name: '深度神经网络', status: 'failed',
      progress: 43, current_phase: 'course_teaching_plan_batch_validation', message: '第 3 批结构检查失败',
      recovery: {
        state: 'manual_resume', can_resume: true, reason_code: 'checkpoint_available', reason: 'checkpoint available',
        checkpoint: {
          phase: 'course_teaching_plan_batch_validation', completed_nodes: 0, total_nodes: 0,
          draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [],
          outline_ready: true, teaching_plan_ready: false, teaching_plan_mode: 'batched',
          completed_teaching_plan_batches: 2, total_teaching_plan_batches: 4,
          completed_teaching_plan_sections: 6, total_teaching_plan_sections: 12,
          failed_teaching_plan_batch_id: 'TP-B03', next_teaching_plan_batch_index: 3,
        },
      },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('检查当前详细教案批次')
    expect(wrapper.text()).toContain('已保留 6/12 个小节教案，可从第 3 批继续；正文尚未开始')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.text()).toContain('Validating the current lesson-plan batch')
    expect(wrapper.text()).toContain('6/12 section lesson plans are preserved; resume from batch 3. Content has not started')
  })

  it('目录前失败显示重试当前阶段，不伪造 0/0 正文检查点', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-outline', course_id: 'course-1', course_name: '概率论', status: 'failed',
      progress: 34, current_phase: 'outline_validation',
      message: '课程目录未通过检查',
      error: 'AI provider unavailable: not_configured',
      recovery: {
        state: 'manual_resume', can_resume: true,
        reason_code: 'stage_restart_available',
        reason: '已保留课程需求与资料处理结果；继续后将重新生成课程目录',
        checkpoint: {
          phase: 'outline_validation', completed_nodes: 0, total_nodes: 0,
          draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [],
          requirements_ready: true, outline_ready: false,
        },
      },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('生成中断，可以重试当前阶段')
    expect(wrapper.text()).toContain('已保存课程需求和资料处理结果')
    expect(wrapper.find('.task-actions .primary-button').text()).toContain('重试当前阶段')
    expect(wrapper.text()).not.toContain('已保留 0/0 个内容块')
    expect(wrapper.text()).not.toContain('已完成内容和中断草稿')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.text()).toContain('Generation stopped and can retry the current stage')
    expect(wrapper.text()).toContain('Course requirements and processed materials are saved')
    expect(wrapper.find('.task-actions .primary-button').text()).toContain('Retry current stage')
  })

  it('把旧版逐节知识任务明确标成兼容检查点', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-knowledge', course_id: 'course-1', course_name: '线性代数', status: 'failed',
      progress: 39, current_phase: 'section_knowledge_validation',
      message: '第二小节知识包未通过检查',
      error: '小节「线性映射」知识包缺少可验证掌握标准',
      phase_detail: {
        artifact_type: 'section_knowledge_package',
        item_name: '线性映射',
        completed_items: 1,
        total_items: 3,
      },
      recovery: {
        state: 'manual_resume', can_resume: true, reason_code: 'checkpoint_available', reason: 'checkpoint available',
        checkpoint: {
          phase: 'section_knowledge_validation', completed_nodes: 0, total_nodes: 3,
          draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [],
          outline_ready: true, completed_knowledge_packages: 1, total_knowledge_packages: 3,
        },
      },
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('检查旧版知识检查点')
    expect(wrapper.text()).toContain('旧版知识检查点')
    expect(wrapper.text()).toContain('1 / 3')
    expect(wrapper.text()).toContain('具体原因：小节「线性映射」知识包缺少可验证掌握标准')
    expect(wrapper.text()).toContain('目录与旧版知识检查点已保留，完成 1/3')
    expect(wrapper.text()).not.toContain('已保留 0/3 个内容块')
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
