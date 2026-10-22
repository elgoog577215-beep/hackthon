import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, onMounted, onUnmounted, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ReadingCompanionSurface from '@/components/ReadingCompanionSurface.vue'

describe('one reading companion across inline and full presentation', () => {
  let wrapper: VueWrapper | undefined
  let anchor: HTMLElement
  let full: HTMLElement
  const mounted = vi.fn(), disposed = vi.fn()
  const Session = defineComponent({
    setup() {
      const draft = ref(''), answer = ref('waiting')
      onMounted(mounted); onUnmounted(disposed)
      return { draft, answer }
    },
    template: '<section data-session="same"><textarea v-model="draft" /><button @click="answer = \'complete\'">finish</button><p>{{ answer }}</p></section>',
  })
  beforeEach(() => {
    mounted.mockClear(); disposed.mockClear()
    anchor = document.createElement('div'); anchor.dataset.studyCompanionAnchor = ''
    full = document.createElement('aside'); full.id = 'full-companion'
    document.body.append(anchor, full)
  })
  afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.replaceChildren() })
  async function start(target: HTMLElement | null = anchor) {
    wrapper = mount(ReadingCompanionSurface, {
      props: { anchor: target, fullTarget: '#full-companion', visible: true },
      slots: { default: Session }, attachTo: document.body,
    })
    await flushPromises()
    return wrapper
  }
  async function click(testId: string) {
    const button = document.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)
    expect(button).not.toBeNull(); button!.click(); await flushPromises()
  }
  it('opens at the passage, expands and returns without recreating the session or clearing the draft', async () => {
    await start()
    const session = anchor.querySelector('[data-session]')!
    const textarea = session.querySelector('textarea')!
    textarea.value = 'unfinished follow-up'; textarea.dispatchEvent(new Event('input'))
    await click('companion-expand')
    expect(full.querySelector('[data-session]')).toBe(session)
    expect((full.querySelector('textarea') as HTMLTextAreaElement).value).toBe('unfinished follow-up')
    await click('companion-return-inline')
    expect(anchor.querySelector('[data-session]')).toBe(session)
    expect(mounted).toHaveBeenCalledTimes(1); expect(disposed).not.toHaveBeenCalled()
  })
  it('collapse keeps the session alive and resumes the same answer', async () => {
    await start()
    await click('companion-collapse')
    expect(disposed).not.toHaveBeenCalled()
    anchor.querySelector<HTMLButtonElement>('[data-session] button')!.click()
    await click('companion-reopen')
    expect(anchor.textContent).toContain('complete')
    expect(mounted).toHaveBeenCalledTimes(1)
  })
  it('hiding and reopening the panel does not terminate its session', async () => {
    const view = await start()
    await view.setProps({ visible: false }); await view.setProps({ visible: true })
    expect(mounted).toHaveBeenCalledTimes(1); expect(disposed).not.toHaveBeenCalled()
  })
  it('moves the same session to the new anchor without leaving it under the previous passage', async () => {
    const view = await start()
    const second = document.createElement('div'); document.body.append(second)
    const session = anchor.querySelector('[data-session]')
    await view.setProps({ anchor: second })
    expect(second.querySelector('[data-session]')).toBe(session)
    expect(anchor.querySelector('[data-session]')).toBeNull()
  })
  it('uses the full surface when the current source has no exact inline anchor', async () => {
    await start(null)
    expect(full.querySelector('[data-session]')).not.toBeNull()
    expect(document.querySelector('[data-testid="companion-return-inline"]')).toBeNull()
  })
  it('does not teleport into a detached historical source', async () => {
    const detached = document.createElement('div')
    await start(detached)
    expect(detached.querySelector('[data-session]')).toBeNull()
    expect(full.querySelector('[data-session]')).not.toBeNull()
  })
  it('falls back to the full surface if a course rerender removes its anchor', async () => {
    await start()
    const session = anchor.querySelector('[data-session]')
    anchor.remove(); await flushPromises()
    expect(full.querySelector('[data-session]')).toBe(session)
    expect(disposed).not.toHaveBeenCalled()
  })
  it('preserves the reading position while expanding or returning', async () => {
    const scroll = document.createElement('div'); scroll.dataset.readingScroll = ''
    document.body.append(scroll); scroll.append(anchor); scroll.scrollTop = 145
    await start()
    await click('companion-expand')
    expect(scroll.scrollTop).toBe(145)
    await click('companion-return-inline')
    expect(scroll.scrollTop).toBe(145)
  })
})
