import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CourseNavigator from '@/components/CourseNavigator.vue'
import { useCourseStore } from '@/stores/course'
import { setLocale } from '@/shared/i18n'
import { isLessonNavigation } from '@/utils/course-navigation'
import type { Node } from '@/stores/types'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const lesson = (number: number, title: string): Node => ({
  node_id: `lesson-${number}`, parent_node_id: 'root', node_level: 1,
  node_name: `第${number}讲 ${title}`, node_content: '', node_type: 'original',
  generation_status: 'completed', generated_chars: 0,
  children: [{
    node_id: `section-${number}`, parent_node_id: `lesson-${number}`, node_level: 2,
    node_name: title, node_content: '正文', node_type: 'original',
    generation_status: 'completed', generated_chars: 2, children: [],
  }],
})

describe('讲次式课程目录', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
    await setLocale('zh')
    setActivePinia(createPinia())
    useCourseStore().courseTree = [lesson(1, '辩论导论：定义与价值'), lesson(7, '结构化表达：起承转合')]
  })
  afterEach(async () => { await setLocale('zh'); vi.unstubAllGlobals() })

  it('恢复原版书本图标和讲次名称，仍选择承载正式内容的稳定节点', async () => {
    const store = useCourseStore()
    store.currentNode = store.courseTree[1]!.children![0]!
    const wrapper = mount(CourseNavigator)
    expect(wrapper.find('.lesson-number').exists()).toBe(false)
    expect(wrapper.findAll('.chapter-kind')).toHaveLength(2)
    expect(wrapper.findAll('.node-label').map(row => row.text())).toEqual(['第1讲 辩论导论：定义与价值', '第7讲 结构化表达：起承转合'])
    expect(wrapper.get('[aria-current="location"]').attributes('aria-label')).toBe('第7讲 结构化表达：起承转合')
    await wrapper.findAll('.node-button')[1]!.trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ node_id: 'section-7' })
  })

  it('筛选后保留原编号，无匹配时提示并能清空恢复', async () => {
    const wrapper = mount(CourseNavigator)
    await wrapper.get('input').setValue('结构化')
    expect(wrapper.findAll('.node-label').map(row => row.text())).toEqual(['第7讲 结构化表达：起承转合'])
    await wrapper.get('input').setValue('不存在的标题')
    expect(wrapper.get('[role="status"]').text()).toBe(zh.learningNavigator.noResults)
    await wrapper.get('input').setValue('')
    expect(wrapper.findAll('.node-button')).toHaveLength(2)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('保留历史多级目录，不把多个小节投影成单讲', () => {
    const branch = lesson(1, '历史章节')
    branch.children!.push({ ...branch.children![0]!, node_id: 'section-2' })
    expect(isLessonNavigation([branch])).toBe(false)
    useCourseStore().courseTree = [branch]
    const wrapper = mount(CourseNavigator)
    expect(wrapper.find('.lesson-navigator').exists()).toBe(false)
    expect(wrapper.findAll('.navigator-node')).toHaveLength(3)
  })

  it('英文目录控件和空状态有完整翻译', async () => {
    await setLocale('en')
    const wrapper = mount(CourseNavigator)
    expect(wrapper.get('input').attributes('placeholder')).toBe(en.learningNavigator.search)
    await wrapper.get('input').setValue('not found')
    expect(wrapper.get('[role="status"]').text()).toBe(en.learningNavigator.noResults)
    expect(wrapper.text()).not.toContain('learningNavigator.')
  })
})
