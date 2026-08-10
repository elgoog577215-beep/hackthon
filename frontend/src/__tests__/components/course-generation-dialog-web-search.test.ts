import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseGenerationDialog from '@/components/CourseGenerationDialog.vue'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post } }))

const readyPreflight = {
  schema_version: 'generation_preflight_v1',
  preflight_id: 'gpf-web-search',
  status: 'ready',
  acceptance_required: false,
  provider: { status: 'ready', probe_status: 'passed', active_route: 'primary' },
  retrieval: { requested: true, available: true, status: 'ready' },
  materials: { count: 0, readable: 0 },
  capacity: { recommended_concurrency: 2, estimated_calls: 27, estimated_sections: 8 },
  issues: [],
}

/** 教师端只暴露一个真实生效的「联网研究」开关。 */
describe('CourseGenerationDialog 联网资料控制', () => {
  beforeEach(async () => {
    post.mockReset()
    post.mockResolvedValue({ data: readyPreflight })
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

  it('不暴露尚未闭环的二次入库开关', async () => {
    const wrapper = mountDialog()
    expect(wrapper.find('[data-testid="web-material-ingest"]').exists()).toBe(false)
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)
    await flushPromises()
    expect(wrapper.find('[data-testid="web-material-ingest"]').exists()).toBe(false)
  })

  it('未开启时请求里的检索授权显式为 false', async () => {
    const payload = await submit(mountDialog())
    expect(payload.options.retrieval).toEqual({ enabled: false })
  })

  it('开启检索后只下发联网授权，合格资料自动进入证据链', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-testid="web-retrieval"]').setValue(true)

    const payload = await submit(wrapper)
    expect(payload.options.retrieval).toEqual({ enabled: true })
    expect(payload.options.web_material_ingest).toBeUndefined()
  })

  it('英文界面的联网开关没有中文残留', async () => {
    await setLocale('en')
    const wrapper = mountDialog()
    const section = wrapper.get('[data-testid="web-retrieval"]')
      .element.closest('label')!

    expect(section.textContent).toContain('Web research')
    expect(section.textContent).not.toMatch(/[一-鿿]/)
  })
})
