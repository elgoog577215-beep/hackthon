import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { expect, it, vi } from 'vitest'
import View from '@/components/CourseKnowledgeStudy.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import http from '@/utils/http'
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() }, teacherRequestConfig: () => ({}) }))

it('never replaces a filtered preview tree with private working knowledge', async () => {
  setActivePinia(createPinia()); vi.clearAllMocks()
  useCourseStore().currentCourseId = 'c'
  vi.spyOn(useCourseWorkspaceStore(), 'loadPreviewKnowledge').mockResolvedValue({ knowledge_tree_authoritative: true,
    knowledge_library: [{ schema_version: 'knowledge_library_view_v3', nodes: [] }] })
  const w = mount(View, { props: { visible: true, preview: true }, global: { stubs: { KnowledgeMasteryProfile: true } } })
  await flushPromises()
  expect(http.get).not.toHaveBeenCalled()
  w.unmount()
})
