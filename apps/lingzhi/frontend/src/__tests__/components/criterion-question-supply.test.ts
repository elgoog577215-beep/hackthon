import { mount,flushPromises } from '@vue/test-utils'
import { beforeEach,expect,it,vi } from 'vitest'
import Supply from '@/components/CriterionQuestionSupply.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
const http=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('@/utils/http',()=>({default:http,teacherRequestConfig:()=>({identityScope:'teacher'})}))
const props={courseId:'c',knowledgeId:'K',knowledgeRevision:'KR',criterionId:'C',criterionRevision:'CR'}
beforeEach(async()=>{vi.clearAllMocks();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh');http.get.mockResolvedValue({data:{can_generate:true,available_count:0,pending_count:0,node_id:'L',knowledge_baseline_revision:'kb',job:null}})})
it('calls the existing bank rebuild with exact criterion and knowledge revisions',async()=>{
 http.post.mockResolvedValue({data:{job_id:'J',status:'queued'}})
 const w=mount(Supply,{props});await flushPromises();await w.get('[data-testid=criterion-generate]').trigger('click');await flushPromises()
 expect(http.post.mock.calls[0][0]).toBe('/api/courses/c/question-bank/rebuild')
 expect(http.post.mock.calls[0][1]).toMatchObject({scope:'nodes',mode:'incremental',knowledge_ids:['K'],knowledge_baseline_revision:'kb',criterion_revision_refs:{C:'CR'},retrieval_enabled:false})
 w.unmount()
})
it('does not start another job when the course bank is already running',async()=>{
 http.get.mockResolvedValue({data:{can_generate:true,available_count:0,pending_count:0,node_id:'L',knowledge_baseline_revision:'kb',job:{job_id:'J',status:'running',related:true}}})
 const w=mount(Supply,{props});await flushPromises()
 expect(w.get('[data-testid=criterion-generate]').attributes('disabled')).toBeDefined();expect(http.post).not.toHaveBeenCalled();w.unmount()
})
