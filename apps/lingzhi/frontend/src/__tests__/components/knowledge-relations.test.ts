import {flushPromises,mount} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import Manager from '@/components/TeacherKnowledgeManager.vue'
import http from '@/utils/http'
import {setLocale} from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'

const tree = {revision_id:'base',status:'accepted',source_mode:'handouts',categories:[],knowledge_points:[{knowledge_id:'k1',revision_id:'p1',name:'栈',statement:'栈先进后出',section_refs:['cpu']}],relations:[],lessons:[{topic:'cpu',title:'栈',knowledge_ids:['k1']}],source_handouts:[]}
function view(){return {enabled:true,can_edit:true,workflow:'knowledge_first_generic_v1',source_mode:'handouts',result_version:'v',document_revision:'d',knowledge_revision:'base',tree,history:[tree],jobs:[],active_jobs:[],candidates:[],handouts:[],source_handouts:[],lesson_options:[{lesson_id:'cpu',title:'栈',can_generate:true,blocking_job_ids:[]}]}}
it('analyzes a completed unadopted candidate independently while preserving its adoption block',async()=>{
  const v:any=view();v.candidates=[{lesson_id:'cpu',job_id:'source-candidate',tree:{...tree,status:'candidate',revision_id:'candidate',
    atomic_assessment:{ready_for_adoption:false,issues:[{code:'source_focus_pending',severity:'blocking'}]}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v});const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  const button=w.get('[data-testid="generate-knowledge-relations"]');expect(button.attributes('disabled')).toBeUndefined()
  expect(w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.attributes('disabled')).toBeDefined()
  await button.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({
    pipeline:'knowledge_relations_v1',relation_source_job_id:'source-candidate'}))
  w.unmount()
})
beforeEach(async()=>{vi.restoreAllMocks();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh');vi.spyOn(http,'post').mockResolvedValue({data:{}})})
it('starts relation analysis separately without regenerating knowledge points',async()=>{
  vi.spyOn(http,'get').mockResolvedValue({data:view()});const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-testid="generate-knowledge-relations"]').trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/generate/tree',expect.objectContaining({pipeline:'knowledge_relations_v1',lesson_id:'cpu'}));expect(http.post).toHaveBeenCalledTimes(1)
  expect(w.find('.content-tree').exists()).toBe(true);w.unmount()
})
it('keeps relation adoption disabled until the owner reviews the suggestions',async()=>{
  const v:any=view();const candidate={...tree,revision_id:'candidate',relation_assessment:{ready_for_adoption:true,semantics_verified:false,proposed_count:1}}
  v.candidates=[{lesson_id:'cpu',job_id:'rjob',tree:candidate}]
  vi.spyOn(http,'get').mockResolvedValue({data:v});const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  const adopt=w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!;expect(adopt.attributes('disabled')).toBeDefined()
  await w.get('[data-testid="confirm-knowledge-relations"]').setValue(true);await adopt.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/adopt/rjob',expect.objectContaining({confirm_relations:true}));w.unmount()
})
it('lets the owner omit a suggestion while adopting the others',async()=>{
  const v:any=view();v.candidates=[{lesson_id:'cpu',job_id:'rjob',tree:{...tree,revision_id:'candidate',relations:[
    {id:'r1',source_id:'k1',target_id:'k2',type:'applies_to',reason:'具体应用'},
    {id:'r2',source_id:'k1',target_id:'k2',type:'prerequisite',reason:'待核对的必要性'},
  ],relation_assessment:{ready_for_adoption:true,proposed_ids:['r1','r2'],proposed_count:2}}}]
  vi.spyOn(http,'get').mockResolvedValue({data:v});const w=mount(Manager,{props:{courseId:'c',treeOnly:true}});await flushPromises()
  await w.get('[data-relation-id="r2"]').setValue(false)
  await w.get('[data-testid="confirm-knowledge-relations"]').setValue(true)
  await w.findAll('button').find(b=>b.text().includes('采用这版知识树'))!.trigger('click');await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/knowledge-first/adopt/rjob',expect.objectContaining({selected_relation_ids:['r1']}));w.unmount()
})
