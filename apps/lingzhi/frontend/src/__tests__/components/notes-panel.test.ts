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

  it('用学习者看得懂的状态文案，并为已归档记录提供可用的恢复动作', async () => {
    const noteStore = useNoteStore()
    noteStore.notes = [
      { id:'note-1', nodeId:'n1', recordType:'note', content:'随手记', createdAt:4, status:'active' },
      { id:'issue-1', nodeId:'n1', recordType:'issue', content:'这里有个疑问', createdAt:3, status:'awaiting_verification' },
      { id:'archived-issue', nodeId:'n1', recordType:'issue', content:'旧问题', createdAt:2, status:'archived' },
      { id:'archived-review', nodeId:'n1', recordType:'review_task', content:'复习定义', createdAt:1, status:'archived' },
    ] as any
    const updateStatus = vi.spyOn(noteStore, 'updateRecordStatus').mockResolvedValue({ id:'updated' } as any)
    const wrapper = mount(NotesPanel)

    expect(wrapper.findAll('.record-status').map(status => status.text())).toEqual(['已记录', '待验证', '已归档', '已归档'])
    expect(wrapper.findAll('.record-type').map(type => type.text())).toEqual(['笔记', '问题', '问题', '复习'])
    expect(wrapper.text()).not.toContain('active')
    await wrapper.get('[data-record-id="archived-issue"] .record-actions button:last-child').trigger('click')
    await wrapper.get('[data-record-id="archived-review"] .record-actions button:last-child').trigger('click')
    expect(updateStatus).toHaveBeenNthCalledWith(1, 'archived-issue', 'reopened')
    expect(updateStatus).toHaveBeenNthCalledWith(2, 'archived-review', 'pending')
  })

  it('状态更新失败时说明失败原因，并允许直接重试', async () => {
    const noteStore = useNoteStore()
    noteStore.notes = [{ id:'issue-1', nodeId:'n1', recordType:'issue', content:'待解决的问题', createdAt:1, status:'open' }] as any
    const updateStatus = vi.spyOn(noteStore, 'updateRecordStatus')
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({ id:'issue-1' } as any)
    const wrapper = mount(NotesPanel)
    const row = wrapper.get('[data-record-id="issue-1"]')

    await row.get('.record-actions button:last-child').trigger('click')
    await flushPromises()
    expect(row.get('[role="alert"]').text()).toContain('状态没有保存')
    expect(row.get('.record-actions button:last-child').text()).toContain('重试')
    await row.get('.record-actions button:last-child').trigger('click')
    await flushPromises()
    expect(updateStatus).toHaveBeenCalledTimes(2)
    expect(row.find('[role="alert"]').exists()).toBe(false)
  })

  it('状态保存等待中会显示进度并阻止重复提交', async () => {
    const noteStore = useNoteStore()
    noteStore.notes = [{ id:'issue-1', nodeId:'n1', recordType:'issue', content:'待解决的问题', createdAt:1, status:'open' }] as any
    let finishUpdate!: (value: any) => void
    const pending = new Promise<any>(resolve => { finishUpdate = resolve })
    vi.spyOn(noteStore, 'updateRecordStatus').mockReturnValue(pending)
    const wrapper = mount(NotesPanel)
    const row = wrapper.get('[data-record-id="issue-1"]')
    const action = row.get('.record-actions button:last-child')

    await action.trigger('click')
    expect(action.attributes('disabled')).toBeDefined()
    expect(action.attributes('aria-busy')).toBe('true')
    expect(action.text()).toContain('正在更新')
    finishUpdate({ id:'issue-1' })
    await flushPromises()
    expect(row.get('.record-actions button:last-child').attributes('disabled')).toBeUndefined()
  })

  it('快速笔记保存失败后保留正文并展示保存成功状态', async () => {
    const noteStore = useNoteStore()
    vi.spyOn(noteStore, 'createNote')
      .mockResolvedValueOnce(null as any)
      .mockResolvedValueOnce({ id:'quick-note-retry', nodeId:'n1', recordType:'note', content:'保留的笔记', status:'active' } as any)
    const wrapper = mount(NotesPanel)
    await wrapper.get('.quick-note-trigger').trigger('click')
    await wrapper.get('.quick-note-composer textarea').setValue('保留的笔记')
    await wrapper.get('.quick-note-composer').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.quick-note-composer textarea').element).toHaveProperty('value', '保留的笔记')
    expect(wrapper.get('.quick-note-error').text()).toContain('保存失败')
    await wrapper.get('.quick-note-composer').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.quick-note-composer').exists()).toBe(false)
    expect(wrapper.get('.quick-note-saved').text()).toContain('已保存')
  })

  it('moves keyboard focus to the quick note input when opening the composer', async () => {
    const wrapper = mount(NotesPanel, { attachTo:document.body })
    await wrapper.get('.quick-note-trigger').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    wrapper.unmount()
  })

})
