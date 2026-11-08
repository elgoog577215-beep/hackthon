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

  it('distinguishes a search miss from an empty notebook and clears the query', async () => {
    const store = useNoteStore()
    store.notes = [{ id:'note-1', nodeId:'n1', recordType:'note', content:'线性组合', summary:'线性组合', createdAt:1 }] as any
    const wrapper = mount(NotesPanel)
    await wrapper.get('input[type="search"]').setValue('不存在的内容')
    expect(wrapper.text()).toContain('没有找到相关内容')
    expect(wrapper.text()).not.toContain('笔记本还是空的')
    await wrapper.get('.records-empty button').trigger('click')
    expect(wrapper.find('.records-empty').exists()).toBe(false)
    expect(wrapper.text()).toContain('线性组合')
  })

  it('按课程树顺序分组，并能在笔记本里管理优先级和标签', async () => {
    const courseStore = useCourseStore()
    courseStore.nodes = [currentNode(), { ...currentNode(), node_id: 'n2', node_name: '图论' }]
    vi.spyOn(courseStore, 'getLinearNodes').mockReturnValue([
      { ...currentNode(), node_id: 'n2', node_name: '图论' },
      currentNode(),
    ] as any)
    const noteStore = useNoteStore()
    noteStore.notes = [
      { id:'note-vector', nodeId:'n1', recordType:'note', content:'向量记录', summary:'向量记录', createdAt:2, priority:'medium', tags:['线性代数'] },
      { id:'note-graph', nodeId:'n2', recordType:'note', content:'路径记录', summary:'路径记录', createdAt:1, priority:'low', tags:['旧标签'] },
    ] as any
    const updatePriority = vi.spyOn(noteStore, 'updateNotePriority').mockResolvedValue(true)
    const updateTags = vi.spyOn(noteStore, 'updateNoteTags').mockResolvedValue(true)
    const wrapper = mount(NotesPanel)

    await wrapper.findAll('.records-tools button')[0]!.trigger('click')
    expect(wrapper.findAll('.record-group-heading').map(heading => heading.text())).toEqual(['图论1', '向量空间1'])
    expect(wrapper.get('[data-record-id="note-graph"]').text()).toContain('旧标签')

    const graphRow = wrapper.get('[data-record-id="note-graph"]')
    await graphRow.get('.record-priority select').setValue('high')
    expect(updatePriority).toHaveBeenCalledWith('note-graph', 'high')
    await graphRow.get('.record-tags-edit').trigger('click')
    await graphRow.get('.record-tag-form input').setValue('图论，最短路径')
    await graphRow.get('.record-tag-form').trigger('submit')
    expect(updateTags).toHaveBeenCalledWith('note-graph', ['图论', '最短路径'])
  })

  it('标签保存失败时保留编辑内容并给出重试提示', async () => {
    const noteStore = useNoteStore()
    noteStore.notes = [{ id:'note-1', nodeId:'n1', recordType:'note', content:'待分类笔记', createdAt:1, tags:['旧标签'] }] as any
    vi.spyOn(noteStore, 'updateNotePriority').mockResolvedValue(false)
    vi.spyOn(noteStore, 'updateNoteTags').mockResolvedValue(false)
    const wrapper = mount(NotesPanel)
    const row = wrapper.get('[data-record-id="note-1"]')

    await row.get('.record-priority select').setValue('high')
    await flushPromises()
    expect((row.get('.record-priority select').element as HTMLSelectElement).value).toBe('medium')
    expect(row.get('.record-priority-error').text()).toContain('优先级保存失败')
    await row.get('.record-tags-edit').trigger('click')
    await row.get('.record-tag-form input').setValue('新标签')
    await row.get('.record-tag-form').trigger('submit')

    expect(row.get('.record-tag-form input').element).toHaveProperty('value', '新标签')
    expect(row.get('.record-tag-error').text()).toContain('保存失败')
  })

  it('moves keyboard focus to the quick note input when opening the composer', async () => {
    const wrapper = mount(NotesPanel, { attachTo:document.body })
    await wrapper.get('.quick-note-trigger').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    wrapper.unmount()
  })

})
