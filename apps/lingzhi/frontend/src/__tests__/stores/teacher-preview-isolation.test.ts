import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { setTeacherPreviewCourse } from '@/utils/teacher-preview'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useLearningSessionStore } from '@/stores/learningSession'
import { useNoteStore } from '@/stores/notes'
import { useAITeacherStore } from '@/stores/aiTeacher'
import http from '@/utils/http'
import { buildHandoutConceptSections } from '@/utils/handout-concepts'

vi.mock('@/utils/http', () => ({ default: {get:vi.fn(),post:vi.fn(),patch:vi.fn()},
  teacherRequestConfig:(value={})=>value, identityRequestConfig:(_scope:unknown,value={})=>value,
  identityReadRequestConfig:(_scope:unknown,value={})=>value,
  getActiveRequestIdentityScope:()=> 'teacher', identityScopeHeaders:(_scope:unknown,value={})=>value,
  withApiBase:(value:string)=>value }))

beforeEach(() => {
  setActivePinia(createPinia()); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear()
  setTeacherPreviewCourse('c')
  useCourseStore().teacherPreviewSnapshot = {course_id:'c',preview_revision:'r1',document:{sections:[]},questions:[
    {revision_id:'q1',node_id:'s1',prompt:'第一题'}, {revision_id:'q2',node_id:'s2',prompt:'第二题'},
  ]}
})
afterEach(() => { setTeacherPreviewCourse(''); vi.unstubAllGlobals() })

it('updates preview drafts from structured replies without formal writes or caches', async () => {
  const store=useAITeacherStore();await store.load('c','s1','teacher')
  const conversation=await store.openStudyDialogue({kind:'note',nodeId:'s1',quote:'Selected text'})
  conversation!.study_workspace!.draft='My manual draft'
  vi.mocked(http.post).mockResolvedValue({data:{preview_revision:'r1',reply:'Explained.',draft:'My manual draft with an example.'}})
  await store.discussStudyPreview(conversation!.conversation_id,'Add an example')
  expect(conversation!.study_workspace!.draft).toBe('My manual draft with an example.')
  expect(conversation!.messages.at(-1)?.content).toBe('Explained.')
  expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/preview/study-dialogue',expect.objectContaining({draft:'My manual draft',question:'Add an example'}),expect.anything())
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(useNoteStore().notes).toEqual([]);expect(localStorage.length).toBe(0)
})

it('does not overwrite preview edits made while the model is responding', async () => {
  const store=useAITeacherStore();await store.load('c','s1','teacher')
  const conversation=await store.openStudyDialogue({kind:'note',nodeId:'s1',quote:'Selected text'})
  let finish!: (response:any)=>void
  vi.mocked(http.post).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const pending=store.discussStudyPreview(conversation!.conversation_id,'Explain')
  conversation!.study_workspace!.draft='Newer manual text'
  finish({data:{preview_revision:'r1',reply:'Explained.',draft:'Older model text'}})
  await pending
  expect(conversation!.study_workspace!.draft).toBe('Newer manual text')
  expect(conversation!.messages.at(-1)?.status).toBe('complete')
})

it('displays preview answer chunks before completion without formal conversation writes', async () => {
  useCourseStore().teacherPreviewSnapshot.document.blocks = [{block_id:'public'}]
  const store=useAITeacherStore();await store.load('c','s1','teacher')
  let stream!: ReadableStreamDefaultController<Uint8Array>
  const body=new ReadableStream<Uint8Array>({start(controller){stream=controller}})
  const fetchMock=vi.fn().mockResolvedValue(new Response(body,{headers:{'Content-Type':'text/event-stream'}}))
  vi.stubGlobal('fetch',fetchMock)
  const pending=store.sendMessage({courseId:'c',nodeId:'s1',question:'什么是函数',displayQuestion:'讲解选中的原文',selection:'原文与我的笔记',identityScope:'teacher',contextRef:{course_id:'c',content_anchor:{block_id:'public'}}})
  const encoder=new TextEncoder()
  stream.enqueue(encoder.encode('event: answer\ndata: {"chunk":"函数"}\n\n'))
  await vi.waitFor(()=>expect(store.conversations[0]?.messages.at(-1)?.content).toBe('函数'))
  expect(store.conversations[0]?.messages.at(-1)?.status).toBe('streaming')
  stream.enqueue(encoder.encode('event: answer\ndata: {"chunk":"的输出唯一。"}\n\nevent: complete\ndata: {"preview_revision":"r1"}\n\n'))
  stream.close();await pending
  expect(store.conversations[0]?.messages.at(-1)?.content).toBe('函数的输出唯一。')
  expect(store.conversations[0]?.messages.at(-1)?.status).toBe('complete')
  expect(fetchMock).toHaveBeenCalledWith('/api/teacher/courses/c/preview/ask',expect.objectContaining({body:expect.stringContaining('"preview_revision":"r1"')}))
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body).selection).toBe('原文与我的笔记')
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body).block_ids).toEqual(['public'])
  expect(store.conversations[0]?.messages[0]?.content).toBe('讲解选中的原文')
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body).question).toBe('什么是函数')
  expect(http.post).not.toHaveBeenCalled();expect(localStorage.length).toBe(0)
})

