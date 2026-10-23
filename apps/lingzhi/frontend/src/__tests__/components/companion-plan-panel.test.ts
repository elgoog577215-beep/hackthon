import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionPlanPanel from '@/components/CompanionPlanPanel.vue'
import { useCompanionPreferencesStore } from '@/stores/companionPreferences'
import http from '@/utils/http'
vi.mock('@/utils/http',()=>({default:{get:vi.fn(),post:vi.fn(),patch:vi.fn()},getLearnerIdentity:()=> 'u'}))
const state=()=>({revision:1,goal:null,goal_history:[],plan:null,proposal:null,memories:[],catalog:[{id:'n',title:'导数'}],progress:[]})
describe('owned learning plan and companion preferences',()=>{
 beforeEach(()=>{setActivePinia(createPinia());vi.resetAllMocks();vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:state()}))})
 it('waits for the server preference, preserves an explicit on-request mode, and updates by revision',async()=>{
  const store=useCompanionPreferencesStore()
  expect(store.proactive).toBe(false)
  await store.load();expect(store.proactive).toBe(true)
  vi.mocked(http.patch).mockResolvedValue({data:{mode:'on_request',revision:2}})
  await store.change('on_request')
  expect(store.proactive).toBe(false)
  expect(http.patch).toHaveBeenCalledWith('/api/study/companion/preferences',expect.objectContaining({expected_revision:1,mode:'on_request',request_id:expect.any(String)}))
 })
 it('stays quiet when preference loading fails instead of overwriting with defaults',async()=>{
  vi.mocked(http.get).mockRejectedValue(new Error('offline'));const store=useCompanionPreferencesStore()
  await store.load();expect(store.proactive).toBe(false);expect(http.patch).not.toHaveBeenCalled()
 })
 it('shows an owned course goal editor, submits a versioned command and keeps it separate from the lesson',async()=>{
  const w=mount(CompanionPlanPanel,{props:{courseId:'c'},attachTo:document.body})
  await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
  const modal=document.querySelector('[data-testid="companion-plan-dialog"]')!
  const text=modal.querySelector('textarea')!;text.value='两周后考微积分';text.dispatchEvent(new Event('input'))
  vi.mocked(http.post).mockResolvedValue({data:{...state(),revision:2,goal:{text:'两周后考微积分',purpose:'exam'}}})
  modal.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/courses/c/learning-records/companion',expect.objectContaining({action:'save_goal',expected_revision:1,value:expect.objectContaining({text:'两周后考微积分'})}))
  w.unmount()
 })
 it('allows a new course command while an old course response is still pending',async()=>{
  let finishOld!:(value:any)=>void
  vi.mocked(http.post).mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve}))
  const w=mount(CompanionPlanPanel,{props:{courseId:'old'},attachTo:document.body})
  try {
   await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
   document.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
   await w.setProps({courseId:'new'})
   await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
   vi.mocked(http.post).mockResolvedValueOnce({data:{...state(),revision:2}})
   document.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
   expect(http.post).toHaveBeenCalledWith('/api/courses/new/learning-records/companion',expect.anything())
   finishOld({data:{...state(),goal:{text:'OLD COURSE'}}});await flushPromises()
   expect(document.querySelector('textarea')!.value).not.toContain('OLD COURSE')
  } finally {w.unmount()}
 })
 it('does not send a delayed withdrawal to a different course',async()=>{
  let finish!:(value:any)=>void
  vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:{...state(),feedback_consent:true}}))
  vi.mocked(http.post).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  const w=mount(CompanionPlanPanel,{props:{courseId:'exchange_old'},attachTo:document.body})
  try {
   await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
   const checkbox=document.querySelector<HTMLInputElement>('input[type="checkbox"]')!
   checkbox.checked=false;checkbox.dispatchEvent(new Event('change',{bubbles:true}));await flushPromises()
   await w.setProps({courseId:'exchange_new'})
   finish({data:{...state(),revision:2,feedback_consent:false}});await flushPromises()
   expect(http.post).toHaveBeenCalledTimes(1)
  } finally {w.unmount()}
 })
 it('opens material preparation with the saved adopted purpose, without generating from unsaved edits',async()=>{
  vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:{...state(),goal:{text:'完成项目',purpose:'project'},source_revision:'cv',plan:{status:'active',source_revision:'cv',steps:[]}}}))
  const w=mount(CompanionPlanPanel,{props:{courseId:'c'},attachTo:document.body})
  await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
  const button=document.querySelector<HTMLButtonElement>('[data-testid="prepare-goal-material"]')!
  expect(button).not.toBeNull();button.click();await flushPromises()
  expect(w.emitted('prepareMaterial')?.[0]).toEqual([{courseId:'c',purpose:'project'}])
  expect(http.post).not.toHaveBeenCalled();w.unmount()
 })
 it('shows the independent check result separately from the current profile judgement',async()=>{
  vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:{...state(),help_outcomes:[{task_revision_id:'private-q-id',knowledge_name:'循环边界',verification_state:'independent_pass',current_profile:{status:'checking'},attempts:[]}]}}))
  const w=mount(CompanionPlanPanel,{props:{courseId:'c'},attachTo:document.body})
  await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
  const text=document.querySelector('[data-testid="companion-plan-dialog"]')!.textContent!
  expect(text).toContain('新题已独立通过');expect(text).toContain('画像当前判断')
  expect(text).not.toContain('private-q-id');w.unmount()
 })
 it('does not read or write personal context from teacher preview',async()=>{
  const w=mount(CompanionPlanPanel,{props:{courseId:'c',preview:true}})
  expect(w.find('[data-testid="companion-plan-open"]').exists()).toBe(false)
  expect(http.get).not.toHaveBeenCalled();w.unmount()
 })
 it('keeps a goal draft when reloading after a revision conflict and reuses a lost-response request',async()=>{
  const original={...state(),goal:{text:'原目标',purpose:'systematic'}}
  vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:original}))
  const w=mount(CompanionPlanPanel,{props:{courseId:'c'},attachTo:document.body})
  await w.get('[data-testid="companion-plan-open"]').trigger('click');await flushPromises()
  const modal=document.querySelector('[data-testid="companion-plan-dialog"]')!
  const text=modal.querySelector('textarea')!;text.value='我的未保存目标';text.dispatchEvent(new Event('input'))
  vi.mocked(http.post).mockRejectedValue({response:{status:409}})
  const form=modal.querySelector('form')!
  form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
  expect((vi.mocked(http.post).mock.calls[1]![1] as any).request_id).toBe((vi.mocked(http.post).mock.calls[0]![1] as any).request_id)
  Array.from(modal.querySelectorAll('button')).find(b=>b.textContent?.trim()==='重新读取')!.click();await flushPromises()
  expect(text.value).toBe('我的未保存目标');w.unmount()
 })
})
