import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CourseReadingState from '@/components/CourseReadingState.vue'
import { setLocale } from '@/shared/i18n'

const props = { loading: false, error: null, courseSelected: true }

afterEach(async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
  await setLocale('zh')
  vi.unstubAllGlobals()
})

describe('course reading availability', () => {
  it('stops spinning after an empty teacher preview finishes and offers the workspace', async () => {
    const wrapper = mount(CourseReadingState, { props: { ...props, teacherPreview: true, loading: true } })
    expect(wrapper.text()).toContain('正在加载课程内容')
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({ loading: false })
    expect(wrapper.text()).toContain('暂无可试读的讲义')
    expect(wrapper.find('.course-reading-state__spinner').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('returnWorkbench')).toHaveLength(1)
    expect(wrapper.emitted('retry')).toBeUndefined()
  })

  it('shows a read error rather than the course selection guide and allows retry', async () => {
    const wrapper = mount(CourseReadingState, { props: { ...props, courseSelected: false, error: '网络连接暂不可用。', teacherPreview: true } })
    expect(wrapper.get('[role="alert"]').text()).toContain('课程加载失败')
    expect(wrapper.text()).toContain('网络连接暂不可用。')
    expect(wrapper.find('.course-reading-state__spinner').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('returnWorkbench')).toHaveLength(1)
    await wrapper.setProps({ loading: true, error: null })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('distinguishes student empty content from course selection and generation preparation', async () => {
    const wrapper = mount(CourseReadingState, { props })
    expect(wrapper.text()).toContain('暂无可阅读内容')
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({ courseSelected: false })
    expect(wrapper.text()).toContain('选择一个课程或章节')
    await wrapper.setProps({ courseSelected: true, generationPreview: true })
    expect(wrapper.text()).toContain('正在准备课程结构')
    expect(wrapper.text()).not.toContain('暂无可阅读内容')
  })

  it.each(['zh', 'en'] as const)('shows the actual %s preview and failure translations', async locale => {
    const messages = JSON.parse(readFileSync(resolve(process.cwd(), `public/locales/${locale}/translation.json`), 'utf8'))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => messages }))
    await setLocale(locale)
    const wrapper = mount(CourseReadingState, { props: { ...props, teacherPreview: true } })
    expect(wrapper.text()).toContain(messages.courseWorkspace.readingState.previewEmpty)
    expect(wrapper.get('button').text()).toBe(messages.courseWorkspaceFlow.returnWorkbench)
    await wrapper.setProps({ error: messages.courseWorkspace.readingState.failedHelp })
    expect(wrapper.text()).toContain(messages.courseWorkspace.readingState.failed)
    expect(wrapper.get('button').text()).toBe(messages.courseWorkspace.readingState.retry)
  })
})
