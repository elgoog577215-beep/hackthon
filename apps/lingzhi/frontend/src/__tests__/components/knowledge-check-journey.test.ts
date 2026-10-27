import { mount,flushPromises } from '@vue/test-utils'
import { beforeEach,expect,it,vi } from 'vitest'
import Journey from '@/components/KnowledgeCheckJourney.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
const http=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('@/utils/http',()=>({default:http}))
const props={courseId:'c',knowledgeId:'K',knowledgeRevision:'KR',preview:false}
const options={global:{stubs:{MarkdownRenderer:{props:['content'],template:'<div>{{content}}</div>'}}}}
const view={criteria:[{criterion_id:'C',revision_id:'CR',name:'区分两个量',observable_performance:'分别判断变化',has_next:true,
 measurement:{status:'unassessed',latest_score:null,max_score:2,independent_successes:0}}]}
beforeEach(async()=>{vi.clearAllMocks();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh');http.get.mockResolvedValue({data:view})})
it('teacher preview never loads or writes learner attempts',async()=>{
 const w=mount(Journey,{props:{...props,preview:true},...options});await flushPromises()
 expect(http.get).not.toHaveBeenCalled();expect(http.post).not.toHaveBeenCalled();expect(w.text()).toContain('教师预览');w.unmount()
})
it('uses original attempts for checkpoint feedback and retains assisted status',async()=>{
 http.post.mockImplementation(async(url:string)=>{
  if(url.endsWith('/target'))return {data:{status:'available',task_revision_id:'T',question:{prompt:'说明两者的变化'}}}
  if(url.endsWith('/attempts'))return {data:{attempt:{attempt_id:'A',revision:1,status:'in_progress'}}}
  if(url.includes('/hints/'))return {data:{hint:{text:'先分别观察'},attempt:{attempt_id:'A',revision:2,status:'in_progress'}}}
  return {data:{attempt:{attempt_id:'A',revision:3,status:'graded'},result:{status:'graded',passed:true,support_level:1,checkpoint_feedback:[{checkpoint_id:'p',label:'判断变化',met:true,feedback:'判断完整'}]}}}
 })
 const w=mount(Journey,{props,...options});await flushPromises()
 expect(w.text()).toContain('尚未检查')
 await w.get('[data-testid=check-start]').trigger('click');await flushPromises()
 await w.get('textarea').setValue('我的判断和理由')
 await w.get('[data-testid=check-hint]').trigger('click');await flushPromises()
 expect(w.text()).toContain('先分别观察')
 await w.get('[data-testid=check-submit]').trigger('click');await flushPromises()
 expect(w.text()).toContain('判断完整');expect(w.text()).toContain('提示后完成')
 const submitted=http.post.mock.calls.find(([url])=>String(url).endsWith('/submit'))!
 expect(submitted[1].expected_revision).toBe(2);expect(submitted[1].answer_payload.text).toBe('我的判断和理由')
 expect(w.emitted('graded')).toHaveLength(1);w.unmount()
})
it('late responses cannot replace a newly selected knowledge point',async()=>{
 let finish:(v:any)=>void=()=>{};http.get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const w=mount(Journey,{props,...options});await w.setProps({knowledgeId:'J',knowledgeRevision:'JR'});await flushPromises()
 finish({data:{criteria:[{...view.criteria[0],name:'迟到的旧标准'}]}});await flushPromises()
 expect(w.text()).not.toContain('迟到的旧标准');w.unmount()
})
