import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'
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

describe('OutlineGrowthStream teacher outline', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })
  it('整份生成展示未闭合内容和真实接收量，不冒充已保存', () => {
    const wrapper = mount(OutlineGrowthStream, { props: {
      mode: 'full',
      growth: { state: 'full_growing', streamed_content_chars: 120,
        course_preview: [{ field: 'course_intro_zh', text: '从真实问题开始分析' }],
        chapters: [lecture(1, '数据分析', 'growing', 0, '能识别数据中的')],
      },
    } })
    expect(wrapper.text()).toContain('正在生成完整课程大纲')
    expect(wrapper.text()).toContain('从真实问题开始分析')
    expect(wrapper.text()).toContain('能识别数据中的')
    expect(wrapper.text()).toContain('已接收 120 个字符')
    expect(wrapper.text()).toContain('已解析 0/1 讲')
    expect(wrapper.text()).not.toContain('课程大纲已生成')
  })
  it('暂停保留部分内容并停止吐字动画', () => {
    const wrapper = mount(OutlineGrowthStream, { props: { running: false, mode: 'full',
      growth: { chapters: [lecture(1, '数据分析', 'growing', 0, '已收到的片段')] },
    } })
    expect(wrapper.text()).toContain('已收到的片段')
    expect(wrapper.text()).toContain('已保留收到的内容')
    expect(wrapper.find('.spin').exists()).toBe(false)
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
