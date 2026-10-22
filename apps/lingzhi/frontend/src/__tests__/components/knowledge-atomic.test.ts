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
it('replaces inventory, batch diagnostics and timings with one percentage bar',async()=>{
  const v:any=view();v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'failed',stage_observations:[{stage:'atomize',seconds:9}]}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="knowledge-atomic-workbench"]').exists()).toBe(false)
  expect(w.find('[data-testid="knowledge-source-issues"]').exists()).toBe(false)
  expect(w.text()).not.toContain('请求耗时记录')
  expect(w.text()).not.toContain('分批细化候选')
  expect(w.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('37')
  expect(w.get('[data-testid="knowledge-generation-progress"]').text()).toContain('37%')
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})
it('uses the inventory pipeline for new lecture generations',async()=>{
  const v=view();v.atomic_runs=[];vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.findAll('button').find(b=>b.text().includes('生成本讲知识树'))!.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({pipeline:'inventory_atomic_v1',lesson_id:'cpu',organize_hierarchy:true}))
  w.unmount()
})
it('organizes only saved leaf batches after an explicit click',async()=>{
  const v:any=view();v.atomic_runs[0].status='completed';v.atomic_runs[0].pipeline.batches[1].status='completed'
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(http.post).not.toHaveBeenCalled()
  await w.get('[data-testid="organize-knowledge-hierarchy"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',retry_batch_id:'hierarchy',organize_hierarchy:true}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
it('offers adaptive organization for an old hierarchy without restoring diagnostic panels',async()=>{
  const v:any=view();v.atomic_runs[0].status='completed';v.atomic_runs[0].pipeline.batches[1].status='completed'
  v.atomic_runs[0].pipeline.hierarchy={status:'completed',result:{schema_version:'knowledge_hierarchy_v2'}}
  vi.spyOn(http,'get').mockImplementation(async()=>({data:structuredClone(v)}))
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="organize-knowledge-hierarchy"]').exists()).toBe(true)
  expect(w.find('[data-testid="knowledge-atomic-workbench"]').exists()).toBe(false)
  v.atomic_runs[0].pipeline.hierarchy.result.schema_version='knowledge_hierarchy_v5'
  await w.findAll('button').find(b=>b.text().includes('整理本讲层级'))!.trigger('click');await flushPromises()
  expect(w.find('[data-testid="organize-knowledge-hierarchy"]').exists()).toBe(false)
  w.unmount()
})
it('shows validated streaming points while keeping the preview unadoptable',async()=>{
  const v:any=view();v.atomic_runs[0].status='running'
  v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'running',progress:85}];v.active_jobs=v.jobs
  v.lesson_options[0].blocking_job_ids=['atomic-job']
  v.generation_previews=[{job_id:'atomic-job',lesson_id:'cpu',tree:{revision_id:'preview:atomic-job',generation_preview:true,
    categories:[{id:'s',name:'栈的基本操作',parent_id:null}],knowledge_points:[{knowledge_id:'k',name:'入栈接口',statement:'插入栈顶',parent_id:'s',section_refs:['cpu']}],
    relations:[],atomic_assessment:{ready_for_adoption:false}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.text()).toContain('入栈接口')
  expect(w.text()).toContain('正在生成，已完成部分会陆续显示')
  expect(w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.attributes('disabled')).toBeDefined()
  w.unmount()
})
it('can continue after hierarchy fails with every leaf batch already saved',async()=>{
  const v:any=view();v.atomic_runs[0].pipeline.batches[1].status='completed';v.atomic_runs[0].pipeline.organize_hierarchy=true
  v.atomic_runs[0].pipeline.hierarchy={status:'pending'}
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="continue-knowledge-batches"]').exists()).toBe(true)
  await w.get('[data-testid="continue-knowledge-batches"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
it('continues the saved task only after the user clicks',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-testid="continue-knowledge-batches"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',pipeline:'inventory_atomic_v1'}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})
it('hides an empty refinement panel after the model service fails before inventory',async()=>{
  const v:any=view();v.jobs=[{id:'gateway-job',lesson_unit_id:'tree',knowledge_lesson_id:'cpu',status:'failed',error:{code:'ModelConnectionUnavailable',message:'模型服务暂时不可用'}}]
  v.atomic_runs=[{job_id:'gateway-job',lesson_id:'cpu',status:'failed',pipeline:{schema_version:'inventory_atomic_v1',revision:1,items:[],batches:[],inventory_batches:[{id:'inventory-1',status:'pending'}]}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="knowledge-atomic-workbench"]').exists()).toBe(false)
  expect(w.text()).toContain('模型连接暂不可用')
  w.unmount()
})
it('shows unresolved original passages and keeps the incomplete candidate unadoptable',async()=>{
  const v:any=view();v.candidates=[{job_id:'candidate-job',lesson_id:'cpu',tree:{revision_id:'candidate',source_mode:'handouts',categories:[],knowledge_points:[],relations:[],lessons:[],
    atomic_assessment:{ready_for_adoption:false,issues:[{code:'source_span_uncovered',severity:'blocking'}],uncovered_passages:[{key:'S2.1',source_key:'S2',text:'尾部还有一个尚未承载的重要结论。'}]}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-atomic-adoption"]').text()).toContain('候选内容需要修正')
  expect(w.text()).not.toContain('尾部还有一个尚未承载的重要结论。')
  expect(w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.attributes('disabled')).toBeDefined();w.unmount()
})
it('rebuilds only leaf batches from the frozen inventory after an explicit click',async()=>{
  const v:any=view();v.candidates=[{job_id:'atomic-job',lesson_id:'cpu',tree:{revision_id:'candidate',knowledge_points:[],categories:[],relations:[],atomic_assessment:{ready_for_adoption:false}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-testid="rebuild-knowledge-leaves"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',retry_batch_id:'all_atoms'}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})

it('shows the actual failed relation stage and allows only missing relations despite an older candidate',async()=>{
  const v:any=view();const p=v.atomic_runs[0].pipeline
  p.batches[1].status='completed';p.inventory_batches=[{status:'completed'}];p.organize_hierarchy=true
  p.hierarchy={status:'completed',result:{schema_version:'knowledge_hierarchy_v5'}}
  p.include_relations=true;p.relations={status:'pending',batches:[{id:'tree-relations-7',status:'pending'}]}
  v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'failed',phase:'failed',pipeline_stage:'hierarchy',progress:93,
    error:{code:'ModelConnectionUnavailable',stage:'tree_relations',batch_id:'tree-relations-7'}}]
  v.candidates=[{job_id:'older-job',lesson_id:'cpu',tree:{revision_id:'old',categories:[],knowledge_points:[],relations:[],relation_assessment:{proposed_count:43}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  const text=w.get('[data-testid="knowledge-generation-progress"]').text()
  expect(text).toContain(zh.knowledgeFirst.relationCandidates);expect(text).not.toContain(zh.knowledgeFirst.organizeHierarchy)
  expect(http.post).not.toHaveBeenCalled()
  await w.get('[data-testid="continue-knowledge-batches"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({resume_job_id:'atomic-job',retry_batch_id:'relations'}))
  w.unmount()
})

it('shows compact connection recovery while other parallel work reports hierarchy',async()=>{
  const v:any=view();v.atomic_runs[0].status='running'
  v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'running',phase:'model_streaming',pipeline_stage:'hierarchy',progress:93,
    transport_retry_active_count:1,transport_retry_stage:'tree_relations'}];v.active_jobs=v.jobs
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-generation-progress"]').text()).toContain('正在恢复模型连接')
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})

it('continues equivalence review before pending relations and names the actual failed stage',async()=>{
  const v:any=view();const p=v.atomic_runs[0].pipeline
  p.batches[1].status='completed';p.inventory_batches=[{status:'completed'}]
  p.organize_hierarchy=true;p.hierarchy={status:'completed',result:{schema_version:'knowledge_hierarchy_v5'}}
  p.semantic_equivalence_contract='knowledge_equivalence_v3';p.semantic_equivalence={status:'failed'}
  p.include_relations=true;p.relations={status:'pending',batches:[]}
  v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'failed',phase:'failed',progress:85,
    error:{code:'CourseDocumentConflict',stage:'semantic_equivalence_pairs'}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-generation-progress"]').text()).toContain('核对同义知识')
  expect(http.post).not.toHaveBeenCalled()
  await w.get('[data-testid="continue-knowledge-batches"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({
    resume_job_id:'atomic-job',retry_batch_id:''}))
  expect(http.post).toHaveBeenCalledTimes(1);w.unmount()
})

it('keeps the continue action when only required equivalence review remains incomplete',async()=>{
  const v:any=view();const p=v.atomic_runs[0].pipeline
  p.batches[1].status='completed';p.inventory_batches=[{status:'completed'}]
  p.organize_hierarchy=true;p.hierarchy={status:'completed',result:{schema_version:'knowledge_hierarchy_v5'}}
  p.include_relations=true;p.relations={status:'completed'}
  p.semantic_equivalence_contract='knowledge_equivalence_v3'
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.find('[data-testid="continue-knowledge-batches"]').exists()).toBe(true)
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})

it('uses unrecovered failed observations for a historical job with a stale hierarchy label',async()=>{
  const v:any=view();v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status:'failed',phase:'failed',pipeline_stage:'hierarchy',progress:93,
    stage_observations:[{stage:'tree_relations',status:'failed',request_fingerprint:'r7'},{stage:'hierarchy_subtree',status:'completed',request_fingerprint:'h1'}]}]
  vi.spyOn(http,'get').mockResolvedValue({data:v})
  const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  expect(w.get('[data-testid="knowledge-generation-progress"]').text()).toContain(zh.knowledgeFirst.relationCandidates)
  expect(http.post).not.toHaveBeenCalled();w.unmount()
})


it.each(['failed','paused','cancelled'])('keeps the current %s preview visible instead of selecting an older candidate', async(status)=>{
 const v:any=view();v.atomic_runs[0].status=status
 v.jobs=[{id:'atomic-job',knowledge_lesson_id:'cpu',status,progress:80}]
 const tree=(name:string)=>({revision_id:name,categories:[{id:'s',name:'基本操作',parent_id:null}],
  knowledge_points:[{knowledge_id:name,name,statement:'完整知识正文',parent_id:'s',section_refs:['cpu']}],relations:[]})
 v.candidates=[{job_id:'old-job',lesson_id:'cpu',tree:tree('旧候选知识')}]
 v.generation_previews=[{job_id:'atomic-job',lesson_id:'cpu',tree:{...tree('本次短知识名'),generation_preview:true}}]
 vi.spyOn(http,'get').mockResolvedValue({data:v})
 const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
 expect(w.text()).toContain('本次短知识名');expect(w.text()).not.toContain('旧候选知识')
 expect(w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.attributes('disabled')).toBeDefined()
 expect(http.post).not.toHaveBeenCalled();w.unmount()
})
