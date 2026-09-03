import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OutlineGrowthStream from '@/components/OutlineGrowthStream.vue'

const lecture = (
  number: number,
  title: string,
  status: 'completed' | 'growing' | 'waiting',
  completed: number,
) => ({
  chapter_number: number,
  title,
  learning_focus: `第 ${number} 讲目标`,
  section_count: 1,
  completed_section_count: completed,
  status,
  sections: [],
})

describe('OutlineGrowthStream two-stage teacher outline', () => {
  it('完整框架形成前不逐个泄露讲次标题', () => {
    const wrapper = mount(OutlineGrowthStream, {
      props: {
        growth: {
          authoring_structure_version: 'lecture_v1',
          state: 'growing',
          completed_sections: 1,
          total_sections: 2,
          chapters: [
            lecture(1, '已经返回的第一讲', 'completed', 1),
            lecture(2, '正在生成本讲主题…', 'growing', 0),
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('正在生成完整课程框架')
    expect(wrapper.text()).not.toContain('已经返回的第一讲')
  })

  it('框架完成后一次显示全部标题并报告详情进度', async () => {
    const framework = {
      authoring_structure_version: 'lecture_v1',
      state: 'framework_ready',
      completed_sections: 0,
      total_sections: 2,
      chapters: [
        lecture(1, '问题与数据', 'waiting', 0),
        lecture(2, '模型与判断', 'waiting', 0),
      ],
    }
    const wrapper = mount(OutlineGrowthStream, {
      props: { growth: framework },
    })

    expect(wrapper.text()).toContain('课程框架已生成，正在补全教学安排')
    expect(wrapper.text()).toContain('第1讲 问题与数据')
    expect(wrapper.text()).toContain('第2讲 模型与判断')
    expect(wrapper.text()).toContain('已补全 0/2')

    await wrapper.setProps({
      growth: {
        ...framework,
        state: 'detailing',
        completed_sections: 1,
        chapters: [
          lecture(1, '问题与数据', 'completed', 1),
          lecture(2, '模型与判断', 'growing', 0),
        ],
      },
    })
    expect(wrapper.text()).toContain('已补全 1/2')
  })
})
