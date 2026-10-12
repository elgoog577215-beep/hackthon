import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCompanionWelcome } from '@/composables/useCompanionWelcome'

describe('first course welcome', () => {
  let scopes: ReturnType<typeof effectScope>[] = []
  beforeEach(() => localStorage.clear())
  afterEach(() => { scopes.forEach(scope => scope.stop()); scopes = []; vi.restoreAllMocks() })
  function start(available = true, user = 'learner-a') {
    const ready = ref(available), identity = ref(user), scope = effectScope()
    scopes.push(scope)
    const welcome = scope.run(() => useCompanionWelcome(ready, identity))!
    return { ...welcome, ready, identity }
  }

  it('waits for a ready course and never opens for an absent learner identity', async () => {
    const welcome = start(false)
    expect(welcome.visible.value).toBe(false)
    welcome.ready.value = true
    await nextTick()
    expect(welcome.visible.value).toBe(true)
    welcome.ready.value = false
    await nextTick()
    expect(welcome.visible.value).toBe(false)
    expect(start(true, '').visible.value).toBe(false)
  })

  it('acknowledgement survives reload and other courses, but is isolated by learner', async () => {
    const welcome = start()
    expect(welcome.visible.value).toBe(true)
    welcome.dismiss()
    expect(welcome.visible.value).toBe(false)
    expect(start().visible.value).toBe(false)
    welcome.ready.value = false
    await nextTick()
    welcome.ready.value = true
    await nextTick()
    expect(welcome.visible.value).toBe(false)
    welcome.identity.value = 'learner-b'
    await nextTick()
    expect(welcome.visible.value).toBe(true)
  })

  it('does not persist a dismissed state just because a preview or loading screen was opened', () => {
    start(false)
    expect(localStorage.length).toBe(0)
    expect(start().visible.value).toBe(true)
  })

  it('still dismisses for the session when browser storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('unavailable') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('unavailable') })
    const welcome = start()
    expect(welcome.visible.value).toBe(true)
    expect(() => welcome.dismiss()).not.toThrow()
    welcome.ready.value = false
    await nextTick()
    welcome.ready.value = true
    await nextTick()
    expect(welcome.visible.value).toBe(false)
  })
})
