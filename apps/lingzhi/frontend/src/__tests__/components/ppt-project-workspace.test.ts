import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import PptProjectWorkspace from '@/components/PptProjectWorkspace.vue'
import http from '@/utils/http'
import { setLocale } from '@/shared/i18n'
import messages from '../../../public/locales/zh/translation.json'
vi.mock('@/utils/http', () => ({ default:{get:vi.fn(),post:vi.fn(),patch:vi.fn()},identityRequestConfig:(_s:any,c:any)=>c,withApiBase:(url:string)=>url,teacherIdentityHeaders:()=>({'X-User-Id':'teacher-test'}) }))
it('uses the workbench sidebar actions without an embedded step wizard', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 const draft={project_id:'p',revision:'r',status:'draft',lesson_ids:['l1'],asset_ids:[],confirmable:true,manuscript:{manuscript_revision:'m'}}
 vi.mocked(http.get).mockImplementation(async(url:any)=>({data:String(url).endsWith('/ppt-projects')?{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready:true}],uploads:[],projects:[{project_id:'p',title:'课件'}]}:draft}))
 vi.mocked(http.post).mockImplementation(async()=>{Object.assign(draft,{confirmed_revision:'m',status:'confirmed'});return {data:draft}})
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c',embedded:true},global:{plugins:[router],stubs:{PptManuscriptWorkflow:{name:'PptManuscriptWorkflow',template:'<div />'},SlideCanvas:true}}})
 await flushPromises();expect(wrapper.find('.project-toolbar nav').exists()).toBe(false)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 const vm=wrapper.vm as any
 expect(vm.sources.lectures[0].lesson_id).toBe('l1')
 await vm.runContextAction('confirm');await flushPromises()
 expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/ppt-projects/p/confirm',{expected_revision:'r'},expect.anything())
 expect(wrapper.findComponent({name:'PptManuscriptWorkflow'}).exists()).toBe(true)
 wrapper.getComponent({name:'PptManuscriptWorkflow'}).vm.$emit('dirty-change',true);await flushPromises()
 await vm.runContextAction('render');expect(http.post).toHaveBeenCalledTimes(1)
 wrapper.unmount()
})
beforeEach(async()=>{ vi.clearAllMocks();vi.spyOn(globalThis,'fetch').mockResolvedValue({ok:true,json:async()=>messages} as Response);await setLocale('zh') })
afterEach(()=>vi.useRealTimers())
it('blocks an unavailable default lecture and refreshes when its teacher revision is ready', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 let ready=false
 vi.mocked(http.get).mockImplementation(async()=>({data:{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready}],uploads:[],projects:[]}}))
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c',initialLessonId:'l1',sourceRevision:'pending',embedded:true},global:{plugins:[router],stubs:{PptManuscriptWorkflow:true,SlideCanvas:true}}})
 await flushPromises()
 const vm=wrapper.vm as any
 expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
 expect(vm.context.actions.find((action:any)=>action.id==='prepare').disabled).toBe(true)
 await vm.runContextAction('prepare')
 expect(http.post).not.toHaveBeenCalled()
 ready=true
 await wrapper.setProps({sourceRevision:'ready-r1'});await flushPromises()
 expect(wrapper.get('input[type="checkbox"]').attributes('disabled')).toBeUndefined()
 await wrapper.get('input[type="checkbox"]').setValue(true)
 expect(vm.context.actions.find((action:any)=>action.id==='prepare').disabled).toBe(false)
 expect(http.get).toHaveBeenCalledTimes(2)
 wrapper.unmount()
})

