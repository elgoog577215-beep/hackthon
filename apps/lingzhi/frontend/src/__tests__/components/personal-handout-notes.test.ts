import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ createNote: vi.fn(), updateNote: vi.fn(), deleteNote: vi.fn(), listNotes: vi.fn() }))
vi.mock('@/api/study', () => ({ studyApi: api, StudyApiError: class extends Error { constructor(public status: number, message: string) { super(message) } } }))
import Notes from '@/components/PersonalHandoutNotes.vue'
import { StudyApiError, type StudyNote } from '@/api/study'
import { activeLocale } from '@/shared/i18n'
const note: StudyNote = { id: 'n1', revision_id: 'r1', section_id: 's1', section_title: '第一讲', block_id: 'b1', block_title: '定义', content_type: 'definition', quote: '原文定义', anchor_prefix: '', anchor_suffix: '', content: '我的理解', kind: 'note', question_state: 'open', important: false, version: 1, source_type: 'self', created_at: '2026-11-01', updated_at: '2026-11-01', source_sha256: '', location_status: 'current' }
let wrapper: VueWrapper
function page(notes: StudyNote[] = [note], ownerId = 'student-a') {
  wrapper = mount(Notes, { props: { ownerId, materialId: 'm1', revisionId: 'r1', notes, currentSection: 's1', sections: [{ id: 's1', title: '第一讲', blocks: [{ block_id: 'b1', title: '定义', content_type: 'definition', content: '原文定义' }] }] as any }, global: { stubs: { MathText: { props: ['content'], template: '<span>{{ content }}</span>' }, MarkdownRenderer: { props: ['content'], template: '<div>{{ content }}</div>' } } } })
  return wrapper
}
beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear(); activeLocale.value = 'zh' })
afterEach(() => wrapper?.unmount())
describe('personal notes', () => {
  it('keeps a mark without requiring a written comment and binds it to the passage', async () => {
    const view = page([]); api.createNote.mockResolvedValue({ ...note, content: '', kind: 'mark', important: true })
    ;(view.vm as any).create({ section_id: 's1', block_id: 'b1', quote: '原文定义' }, 'mark')
    await flushPromises(); await view.get('.note-editor footer button').trigger('click'); await flushPromises()
    expect(api.createNote).toHaveBeenCalledWith('m1', expect.objectContaining({ quote: '原文定义', content: '', kind: 'mark', block_id: 'b1', revision_id: 'r1' }))
    expect(view.emitted('saved')).toHaveLength(1)
  })
  it('compares a stale note while preserving the student draft until an explicit choice', async () => {
    const view = page(); await view.get('.note-card-open').trigger('click')
    await view.get('textarea').setValue('刚写好的理解')
    api.updateNote.mockRejectedValue(new StudyApiError(409, '版本冲突')); api.listNotes.mockResolvedValue({ entries: [{ ...note, version: 2, content: '另一处保存的内容' }] })
    await view.get('.note-editor footer button').trigger('click'); await flushPromises()
    expect(view.get('textarea').element).toHaveProperty('value', '刚写好的理解')
    expect(view.get('.notes-conflict').text()).toContain('另一处保存的内容')
    expect(view.get('.note-editor footer button').attributes('disabled')).toBeDefined()
  })
  it('applies an AI draft only to the matching unchanged draft, never saving automatically', async () => {
    const view = page(); await view.get('.note-card-open').trigger('click')
    ;(view.vm as any).receiveSuggestion({ noteId: 'n1', noteVersion: 1, content: 'AI 整理的理解', messageId: 'a1', basedOnDraft: '我的理解' })
    await flushPromises(); expect(view.get('textarea').element).toHaveProperty('value', 'AI 整理的理解')
    expect(api.updateNote).not.toHaveBeenCalled()
    await view.get('textarea').setValue('我又补充了一句')
    ;(view.vm as any).receiveSuggestion({ noteId: 'n1', noteVersion: 1, content: '稍晚的 AI 内容', messageId: 'a2', basedOnDraft: 'AI 整理的理解' })
    await flushPromises(); expect(view.get('textarea').element).toHaveProperty('value', '我又补充了一句')
    expect(view.get('.notes-suggestion').text()).toContain('稍晚的 AI 内容')
  })
  it('does not erase edits typed while a save is in flight', async () => {
    let finish!: (v: StudyNote) => void
    api.updateNote.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const view = page(); await view.get('.note-card-open').trigger('click')
    await view.get('textarea').setValue('第一次编辑'); await view.get('.note-editor footer button').trigger('click')
    await view.get('textarea').setValue('请求期间继续编辑'); finish({ ...note, version: 2, content: '第一次编辑' }); await flushPromises()
    expect(view.get('textarea').element).toHaveProperty('value', '请求期间继续编辑')
    expect((view.vm as any).currentDraft('n1')).toBe('请求期间继续编辑')
  })
  it('shows failures from card actions even with the editor closed', async () => {
    const view = page(); api.updateNote.mockRejectedValue(new Error('无法保存重点'))
    await view.get('.personal-note-card header button').trigger('click'); await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('无法保存重点')
  })
  it('restores a draft for its owner without leaking it to another student', async () => {
    const view = page(); await view.get('.note-card-open').trigger('click'); await view.get('textarea').setValue('未保存的个人理解'); view.unmount()
    const restored = page(); expect(restored.get('textarea').element).toHaveProperty('value', '未保存的个人理解'); restored.unmount()
    const other = page([], 'student-b'); expect(other.find('textarea').exists()).toBe(false)
  })
  it('keeps editing controls compact and restores the exact list filters on return', async () => {
    const view = page()
    await view.get('input[type="search"]').setValue('理解')
    await view.get('.notes-filters select').setValue('open')
    await view.get('.note-card-open').trigger('click')
    expect(view.find('.reading-aid-controls').exists()).toBe(false)
    expect(view.text()).not.toContain('编辑中，点击保存')
    expect(view.find('.reading-aid-scope').exists()).toBe(false)
    expect(view.find('input[type="search"]').exists()).toBe(false)
    expect(view.find('.notes-filters').exists()).toBe(false)
    expect(view.get('textarea').attributes('aria-label')).toBe('我的记录')
    await view.get('.note-editor header button').trigger('click')
    expect(view.get('input[type="search"]').element).toHaveProperty('value', '理解')
    expect(view.get('.notes-filters select').element).toHaveProperty('value', 'open')
    expect(view.get('.notes-legacy').attributes('open')).toBeUndefined()
  })
  it('does not attach a newer unsaved note to the old save response', async () => {
    const view = page([])
    let finish!: (value: StudyNote) => void
    api.createNote.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    ;(view.vm as any).create({ content: '第一条新笔记' })
    await flushPromises(); await view.get('.note-editor footer button').trigger('click')
    ;(view.vm as any).create({ content: '第二条还没保存' })
    await flushPromises()
    finish({ ...note, content: '第一条新笔记' }); await flushPromises()
    expect(view.get('textarea').element).toHaveProperty('value', '第二条还没保存')
    expect(view.get('.note-editor header').text()).toContain('返回列表')
    const draft = JSON.parse(sessionStorage.getItem('lingzhi-personal-notes:student-a:m1:r1:new')!)
    expect(draft.id).toBe(''); expect(draft.content).toBe('第二条还没保存')
  })
  it('does not send another note draft after switching editors during save-and-discuss', async () => {
    const view = page([note, { ...note, id: 'n2', content: '另一条笔记' }])
    let finish!: (value: StudyNote) => void
    api.updateNote.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await view.findAll('.note-card-open')[0]!.trigger('click')
    await view.get('textarea').setValue('需要保存的新理解')
    await view.findAll('.note-editor footer button')[1]!.trigger('click')
    await (view.vm as any).open({ ...note, id: 'n2', content: '另一条笔记' })
    finish({ ...note, version: 2 }); await flushPromises()
    expect(view.emitted('discuss')).toBeUndefined()
    expect(view.get('textarea').element).toHaveProperty('value', '另一条笔记')
  })
  it('shows a stale AI suggestion as unavailable and retains the current draft', async () => {
    const view = page([{ ...note, version: 2 }]); await view.get('.note-card-open').trigger('click')
    ;(view.vm as any).receiveSuggestion({ noteId: 'n1', noteVersion: 1, content: '旧建议', messageId: 'a1', basedOnDraft: '我的理解' })
    await flushPromises()
    expect(view.get('.notes-suggestion').text()).toContain('旧版笔记')
    expect(view.get('.notes-suggestion button').attributes('disabled')).toBeDefined()
    expect(view.get('textarea').element).toHaveProperty('value', '我的理解')
  })
  it('ignores save callbacks after leaving the owned note panel', async () => {
    const view = page(); await view.get('.note-card-open').trigger('click')
    let finish!: (value: StudyNote) => void
    api.updateNote.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await view.get('textarea').setValue('离开前编辑'); await view.get('.note-editor footer button').trigger('click'); view.unmount()
    finish({ ...note, version: 2 }); await flushPromises()
    expect(view.emitted('saved')).toBeUndefined()
  })
  it('reopens an unchanged note discussion without incrementing its version and can restore its saved suggestion', async () => {
    const view = page(); await view.get('.note-card-open').trigger('click')
    await view.findAll('.note-editor footer button')[1]!.trigger('click'); await flushPromises()
    expect(api.updateNote).not.toHaveBeenCalled()
    expect(view.emitted('discuss')?.[0]).toEqual([{ note, draft: note.content }])
    view.unmount()
    const restored = page(); await flushPromises()
    await restored.findAll('.note-editor footer button')[1]!.trigger('click'); await flushPromises()
    expect(api.updateNote).not.toHaveBeenCalled()
    expect(restored.emitted('discuss')?.[0]).toEqual([{ note, draft: note.content }])
    ;(restored.vm as any).receiveSuggestion({ noteId: 'n1', noteVersion: 1, content: '历史讨论的整理稿', messageId: 'a1', basedOnDraft: note.content })
    await flushPromises()
    expect(restored.get('textarea').element).toHaveProperty('value', '历史讨论的整理稿')
    expect(restored.emitted('saved')).toBeUndefined()
  })
})


it('separates editing from the list and enables save only for changed content', async () => {
  const view = page(); await view.get('.note-card-open').trigger('click')
  expect(view.find('.personal-note-card').exists()).toBe(false)
  expect(view.find('.notes-legacy').exists()).toBe(false)
  expect(view.get('[data-action="save"]').attributes('disabled')).toBeDefined()
  await view.get('textarea').setValue('新的理解')
  expect(view.get('[data-action="save"]').attributes('disabled')).toBeUndefined()
  await view.get('.note-editor header button').trigger('click')
  expect(view.find('.personal-note-card').exists()).toBe(true)
  await view.get('.note-card-open').trigger('click')
  expect(view.get('textarea').element).toHaveProperty('value', '新的理解')
})
