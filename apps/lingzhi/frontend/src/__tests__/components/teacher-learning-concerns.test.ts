import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import TeacherLearningConcerns from '@/components/TeacherLearningConcerns.vue'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import http from '@/utils/http'
vi.mock('@/utils/http',()=>({default:{get:vi.fn(),post:vi.fn()},teacherRequestConfig:()=>({})}))
beforeEach(()=>{setActivePinia(createPinia());vi.clearAllMocks();vi.mocked(http.get).mockResolvedValue({data:{roster_count:3,evidence_students:2,no_data_students:1,release_id:'r',available_releases:['r'],snapshot_id:'s',unattributed_attempts:0,shared_goals:[],topics:[{topic_id:'t',title:'链式法则',knowledge_id:'k',knowledge_revision_id:'kr',node_id:'n',evidence_students:2,no_data_students:1,repeated_failure_students:1,failed_students:1,assisted_students:1,independent_pass_students:0,unknown_students:0,evidence:[]}]}})})
it('shows roster coverage and requests a change only after the teacher chooses a concern',async()=>{
 const store=useCourseEvolutionStore();vi.spyOn(store,'load').mockResolvedValue({})
 const generate=vi.spyOn(store,'createCoursePlan').mockImplementation(async()=>{store.plans=[{change_set_id:'new-plan',teacher_change_planning:{}} as any];return {}})
 const w=mount(TeacherLearningConcerns,{props:{courseId:'c'}});await flushPromises()
 expect(w.text()).toContain('3');expect(w.text()).toContain('链式法则');expect(generate).not.toHaveBeenCalled()
 await w.get('[data-testid="teacher-concern-suggest"]').trigger('click');await flushPromises()
 expect(generate).toHaveBeenCalledWith(expect.objectContaining({instruction:expect.stringContaining('s'),assetTypes:['course_content','question_bank']}))
 expect(w.emitted('openPlan')?.[0]?.[0]).toEqual({planId:'new-plan',sectionId:'n'})
 w.unmount()
})
