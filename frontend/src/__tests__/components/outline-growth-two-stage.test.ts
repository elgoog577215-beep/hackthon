import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OutlineGrowthStream from '@/components/OutlineGrowthStream.vue'

const lecture = (
  number: number,
  title: string,
  status: 'completed' | 'growing' | 'waiting',
  completed: number,
  summary = '',
) => ({
  chapter_number: number,
  title,
  content_summary: summary,
  section_count: 1,
  completed_section_count: completed,
  status,
  sections: [],
})

describe('OutlineGrowthStream two-stage teacher outline', () => {
  it('完整内容仍在自动优化时不会提前显示已生成', () => {
    const wrapper = mount(OutlineGrowthStream, { props: {
      reviewReady: true,
      growth: { state: 'optimizing', chapters: [lecture(1, '论点与证据', 'completed', 1)] },
    } })
    expect(wrapper.text()).toContain('正在自动优化大纲并复审')
    expect(wrapper.text()).toContain('正在检查最终内容')
    expect(wrapper.text()).not.toContain('课程大纲已生成')
  })
  it('轻量方案生成时逐讲显示已返回内容和真实状态', () => {
    const wrapper = mount(OutlineGrowthStream, {
      props: {
        growth: {
          authoring_structure_version: 'lecture_v1',
          state: 'growing',
          completed_sections: 1,
          total_sections: 2,
          chapters: [
            lecture(1, '已经返回的第一讲', 'completed', 1, '介绍第一讲的主要内容。'),
            lecture(2, '正在生成本讲主题…', 'growing', 0),
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('正在生成讲次方案')
    expect(wrapper.text()).toContain('已经返回的第一讲')
    expect(wrapper.text()).toContain('介绍第一讲的主要内容。')
    expect(wrapper.text()).toContain('正在生成')
    expect(wrapper.text()).toContain('已生成 1/2')
  })

  it('框架完成后一次显示全部标题并报告详情进度', async () => {
    const framework = {
      authoring_structure_version: 'lecture_v1',
      state: 'framework_ready',
      completed_sections: 0,
      total_sections: 2,
      chapters: [
        lecture(1, '问题与数据', 'waiting', 0, '从真实问题识别数据边界。'),
        lecture(2, '模型与判断', 'waiting', 0, '比较模型输出并形成判断。'),
      ],
    }
    const wrapper = mount(OutlineGrowthStream, {
      props: { growth: framework },
    })

    expect(wrapper.text()).toContain('讲次方案已生成')
    expect(wrapper.text()).toContain('第1讲 问题与数据')
    expect(wrapper.text()).toContain('第2讲 模型与判断')
    expect(wrapper.text()).toContain('从真实问题识别数据边界。')
    expect(wrapper.text()).toContain('已生成 2/2')

    await wrapper.setProps({
      growth: {
        ...framework,
        state: 'detailing',
        completed_sections: 1,
        chapters: [
          lecture(1, '问题与数据', 'completed', 1, '从真实问题识别数据边界。'),
          lecture(2, '模型与判断', 'growing', 0, '比较模型输出并形成判断。'),
        ],
      },
    })
    expect(wrapper.text()).toContain('正在生成完整课程大纲')
    expect(wrapper.text()).toContain('已补全 1/2')
  })
})
