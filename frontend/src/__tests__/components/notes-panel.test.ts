import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NotesPanel from '@/components/NotesPanel.vue'
import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'

function currentNode() {
  return {
    node_id: 'n1',
    parent_node_id: 'root',
    node_name: '向量空间',
    node_level: 2,
    node_content: '向量空间正文',
    node_type: 'original' as const,
    generation_status: 'completed' as const,
    generated_chars: 6,
  }
}

describe('NotesPanel quick note', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const courseStore = useCourseStore()
    courseStore.currentCourseId = 'c1'
    courseStore.currentNode = currentNode()
    courseStore.nodes = [currentNode()]
    useNoteStore().courseId = 'c1'
  })

  it('在学习记录页把随手记保存为当前章节的正式学习记录', async () => {
    const noteStore = useNoteStore()
    const createNote = vi.spyOn(noteStore, 'createNote').mockResolvedValue({
      id: 'quick-note-1',
      nodeId: 'n1',
      highlightId: '',
      quote: '',
      title: '线性组合需要同一数域',
      content: '线性组合需要同一数域\n复习时再补一个反例',
      color: 'amber',
      createdAt: Date.now(),
      sourceType: 'user',
      recordType: 'note',
      status: 'active',
    })
    const wrapper = mount(NotesPanel)

    await wrapper.get('.quick-note-trigger').trigger('click')
    await wrapper.get('.quick-note-composer textarea').setValue('  线性组合需要同一数域\n复习时再补一个反例  ')
    await wrapper.get('.quick-note-composer').trigger('submit')
    await flushPromises()

    expect(createNote).toHaveBeenCalledWith(expect.objectContaining({
      nodeId: 'n1',
      quote: '',
      title: '线性组合需要同一数域',
      content: '线性组合需要同一数域\n复习时再补一个反例',
      sourceType: 'user',
      recordType: 'note',
      status: 'active',
      origin: 'user_quick_note',
      metadata: { record_subtype: 'quick_note' },
    }))
    expect(wrapper.find('.quick-note-composer').exists()).toBe(false)
  })

  it('没有当前章节时禁用随手记并解释原因', () => {
    useCourseStore().currentNode = null

    const wrapper = mount(NotesPanel)

    expect(wrapper.get('.quick-note-trigger').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('请先选择一个课程章节')
  })
})