it('keeps practice attempts in memory and sends the teacher source revision', async () => {
  const store=useCourseWorkspaceStore()
  await store.loadPractice('c','s1'); await store.startPracticeAttempt('c','q1')
  store.currentDraft={text:'答案'}; await store.savePracticeDraft('c')
  vi.mocked(http.post).mockResolvedValue({data:{feedback:{passed:true}}})
  await store.submitCurrentPractice('c')
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/preview/grade',expect.objectContaining({preview_revision:'r1',question_revision_id:'q1',answer_payload:{text:'答案'}}),expect.anything())
  expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0)
  await store.loadPractice('c','s2');expect(store.currentAttempt).toBeNull();expect(store.currentDraft).toEqual({})
})

it('rejects late grading after the preview closes', async () => {
  const store=useCourseWorkspaceStore();await store.loadPractice('c','s1');await store.startPracticeAttempt('c','q1')
  let finish!: (value:any)=>void
  vi.mocked(http.post).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const pending=store.submitCurrentPractice('c')
  setTeacherPreviewCourse('');store.$reset();finish({data:{feedback:{passed:true}}})
  await expect(pending).rejects.toThrow('preview_context_changed');expect(store.practiceResult).toBeNull()
})

it('does not migrate or persist reading position even after route exit', async () => {
  const store=useLearningSessionStore();await store.load('c')
  store.migrateLegacy('c','r1','s1','第一节',100)
  store.updatePosition({courseId:'c',courseVersionId:'r1',nodeId:'s1',nodeName:'第一节',anchor:null,fallbackScrollTop:100})
  setTeacherPreviewCourse('');await store.flush()
  expect(store.snapshot).toBeNull();expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0)
  expect(http.post).not.toHaveBeenCalled();expect(http.get).not.toHaveBeenCalled()
})

it('does not reuse formal notes when entering a preview of the same course', async () => {
  const store=useNoteStore();store.courseId='c'
  store.notes=[{id:'formal',nodeId:'s1',highlightId:'',quote:'',content:'正式笔记',color:'yellow',createdAt:0}]
  await store.loadCourseRecords('c');expect(store.notes).toEqual([])
  await store.createNote({id:'trial',nodeId:'s1',highlightId:'',quote:'',content:'试记',color:'yellow',createdAt:0})
  await store.loadCourseRecords('c');expect(store.notes).toHaveLength(1)
  expect(http.post).not.toHaveBeenCalled();expect(localStorage.length).toBe(0)
})

it('clears preview AI conversations without creating formal records or caches', async () => {
  const store=useAITeacherStore();await store.load('c','s1','teacher')
  expect(store.conversations).toHaveLength(1)
  const message={message_id:'trial',role:'assistant' as const,content:'答案',status:'complete' as const}
  await store.proposeForMessage(message,'create_note',{},{});await store.confirmProposal(message)
  setTeacherPreviewCourse('');store.clearPreviewSession()
  expect(store.conversations).toEqual([]);expect(http.post).not.toHaveBeenCalled();expect(http.get).not.toHaveBeenCalled();expect(localStorage.length).toBe(0)
})

it('loads knowledge lazily from the same preview revision and reuses it', async () => {
  const store=useCourseWorkspaceStore()
  await store.loadAssets('c');expect(http.get).not.toHaveBeenCalled()
  vi.mocked(http.get).mockResolvedValue({data:{preview_revision:'r1',assets:{knowledge_library:[{schema_version:'knowledge_library_view_v3'}]}}})
  await store.loadPreviewKnowledge('c');await store.loadPreviewKnowledge('c')
  expect(http.get).toHaveBeenCalledTimes(1)
  expect(http.get).toHaveBeenCalledWith('/api/teacher/courses/c/preview',{params:{include_assets:true}})
})

