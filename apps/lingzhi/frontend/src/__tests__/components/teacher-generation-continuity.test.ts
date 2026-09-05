import TeacherLessonPlanDocument from '@/components/TeacherLessonPlanDocument.vue'
import TeacherScriptDocument from '@/components/TeacherScriptDocument.vue'
import { mergeLessonJobSnapshots, lessonJobsToObserve } from '@/stores/teacherLessonAuthoring'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherCourseWorkbench from '@/components/TeacherCourseWorkbench.vue'
import { useCourseStore } from '@/stores/course'
import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import http from '@/utils/http'

const strictProductionStage = (overrides: Record<string, unknown> = {}) => ({
  display_state: 'not_generated', task_state: 'idle', availability: 'missing', source_state: 'missing',
  latest_attempt_failed: false, update_required: false, task_ids: [], allowed_actions: [],
  counts: { total: 1, available: 0, generating: 0, failed: 0, stale: 0 }, issues: [],
  ...overrides,
})

const strictProductionSnapshot = (
  stageOverrides: Partial<Record<'outline' | 'lesson_plan' | 'script' | 'ppt', Record<string, unknown>>>,
  issues: Record<string, unknown>[] = [],
) => ({
  schema_version: 'course_production_state_v1',
  course_id: 'course-1',
  preparation_state: 'preparing',
  stages: {
    outline: strictProductionStage(stageOverrides.outline),
    lesson_plan: strictProductionStage(stageOverrides.lesson_plan),
    script: strictProductionStage(stageOverrides.script),
    ppt: strictProductionStage(stageOverrides.ppt),
  },
  lessons: [],
  issues,
})

const outlineFinishEditing = vi.fn(async () => true)
const outlineRequestAiCandidate = vi.fn(async () => null as Record<string, any> | null)
const outlineResolveAiCandidate = vi.fn(async (_accept: boolean) => true)
const outlineFocusQualityIssue = vi.fn(async () => true)
let outlineResolvedQualityReport: Record<string, any> | null = null

const mountWorkbench = (props: Record<string, unknown> = {}, documentStubs: Record<string, any> = {}) => {
  const courseId = String(props.courseId || 'course-1')
  const legacyTestProjection = useTeacherLessonAuthoringStore().productionState
  if (legacyTestProjection && !useCourseStore().teacherProductionStates[courseId]) {
    useCourseStore().setTeacherProductionState(courseId, legacyTestProjection)
  }
  return mount(TeacherCourseWorkbench, {
  props: {
    courseId: 'course-1',
    courseTitle: 'C 语言程序设计',
    generationOptions: {} as any,
    ...props,
  },
  global: {
    stubs: {
      'el-dialog': {
        props: ['modelValue'],
        template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>',
      },
      CourseReferenceTray: {
        name: 'CourseReferenceTray',
        props: ['modelValue', 'scopeTargetId', 'scopeTargetLabel', 'previousScopeTargetId', 'workflowState', 'workflowDetail', 'workflowProgress', 'workflowCanRetry', 'hideWorkflowStatus', 'readonly', 'deferPersistence', 'showCourseInformation'],
        template: '<aside data-testid="reference-tray-stub" :data-readonly="readonly ? \'true\' : \'false\'"><span v-if="hideWorkflowStatus === undefined">{{ workflowDetail }}</span><i data-testid="workflow-progress">{{ workflowProgress }}</i><button v-if="showCourseInformation !== false" data-testid="open-course-information" type="button" @click="$emit(\'open-course-information\')">课程信息</button><button v-if="workflowCanRetry && hideWorkflowStatus === undefined" data-testid="retry-workflow" type="button" @click="$emit(\'retry-workflow\')">重试生成</button><slot name="workflow-action" /></aside>',
        emits: ['open-course-information', 'retry-workflow', 'regenerate-workflow', 'source-state-change', 'update:modelValue'],
      },
      CompanionDocumentStudio: true,
      QuestionBankReviewPanel: true,
      TeacherScriptDocument: {
        name: 'TeacherScriptDocument',
        props: ['generationJob'],
        template: '<section data-testid="script-document-stub"><slot name="toolbar" /></section>',
      },
      ...documentStubs,
      MarkdownRenderer: true,
      CourseOutlineReview: {
        name: 'CourseOutlineReview',
        props: ['editable', 'variant', 'requiresConfirmation', 'lessonTypes', 'lessonTypeOptions', 'lessonTypeSavingId', 'lessonTypeError', 'lessonTypeErrorId'],
        template: '<section data-testid="inline-outline-editor" :data-mode="editable ? \'edit\' : \'view\'" :data-variant="variant"><label v-for="lesson in lessonTypes" :key="lesson.lessonUnitId" class="inline-lesson-type-control"><select :value="lesson.value" @change="$emit(\'lesson-type-change\', { lessonUnitId: lesson.lessonUnitId, lessonType: $event.target.value })"><option v-for="option in lessonTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></section>',
        emits: ['lesson-type-change', 'ai-resolved', 'quality-review-change'],
        setup(_props: unknown, { emit, expose }: any) {
          expose({
            finishEditing: outlineFinishEditing,
            requestAiCandidate: outlineRequestAiCandidate,
            requestQualityRepair: (issue: Record<string, any>) => String(issue.repair_instruction || ''),
            focusQualityIssueEditor: outlineFocusQualityIssue,
            resolveAiCandidate: async (accept: boolean) => {
              const resolved = await outlineResolveAiCandidate(accept)
              if (resolved) {
                if (accept && outlineResolvedQualityReport) emit('quality-review-change', outlineResolvedQualityReport)
                emit('ai-resolved', { accept })
              }
              return resolved
            },
            focusAiCandidate: vi.fn(async () => undefined),
          })
          return {}
        },
      },
    },
  },
  })
}


