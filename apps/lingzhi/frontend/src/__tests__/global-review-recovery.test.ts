import { mount } from '@vue/test-utils'
import { createPinia, type Pinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import CourseEvolutionWorkspace from '@/components/CourseEvolutionWorkspace.vue'
import zhMessages from '@/../public/locales/zh/translation.json'
import { setLocale } from '@/shared/i18n'
import {
  useCourseEvolutionStore,
  type CourseEvolutionPlan,
  type TeacherCourseChangeContext,
  type TeacherCourseChangePlanning,
} from '@/stores/courseEvolution'

function context(): TeacherCourseChangeContext {
  return {
    schema_version: 'teacher_course_change_context_v1',
    index_schema_version: 'teacher_course_change_index_v1',
    course_id: 'course-1',
    course_title: '大学物理',
    source_mode: 'authoring_workspace',
    ready: true,
    readiness_message: '已连接课程结构与现有教学资产',
    base_revision_vector: { teacher_outline: 'outline-1' },
    assets: [
      { asset_type: 'outline', label: '课程大纲', state: 'available', count: 24, source: 'teacher_generation_workspace', revision: 'outline-1' },
      { asset_type: 'lesson_plan', label: '教案', state: 'partial', count: 3, source: 'teacher_lesson_authoring', revision: '12' },
      { asset_type: 'script', label: '讲稿', state: 'available', count: 23, source: 'teacher_lesson_authoring', revision: '12' },
      { asset_type: 'ppt', label: 'PPT', state: 'available', count: 44, source: 'teaching_representation', revision: '12' },
      { asset_type: 'question_bank', label: '题库', state: 'missing', count: 0, source: 'question_bank', revision: '' },
    ],
    outline: [
      { node_id: 'c1', parent_node_id: 'root', node_name: '第一章 原理', node_level: 1 },
      { node_id: 's1', parent_node_id: 'c1', node_name: '1.1 力与加速度', node_level: 2 },
    ],
    units: [],
    updated_at: '2026-08-25T10:00:00Z',
    summary: { available_assets: 4, missing_assets: 1, indexed_units: 94, outline_nodes: 24 },
  }
}

function planning(overrides: Partial<TeacherCourseChangePlanning> = {}): TeacherCourseChangePlanning {
  return {
    schema_version: 'course_change_plan_v1',
    scenario_matrix_version: 'course_change_scenario_matrix_v1',
    plan_id: 'change-1',
    course_id: 'course-1',
    intent: {
      schema_version: 'course_change_intent_v1',
      intent_id: 'intent-1',
      course_id: 'course-1',
      raw_request: '所有案例都补充完整推导，但保留原始资料。',
      interpreted_goal: '扩写全课案例，并同步讲稿与 PPT。',
      scope_hint: {},
      hard_constraints: [],
      soft_preferences: [],
      protected_requirements: ['保留原始资料'],
      source_refs: [],
      signals: [],
      assumptions: [],
      blocking_questions: [],
      can_proceed_without_clarification: true,
      interpretation_revision: 'intent-1',
    },
    base_revision_vector: { teacher_outline: 'outline-1' },
    execution_strategies: ['semantic_impact'],
    strategy_status: 'resolved',
    scenario_tags: [],
    structural_operations: [],
    unit_migrations: [],
    structure_review_status: 'not_required',
    status: 'impact_ready',
    supersedes_plan_id: '',
    replan_reasons: [],
    created_at: '2026-08-25T10:00:00Z',
    updated_at: '2026-08-25T10:05:00Z',
    ...overrides,
  }
}

function plan(overrides: Partial<CourseEvolutionPlan> = {}): CourseEvolutionPlan {
  return {
    change_set_id: 'change-1',
    hypothesis_id: '',
    evidence_ids: [],
    operations: [],
    allowed_scopes: [],
    impact_summary: {},
    expected_effect: '扩写全课案例',
    status: 'pending',
    application_receipt: {},
    undo_receipt: {},
    effect_evaluation: {},
    teacher_change_planning: planning(),
    ...overrides,
  }
}

function mountWorkspace(pinia: Pinia) {
  const store = useCourseEvolutionStore(pinia)
  store.courseContext = store.courseContext || context()
  vi.spyOn(store, 'refreshProgress').mockResolvedValue({} as any)
  vi.spyOn(store, 'loadCourseContext').mockResolvedValue(store.courseContext)
  return mount(CourseEvolutionWorkspace, {
    attachTo: document.body,
    props: { modelValue: true, courseId: 'course-1', courseTitle: '大学物理' },
    global: { plugins: [pinia], stubs: { Teleport: true, Transition: false } },
  })
}


import { afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useCourseUpdateCenterStore } from '@/stores/courseUpdateCenter'
const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock, activeIdentityHeaders: () => new Headers() }))
const wrappers: any[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks(); httpMock.get.mockReset(); httpMock.post.mockReset() })
beforeEach(async () => { vi.stubGlobal('fetch', vi.fn(async () => ({ ok:true,json:async()=>zhMessages }))); await setLocale('zh') })
it('all failed candidates must still show failure detail and recovery', async () => {
 const pinia=createPinia(), store=useCourseEvolutionStore(pinia)
 store.plans=[plan({generation_status:'failed',teacher_change_planning:planning({status:'blocked'}),impact_summary:{scope_review:{reviewed_at:'now',selected_migration_ids:['m1']},candidate_bundle:{operation_count:0},affected_units:[{migration_id:'m1',unit_id:'script:b1',asset_type:'script',title:'案例',section_ids:['s1'],disposition:'rewrite_partial',candidate_status:'failed',candidate_error:'必须补充实验条件',confidence:.9}]}})]
 const w=mountWorkspace(pinia); wrappers.push(w); await flushPromises()
 expect(w.text()).toContain('必须补充实验条件')
})
it('partial application must not be presented as fully complete', async()=>{
 const pinia=createPinia(), store=useCourseEvolutionStore(pinia)
 store.plans=[plan({status:'applied',application_receipt:{status:'partial',applied_count:1,failed_count:1,unchanged_count:0}})]
 const w=mountWorkspace(pinia);wrappers.push(w);await flushPromises()
 expect(w.get('.receipt-state h3').text()).toMatch(/部分|未完成/)
})
it('undone plan must remain distinct from applied in center',()=>{
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 store.plans=[plan({status:'undone'})]
 expect(useCourseUpdateCenterStore(pinia).courseChangeSources[0]?.status).toBe('undone')
})
it('late old-course context must not overwrite current course',async()=>{
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 let resolveOld:any,resolveNew:any
 httpMock.get.mockImplementation((url:string)=>new Promise(resolve=>{if(url.includes('old'))resolveOld=resolve;else resolveNew=resolve}))
 const old=store.loadCourseContext('old');const current=store.loadCourseContext('new')
 resolveNew({data:{course_id:'new',ready:true}});await current
 resolveOld({data:{course_id:'old',ready:true}});await old
 expect(store.courseId).toBe('new');expect(store.courseContext?.course_id).toBe('new')
})
it('new analysis from a focused old plan must open its own result',async()=>{
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 store.plans=[plan({change_set_id:'old-plan'})]
 const create=vi.spyOn(store,'createCoursePlan').mockImplementation(async()=>{store.plans=[...store.plans,plan({change_set_id:'new-plan',impact_summary:{affected_units:[{migration_id:'new',asset_type:'script',title:'新的修改目标',section_ids:[],disposition:'rewrite_partial',confidence:.9}]}})];return {course_evolution_plans:store.plans}})
 const w=mountWorkspace(pinia);wrappers.push(w);await w.setProps({focusPlanId:'old-plan'});await flushPromises()
 ;(w.vm as any).startNewRequest();await flushPromises()
 await w.get('textarea').setValue('新的调整要求');await w.get('.request-composer form').trigger('submit');await flushPromises()
 expect(create).toHaveBeenCalled();expect(w.text()).toContain('新的修改目标')
})

