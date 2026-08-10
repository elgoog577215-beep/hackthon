import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

/**
 * 教师必须能看到：搜了什么、采用了哪些、为什么排除了某些、
 * 以及联网失败时的明确告知。不做成黑盒自动注入。
 */
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

const READY_SUMMARY = {
  enabled: true,
  status: 'ready',
  degraded: false,
  message_code: 'web_search_ready',
  queries: ['线性代数 特征值 教学资料'],
  sources: [{
    asset_id: 'mat-1',
    source_id: 'src_mit',
    url: 'https://ocw.mit.edu/linear-algebra',
    title: '线性代数公开讲义',
    domain: 'ocw.mit.edu',
    credibility: 'high',
    retrieved_at: '2026-08-05T00:00:00+00:00',
  }, {
    asset_id: 'mat-2',
    source_id: 'src_openstax',
    url: 'https://openstax.org/linear-algebra',
    title: 'OpenStax 线性代数',
    domain: 'openstax.org',
    credibility: 'high',
    retrieved_at: '2026-08-05T00:00:00+00:00',
  }],
  rejected: [{ url: 'https://blog.example.com/post', reason: 'low_relevance' }],
}

const taskWith = (webSearch: Record<string, unknown> | undefined) => ({
  id: 'task-1',
  course_id: 'course-1',
  course_name: '线性代数',
  status: 'running',
  progress: 20,
  current_phase: 'material_processing',
  message: '正在处理参考资料',
  ...(webSearch ? { phase_detail: { web_search: webSearch } } : {}),
})

describe('CourseTaskCenter 联网资料审阅', () => {
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

  const render = async (webSearch: Record<string, unknown> | undefined) => {
    const generation = useGenerationStore()
    generation.globalTasks = [taskWith(webSearch) as never]
    const wrapper = mountCenter()
    await flushPromises()
    return wrapper
  }

  it('未联网时不显示联网资料区块', async () => {
    const wrapper = await render(undefined)
    expect(wrapper.find('[data-testid="web-search-summary"]').exists()).toBe(false)
  })

  it('开关关闭时也不显示，避免噪音', async () => {
    const wrapper = await render({ enabled: false, status: 'disabled', degraded: true })
    expect(wrapper.find('[data-testid="web-search-summary"]').exists()).toBe(false)
  })

  it('展示检索关键词、采用来源、可信度与抓取时间', async () => {
    const wrapper = await render(READY_SUMMARY)
    const panel = wrapper.find('[data-testid="web-search-summary"]')

    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('线性代数 特征值 教学资料')
    expect(panel.text()).toContain('线性代数公开讲义')
    expect(panel.text()).toContain('2026-08-05T00:00:00+00:00')
    expect(panel.text()).toContain('高')
  })

  it('来源链接指向原文并带安全的 rel', async () => {
    const wrapper = await render(READY_SUMMARY)
    const link = wrapper.find('[data-testid="web-search-summary"] a')

    expect(link.attributes('href')).toBe('https://ocw.mit.edu/linear-algebra')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('把排除原因翻译成人话而不是机器码', async () => {
    const wrapper = await render(READY_SUMMARY)
    const panel = wrapper.find('[data-testid="web-search-summary"]')

    expect(panel.text()).toContain('已排除 1 条')
    expect(panel.text()).toContain('与课程相关性不足')
    expect(panel.text()).not.toContain('low_relevance')
  })

  it('联网失败时明确告知本次没有联网资料', async () => {
    const wrapper = await render({
      enabled: true,
      status: 'provider_unavailable',
      degraded: true,
      message_code: 'web_search_provider_failed',
      queries: ['线性代数 教学资料'],
      sources: [],
      rejected: [],
    })
    const panel = wrapper.find('[data-testid="web-search-summary"]')

    expect(panel.text()).toContain('已降级为仅用导入资料')
    expect(panel.text()).not.toContain('web_search_provider_failed')
  })

  it('英文界面无中文残留且无原始 key', async () => {
    await setLocale('en')
    const wrapper = await render(READY_SUMMARY)
    const panel = wrapper.find('[data-testid="web-search-summary"]')

    expect(panel.text()).toContain('Web materials')
    expect(panel.text()).toContain('Not relevant enough')
    expect(panel.text()).not.toContain('courseGeneration.materials')
    // 来源标题来自网页本身，允许非英文；只检查界面自身文案。
    expect(panel.find('.web-search-summary__hint').text()).not.toMatch(/[一-鿿]/)
  })

  it('不展示尚未接通后端的假剔除按钮', async () => {
    const wrapper = await render(READY_SUMMARY)
    expect(wrapper.find('[data-testid^="web-source-toggle-"]').exists()).toBe(false)
    expect(wrapper.find('.web-search-summary__pending').exists()).toBe(false)
  })
})