const auditSetup = (stage: 'lesson_plan' | 'script' = 'lesson_plan') => {
  const store = useTeacherLessonAuthoringStore()
  store.lessons = [1, 2].map(number => ({
    lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45, sections: [],
    plan: { working_revision_id: '', source_state: 'current', current_revision: null, ppt_assets: [] },
    script: { ready: false, sections: [], source_state: 'current' },
  })) as any
  store.jobs = [24, 68].map((progress, index) => ({
    id: `audit-job-${index + 1}`, course_id: 'course-1', lesson_unit_id: `L1-${index + 1}`,
    type: stage === 'script' ? 'teacher_lesson_script_generation' : 'teacher_lesson_plan_generation',
    status: 'running', progress, message: `正在写第${index + 1}讲`, warnings: [],
    stream_batches: { 'TP-B01': '{"sections":[{"learning_objective":"已经生成的部分教案内容' },
  })) as any
  const snapshot = strictProductionSnapshot({ [stage]: {
    display_state: 'generating', task_state: 'running', task_ids: ['audit-job-1','audit-job-2'],
    counts: { total: 2, available: 0, generating: 2, failed: 0, stale: 0 },
    latest_attempt: { attempt_id: 'batch-1', task_ids: ['audit-job-1','audit-job-2'], task_state: 'running',
      target_count: 2, completed: 0, failed: 0, progress: 46, lesson_unit_ids: ['L1-1','L1-2'], message: '整批生成进度', updated_at: '2026-09-05T23:00:00' },
  } }) as any
  snapshot.lessons = [1, 2].map(number => ({ lesson_unit_id: `L1-${number}`, title: `第${number}讲`,
    stages: { [stage]: strictProductionStage({ display_state: 'generating', task_state: 'running', task_ids: [`audit-job-${number}`] }) },
  }))
  const publish = () => useCourseStore().setTeacherProductionState('course-1', structuredClone(snapshot))
  publish()
  return {store, snapshot, publish}
}
describe('教师生成过程与当前讲保持一致', () => {
  beforeEach(() => {
    setActivePinia(createPinia()); vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockResolvedValue({data:{total:0}})
    vi.spyOn(http, 'post').mockResolvedValue({data:{status:'resumed'}})
  })
  it.each(['lesson_plan','script'] as const)('%s 当前讲显示24或68，整课显示46', async stage => {
    auditSetup(stage)
    const wrapper=mountWorkbench({initialStage:stage==='script'?'script':'lesson',initialLessonId:'L1-1'})
    expect(wrapper.findAll('.lesson-progress-ring').map(x=>x.attributes('aria-valuenow'))).toEqual(['24','68'])
    expect(wrapper.get('.context-pane-heading__progress').attributes('aria-valuenow')).toBe('24')
    expect(wrapper.get('.context-pane-heading').text()).toContain('正在写第1讲')
    if(stage==='lesson_plan') expect(wrapper.get('.lesson-generation-status em').text()).toBe('24%')
    const stageIndex=stage==='lesson_plan'?1:2
    expect(wrapper.findAll('.stage-state')[stageIndex]!.attributes('data-progress')).toBe('46')
    await wrapper.findAll('.lesson-outline-chapter-button')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('.context-pane-heading__progress').attributes('aria-valuenow')).toBe('68')
    if(stage==='lesson_plan') expect(wrapper.get('.lesson-generation-status em').text()).toBe('68%')
    wrapper.unmount()
  })
  it('只重试一讲时整课进度仍按全部三讲计算', () => {
    const { snapshot, publish } = auditSetup()
    snapshot.stages.lesson_plan.counts = { total: 3, available: 2, generating: 1, failed: 0, stale: 0 }
    snapshot.stages.lesson_plan.latest_attempt.target_count = 1
    snapshot.stages.lesson_plan.latest_attempt.progress = 24
    snapshot.lessons[1].stages.lesson_plan = strictProductionStage({ display_state: 'available', task_state: 'completed', availability: 'usable' })
    snapshot.lessons.push({ ...snapshot.lessons[1], lesson_unit_id: 'L1-3' })
    publish()
    const wrapper = mountWorkbench({ initialStage: 'lesson', initialLessonId: 'L1-1' })
    expect(wrapper.findAll('.stage-state')[1]!.attributes('data-progress')).toBe('75')
    expect(wrapper.get('.context-pane-heading__progress').attributes('aria-valuenow')).toBe('24')
    wrapper.unmount()
  })
  it('暂停教案后保留文字并停止光标', async () => {
    const {store,snapshot,publish}=auditSetup()
    const wrapper=mountWorkbench({initialStage:'lesson',initialLessonId:'L1-1'})
    expect(wrapper.get('.lesson-stream-document').text()).toContain('已经生成的部分教案内容')
    store.jobs = mergeLessonJobSnapshots(store.jobs, [{ ...store.jobs[0]!, status: 'paused', stream_batches: {} }]);snapshot.lessons[0].stages.lesson_plan.task_state='paused';publish();await flushPromises()
    expect(store.jobs[0]!.stream_batches?.['TP-B01']).toContain('已经生成的部分教案内容')
    expect(wrapper.get('.lesson-stream-document').text()).toContain('已经生成的部分教案内容')
    expect(wrapper.find('.stream-caret').exists()).toBe(false)
    expect(wrapper.find('[data-testid="lesson-course-preview"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it.each(['lesson_plan','script'] as const)('%s 目录显示暂停、排队和来源过期辅助状态', async stage => {
    const {store,snapshot,publish}=auditSetup(stage)
    store.jobs = mergeLessonJobSnapshots(store.jobs, [{ ...store.jobs[0]!, status: 'paused', stream_batches: {} }]);snapshot.lessons[0].stages[stage].task_state='paused'
    store.jobs[1]!.status='pending';snapshot.lessons[1].stages[stage].task_state='queued';publish()
    const wrapper=mountWorkbench({initialStage:stage==='script'?'script':'lesson'})
    const labels=()=>wrapper.findAll('.lesson-outline-chapter-button').map(x=>x.attributes('aria-label'))
    expect(labels()[0]).toContain('暂停');expect(labels()[0]).not.toContain('生成中')
    expect(labels()[1]).toContain('等待');expect(labels()[1]).not.toContain('生成中')
    snapshot.lessons[0].stages[stage]=strictProductionStage({display_state:'available',task_state:'completed',availability:'stale',source_state:'stale',update_required:true})
    publish();await flushPromises()
    const row=wrapper.findAll('.lesson-outline-chapter-button')[0]!
    expect(row.get('.lesson-outline-status').attributes('data-state')).toBe('stale')
    expect(row.find('small').text()).toContain('需更新')
    expect(row.attributes('aria-label')).toContain('可使用')
    expect(row.attributes('aria-label')).toContain('需更新')
    wrapper.unmount()
  })
})

describe('实时内容订阅与连接恢复',()=>{
 beforeEach(()=>{setActivePinia(createPinia());vi.restoreAllMocks();vi.spyOn(http,'get').mockResolvedValue({data:{total:0}})})
 afterEach(()=>vi.unstubAllGlobals())
 it.each(['teacher_lesson_plan_generation','teacher_lesson_script_generation'])('%s 优先观察所选第5讲，连接数不超过4',type=>{
  const jobs=Array.from({length:6},(_,i)=>({id:`job-${i+1}`,lesson_unit_id:`L1-${i+1}`,course_id:'course-1',type,status:'running',batch_position:i+1,progress:20})) as any
  expect(lessonJobsToObserve(jobs, 'L1-5', type).map(x=>x.lesson_unit_id)).toEqual(['L1-5','L1-1','L1-2','L1-3'])
 })
 it('流未到终态就正常结束时进入轮询恢复',async()=>{
  const store=useTeacherLessonAuthoringStore();store.courseId='course-1'
  store.jobs=[{id:'job-eof',course_id:'course-1',lesson_unit_id:'L1-1',type:'teacher_lesson_plan_generation',status:'running',progress:24,warnings:[]}] as any
  const poll=vi.spyOn(store,'pollJob').mockResolvedValue(undefined)
  const load=vi.spyOn(store,'load').mockResolvedValue({} as any)
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(new ReadableStream({start(controller){controller.close()}}),{status:200,headers:{'Content-Type':'text/event-stream'}})))
  await store.streamJob('course-1','job-eof')
  expect(poll).toHaveBeenCalledWith('course-1', 'job-eof', expect.any(AbortSignal));expect(load).not.toHaveBeenCalled()
  expect(store.jobs[0]!.status).toBe('running');expect(store.streamingJobIds['job-eof']).toBeUndefined()
 })
 it('重新生成已有讲义时展示新工作稿，并可查看旧讲义',async()=>{
  const {store}=auditSetup('script')
  const lesson={...store.lessons[0]!,sections:[{section_node_id:'S1',title:'概念'}],script:{...store.lessons[0]!.script,ready:true,current_revision_id:'old',sections:[{section_node_id:'S1',title:'概念',content:'上一次保存的讲义'}]}}
  const job={...store.jobs[0]!,streamed_block_content:{B1:'本次正在生成的新讲义内容'},result_sections:[]}
  const wrapper=mount(TeacherScriptDocument,{props:{courseId:'course-1',lesson:lesson as any,generating:true,generationJob:job,externalToolbar:true}})
  expect(wrapper.text()).toContain('本次正在生成的新讲义内容')
  expect(wrapper.text()).not.toContain('上一次保存的讲义')
  ;(wrapper.vm as any).beginEditing()
  expect((wrapper.vm as any).editing).toBe(false)
  await wrapper.findAll('.script-tabs button')[1]!.trigger('click')
  expect(wrapper.text()).toContain('上一次保存的讲义')
  expect(wrapper.text()).not.toContain('本次正在生成的新讲义内容')
  wrapper.unmount()
 })
})


