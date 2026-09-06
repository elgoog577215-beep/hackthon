import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MaterialInputPanel from '@/components/MaterialInputPanel.vue'
import type { CourseMaterialDraft } from '@/shared/prompt-config'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
// 组件显式带教师身份上传（F-3：资料要落到正确教师的文件空间下），
// 所以 mock 必须同时提供 getTeacherIdentity，否则组件在发请求前就抛错。
vi.mock('@/utils/http', () => ({
  default: { post, delete: vi.fn() },
  getTeacherIdentity: () => 'teacher-test',
}))

describe('MaterialInputPanel', () => {
  beforeEach(() => post.mockReset())

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
    post.mockResolvedValue({ data: { asset_id: 'mat-1', filename: 'notes.pdf', status: 'parsed' } })
    const wrapper = mountPanel()
    const input = wrapper.get('input[type="file"]')
    const file = new File(['pdf'], 'notes.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(post).toHaveBeenCalledOnce()
    const [url, body, config] = post.mock.calls[0]!
    expect(url).toBe('/api/materials')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    expect(config).toEqual({
      headers: {
        'Content-Type': 'multipart/form-data',
        // 必须是**教师**身份：通用拦截器发的是 learner id（开发期为浏览器随机
        // id），而文件空间按教师分包，带错身份资料会落到别人名下。
        'X-User-Id': 'teacher-test',
      },
    })
    const latest = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as Array<{ asset_id?: string; upload_status: string }>
    expect(latest[0]).toEqual(expect.objectContaining({ asset_id: 'mat-1', upload_status: 'uploaded' }))
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
})
