import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import View from '../../components/TeacherKnowledgeManager.vue'
import { setLocale } from '../../shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const mock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../utils/http', () => ({ default: mock }))

describe('knowledge generation failures', () => {
  it.each(['zh', 'en'] as const)('explains persisted budget failures in %s without starting a retry', async locale => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => locale === 'zh' ? zh : en })))
    await setLocale(locale)
    mock.get.mockResolvedValue({ data: { title: '课程', enabled: true, can_edit: true, history: [], handouts: [],
      jobs: [{ id: 'failed-job', status: 'failed', error: { code: 'AIRequestBudgetExceeded', message: 'Generic retained historical error' }, partial_text: '' }] } })
    const wrapper = mount(View, { props: { courseId: 'c' } })
    await flushPromises()
    expect(wrapper.text()).toContain(locale === 'zh' ? '输入超过' : 'input exceeds')
    expect(wrapper.text()).toContain(locale === 'zh' ? '尚未调用模型' : 'No model request was sent')
    expect(wrapper.text()).not.toContain('Generic retained historical error')
    expect(mock.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each(['zh','en'] as const)('shows compact reconnection without changing the task in %s',async locale=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>locale==='zh'?zh:en})));await setLocale(locale)
    const job={id:'same-job',status:'running',pipeline_stage:'hierarchy',phase:'model_streaming',progress:93,
      transport_retry_active_count:1,transport_retry_stage:'tree_relations'}
    mock.get.mockResolvedValue({data:{title:'课程',enabled:true,can_edit:true,history:[],handouts:[],jobs:[job],active_jobs:[job]}})
    mock.post.mockClear()
    const wrapper=mount(View,{props:{courseId:'c',treeOnly:true}});await flushPromises()
    expect(wrapper.get('[data-testid="knowledge-generation-progress"]').text()).toContain(locale==='zh'?'正在恢复模型连接':'Reconnecting to the model')
    expect(mock.post).not.toHaveBeenCalled();wrapper.unmount()
  })
})