it('does not overwrite a new source catalog with a late older response', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 let resolveOld:(value:any)=>void=()=>{}
 vi.mocked(http.get).mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve}))
  .mockResolvedValue({data:{document_revision:'new',lectures:[{lesson_id:'l1',title:'第一讲',ready:true}],uploads:[],projects:[]}})
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c',initialLessonId:'l1',sourceRevision:'pending'},global:{plugins:[router],stubs:{PptManuscriptWorkflow:true,SlideCanvas:true}}})
 await wrapper.setProps({sourceRevision:'ready'});await flushPromises()
 resolveOld({data:{document_revision:'old',lectures:[{lesson_id:'l1',title:'第一讲',ready:false}],uploads:[],projects:[]}});await flushPromises()
 expect(wrapper.get('input[type="checkbox"]').attributes('disabled')).toBeUndefined()
 expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
 wrapper.unmount()
})

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
it('retries a selected project after preparation failed without creating a second project', async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 const existing={project_id:'p',revision:'r',status:'selected',lesson_ids:['l1'],asset_ids:[]}
 vi.mocked(http.get).mockImplementation(async(url:any)=>({data:String(url).endsWith('/ppt-projects')?{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready:true}],uploads:[],projects:[{project_id:'p',title:'未完成课件'}]}:existing}))
 vi.mocked(http.post).mockRejectedValue({response:{status:503,data:{detail:{message:'模型暂不可用'}}}})
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c'},global:{plugins:[router],stubs:{PptManuscriptWorkflow:true,SlideCanvas:true}}})
 await flushPromises();await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 await wrapper.get('.project-empty button').trigger('click');await flushPromises()
 expect(http.post).toHaveBeenCalledWith('/api/teacher/courses/c/ppt-projects/p/prepare',{expected_revision:'r'},expect.anything())
 expect(wrapper.text()).toContain('模型暂不可用')
 await wrapper.findAll('.project-toolbar nav button')[0]!.trigger('click')
 await wrapper.get('.selection-footer .primary').trigger('click');await flushPromises()
 expect(http.post).toHaveBeenCalledTimes(2)
 expect(vi.mocked(http.post).mock.calls.every(([url])=>String(url).endsWith('/p/prepare'))).toBe(true)
 wrapper.unmount()
})

async function stabilityWorkspace(project:any, props:Record<string,any>={}) {
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
 vi.mocked(http.get).mockImplementation(async(url:any)=>({data:String(url).endsWith('/ppt-projects')?{document_revision:'doc',lectures:[{lesson_id:'l1',title:'第一讲',ready:true}],uploads:[],projects:[{project_id:'p',title:'课件'}]}:project}))
 const wrapper=mount(PptProjectWorkspace,{props:{courseId:'c',embedded:true,...props},global:{plugins:[router],stubs:{PptManuscriptWorkflow:{name:'PptManuscriptWorkflow',props:['state'],template:'<div />'},SlideCanvas:true}}})
 await flushPromises()
 return wrapper
}

it('does not prepare an old course project after switching courses during creation',async()=>{
 const wrapper=await stabilityWorkspace(null,{initialLessonId:'l1'})
 let finish:(data:any)=>void=()=>{}
 vi.mocked(http.post).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=(wrapper.vm as any).runContextAction('prepare')
 await wrapper.setProps({courseId:'other'});await flushPromises()
 finish({data:{project_id:'old',revision:'r',status:'selected'}});await pending;await flushPromises()
 expect(http.post).toHaveBeenCalledTimes(1)
 expect(wrapper.findComponent({name:'PptManuscriptWorkflow'}).exists()).toBe(false)
 expect(wrapper.find('.project-selection').exists()).toBe(true)
 wrapper.unmount()
})

it('ignores a pre-pause poll and sends only one pause while its request is pending',async()=>{
 vi.useFakeTimers()
 const running={project_id:'p',revision:'r',status:'building',lesson_ids:['l1'],asset_ids:[]}
 const wrapper=await stabilityWorkspace(running)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 let oldPoll:(data:any)=>void=()=>{},finishPause:(data:any)=>void=()=>{}
 vi.mocked(http.get).mockImplementationOnce(()=>new Promise(resolve=>{oldPoll=resolve}))
 vi.advanceTimersByTime(1800);await flushPromises()
 vi.mocked(http.post).mockImplementationOnce(()=>new Promise(resolve=>{finishPause=resolve}))
 const pending=(wrapper.vm as any).runContextAction('pause')
 await wrapper.get('.project-progress button').trigger('click')
 expect(http.post).toHaveBeenCalledTimes(1)
 const paused={...running,revision:'paused',status:'paused'}
 vi.mocked(http.get).mockResolvedValue({data:paused})
 finishPause({data:paused});await pending;await flushPromises()
 oldPoll({data:running});await flushPromises()
 expect(wrapper.find('.project-progress').exists()).toBe(false)
 expect(wrapper.text()).toContain('任务已暂停')
 wrapper.unmount()
})

