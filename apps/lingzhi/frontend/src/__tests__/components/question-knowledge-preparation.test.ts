import {mount,flushPromises}from '@vue/test-utils'
import {describe,it,vi,expect,beforeEach}from 'vitest'
import Component from '@/components/QuestionKnowledgePreparation.vue'
const {get,post}=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('@/utils/http',()=>({default:{get,post},teacherRequestConfig:(v={})=>v,teacherReadRequestConfig:(v={})=>v}))
vi.mock('@/shared/i18n',()=>({t:(_key:string,fallback?:string)=>fallback||_key}))
const tree={revision_id:'candidate',knowledge_points:[{knowledge_id:'K',name:'测试知识',statement:'完整知识'}],mastery_criteria:[{criterion_id:'C',name:'判据',readiness:'ready'},{criterion_id:'D',name:'有疑点',readiness:'needs_review'}],atomic_assessment:{ready_for_adoption:true,issues:[{severity:'review',message:'待核对提示'}]},relation_assessment:{ready_for_adoption:true,proposed_ids:['R']}}
beforeEach(()=>{get.mockReset();post.mockReset();get.mockResolvedValue({data:{can_edit:true,document_revision:'doc',knowledge_revision:'base',blocking_job_ids:[],candidates:[{lesson_id:'lecture',job_id:'job',tree}]}});post.mockResolvedValue({data:{adopted:true}})})
describe('question knowledge preparation',()=>{
 it('confirms the exact existing candidate only after explicit acknowledgement; leaves pending structures and relations for review',async()=>{
  const w=mount(Component,{props:{courseId:'course',lessonId:'lecture'}});await flushPromises()
  expect(w.text()).toContain('1');expect(post).not.toHaveBeenCalled()
  expect(w.get('[data-testid="confirm-question-baseline"]').attributes('disabled')).toBeDefined()
  await w.get('input[type=checkbox]').setValue(true)
  await w.get('[data-testid="confirm-question-baseline"]').trigger('click');await flushPromises()
  expect(post).toHaveBeenCalledWith('/api/courses/course/knowledge-first/adopt/job',expect.objectContaining({document_revision:'doc',knowledge_revision:'base',confirm_atomic_review:true,confirm_relations:true,selected_relation_ids:[]}),expect.any(Object))
  expect(w.emitted('adopted')).toHaveLength(1)
 })
 it('does not select another lecture or adopt while another task is active',async()=>{
  const w=mount(Component,{props:{courseId:'course',lessonId:'other'}});await flushPromises();expect(w.find('[data-testid="confirm-question-baseline"]').exists()).toBe(false);w.unmount()
  get.mockResolvedValueOnce({data:{can_edit:true,blocking_job_ids:['running'],candidates:[{lesson_id:'lecture',job_id:'job',tree}]}})
  const blocked=mount(Component,{props:{courseId:'course',lessonId:'lecture'}});await flushPromises();expect(blocked.get('[data-testid="confirm-question-baseline"]').attributes('disabled')).toBeDefined();expect(post).not.toHaveBeenCalled()
 })
})
