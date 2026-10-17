import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LearningStats from '@/components/LearningStats.vue'
import LearningMatrix from '@/components/LearningMatrix.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useLearnerModelStore } from '@/stores/learnerModel'
import { useNoteStore } from '@/stores/notes'
import { setTeacherPreviewCourse } from '@/utils/teacher-preview'
import http from '@/utils/http'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn() }, teacherRequestConfig: () => ({ identityScope: 'teacher' }) }))
const view = { schema_version: 'knowledge_library_view_v3', lifecycle_status: 'accepted', binding_revision_id: 'kb1', revision_id: 'lib1', relations: [], nodes: [
  { knowledge_id: 'k1', revision_id: 'r1', node_type: 'knowledge_point', parent_id: null, name: '整数除法', statement: '向零截断', covered_by_course: true, status: 'active', section_ids: ['s1'], block_ids: [] },
] }
function setup() {
  const course = useCourseStore(); course.currentCourseId = 'c1'; course.currentCourseVersionId = 'v1'
  course.nodes = [{ node_id: 's1', node_name: '第1讲' } as any]
  const model = vi.spyOn(useLearnerModelStore(), 'load').mockResolvedValue(null)
  const notes = vi.spyOn(useNoteStore(), 'loadCourseRecords').mockResolvedValue([])
  return { course, model, notes }
}
beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); setTeacherPreviewCourse('') })
describe('LearningStats existing API integration', () => {
  it('loads current knowledge, all saved attempts and notes without showing mastery percentages', async () => {
    const { model, notes } = setup()
    vi.mocked(http.get).mockImplementation(async (url: any) => ({ data: String(url).endsWith('/history') ? { attempts: [
      { attempt_id: 'a1', course_id: 'c1', course_version_id: 'v1', task_revision_id: 'q1', status: 'graded', concept_ids: ['k1'], knowledge_revision_refs: { k1: 'r1' }, result: { passed: false, grading_confidence: .95 }, revealed_hint_levels: [], ai_support_level: 0, solution_revealed: false },
    ] } : { assets: { knowledge_library: [view] } } }) as any)
    const w = mount(LearningStats); await flushPromises()
    expect(w.text()).toContain('整数除法'); expect(w.text()).toContain('答错'); expect(w.text()).not.toContain('%')
    expect(model).toHaveBeenCalledWith('c1'); expect(notes).toHaveBeenCalledWith('c1', { throwOnError: true })
    expect(http.get).toHaveBeenCalledWith('/api/courses/c1/practice/history', { params: { view: 'all' } })
    w.unmount()
  })
  it('teacher preview loads only course knowledge, with no personal endpoints or records', async () => {
    const { model, notes } = setup(); setTeacherPreviewCourse('c1')
    vi.spyOn(useCourseWorkspaceStore(), 'loadPreviewKnowledge').mockResolvedValue({ knowledge_library: [view] } as any)
    const w = mount(LearningStats); await flushPromises()
    expect(w.text()).toContain('教师预览'); expect(w.text()).toContain('整数除法')
    expect(model).not.toHaveBeenCalled(); expect(notes).not.toHaveBeenCalled(); expect(http.get).not.toHaveBeenCalled()
    w.unmount()
  })
  it('does not turn failed history loading into an apparently empty successful profile', async () => {
    setup(); vi.mocked(http.get).mockImplementation(async (url: any) => {
      if (String(url).endsWith('/history')) throw new Error('offline')
      return { data: { assets: { knowledge_library: [view] } } } as any
    })
    const w = mount(LearningStats); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('部分学习记录读取失败')
    w.unmount()
  })
  it('ignores late course responses after switching course', async () => {
    const { course } = setup(); let finish!: (value: any) => void
    vi.mocked(http.get).mockImplementation((url: any) => String(url).includes('/c1/') ? new Promise(resolve => { finish = resolve }) as any : Promise.resolve({ data: { assets: {} } }) as any)
    const w = mount(LearningStats); course.currentCourseId = 'c2'; await flushPromises()
    finish({ data: { assets: { knowledge_library: [view] } } }); await flushPromises()
    expect(w.text()).not.toContain('整数除法'); w.unmount()
  })
  it('forwards matrix navigation to the existing course tools and retries a failed request', async () => {
    setup(); vi.mocked(http.get).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ data: { assets: { knowledge_library: [view] } } })
    const w = mount(LearningStats, { props: { closable: true } }); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('学习矩阵暂时无法读取')
    await w.get('[role="alert"] button').trigger('click'); await flushPromises()
    const child = w.findComponent(LearningMatrix)
    child.vm.$emit('knowledge', view.nodes[0]); child.vm.$emit('lecture', view.nodes[0]); child.vm.$emit('record', 'n1'); child.vm.$emit('practice', 's1', 'q1')
    expect(w.emitted('openKnowledge')?.[0]).toEqual([view.nodes[0]])
    expect(w.emitted('openLecture')?.[0]).toEqual([view.nodes[0]])
    expect(w.emitted('openRecord')?.[0]).toEqual(['n1'])
    expect(w.emitted('openPractice')?.[0]).toEqual(['s1', 'q1'])
    await w.get('[aria-label="关闭学习概况"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1); w.unmount()
  })
})
