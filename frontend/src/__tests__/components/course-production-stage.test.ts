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
    expect(wrapper.text()).toContain('目录 · 已中断')
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

    expect(wrapper.text()).toContain('Course production was interrupted')
    expect(wrapper.text()).toContain('Course requirements and processed sources are saved')
    expect(wrapper.text()).not.toContain('已保留课程需求')
    expect(wrapper.text()).not.toContain('courseGeneration.')
  })

  it('阶段条把当前目录标成中断而不是进行中', () => {
    const wrapper = mount(CourseGenerationLifecycle, { props: { task: interruptedTask } })
    const stages = wrapper.findAll('li')
    expect(stages).toHaveLength(3)
    expect(stages[0]!.attributes('data-status')).toBe('error')
    expect(stages[0]!.attributes('aria-label')).toContain('已中断')
    expect(stages[1]!.attributes('data-status')).toBe('pending')
    expect(stages[2]!.attributes('data-status')).toBe('pending')
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
