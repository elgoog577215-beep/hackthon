import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationLifecycle from '@/components/CourseGenerationLifecycle.vue'
import CourseProductionStage from '@/components/CourseProductionStage.vue'
import { setLocale } from '@/shared/i18n'
import type { Task } from '@/stores/types'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const interruptedTask: Task = {
  id: 'job-1',
  courseId: 'course-1',
  courseName: '量子力学',
  status: 'error',
  progress: 32,
  currentStep: '教学画像与难度契约已确定',
  currentPhase: 'pedagogy_resolution',
  error: 'AI provider unavailable: authentication_failed',
  logs: [],
  shouldStop: false,
  guidedWorkflow: {
    schema_version: 'guided_course_generation_v2',
    current_step: 'outline',
    review_step: null,
    steps: [
      { number: 1, key: 'requirements', status: 'confirmed' },
      { number: 2, key: 'outline', status: 'in_progress' },
      { number: 3, key: 'content', status: 'locked' },
      { number: 4, key: 'release', status: 'locked' },
    ],
  },
  recovery: {
    state: 'manual_resume',
    can_resume: true,
    reason_code: 'stage_restart_available',
    reason: '已保留课程需求与资料处理结果；继续后将重新生成课程目录',
    checkpoint: {
      phase: 'pedagogy_resolution', completed_nodes: 0, total_nodes: 0,
      draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [], requirements_ready: true,
    },
  },
}