describe('离开编辑上下文前保存', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.spyOn(http, 'get').mockResolvedValue({ data: {} })
  })
  it.each(['lesson', 'script'] as const)('%s 切讲或切阶段保存失败时保留输入，成功后再切换', async stage => {
    const store = useTeacherLessonAuthoringStore()
    store.lessons = [1, 2].map(number => ({
      lesson_unit_id: `L1-${number}`, number, title: `第${number}讲`, duration_minutes: 45,
      sections: [{ section_node_id: `S${number}`, title: '本讲概念' }],
      plan: { working_revision_id: `plan-${number}`, source_state: 'current', ppt_assets: [], current_revision: {
        revision_id: `plan-${number}`, plan: { sections: [{ node_id: `S${number}`, learning_objective: '原目标', key_points: ['原知识点'], teaching_modules: [] }] },
      } },
      script: { ready: true, source_state: 'current', current_revision_id: `script-${number}`,
        sections: [{ section_node_id: `S${number}`, title: '本讲概念', content: '原讲义' }] },
    })) as any
    const available = strictProductionStage({ display_state: 'available', availability: 'usable', task_state: 'completed' })
    const snapshot = strictProductionSnapshot({ lesson_plan: available, script: available }) as any
    snapshot.lessons = store.lessons.map(lesson => ({ lesson_unit_id: lesson.lesson_unit_id, title: lesson.title, stages: { lesson_plan: available, script: available } }))
    useCourseStore().setTeacherProductionState('course-1', snapshot)
    const save = vi.spyOn(store, stage === 'lesson' ? 'saveDraft' : 'saveScriptDraft').mockRejectedValue(new Error('保存失败'))
    vi.spyOn(store, 'load').mockResolvedValue({} as any)
    const wrapper = mountWorkbench({ initialStage: stage, initialLessonId: 'L1-1' }, { TeacherScriptDocument: false, MarkdownRenderer: false })
    const editor = wrapper.getComponent(stage === 'lesson' ? TeacherLessonPlanDocument : TeacherScriptDocument).vm as any
    editor.beginEditing()
    await flushPromises()
    await wrapper.findAll('textarea')[0]!.setValue('老师的新内容')
    const beforeUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(beforeUnload)
    expect(beforeUnload.defaultPrevented).toBe(true)
    await wrapper.findAll('.lesson-outline-chapter-button')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.lesson-outline-chapter-button')[0]!.attributes('aria-current')).toBe('page')
    expect((wrapper.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe('老师的新内容')
    await wrapper.findAll('.stage-rail nav button')[stage === 'lesson' ? 2 : 1]!.trigger('click')
    await flushPromises()
    expect((wrapper.findAll('textarea')[0]!.element as HTMLTextAreaElement).value).toBe('老师的新内容')
    expect(await (wrapper.vm as any).finishEditing()).toBe(false)
    save.mockResolvedValue({} as any)
    await wrapper.findAll('.lesson-outline-chapter-button')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.lesson-outline-chapter-button')[1]!.attributes('aria-current')).toBe('page')
    expect(JSON.stringify(save.mock.calls.at(-1))).toContain('老师的新内容')
    expect(save.mock.calls.at(-1)?.[1]).toBe('L1-1')
    wrapper.unmount()
  })
})

