import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LearningCompanion from '@/components/LearningCompanion.vue'
const mountCompanion = () => mount(LearningCompanion, { global: { stubs: { Teleport: true } } })

describe('learning companion safe dragging', () => {
  it('reuses the existing welcome bubble as the explicit help host and preserves it across closing',async()=>{
    const wrapper=mount(LearningCompanion,{props:{helpOpen:true,welcome:true},global:{stubs:{Teleport:true}}})
    expect(wrapper.findAll('.companion-reminder')).toHaveLength(1)
    expect(wrapper.find('.companion-welcome p').exists()).toBe(false)
    const host=wrapper.get('[data-companion-help-host]').element
    await wrapper.get('.reminder-heading button').trigger('click')
    expect(wrapper.emitted('close-help')).toHaveLength(1)
    await wrapper.setProps({helpOpen:false,welcome:false})
    await wrapper.setProps({helpOpen:true})
    expect(wrapper.get('[data-companion-help-host]').element).toBe(host)
    wrapper.unmount()
  })
  let resize: ResizeObserverCallback
  let height = 600
  beforeEach(() => {
    height = 600
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return { x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: height, width: 1000, height, toJSON: () => ({}) }
    })
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resize = callback }
      observe() {}
      disconnect() {}
    })
  })
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('follows dragging across the viewport, then snaps without opening chat', async () => {
    const wrapper = mountCompanion()
    const pet = wrapper.get('[data-testid="companion-open"]')
    await pet.trigger('pointerdown', { button: 0, pointerId: 1, clientX: 950, clientY: 540 })
    await pet.trigger('pointermove', { pointerId: 1, clientX: 300, clientY: 180 })
    expect(Number(wrapper.get('.companion-pet').attributes('data-x'))).toBeGreaterThanOrEqual(0)
    expect(Number(wrapper.get('.companion-pet').attributes('data-x'))).toBeLessThan(500)
    expect(Number(wrapper.get('.companion-pet').attributes('data-y'))).toBeGreaterThanOrEqual(0)
    await pet.trigger('pointerup', { pointerId: 1 })
    pet.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
    expect(wrapper.emitted('open')).toBeUndefined()
    expect(wrapper.get('.companion-pet').attributes('data-edge')).toBe('left')
    await pet.trigger('pointerdown', { button: 0, pointerId: 2, clientX: 950, clientY: 180 })
    await pet.trigger('pointerup', { pointerId: 2 })
    pet.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
    expect(wrapper.emitted('open')).toHaveLength(1)
    wrapper.unmount()
  })

  it('supports keyboard movement and keeps the pet inside a resized viewport', async () => {
    const wrapper = mountCompanion()
    const pet = wrapper.get('[data-testid="companion-open"]')
    await pet.trigger('keydown', { key: 'End' })
    const bottom = Number(wrapper.get('.companion-pet').attributes('data-y'))
    await pet.trigger('keydown', { key: 'ArrowUp' })
    expect(Number(wrapper.get('.companion-pet').attributes('data-y'))).toBe(bottom - 24)
    height = 220
    resize([], {} as ResizeObserver)
    await flushPromises()
    expect(Number(wrapper.get('.companion-pet').attributes('data-y'))).toBeLessThanOrEqual(220 - 104)
    await pet.trigger('keydown', { key: 'Home' })
    expect(wrapper.get('.companion-pet').attributes('data-y')).toBe('6')
    expect(wrapper.emitted('open')).toBeUndefined()
    wrapper.unmount()
  })

  it('cancels interrupted dragging, and docking/restoring preserves position', async () => {
    const wrapper = mountCompanion()
    const pet = wrapper.get('[data-testid="companion-open"]')
    await pet.trigger('pointerdown', { button: 0, pointerId: 1, clientX: 950, clientY: 540 })
    await pet.trigger('pointermove', { pointerId: 1, clientX: 980, clientY: 220 })
    await pet.trigger('pointercancel', { pointerId: 1 })
    expect(wrapper.find('.is-dragging').exists()).toBe(false)
    expect(wrapper.emitted('open')).toBeUndefined()
    const position = wrapper.get('.companion-pet').attributes('data-y')
    await wrapper.get('[data-testid="companion-dock"]').trigger('click')
    await wrapper.get('[data-testid="companion-restore"]').trigger('click')
    expect(wrapper.get('.companion-pet').attributes('data-y')).toBe(position)
    wrapper.unmount()
  })

  it('reuses the reminder bubble for a single welcome, with no multi-step controls or chat action', async () => {
    const reminder = { id:'review:n1', note:{ id:'n1' } as any, title:'Check this note', message:'Review the definition.' }
    const wrapper = mount(LearningCompanion, { props:{ welcome:true, reminder }, global:{ stubs:{ Teleport:true } } })
    expect(wrapper.findAll('.companion-reminder')).toHaveLength(1)
    expect(wrapper.findAll('.companion-welcome p')).toHaveLength(1)
    expect(wrapper.find('.reminder-body').exists()).toBe(false)
    await wrapper.get('.companion-welcome footer button').trigger('click')
    await wrapper.get('.companion-welcome .reminder-heading button').trigger('click')
    await wrapper.get('.companion-welcome').trigger('keydown', { key:'Escape' })
    expect(wrapper.emitted('dismiss-welcome')).toHaveLength(3)
    expect(wrapper.emitted('open')).toBeUndefined()
    await wrapper.setProps({ welcome:false })
    expect(wrapper.find('.companion-welcome').exists()).toBe(false)
    expect(wrapper.get('.reminder-body').text()).toContain('Review the definition.')
    wrapper.unmount()
  })

  it('exposes evidence and emits the exact reminder target without opening chat', async () => {
    const reminder = { id:'review:n1', note:{ id:'n1' } as any, title:'Check this note', message:'Review the definition.', quote:'My definition', source:'Course definition' }
    const wrapper = mount(LearningCompanion, { props:{ reminder, remindersEnabled:true }, global:{ stubs:{ Teleport:true } } })
    expect(wrapper.get('.companion-reminder').text()).toContain('Course definition')
    await wrapper.get('.reminder-body').trigger('click')
    expect(wrapper.emitted('reminder')?.[0]).toEqual([reminder])
    expect(wrapper.emitted('open')).toBeUndefined()
    await wrapper.get('.reminder-heading button').trigger('click')
    expect(wrapper.emitted('dismiss-reminder')).toHaveLength(1)
    await wrapper.get('.companion-reminder-toggle').trigger('click')
    expect(wrapper.emitted('toggle-reminders')).toHaveLength(1)
    wrapper.unmount()
  })
})
