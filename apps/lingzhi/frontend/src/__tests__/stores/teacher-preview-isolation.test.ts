import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { setTeacherPreviewCourse } from '@/utils/teacher-preview'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useLearningSessionStore } from '@/stores/learningSession'
import { useNoteStore } from '@/stores/notes'
import { useAITeacherStore } from '@/stores/aiTeacher'
import http from '@/utils/http'

vi.mock('@/utils/http', () => ({ default: {get:vi.fn(),post:vi.fn(),patch:vi.fn()},
  teacherRequestConfig:(value={})=>value, identityRequestConfig:(_scope:unknown,value={})=>value,
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

it('displays preview answer chunks before completion without formal conversation writes', async () => {
  const store=useAITeacherStore();await store.load('c','s1','teacher')
  let stream!: ReadableStreamDefaultController<Uint8Array>
  const body=new ReadableStream<Uint8Array>({start(controller){stream=controller}})
  const fetchMock=vi.fn().mockResolvedValue(new Response(body,{headers:{'Content-Type':'text/event-stream'}}))
  vi.stubGlobal('fetch',fetchMock)
  const pending=store.sendMessage({courseId:'c',nodeId:'s1',question:'什么是函数',identityScope:'teacher'})
  const encoder=new TextEncoder()
  stream.enqueue(encoder.encode('event: answer\ndata: {"chunk":"函数"}\n\n'))
  await vi.waitFor(()=>expect(store.conversations[0]?.messages.at(-1)?.content).toBe('函数'))
  expect(store.conversations[0]?.messages.at(-1)?.status).toBe('streaming')
  stream.enqueue(encoder.encode('event: answer\ndata: {"chunk":"的输出唯一。"}\n\nevent: complete\ndata: {"preview_revision":"r1"}\n\n'))
  stream.close();await pending
  expect(store.conversations[0]?.messages.at(-1)?.content).toBe('函数的输出唯一。')
  expect(store.conversations[0]?.messages.at(-1)?.status).toBe('complete')
  expect(fetchMock).toHaveBeenCalledWith('/api/teacher/courses/c/preview/ask',expect.objectContaining({body:expect.stringContaining('"preview_revision":"r1"')}))
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