it('切到第六讲会释放旧订阅，两个阶段合计不超过四条流，也不控制后台任务', async () => {
  setActivePinia(createPinia())
  const store = useTeacherLessonAuthoringStore()
  store.courseId = 'course-1'
  store.jobs = ['teacher_lesson_plan_generation', 'teacher_lesson_script_generation'].flatMap(type => (
    Array.from({ length: 6 }, (_, index) => ({
      id: `${type}-${index + 1}`, type, lesson_unit_id: `L1-${index + 1}`, course_id: 'course-1',
      status: 'running', batch_position: index + 1, progress: 20,
    }))
  )) as any
  const connections = new Map<string, AbortSignal>()
  const poll = vi.spyOn(store, 'pollJob')
  const post = vi.spyOn(http, 'post')
  const remove = vi.spyOn(http, 'delete')
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    connections.set(url, init.signal as AbortSignal)
    return new Response(new ReadableStream({ start(controller) {
      init.signal?.addEventListener('abort', () => controller.close(), { once: true })
    } }), { status: 200 })
  }))
  try {
    store.focusLesson('L1-1', 'teacher_lesson_script_generation')
    await flushPromises()
    expect([...connections.values()].filter(signal => !signal.aborted)).toHaveLength(4)
    store.focusLesson('L1-6', 'teacher_lesson_script_generation')
    await flushPromises()
    expect([...connections.values()].filter(signal => !signal.aborted)).toHaveLength(4)
    expect([...connections.entries()].some(([url, signal]) => url.includes('teacher_lesson_script_generation-6/stream') && !signal.aborted)).toBe(true)
    expect(store.jobs.every(job => job.status === 'running')).toBe(true)
    expect(poll).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
    expect(remove).not.toHaveBeenCalled()
  } finally {
    store.stopObserving()
    await flushPromises()
    vi.unstubAllGlobals()
  }
  expect([...connections.values()].every(signal => signal.aborted)).toBe(true)
})
