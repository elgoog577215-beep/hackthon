import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

function view() {
  return { enabled:true, can_edit:true, workflow:'knowledge_first_generic_v1', source_mode:'handouts', result_version:'v1',
    document_revision:'d', knowledge_revision:'', tree:null, history:[], jobs:[], active_jobs:[], candidates:[], handouts:[], source_handouts:[],
    lesson_options:[{lesson_id:'cpu',title:'栈操作',can_generate:true,blocking_job_ids:[]}],
    atomic_runs:[{job_id:'atomic-job',lesson_id:'cpu',status:'failed',pipeline:{schema_version:'inventory_atomic_v1',revision:2,
      items:[{key:'I1',name:'入栈',claim:'插入栈顶元素',kind:'rule',sources:[{key:'S1',quote:'入栈插入栈顶元素。'}]}],
      batches:[{id:'atoms-1',status:'completed',item_keys:['I1'],tree:{knowledge_points:[{knowledge_id:'new-k',name:'入栈',statement:'插入栈顶元素'}]},
        report:{ready_for_adoption:false,issues:[{code:'question_focus_missing',point_key:'K1',inventory_key:'I1'}]}},{id:'atoms-2',status:'pending',item_keys:['I2']}]}}] }
}
beforeEach(async()=>{
  vi.restoreAllMocks();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh')
  vi.spyOn(http,'post').mockResolvedValue({data:{}})
})
it('retries only the selected saved batch after an explicit click',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.findAll('button').find(b=>b.text().includes('重新细化本批'))!.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',retry_batch_id:'atoms-1'}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
it('shows the saved inventory and batch issues without applying or restarting them',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  const panel=w.get('[data-testid="knowledge-atomic-workbench"]')
  expect(panel.text()).toContain('知识清单');expect(panel.text()).toContain('入栈');expect(panel.text()).toContain('元问题')
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})
it('uses the inventory pipeline for new lecture generations',async()=>{
  const v=view();v.atomic_runs=[];vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.findAll('button').find(b=>b.text().includes('生成本讲知识树'))!.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({pipeline:'inventory_atomic_v1',lesson_id:'cpu'}))
  w.unmount()
})
it('continues the saved task only after the user clicks',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-testid="continue-knowledge-batches"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',pipeline:'inventory_atomic_v1'}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
it('shows source doubts beside the frozen quote without treating them as verified corrections',async()=>{
  const v=view();(v.atomic_runs[0]!.pipeline as any).inventory_batches=[{id:'inventory-1',source_coverage:[],source_issues:[{source_key:'S1',quote:'原文中的可疑结论。',kind:'suspected_error',detail:'需要核对原讲义的适用条件。'}]}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-source-issues"]').text()).toContain('未核验')
  expect(w.text()).toContain('原文中的可疑结论。');expect(w.text()).toContain('需要核对原讲义的适用条件。')
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})
it('hides an empty refinement panel after the model service fails before inventory',async()=>{
  const v:any=view();v.jobs=[{id:'gateway-job',lesson_unit_id:'tree',knowledge_lesson_id:'cpu',status:'failed',error:{code:'ModelConnectionUnavailable',message:'模型服务暂时不可用'}}]
  v.atomic_runs=[{job_id:'gateway-job',lesson_id:'cpu',status:'failed',pipeline:{schema_version:'inventory_atomic_v1',revision:1,items:[],batches:[],inventory_batches:[{id:'inventory-1',status:'pending'}]}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="knowledge-atomic-workbench"]').exists()).toBe(false)
  expect(w.text()).toContain('模型服务暂未连接')
  w.unmount()
})
it('shows unresolved original passages and keeps the incomplete candidate unadoptable',async()=>{
  const v:any=view();v.candidates=[{job_id:'candidate-job',lesson_id:'cpu',tree:{revision_id:'candidate',source_mode:'handouts',categories:[],knowledge_points:[],relations:[],lessons:[],
    atomic_assessment:{ready_for_adoption:false,issues:[{code:'source_span_uncovered',severity:'blocking'}],uncovered_passages:[{key:'S2.1',source_key:'S2',text:'尾部还有一个尚未承载的重要结论。'}]}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-uncovered-passages"]').text()).toContain('尾部还有一个尚未承载的重要结论。')
  expect(w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.attributes('disabled')).toBeDefined();w.unmount()
})
it('rebuilds only leaf batches from the frozen inventory after an explicit click',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-testid="rebuild-knowledge-leaves"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',retry_batch_id:'all_atoms'}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
