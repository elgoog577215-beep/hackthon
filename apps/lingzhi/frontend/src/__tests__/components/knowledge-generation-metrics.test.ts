import {mount} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import Metrics from '@/components/KnowledgeGenerationMetrics.vue'
import {setLocale} from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
beforeEach(async()=>{vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh')})
it('shows measured request and first-content times with actual token counts',()=>{
  const w=mount(Metrics,{props:{observations:[{stage:'inventory',seconds:12.75,first_content_seconds:1.25,input_tokens:120,output_tokens:80,tokens_source:'provider'}]}})
  expect(w.text()).toContain('请求耗时记录');expect(w.text()).toContain('12.8');expect(w.text()).toContain('1.3');expect(w.text()).toContain('120 / 80');w.unmount()
})
it('does not turn missing first-content or token data into zero',()=>{
  const w=mount(Metrics,{props:{observations:[{stage:'inventory',seconds:4,first_content_seconds:null}]}})
  expect(w.text()).toContain('未收到正文');expect(w.text()).toContain('无数据');expect(w.text()).not.toContain('NaN');w.unmount()
})