it('recovers a temporary poll error when the same task finishes',async()=>{
 vi.useFakeTimers()
 const running={project_id:'p',revision:'r',status:'building',lesson_ids:['l1'],asset_ids:[]}
 const wrapper=await stabilityWorkspace(running)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 vi.mocked(http.get).mockRejectedValueOnce({response:{status:503,data:{detail:{message:'暂时断网'}}}})
 vi.advanceTimersByTime(1800);await flushPromises()
 expect(wrapper.text()).toContain('暂时断网')
 vi.mocked(http.get).mockResolvedValue({data:{...running,revision:'done',status:'draft',manuscript:{manuscript_revision:'m'}}})
 vi.advanceTimersByTime(1800);await flushPromises()
 expect(wrapper.find('[role="alert"]').exists()).toBe(false)
 expect((wrapper.vm as any).context.phase).toBe('after')
 wrapper.unmount()
})

it('keeps the source selection usable when opening a project fails',async()=>{
 const wrapper=await stabilityWorkspace(null)
 vi.mocked(http.get).mockRejectedValueOnce({response:{status:503,data:{detail:'暂时无法读取'}}})
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 expect(wrapper.find('.project-selection').exists()).toBe(true)
 expect(wrapper.text()).toContain('暂时无法读取')
 expect(wrapper.find('.project-empty').exists()).toBe(false)
 wrapper.unmount()
})

it('does not overwrite edits with a source refresh that was already in flight',async()=>{
 const project={project_id:'p',revision:'r',status:'draft',lesson_ids:['l1'],asset_ids:[],manuscript:{manuscript_revision:'m'}}
 const wrapper=await stabilityWorkspace(project)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 let finish:(data:any)=>void=()=>{}
 vi.mocked(http.get).mockImplementation(async(url:any)=>String(url).endsWith('/ppt-projects')?{data:{lectures:[],uploads:[]}}:new Promise(resolve=>{finish=resolve}))
 await wrapper.setProps({sourceRevision:'new'});await flushPromises()
 const editor=wrapper.getComponent({name:'PptManuscriptWorkflow'})
 editor.vm.$emit('dirty-change',true);await flushPromises()
 finish({data:{...project,revision:'new',source_state:'stale'}});await flushPromises()
 expect(editor.props('state').revision).toBe('r')
 expect((wrapper.vm as any).prepareToLeave()).toBe(false)
 wrapper.unmount()
})

function pptStream() {
 let controller!:ReadableStreamDefaultController<Uint8Array>
 const body=new ReadableStream<Uint8Array>({start(value){controller=value}})
 const response={ok:true,body} as Response
 vi.mocked(fetch).mockResolvedValue(response)
 return {
  emit(sequence:number,batches:Record<string,string>,status='running',id='j'){
   const payload={job:{id,status,progress:42,stream_sequence:sequence,stream_batches:batches}}
   controller.enqueue(new TextEncoder().encode(`event: lesson_plan_stream\ndata: ${JSON.stringify(payload)}\n\n`))
  },
  close(){controller.close()},
 }
}

const streamingProject=()=>({project_id:'p',revision:'r',status:'building',job_id:'j',job:{id:'j',status:'running',stream_sequence:0,stream_batches:{}},lesson_ids:['l1'],asset_ids:[]})

it('shows incremental PPT text immediately, keeps pages separate and replaces a reset batch without POSTs',async()=>{
 const stream=pptStream(), wrapper=await stabilityWorkspace(streamingProject())
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 stream.emit(1,{page1:'导数的定义'});await flushPromises()
 expect(wrapper.get('[data-batch-id="page1"]').text()).toContain('导数的定义')
 stream.emit(2,{page1:'导数的定义：变化率',page2:'切线与斜率'});await flushPromises()
 expect(wrapper.get('[data-batch-id="page1"]').text()).toContain('变化率')
 expect(wrapper.get('[data-batch-id="page2"]').text()).toContain('切线与斜率')
 stream.emit(3,{page1:'',page2:'切线与斜率'});await flushPromises()
 expect(wrapper.find('[data-batch-id="page1"]').exists()).toBe(false)
 stream.emit(4,{page1:'重新生成的定义',page2:'切线与斜率'});await flushPromises()
 expect(wrapper.get('[data-batch-id="page1"]').text()).toBe('重新生成的定义')
 expect(wrapper.text()).not.toContain('变化率')
 expect(http.post).not.toHaveBeenCalled()
 stream.close();wrapper.unmount()
})

