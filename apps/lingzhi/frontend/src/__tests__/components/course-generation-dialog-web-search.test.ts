import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationDialog from '@/components/CourseGenerationDialog.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

/**
 * 合并后教师端有两个层次的控制：
 *  - 团队的「联网研究」开关（retrieval）决定是否检索，默认关闭；
 *  - 我方的「并入课程资料库」开关（web_material_ingest）决定检索结果是否落成资料资产。
 * 后者只在前者打开时才有意义，因此仅在开启检索后出现。
 */
describe('CourseGenerationDialog 联网资料控制', () => {
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
    return wrapper.emitted('generate')?.[0]?.[0] as { options: Record<string, any> }
  }

  it('默认不联网，检索开关处于关闭状态', async () => {
    const wrapper = mountDialog()
    const toggle = wrapper.find('[data-testid="web-retrieval"]')

    expect(toggle.exists()).toBe(true)
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
  })

  it('未开启检索时不显示资料入库开关', async () => {
    const wrapper = mountDialog()
    expect(wrapper.find('[data-testid="web-material-ingest"]').exists()).toBe(false)
  })

  it('未开启时请求里的检索授权显式为 false', async () => {
    const payload = await submit(mountDialog())
    expect(payload.options.retrieval).toEqual({ enabled: false })
  })

  it('开启检索后请求里带上授权', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)

    const payload = await submit(wrapper)
    expect(payload.options.retrieval).toEqual({ enabled: true })
  })

  it('开启检索后出现入库开关，且默认入库', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)
    await flushPromises()
    const ingest = wrapper.find('[data-testid="web-material-ingest"]')

    expect(ingest.exists()).toBe(true)
    expect((ingest.element as HTMLInputElement).checked).toBe(true)

    // 默认入库时不必额外发字段，保持载荷精简。
    const payload = await submit(wrapper)
    expect(payload.options.web_material_ingest).toBeUndefined()
  })

  it('教师关闭入库时请求里显式声明只引用不落库', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)
    await flushPromises()
    await wrapper.find('[data-testid="web-material-ingest"]').setValue(false)

    const payload = await submit(wrapper)
    expect(payload.options.retrieval).toEqual({ enabled: true })
    expect(payload.options.web_material_ingest).toEqual({ skip_ingest: true })
  })

  it('中文界面显示入库说明，且不出现原始 key', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)
    await flushPromises()

    expect(wrapper.text()).toContain('把联网资料并入课程资料库')
    expect(wrapper.text()).not.toContain('courseGeneration.materials.webSearch')
  })

  it('英文界面显示入库说明，且没有中文残留', async () => {
    await setLocale('en')
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)
    await flushPromises()
    const section = wrapper.findAll('.web-enrichment-setting').at(-1)!

    expect(section.text()).toContain('course material library')
    expect(section.text()).not.toMatch(/[一-鿿]/)
  })
})
