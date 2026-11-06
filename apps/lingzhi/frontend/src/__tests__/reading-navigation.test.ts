import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useReadingNavigation } from '@/composables/useReadingNavigation'

function fixture() {
  const root = document.createElement('main')
  root.innerHTML = '<section id="lecture"><div id="block" data-block-id="b"><details class="handout-block--answer"><summary>Answer</summary>Answer</details></div></section>'
  document.body.append(root)
  root.getBoundingClientRect = () => ({ top: 100 } as DOMRect)
  const block = root.querySelector<HTMLElement>('#block')!
  block.getBoundingClientRect = () => ({ top: 500 } as DOMRect)
  root.scrollTo = vi.fn()
  const after = vi.fn()
  let navigation!: ReturnType<typeof useReadingNavigation>
  const wrapper = mount({ setup() { navigation = useReadingNavigation(ref(root), after); return () => null } })
  return { root, block, navigation, after, close: () => { wrapper.unmount(); root.remove() } }
}
describe('shared reading navigation', () => {
  it('follows an exact reference without opening answers or moving focus', async () => {
    const f = fixture(), focus = vi.spyOn(f.block, 'focus')
    await f.navigation.navigate('block', { source: 'reference', referenceId: 'b:r2', rect: () => ({ top: 720 } as DOMRect) })
    expect(f.root.scrollTo).toHaveBeenCalledWith({ top: 596, behavior: 'instant' })
    expect(f.navigation.referenceId.value).toBe('b:r2')
    expect(f.root.querySelector('details')!.open).toBe(false)
    expect(focus).not.toHaveBeenCalled()
    expect(f.after).toHaveBeenCalledTimes(1)
    f.close()
  })
  it('lets a new body gesture cancel a pending follower navigation', async () => {
    const f = fixture()
    const pending = f.navigation.navigate('block', { source: 'reference' })
    f.navigation.interact(new Event('wheel'))
    expect(await pending).toBe(false)
    expect(f.root.scrollTo).not.toHaveBeenCalled()
    expect(f.navigation.owner.value).toBe('body')
    f.close()
  })
  it('opens a clicked answer only, keeping other answers folded on lecture jumps', async () => {
    const f = fixture()
    await f.navigation.navigate('lecture')
    expect(f.root.querySelector('details')!.open).toBe(false)
    await f.navigation.navigate('block')
    expect(f.root.querySelector('details')!.open).toBe(true)
    expect(document.activeElement).toBe(f.block)
    f.close()
  })
  it('ignores typing, cancels stale work on unmount, and accepts reading keys', async () => {
    const f = fixture()
    f.navigation.claim('reference')
    f.navigation.interact(new KeyboardEvent('keydown', { key: 'a' }))
    expect(f.navigation.owner.value).toBe('reference')
    f.navigation.interact(new KeyboardEvent('keydown', { key: 'PageDown' }))
    expect(f.navigation.owner.value).toBe('body')
    const pending = f.navigation.navigate('block'); f.close(); await nextTick()
    expect(await pending).toBe(false)
    expect(f.root.scrollTo).not.toHaveBeenCalled()
  })
})