it('keeps one stream subscription and its newest text when an older poll replaces the project snapshot',async()=>{
 vi.useFakeTimers()
 const stream=pptStream(), project=streamingProject(), wrapper=await stabilityWorkspace(project)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 stream.emit(5,{page1:'最新正文'});await flushPromises()
 const subscriptions=vi.mocked(fetch).mock.calls.length
 vi.mocked(http.get).mockResolvedValue({data:{...project,job:{...project.job,stream_sequence:1,stream_batches:{page1:'旧正文'}}}})
 vi.advanceTimersByTime(1800);await flushPromises()
 expect(wrapper.get('[data-batch-id="page1"]').text()).toBe('最新正文')
 expect(fetch).toHaveBeenCalledTimes(subscriptions)
 stream.emit(2,{page1:'迟到正文'});await flushPromises()
 expect(wrapper.get('[data-batch-id="page1"]').text()).toBe('最新正文')
 expect(http.post).not.toHaveBeenCalled()
 stream.close();wrapper.unmount()
})

it('aborts only stream observation on course change and ignores late old-course text',async()=>{
 const stream=pptStream(), wrapper=await stabilityWorkspace(streamingProject())
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 const call=vi.mocked(fetch).mock.calls.find(([url])=>String(url).includes('/lesson-jobs/'))!
 expect(String(call[0])).toBe('/api/teacher/courses/c/lesson-jobs/j/stream')
 const signal=call[1]!.signal as AbortSignal
 expect(signal.aborted).toBe(false)
 await wrapper.setProps({courseId:'other'});await flushPromises()
 expect(signal.aborted).toBe(true)
 stream.emit(1,{page1:'旧课程正文'});await flushPromises()
 expect(wrapper.find('[data-testid="ppt-live-draft"]').exists()).toBe(false)
 expect(wrapper.text()).not.toContain('旧课程正文')
 expect(http.post).not.toHaveBeenCalled()
 stream.close();wrapper.unmount()
})

it('continues polling after stream disconnection and replaces live text with the completed manuscript',async()=>{
 vi.useFakeTimers()
 const stream=pptStream(), project=streamingProject(), wrapper=await stabilityWorkspace(project)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 stream.emit(1,{page1:'生成中的正文'});await flushPromises();stream.close();await flushPromises()
 vi.mocked(http.get).mockResolvedValue({data:{...project,revision:'done',status:'draft',manuscript:{manuscript_revision:'m',pages:[{page_id:'page1',title:'完成稿'}]}}})
 vi.advanceTimersByTime(1800);await flushPromises()
 expect(wrapper.find('[data-testid="ppt-live-draft"]').exists()).toBe(false)
 expect(wrapper.getComponent({name:'PptManuscriptWorkflow'}).props('state').manuscript.manuscript_revision).toBe('m')
 expect((wrapper.vm as any).context.phase).toBe('after')
 expect(wrapper.find('[role="alert"]').exists()).toBe(false)
 expect(http.post).not.toHaveBeenCalled()
 wrapper.unmount()
})

it('reconciles a terminal stream immediately without confirming or rendering the manuscript',async()=>{
 const stream=pptStream(), project=streamingProject(), wrapper=await stabilityWorkspace(project)
 await wrapper.get('.existing-projects button').trigger('click');await flushPromises()
 vi.mocked(http.get).mockResolvedValue({data:{...project,status:'draft',confirmable:true,manuscript:{manuscript_revision:'final'}}})
 stream.emit(2,{page1:'完整正文'},'completed');await flushPromises()
 expect(wrapper.getComponent({name:'PptManuscriptWorkflow'}).props('state').manuscript.manuscript_revision).toBe('final')
 expect(wrapper.find('[data-testid="ppt-live-draft"]').exists()).toBe(false)
 expect(http.post).not.toHaveBeenCalled()
 stream.close();wrapper.unmount()
})
