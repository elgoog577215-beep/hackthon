import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CourseKnowledgeStudy from '@/components/CourseKnowledgeStudy.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useLearnerModelStore } from '@/stores/learnerModel'
import http from '@/utils/http'

vi.mock('@/utils/http',()=>({default:{get:vi.fn()},teacherRequestConfig:()=>({identityScope:'teacher'})}))
const view={schema_version:'knowledge_library_view_v3',lifecycle_status:'accepted',binding_revision_id:'base-1',revision_id:'lib-1',nodes:[
  {knowledge_id:'point-1',revision_id:'r1',node_type:'knowledge_point',parent_id:null,name:'Real point',statement:'Real rule',covered_by_course:true,status:'active',section_ids:['s1'],block_ids:[]},
]}
function mountStudy(preview=false) { return mount(CourseKnowledgeStudy,{props:{visible:true,preview},global:{stubs:{KnowledgeMasteryProfile:{name:'KnowledgeMasteryProfile',props:['profile','learningContent'],template:'<div class="profile-stub">{{profile?.nodes[0]?.name}}</div>'}}}}) }
beforeEach(()=>{
  setActivePinia(createPinia());vi.clearAllMocks()
  const course=useCourseStore();course.currentCourseId='c1';course.currentCourseVersionId='v1'
  vi.spyOn(useLearnerModelStore(),'load').mockResolvedValue(null)
})
describe('real course knowledge entry',()=>{
  it('loads formal learning assets and personal evidence through the existing course APIs',async()=>{
    vi.mocked(http.get).mockResolvedValue({data:{assets:{knowledge_library:[view]}}})
    const wrapper=mountStudy();await flushPromises()
    expect(http.get).toHaveBeenCalledWith('/api/courses/c1/learning-assets')
    expect(useLearnerModelStore().load).toHaveBeenCalledWith('c1')
    expect(wrapper.text()).toContain('Real point')
    wrapper.unmount()
  })
  it('uses the preview snapshot without loading student evidence',async()=>{
    const preview=vi.spyOn(useCourseWorkspaceStore(),'loadPreviewKnowledge').mockResolvedValue({knowledge_library:[view]})
    const wrapper=mountStudy(true);await flushPromises()
    expect(preview).toHaveBeenCalledWith('c1',true)
    expect(useLearnerModelStore().load).not.toHaveBeenCalled()
    expect(http.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Real point')
    wrapper.unmount()
  })
  it('uses the adopted tree when the legacy learner projection has points but no course bindings',async()=>{
    vi.mocked(http.get).mockImplementation(async url=>String(url).endsWith('/knowledge-first') ? {data:{enabled:true,knowledge_revision:'kb1',tree:{revision_id:'kb1',categories:[],knowledge_points:[{knowledge_id:'real',revision_id:'r1',parent_id:'',topic:'s1',name:'Adopted point',statement:'Current rule'}]}}} : {data:{assets:{knowledge_library:[{...view,nodes:view.nodes.map(n=>({...n,covered_by_course:false}))}]}}})
    const wrapper=mountStudy();await flushPromises()
    expect(http.get).toHaveBeenCalledWith('/api/courses/c1/knowledge-first',undefined)
    expect(wrapper.text()).toContain('Adopted point')
    wrapper.unmount()
  })
  it('ignores a late response after closing the knowledge entry',async()=>{
    let resolve!:(data:unknown)=>void
    vi.mocked(http.get).mockImplementation(()=>new Promise(r=>{resolve=r}))
    const wrapper=mountStudy();await wrapper.setProps({visible:false})
    resolve({data:{assets:{knowledge_library:[view]}}});await flushPromises()
    expect(wrapper.text()).not.toContain('Real point')
    expect(useLearnerModelStore().load).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
