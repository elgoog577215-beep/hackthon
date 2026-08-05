import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationDialog from '@/components/CourseGenerationDialog.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

/**
 * 联网检索是敏感能力：教师必须能看到开关、默认不联网、
 * 开启后请求里带上明确的 web_material_search。
 */
describe('CourseGenerationDialog 联网资料开关', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  const mountDialog = () => mount(CourseGenerationDialog, {
    props: { modelValue: true },
    global: {
      stubs: {
        Teleport: true,
        MaterialInputPanel: { template: '<div class="material-stub" />' },
      },
    },
  })

  const submit = async (wrapper: ReturnType<typeof mountDialog>) => {
    await wrapper.get('#course-subject').setValue('线性代数基础')
    await wrapper.find('.generation-dialog__footer .primary-button').trigger('click')
    await flushPromises()
    return wrapper.emitted('generate')?.[0]?.[0] as { options: Record<string, unknown> }
  }

  it('默认不联网，开关处于关闭状态', async () => {
    const wrapper = mountDialog()
    const toggle = wrapper.find('[data-testid="web-material-search"]')

    expect(toggle.exists()).toBe(true)
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
  })

  it('未开启时请求里的联网检索显式为 false', async () => {
    const payload = await submit(mountDialog())
    expect(payload.options.web_material_search).toEqual({ enabled: false })
  })

  it('开启后请求里带上联网检索', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-material-search"]').setValue(true)

    const payload = await submit(wrapper)
    expect(payload.options.web_material_search).toEqual({ enabled: true })
  })

  it('联网开关与题库联网补充是两个独立开关', async () => {
    const wrapper = mountDialog()
    // 题库补充默认开启，联网资料默认关闭，两者不应互相牵连。
    await wrapper.find('[data-testid="web-material-search"]').setValue(true)

    const payload = await submit(wrapper)
    expect(payload.options.web_material_search).toEqual({ enabled: true })
    expect(payload.options.web_question_enrichment).toEqual({ enabled: true })
  })

  it('中文界面显示联网说明，且不出现原始 key', async () => {
    const wrapper = mountDialog()
    const text = wrapper.text()

    expect(text).toContain('本次生成允许联网检索')
    expect(text).toContain('默认不联网')
    expect(text).not.toContain('courseGeneration.materials.webSearch')
  })

  it('英文界面显示联网说明，且没有中文残留', async () => {
    await setLocale('en')
    const wrapper = mountDialog()
    await flushPromises()
    const section = wrapper.findAll('.web-enrichment-setting').at(-1)!

    expect(section.text()).toContain('Allow web search for this generation')
    expect(section.text()).toContain('never past paywalls or logins')
    expect(section.text()).not.toMatch(/[一-鿿]/)
  })
})