import { routeTeacherProductionRequest } from '@/composables/useTeacherProductionAiCollaboration'
it.each(['lesson','script'] as const)('lecture deletion from %s must route to whole-course change', domain=>{
 expect(routeTeacherProductionRequest(domain,'删除第10讲，后续讲次补位上来').capability).toBe('plan_course_change')
})

it('find and replace submits exact text including empty replacement and excludes PPT', async () => {
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 const create=vi.spyOn(store,'createCoursePlan').mockResolvedValue({course_evolution_plans:[]})
 const w=mountWorkspace(pinia);wrappers.push(w);await flushPromises()
 await w.get('.request-modes button:nth-child(2)').trigger('click')
 await w.get('.literal-replacement input[type=text]').setValue('  原词  ')
 await w.get('.request-composer form').trigger('submit');await flushPromises()
 expect(create).toHaveBeenCalledWith(expect.objectContaining({literalReplacement:{before:'  原词  ',after:''}}))
 expect(create.mock.calls[0]![0].assetTypes).not.toContain('ppt')
})
it('history is reachable from the embedded center and includes undone plans', async () => {
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 store.plans=[plan({status:'undone',request_text:'可追溯的修改'})]
 const w=mountWorkspace(pinia);wrappers.push(w);await w.setProps({standalone:true,embeddedInCenter:true});await flushPromises()
 Element.prototype.scrollIntoView=vi.fn()
 ;(w.vm as any).showHistory();await flushPromises()
 expect(w.get('.recent-changes').text()).toContain('可追溯的修改')
 expect(w.get('.recent-changes').text()).toContain('已撤销')
})
it('input conflicts offer correction rather than a blind retry', async () => {
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 store.plans=[plan({generation_status:'failed',impact_summary:{scope_review:{reviewed_at:'now',selected_migration_ids:['m1']},affected_units:[{migration_id:'m1',unit_id:'script:b1',asset_type:'script',title:'案例',section_ids:['s1'],disposition:'rewrite_partial',candidate_status:'failed',candidate_error:'来源已变化',candidate_error_detail:{retryable:false},confidence:.9}]}})]
 const w=mountWorkspace(pinia);wrappers.push(w);await flushPromises()
 expect(w.text()).not.toContain('只重试失败项')
 await w.get('.candidate-error button').trigger('click')
 expect(w.find('.correction-bar').exists()).toBe(true)
})
it('moving and deleting a lecture carries its nested teaching content', async () => {
 const pinia=createPinia(),store=useCourseEvolutionStore(pinia)
 const nodes=[{provisional_id:'a',title:'第一讲',parent_ref:'root',source_node_ids:['a']},{provisional_id:'a1',title:'讲内内容',parent_ref:'a',source_node_ids:['a1']},{provisional_id:'b',title:'第二讲',parent_ref:'root',source_node_ids:['b']}]
 store.plans=[plan({teacher_change_planning:planning({execution_strategies:['structural_regeneration'],structure_review_status:'pending'}),impact_summary:{change_kind:'structural',proposed_outline:nodes}})]
 const w=mountWorkspace(pinia);wrappers.push(w);await flushPromises()
 const first=w.findAll('.structure-edit-row')[0]!
 expect(first).toBeTruthy()
 await first.get('button[title="下移"]').trigger('click')
 expect(w.findAll('.structure-edit-row input').map((i:any)=>i.element.value)).toEqual(['第二讲','第一讲','讲内内容'])
 await w.findAll('.structure-edit-row')[1]!.get('button[title="删除"]').trigger('click')
 expect(w.findAll('.structure-edit-row input').map((i:any)=>i.element.value)).toEqual(['第二讲'])
})
