import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TeachingDiagram from '@/components/TeachingDiagram.vue'
import { teachingDiagramSamples } from '../../../dev/teaching-diagram-samples'

afterEach(() => vi.restoreAllMocks())
describe('diagram reading dialog', () => {
  it('keeps internal whitespace clicks open and restores focus after a backdrop click', async () => {
    const sample = teachingDiagramSamples.find(item => item.type === 'vector_plot')!
    const wrapper = mount(TeachingDiagram, { props: { raw: JSON.stringify(sample) }, attachTo: document.body })
    const dialog = wrapper.get('dialog').element as HTMLDialogElement
    dialog.showModal = vi.fn(() => dialog.setAttribute('open', ''))
    dialog.close = vi.fn(() => { dialog.removeAttribute('open'); dialog.dispatchEvent(new Event('close')) })
    vi.spyOn(dialog, 'getBoundingClientRect').mockReturnValue({ left:100,top:100,right:600,bottom:500,width:500,height:400,x:100,y:100,toJSON:()=>({}) })
    const focus = vi.spyOn(wrapper.get('button').element as HTMLElement, 'focus')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(dialog.showModal).toHaveBeenCalledTimes(1)
    expect(dialog.getAttribute('aria-label')).toBe(sample.title)
    await wrapper.get('dialog').trigger('click', { clientX:120, clientY:110 })
    expect(dialog.close).not.toHaveBeenCalled()
    await wrapper.get('dialog').trigger('click', { clientX:30, clientY:20 })
    expect(dialog.close).toHaveBeenCalledTimes(1)
    expect(focus).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
