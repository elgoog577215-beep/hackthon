import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import PptProjectWorkspace from '@/components/PptProjectWorkspace.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'
vi.mock('@/utils/http', () => ({ default:{get:vi.fn(),post:vi.fn(),patch:vi.fn()},identityRequestConfig:(_s:any,c:any)=>c }))
beforeEach(async()=>{ vi.clearAllMocks();vi.spyOn(globalThis,'fetch').mockResolvedValue({ok:true,json:async()=>messages} as Response);await setLocale('zh') })
it('selects multiple lectures and starts only after Next', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 vi.mocked(http.get).mockImplementation(async(url:any)=>({data:String(url).endsWith('/ppt-projects')?{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready:true},{lesson_id:'l2',title:'第二讲',ready:true}],uploads:[],projects:[]}:{project_id:'p',revision:'r2',status:'paused'}}))
 vi.mocked(http.post).mockResolvedValue({data:{project_id:'p',revision:'r1'}})
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c'},global:{plugins:[router],stubs:{PptManuscriptWorkflow:true,SlideCanvas:true}}})
 await flushPromises();expect(http.post).not.toHaveBeenCalled()
 const choices=wrapper.findAll('input[type="checkbox"]');await choices[0]!.setValue(true);await choices[1]!.setValue(true)
 await wrapper.get('.selection-footer .primary').trigger('click');await flushPromises()
 expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/ppt-projects',expect.objectContaining({lesson_ids:['l1','l2']}),expect.anything())
 expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/ppt-projects/p/prepare',{expected_revision:'r1'},expect.anything())
 expect(wrapper.text()).toContain('任务已暂停');wrapper.unmount()
})
it('restores an existing selection, reuses it and protects unsaved edits', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 const existing={project_id:'p',revision:'r',status:'draft',lesson_ids:['l1'],asset_ids:['a'],manuscript:{manuscript_revision:'m'}}
 vi.mocked(http.get).mockImplementation(async(url:any)=>({data:String(url).endsWith('/ppt-projects')?{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready:true}],uploads:[{asset_id:'a',filename:'notes.md'}],projects:[{project_id:'p',title:'现有课件'}]}:existing}))
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c'},global:{plugins:[router],stubs:{PptManuscriptWorkflow:{name:'PptManuscriptWorkflow',template:'<div />'},SlideCanvas:true}}})
 await flushPromises();await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 await wrapper.findAll('.project-toolbar nav button')[0]!.trigger('click')
 expect(wrapper.findAll('input[type="checkbox"]').every(x=>(x.element as HTMLInputElement).checked)).toBe(true)
 await wrapper.get('.selection-footer .primary').trigger('click');await flushPromises()
 expect(http.post).not.toHaveBeenCalled()
 wrapper.getComponent({name:'PptManuscriptWorkflow'}).vm.$emit('dirty-change',true);await flushPromises()
 expect((wrapper.vm as any).prepareToLeave()).toBe(false)
 const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
 wrapper.unmount();const clean=new Event('beforeunload',{cancelable:true});window.dispatchEvent(clean);expect(clean.defaultPrevented).toBe(false)
})
