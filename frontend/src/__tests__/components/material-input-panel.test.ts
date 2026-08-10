import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MaterialInputPanel from '@/components/MaterialInputPanel.vue'
import type { CourseMaterialDraft } from '@/shared/prompt-config'
import { setLocale } from '@/shared/i18n'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post, delete: vi.fn() } }))

describe('MaterialInputPanel', () => {
  beforeEach(async () => {
    post.mockReset()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
    await setLocale('zh')
  })

  const mountPanel = () => {
    let wrapper: ReturnType<typeof mount>
    wrapper = mount(MaterialInputPanel, {
      props: {
        modelValue: [],
        'onUpdate:modelValue': (value: CourseMaterialDraft[]) => wrapper.setProps({ modelValue: value }),
      },
      global: { stubs: { ElInput: true, ElSelect: true, ElOption: true } },
    })
    return wrapper
  }

  it('使用 multipart 上传真实 file 字段并回写资产', async () => {
    post
      .mockResolvedValueOnce({ data: { asset_id: 'mat-1', filename: 'notes.pdf', status: 'uploaded' } })
      .mockResolvedValueOnce({
        data: {
          document: { parse_status: 'parsed', parser_name: 'docling' },
          quality_report: {
            schema_version: 'parsed_document_quality_v2',
            status: 'ready',
            suitability: 'factual_basis',
            summary: '解析结构和来源定位可用于课程事实依据。',
            coverage: { block_count: 5, location_coverage: 1, page_count: 2 },
            observed_structure: { tables: 1, formulas: 0 },
            capabilities_missing: [],
            issues: [],
          },
          preview: [{ block_id: 'b1', kind: 'heading', text: '导数' }],
        },
      })
    const wrapper = mountPanel()
    const input = wrapper.get('input[type="file"]')
    const file = new File(['pdf'], 'notes.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(2)
    const [url, body, config] = post.mock.calls[0]!
    expect(url).toBe('/api/materials')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    expect(config).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
    expect(post.mock.calls[1]?.[0]).toBe('/api/materials/mat-1/parse')
    const latest = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as Array<{ asset_id?: string; upload_status: string }>
    expect(latest[0]).toEqual(expect.objectContaining({ asset_id: 'mat-1', upload_status: 'uploaded' }))
    expect(wrapper.text()).toContain('可作为课程依据')
  })

  it('在发起请求前展示不支持文件类型的可读错误', async () => {
    const wrapper = mountPanel()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['bin'], 'notes.exe')] })
    await input.trigger('change')
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('不支持的文件类型：exe')
  })

  it('英文模式本地化降级摘要并展示缺失解析能力', async () => {
    await setLocale('en')
    post
      .mockResolvedValueOnce({ data: { asset_id: 'mat-ocr', filename: 'scan.pdf', status: 'uploaded' } })
      .mockResolvedValueOnce({
        data: {
          document: { parse_status: 'degraded', parser_name: 'pdf_page_ocr' },
          quality_report: {
            schema_version: 'parsed_document_quality_v2',
            status: 'needs_review',
            suitability: 'teaching_reference',
            summary: '可以作为教学参考，但关键事实应结合原文件复核。',
            coverage: { block_count: 3, location_coverage: 1, page_count: 2 },
            observed_structure: { tables: 0, formulas: 0 },
            capabilities_missing: ['table_structure', 'formula_structure'],
            issues: [{ code: 'ocr_semantics_limited', severity: 'warning', message: '中文降级信息' }],
          },
          preview: [],
        },
      })
    const wrapper = mountPanel()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['pdf'], 'scan.pdf', { type: 'application/pdf' })],
    })
    await input.trigger('change')
    await flushPromises()

    expect(wrapper.text()).toContain('Usable as a teaching reference')
    expect(wrapper.text()).toContain('Table structure')
    expect(wrapper.text()).toContain('Formula structure')
    expect(wrapper.text()).not.toContain('中文降级信息')
  })
})
