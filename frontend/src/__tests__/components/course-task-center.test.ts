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

  it('用中英文产品文案显示知识身份与并行关系阶段', async () => {
    const generation = useGenerationStore()
    generation.globalTasks = [{
      id: 'task-skeleton', course_id: 'course-1', course_name: '线性代数', status: 'running',
      progress: 35, current_phase: 'course_knowledge_skeleton', message: '正在规划知识身份',
    }, {
      id: 'task-relations', course_id: 'course-2', course_name: '微积分', status: 'running',
      progress: 49, current_phase: 'course_relation_generation', message: '正在生成关系邻域',
    }]
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('规划全课知识身份')
    const rows = wrapper.findAll('.task-row')
    await rows[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('并行生成知识关系邻域')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.text()).toContain('Generating knowledge relation neighborhoods in parallel')
    await rows[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Planning course-wide knowledge identities')
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
        schema_version: 'guided_course_generation_v1', current_step: 'outline', review_step: 'outline',
        steps: [
          { number: 1, key: 'requirements', status: 'confirmed' },
          { number: 2, key: 'outline', status: 'waiting_for_confirmation' },
          { number: 3, key: 'knowledge', status: 'locked' },
          { number: 4, key: 'teaching', status: 'locked' },
          { number: 5, key: 'content', status: 'locked' },
          { number: 6, key: 'release', status: 'locked' },
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
    expect(wrapper.text()).toContain('确认后才会生成知识蓝图')
    expect(wrapper.text()).toContain('质量与发布')
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

  it('知识蓝图步骤展示结构摘要并只确认当前步骤', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v1', current_step: 'knowledge', review_step: 'knowledge',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'knowledge', status: 'waiting_for_confirmation' },
        { number: 4, key: 'teaching', status: 'locked' },
        { number: 5, key: 'content', status: 'locked' },
        { number: 6, key: 'release', status: 'locked' },
      ],
    }
    generation.globalTasks = [{
      id: 'task-knowledge', course_id: 'course-1', course_name: '线性代数', status: 'waiting_for_review',
      progress: 48, current_phase: 'knowledge_ready', guided_workflow: workflow,
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'knowledge',
      can_confirm: true,
      guided_workflow: workflow,
      artifact: {
        concept_group_count: 3,
        knowledge_point_count: 12,
        relation_count: 8,
        section_responsibilities: [{
          node_id: 'L2-1-1',
          section_number: '1.1',
          title: '向量空间',
          learning_objective: '判断集合是否构成向量空间',
          scope_boundary: '本节不展开线性映射',
        }],
        concept_groups: [{ name: '向量与空间', summary: '建立线性空间的基本语言' }],
        relations: [{
          source_name: '向量加法',
          target_name: '向量空间公理',
          relation_type: 'prerequisite',
          reason: '先理解运算，才能检查公理',
        }],
      },
    })
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const reopen = vi.spyOn(workspace, 'reopenGenerationStep').mockResolvedValue({ status: 'reopened' })
    const confirm = vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({ status: 'running' })
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('确认知识蓝图')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('向量与空间')
    expect(wrapper.text()).toContain('每节负责教什么')
    expect(wrapper.text()).toContain('本节不展开线性映射')
    expect(wrapper.text()).toContain('向量加法')
    await wrapper.get('.guided-workflow__step:not(:disabled)').trigger('click')
    await flushPromises()
    expect(reopen).toHaveBeenCalledWith('course-1', 'outline')
    await wrapper.get('.task-actions .primary-button').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('course-1', 'knowledge')
  })

  it('教学方案展示课程编排画像、角色分布、块序列和块级难度', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v1', current_step: 'teaching', review_step: 'teaching',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'knowledge', status: 'confirmed' },
        { number: 4, key: 'teaching', status: 'waiting_for_confirmation' },
        { number: 5, key: 'content', status: 'locked' },
        { number: 6, key: 'release', status: 'locked' },
      ],
    }
    generation.globalTasks = [{
      id: 'task-teaching', course_id: 'course-1', course_name: '线性代数',
      status: 'waiting_for_review', progress: 62, current_phase: 'teaching_ready',
      guided_workflow: workflow,
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'teaching',
      can_confirm: true,
      guided_workflow: workflow,
      artifact: {
        composition_profile: {
          style: 'example_driven',
          label: '案例实战',
          summary: '增加典型案例与真实场景。',
          rhythm: ['讲解', '补充案例', '真实场景', '学习者行动', '检查反馈'],
        },
        block_distribution: {
          role_counts: { concept: 4, example: 6, application: 3, activity: 4 },
        },
        sections: [{
          node_id: 'L2-1-1',
          name: '1.1 向量空间',
          learning_objective: '判断集合是否构成向量空间',
          module_plan: [
            {
              module_id: 'core_explanation',
              module_instance_id: 'L2-1-1:core_explanation:1',
              label: '核心教学',
              block_role: 'concept',
              composition_source: 'subject_required',
              block_difficulty_contract: {
                target_level: 'intermediate',
                learner_autonomy: 'shared',
                scaffold_intensity: 'medium',
              },
            },
            {
              module_id: 'composition_case_extension',
              module_instance_id: 'L2-1-1:composition_case_extension:1',
              label: '补充案例',
              block_role: 'example',
              composition_source: 'composition_style',
              selection_reasons: ['composition_style'],
              block_difficulty_contract: {
                target_level: 'intermediate',
                learner_autonomy: 'guided',
                scaffold_intensity: 'medium',
              },
            },
            {
              module_id: 'math_proof',
              module_instance_id: 'L2-1-1:math_proof:1',
              label: '证明与推导',
              block_role: 'reasoning',
              composition_source: 'difficulty_level',
              selection_reasons: ['difficulty_level'],
              block_difficulty_contract: {
                target_level: 'advanced',
                learner_autonomy: 'independent',
                scaffold_intensity: 'low',
              },
            },
          ],
        }],
      },
    })
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('案例实战')
    expect(wrapper.text()).toContain('讲解 → 补充案例 → 真实场景')
    expect(wrapper.text()).toContain('案例')
    expect(wrapper.text()).toContain('补充案例')
    expect(wrapper.text()).toContain('偏好新增')
    expect(wrapper.text()).toContain('难度新增')
    expect(wrapper.text()).toContain('进阶 · 引导完成 · 中支架')
    expect(wrapper.text()).toContain('高阶 · 独立完成 · 低支架')
    expect(wrapper.text()).toContain('3 个课程块 · 偏好新增 1 个 · 难度新增 1 个')

    await setLocale('en')
    await flushPromises()
    expect(wrapper.find('.composition-review').text()).toContain('Case practice')
    expect(wrapper.find('.composition-review').text()).toContain('Explanation → Additional example')
    expect(wrapper.find('.composition-review').text()).not.toContain('案例实战')
    expect(wrapper.find('.module-sequence').text()).toContain('Example')
    expect(wrapper.find('.module-sequence').text()).toContain('Reasoning')
    expect(wrapper.find('.module-sequence').text()).not.toContain('补充案例')
    expect(wrapper.find('.module-sequence').text()).not.toContain('证明与推导')
  })

  it('内容确认步骤展示每道题为什么存在、实际考什么和同源命中结果', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v1', current_step: 'content', review_step: 'content',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'knowledge', status: 'confirmed' },
        { number: 4, key: 'teaching', status: 'confirmed' },
        { number: 5, key: 'content', status: 'waiting_for_confirmation' },
        { number: 6, key: 'release', status: 'locked' },
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

    expect(wrapper.text()).toContain('逐题解析与评判检查')
    expect(wrapper.text()).toContain('为什么出这道题')
    expect(wrapper.text()).toContain('它实际在考什么')
    expect(wrapper.text()).toContain('同时比较大小和方向')
    expect(wrapper.text()).toContain('只比较大小')
    expect(wrapper.text()).toContain('3 / 3')
  })

  it('英文模式完整显示六步和当前确认动作，不泄漏翻译键或中文', async () => {
    const generation = useGenerationStore()
    const workspace = useCourseWorkspaceStore()
    const workflow = {
      schema_version: 'guided_course_generation_v1', current_step: 'knowledge', review_step: 'knowledge',
      steps: [
        { number: 1, key: 'requirements', status: 'confirmed' },
        { number: 2, key: 'outline', status: 'confirmed' },
        { number: 3, key: 'knowledge', status: 'waiting_for_confirmation' },
        { number: 4, key: 'teaching', status: 'locked' },
        { number: 5, key: 'content', status: 'locked' },
        { number: 6, key: 'release', status: 'locked' },
      ],
    }
    generation.globalTasks = [{
      id: 'task-knowledge-en', course_id: 'course-1', course_name: 'Linear Algebra',
      status: 'waiting_for_review', progress: 48, current_phase: 'knowledge_ready',
      guided_workflow: workflow,
    }]
    vi.spyOn(workspace, 'loadGenerationReview').mockResolvedValue({
      step: 'knowledge',
      can_confirm: true,
      guided_workflow: workflow,
      artifact: {
        concept_group_count: 3,
        knowledge_point_count: 12,
        relation_count: 8,
        concept_groups: [{ name: 'Vector spaces', summary: 'Build the language of linear spaces' }],
      },
    })
    vi.spyOn(workspace, 'confirmGenerationStep').mockResolvedValue({ status: 'running' })
    await setLocale('en')

    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.text()).toContain('Confirm knowledge blueprint')
    expect(wrapper.text()).toContain('Knowledge blueprint')
    expect(wrapper.text()).toContain('Quality & release')
    expect(wrapper.text()).not.toContain('courseTasks.')
    expect(wrapper.text()).not.toContain('确认知识蓝图')
  })

  it('把质量阻断翻译为用户文案，并提供删除而非继续操作', async () => {
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

  it('显示当前知识包进度、真实失败原因和知识阶段检查点', async () => {
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

    expect(wrapper.text()).toContain('检查当前小节知识包')
    expect(wrapper.text()).toContain('知识包进度')
    expect(wrapper.text()).toContain('1 / 3')
    expect(wrapper.text()).toContain('具体原因：小节「线性映射」知识包缺少可验证掌握标准')
    expect(wrapper.text()).toContain('目录已保留，知识包已完成 1/3')
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
