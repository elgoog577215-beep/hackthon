import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import AppErrorCenter from '@/components/AppErrorCenter.vue'
import { publishAppError, resolveAppReadError } from '@/utils/app-error'

describe('AppErrorCenter', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('clears only a recovered read for the same course, identity and scope', async () => {
    const wrapper = mount(AppErrorCenter, { attachTo: document.body })
    const config = { method: 'get', url: '/api/courses/a/document', params: { view: 'summary' }, identityScope: 'teacher', usageStartedAt: 20, headers: { 'X-User-Id': 'teacher-a' } }
    const failed = (request: any, title: string) => publishAppError({ isAxiosError: true, config: request, message: 'timeout', request: {} }, { title })
    failed(config, '本课读取失败')
    failed({ ...config, method: 'put' }, '保存未完成')
    failed({ ...config, url: '/api/courses/b/document' }, '其他课程读取失败')
    resolveAppReadError({ ...config, usageStartedAt: 10 })
    resolveAppReadError({ ...config, identityScope: 'learner', usageStartedAt: 30 })
    resolveAppReadError({ ...config, params: { view: 'full' }, usageStartedAt: 30 })
    await nextTick()
    expect(document.body.querySelectorAll('.app-error-notice')).toHaveLength(3)
    resolveAppReadError({ ...config, usageStartedAt: 30 })
    await nextTick()
    expect(document.body.textContent).not.toContain('本课读取失败')
    expect(document.body.textContent).toContain('保存未完成')
    expect(document.body.textContent).toContain('其他课程读取失败')
    wrapper.unmount()
  })

  it('同一异常重复发布时只保留一张错误卡', async () => {
    const wrapper = mount(AppErrorCenter, { attachTo: document.body })

    publishAppError('相同的服务反馈', { title: '课程读取失败', code: 'course_load_failed' })
    publishAppError('相同的服务反馈', { title: '课程读取失败', code: 'course_load_failed' })
    await nextTick()

    expect(document.body.querySelectorAll('.app-error-notice')).toHaveLength(1)
    expect(document.body.textContent).toContain('课程读取失败')
    wrapper.unmount()
  })
})
