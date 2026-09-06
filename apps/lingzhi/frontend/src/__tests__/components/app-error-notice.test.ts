import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppErrorNotice from '@/components/AppErrorNotice.vue'

describe('AppErrorNotice', () => {
  it('先展示中文名和归纳原因，技术详情默认折叠', async () => {
    const wrapper = mount(AppErrorNotice, {
      props: {
        presentation: {
          title: '课程读取失败',
          summary: '服务暂时无法连接，请稍后重试。',
          technicalDetail: '错误码: provider_unavailable\n请求编号: req_12345678',
          code: 'provider_unavailable',
          requestId: 'req_12345678',
          status: 503,
          retryable: true,
        },
        dismissible: true,
      },
    })

    expect(wrapper.get('strong').text()).toBe('课程读取失败')
    expect(wrapper.get('p').text()).toContain('服务暂时无法连接')
    expect(wrapper.get('details').attributes()).not.toHaveProperty('open')
    expect(wrapper.get('code').text()).toContain('provider_unavailable')

    await wrapper.get('header button').trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })
})
