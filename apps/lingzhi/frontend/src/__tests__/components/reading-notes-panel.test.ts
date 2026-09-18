import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReadingNotesPanel from '@/components/ReadingNotesPanel.vue'
import { useCourseStore } from '@/stores/course'
import { useNoteStore } from '@/stores/notes'
import type { Note } from '@/stores/types'

const note = (id: string, quote = '原文'): Note => ({ id, nodeId: 'n1', highlightId: quote ? `hl-${id}` : '', quote, content: `笔记 ${id}`, color: 'amber', createdAt: 1, recordType: 'note', sourceType: 'user' })
afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('ReadingNotesPanel', () => {
  it('锚定正文并避免短条重叠；手动滚动后暂停跟随，恢复时重新对齐', async () => {
    const callbacks: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => { callbacks.push(fn); return callbacks.length })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    const pinia = createPinia(); setActivePinia(pinia)
    useCourseStore().currentNode = { node_id: 'n1', node_name: '第一讲' } as any
    useNoteStore().notes = [note('a'), note('b'), note('loose', '')]
    const root = document.createElement('div'); root.id = 'content-scroll-container'
    root.innerHTML = '<span id="hl-a">原文 A</span><span id="hl-b">原文 B</span>'
    document.body.append(root)
    vi.spyOn(root, 'getBoundingClientRect').mockImplementation(() => ({ top: 100 } as DOMRect))
    Object.defineProperty(root, 'scrollHeight', { value: 2000 })
    root.querySelectorAll('span').forEach((el, i) => vi.spyOn(el, 'getBoundingClientRect').mockImplementation(() => ({ top: 400 + i * 10 - root.scrollTop } as DOMRect)))
    const wrapper = mount(ReadingNotesPanel, { props: { visible: true }, attachTo: document.body, global: { plugins: [pinia] } })
    const viewport = wrapper.get('.reading-notes-viewport').element as HTMLElement
    vi.spyOn(viewport, 'getBoundingClientRect').mockImplementation(() => ({ top: 180 } as DOMRect))
    const tick = async () => { callbacks.splice(0).forEach(fn => fn(0)); await flushPromises() }
    await tick()
    const cards = wrapper.findAll('.reading-note-strip')
    expect(cards).toHaveLength(2)
    expect(cards[0]!.attributes('style')).toContain('top: 300px')
    expect(cards[1]!.attributes('style')).toContain('top: 404px')
    expect(wrapper.get('.loose-notes').text()).toContain('记录在本讲')
    expect(viewport.scrollTop).toBe(80)
    root.scrollTop = 220; root.dispatchEvent(new Event('scroll')); await tick()
    expect(viewport.scrollTop).toBe(300)
    await wrapper.get('.reading-notes-viewport').trigger('wheel')
    root.scrollTop = 450; root.dispatchEvent(new Event('scroll')); await tick()
    expect(viewport.scrollTop).toBe(300)
    await wrapper.get('.follow-toggle').trigger('click'); await tick()
    expect(viewport.scrollTop).toBe(530)
    await wrapper.get('.reading-note-main').trigger('click')
    expect((wrapper.emitted('open')![0]![0] as any).note.id).toBe('a')
    wrapper.unmount()
  })
})