describe('CourseProductionStage', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  it('在课程现场解释中断、保存边界和恢复动作', async () => {
    const wrapper = mount(CourseProductionStage, {
      props: { task: interruptedTask, courseName: '量子力学' },
    })

    expect(wrapper.attributes('data-state')).toBe('error')
    expect(wrapper.text()).toContain('目录确认 · 已中断')
    expect(wrapper.text()).toContain('量子力学')
    expect(wrapper.text()).toContain('目录会在最终位置逐步出现')
    expect(wrapper.text()).toContain('课程生产暂时中断')
    expect(wrapper.text()).toContain('课程需求与资料处理结果已保留')
    expect(wrapper.text()).toContain('AI 服务暂时无法完成身份校验')
    expect(wrapper.find('.production-progress').exists()).toBe(false)
    expect(wrapper.find('.outline-germination').exists()).toBe(true)
    expect(wrapper.text().match(/课程需求与资料处理结果已保留/g)).toHaveLength(1)

    await wrapper.get('.formation-recovery > button').trigger('click')
    expect(wrapper.emitted('resume')).toHaveLength(1)
  })

  it('英文模式不泄漏后端中文恢复文案或翻译键', async () => {
    await setLocale('en')
    const wrapper = mount(CourseProductionStage, {
      props: { task: interruptedTask, courseName: 'Quantum mechanics' },
    })
    const lifecycle = mount(CourseGenerationLifecycle, { props: { task: interruptedTask } })

    expect(wrapper.text()).toContain('Course production was interrupted')
    expect(wrapper.text()).toContain('Course requirements and processed sources are saved')
    expect(wrapper.text()).not.toContain('已保留课程需求')
    expect(wrapper.text()).not.toContain('courseGeneration.')
    expect(lifecycle.text()).toContain('Course production')
    expect(lifecycle.text()).not.toContain('课程生产')
  })

  it('阶段条把当前解析标成中断，并公开 D-05 六阶段', () => {
    const wrapper = mount(CourseGenerationLifecycle, { props: { task: interruptedTask } })
    const stages = wrapper.findAll('li')
    expect(stages).toHaveLength(6)
    expect(stages[0]!.attributes('data-status')).toBe('completed')
    expect(stages[1]!.attributes('data-status')).toBe('error')
    expect(stages[1]!.attributes('aria-label')).toContain('已中断')
    expect(stages[2]!.attributes('data-status')).toBe('pending')
    expect(stages[3]!.attributes('data-status')).toBe('pending')
    expect(stages[4]!.attributes('data-status')).toBe('pending')
    expect(stages[5]!.attributes('data-status')).toBe('pending')
  })

  it('项目实战使用个人路径与项目交付语义', () => {
    const task: Task = {
      ...interruptedTask,
      courseType: 'project',
      status: 'running',
      error: undefined,
      currentPhase: 'outline_generation',
    }
    const stage = mount(CourseProductionStage, {
      props: { task, courseName: '环保保温玻璃杯设计' },
    })
    const lifecycle = mount(CourseGenerationLifecycle, { props: { task } })

    expect(stage.text()).toContain('个人路径 · 进行中')
    expect(stage.text()).toContain('生成轻量课程目录')
    expect(stage.text()).toContain('确认个人路径后')
    expect(lifecycle.text()).toContain('资料接收')
    expect(lifecycle.text()).toContain('解析与分类')
    expect(lifecycle.text()).toContain('检索证据')
    expect(lifecycle.text()).toContain('内容生成')
    expect(lifecycle.text()).toContain('质量检查')
    expect(lifecycle.text()).toContain('导出与发布')
  })

  it('标题下方用可播报的实时阶段摘要取代静态说明', async () => {
    const task: Task = {
      ...interruptedTask,
      status: 'running',
      error: undefined,
      progress: 47,
      currentPhase: 'course_teaching_plan_batch',
      currentStep: '正在生成第 18 批详细教案',
      updatedAt: '2026-08-03T12:17:00+08:00',
      phaseDetail: {
        completed_batches: 0,
        total_batches: 18,
      },
      phaseHistory: [
        { phase: 'course_teaching_plan_batch_validation', status: 'completed' },
      ],
      guidedWorkflow: {
        ...interruptedTask.guidedWorkflow!,
        current_step: 'teaching',
        steps: interruptedTask.guidedWorkflow!.steps,
      },
      recovery: {
        ...interruptedTask.recovery!,
        can_resume: true,
      },
    }
    const wrapper = mount(CourseProductionStage, {
      props: { task, courseName: '局部解剖学' },
    })
    const summary = wrapper.get('.formation-sheet__live-summary')

    expect(summary.attributes('role')).toBe('status')
    expect(summary.attributes('aria-live')).toBe('polite')
    expect(summary.attributes('aria-atomic')).toBe('true')
    expect(summary.text()).toContain('并行生成详细教案批次')
    expect(summary.text()).toContain('已完成 0/18 批')
    expect(summary.text()).toContain('最后更新 12:17')
    expect(wrapper.text()).not.toContain('系统先冻结全课知识职责')

    await wrapper.setProps({ task: { ...task, status: 'paused' } })
    expect(summary.text()).toBe('已暂停，当前检查点已保留')

    await wrapper.setProps({ task: { ...task, status: 'error' } })
    expect(summary.text()).toBe('教案确认中断，可从保存点继续')

    await wrapper.setProps({ task: { ...task, status: 'waiting_for_review' } })
    expect(summary.text()).toBe('教案确认已完成，等待确认')
  })

  it('后端给出可读原因时直接展示它，并保留技术细节可展开', async () => {
    const task: Task = {
      ...interruptedTask,
      error: 'ProviderTimeout: batch 7 timed out after 120s',
      errorCode: 'provider_timeout',
      errorUserMessage: '教案第 7 批超时；已完成批次不会重做，继续即可从该批恢复。',
    }
    const wrapper = mount(CourseProductionStage, { props: { task, courseName: '量子力学' } })

    expect(wrapper.text()).toContain('教案第 7 批超时')
    expect(wrapper.get('.formation-recovery code').text()).toBe('ProviderTimeout: batch 7 timed out after 120s')
  })

  it('后端未给可读原因时由稳定基座按错误类型解释超时', async () => {
    const task: Task = {
      ...interruptedTask,
      error: 'ProviderTimeout: request timed out',
      errorCode: undefined,
      errorUserMessage: undefined,
    }
    const wrapper = mount(CourseProductionStage, { props: { task, courseName: '量子力学' } })

    expect(wrapper.text()).toContain('响应超时')
  })

  it('长任务心跳停滞时在生产现场提示，未停滞时不打扰', async () => {
    const runningTask: Task = {
      ...interruptedTask,
      status: 'running',
      error: undefined,
      currentPhase: 'course_teaching_plan_batch',
      heartbeatAt: new Date(Date.now() - 8 * 1000).toISOString(),
    }
    const wrapper = mount(CourseProductionStage, {
      props: { task: runningTask, courseName: '量子力学' },
    })
    expect(wrapper.find('.formation-heartbeat-alert').exists()).toBe(false)

    await wrapper.setProps({
      task: { ...runningTask, heartbeatAt: new Date(Date.now() - 400 * 1000).toISOString() },
    })
    const alert = wrapper.get('.formation-heartbeat-alert')
    expect(alert.attributes('role')).toBe('status')
    expect(alert.text()).toContain('长时间没有更新')
  })

  it('教案确认后启动正文失败时按正文阶段显示中断', () => {    const task: Task = {
      ...interruptedTask,
      currentPhase: 'teaching_plan_ready',
      guidedWorkflow: {
        ...interruptedTask.guidedWorkflow!,
        current_step: 'content',
        steps: interruptedTask.guidedWorkflow!.steps,
      },
    }
    const wrapper = mount(CourseGenerationLifecycle, { props: { task } })
    const stages = wrapper.findAll('li')

    expect(stages[2]!.attributes('data-status')).toBe('completed')
    expect(stages[3]!.attributes('data-status')).toBe('error')
    expect(stages[3]!.attributes('aria-label')).toContain('已中断')
  })

  it('把真实目录检查点投影为可展开的生长树', async () => {
    const task: Task = {
      ...interruptedTask,
      status: 'running',
      error: undefined,
      progress: 33,
      currentPhase: 'outline_generation',
      phaseDetail: {
        artifact_type: 'course_outline_growth',
        outline_growth: {
          schema_version: 'course_outline_growth_v1',
          state: 'growing',
          active_chapter_number: 2,
          completed_batches: 1,
          total_batches: 3,
          completed_sections: 2,
          total_sections: 6,
          chapters: [
            {
              chapter_number: 1,
              title: '建立坐标',
              learning_focus: '看见概念之间的关系',
              section_count: 2,
              completed_section_count: 2,
              status: 'completed',
              sections: [
                { node_id: 'L2-1-1', section_number: '1.1', title: '从问题出发', learning_objective: '能识别真正问题' },
                { node_id: 'L2-1-2', section_number: '1.2', title: '建立核心概念', learning_objective: '能说明概念边界' },
              ],
            },
            {
              chapter_number: 2,
              title: '展开方法',
              learning_focus: '把概念转成可执行方法',
              section_count: 2,
              completed_section_count: 0,
              status: 'growing',
              sections: [],
            },
            {
              chapter_number: 3,
              title: '完成迁移',
              learning_focus: '在新情境中独立应用',
              section_count: 2,
              completed_section_count: 0,
              status: 'waiting',
              sections: [],
            },
          ],
        },
      },
    }
    const wrapper = mount(CourseProductionStage, {
      props: { task, courseName: '知识生长课' },
    })

    expect(wrapper.findAll('.growth-chapter')).toHaveLength(3)
    expect(wrapper.text()).toContain('2/6 个小节')
    expect(wrapper.text()).toContain('建立坐标')
    expect(wrapper.text()).toContain('这一节正在形成')
    expect(wrapper.get('.growth-chapter[data-state="growing"] .growth-chapter__head').attributes('aria-expanded')).toBe('true')

    const firstChapter = wrapper.get('.growth-chapter[data-state="completed"] .growth-chapter__head')
    expect(firstChapter.attributes('aria-expanded')).toBe('false')
    await firstChapter.trigger('click')
    expect(firstChapter.attributes('aria-expanded')).toBe('true')
    expect(wrapper.text()).toContain('从问题出发')
  })
})
