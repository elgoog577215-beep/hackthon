import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import AppErrorCenter from '@/components/AppErrorCenter.vue'
import { publishAppError } from '@/utils/app-error'

describe('AppErrorCenter', () => {
  afterEach(() => {
    document.body.innerHTML = ''
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