it('refreshes adopted knowledge even when the handout preview revision has not changed',async()=>{
  const store=useCourseWorkspaceStore()
  vi.mocked(http.get).mockResolvedValueOnce({data:{preview_revision:'r1',assets:{knowledge_library:[]}}})
  await store.loadPreviewKnowledge('c')
  const adopted={knowledge_library:[{schema_version:'knowledge_library_view_v3',revision_id:'adopted'}]}
  vi.mocked(http.get).mockResolvedValueOnce({data:{preview_revision:'r1',assets:adopted}})
  expect(await store.loadPreviewKnowledge('c',true)).toEqual(adopted)
  expect(http.get).toHaveBeenCalledTimes(2)
  expect(http.post).not.toHaveBeenCalled()
})

it('opens the explicitly linked preview question instead of the first question',async()=>{
  useCourseStore().teacherPreviewSnapshot!.questions.push({revision_id:'q3',node_id:'s1',prompt:'知识点对应题'})
  const store=useCourseWorkspaceStore()
  store.preparePracticeTask('c','s1','q3')
  await store.loadPractice('c','s1')
  expect(store.currentPracticeQuestion?.revision_id).toBe('q3')
  expect(http.post).not.toHaveBeenCalled()
})

it.each(['trial', 'canonical'] as const)('keeps saved handout types, answer links and concept anchors when loading %s', async (mode) => {
  const document = { course_id: 'c', title: '讲义', document_revision: 'r1', sections: [
    { section_id: 's1', title: '定义', position: 0, level: 2, attributes: {} },
  ], blocks: [
    { block_id: 'd', section_id: 's1', position: 0, status: 'final', role: 'concept', kind: 'rich_text',
      concept_refs: ['k1'], payload: { content_type: 'definition', markdown: '正式定义。' } },
    { block_id: 'q', section_id: 's1', position: 1, status: 'final', role: 'checkpoint', kind: 'rich_text',
      concept_refs: [], payload: { content_type: 'exercise', markdown: '练习。' } },
    { block_id: 'a', section_id: 's1', position: 2, status: 'final', role: 'feedback', kind: 'rich_text',
      concept_refs: ['k2'], payload: { content_type: 'answer', answer_to: 'q', markdown: '正式解答。' } },
  ] }
  const plan = { schema_version: 'course_teaching_plan_projection_v1', status: 'completed', sections: [{
    node_id: 's1', knowledge_structure: [{ knowledge_points: [{ name: '概念', knowledge_id: 'k1' }, { name: '应用', knowledge_id: 'k2' }] }],
    knowledge_relations: [{ source_name: '概念', target_name: '应用', relation_type: 'applies_to', reason: '依据定义应用。' }],
  }] }
  vi.mocked(http.get).mockResolvedValue({ data: { course_id: 'c', projection: 'canonical', document, teaching_plan: plan } })
  const store = useCourseStore()
  if (mode === 'trial') await store.loadCourse('c', { teacherTrial: true })
  else { store.prepareCourseShell('c'); await store.refreshGenerationPreview('c', 'teacher') }
  expect(store.currentTeachingPlan).toEqual(plan)
  const blocks = store.nodes[0]!.course_blocks!
  expect(blocks[0]!.payload.content_type).toBe('definition')
  expect(blocks[2]!.payload.answer_to).toBe('q')
  const concepts = buildHandoutConceptSections(store.currentTeachingPlan?.sections, [{
    id: 's1', title: '定义', anchor: '', blocks: blocks.map(b => ({
      id: b.block_id, anchor: `course-block-${b.block_id}`, content: String(b.payload.markdown), knowledge: b.concept_refs,
    })),
  }])
  expect(concepts[0]!.relations).toHaveLength(1)
  expect(concepts[0]!.nodes.map(n => n.anchor)).toEqual(['course-block-d', 'course-block-a'])
  expect(http.get).toHaveBeenCalledTimes(1)
  expect(http.post).not.toHaveBeenCalled()
  expect(localStorage.length).toBe(0)
})
