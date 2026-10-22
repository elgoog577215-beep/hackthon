import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionPlanPanel from '@/components/CompanionPlanPanel.vue'
import { useCompanionPreferencesStore } from '@/stores/companionPreferences'
import http from '@/utils/http'
vi.mock('@/utils/http',()=>({default:{get:vi.fn(),post:vi.fn(),patch:vi.fn()},getLearnerIdentity:()=> 'u'}))
const state=()=>({revision:1,goal:null,goal_history:[],plan:null,proposal:null,memories:[],catalog:[{id:'n',title:'导数'}],progress:[]})
describe('owned learning plan and companion preferences',()=>{
 beforeEach(()=>{setActivePinia(createPinia());vi.clearAllMocks();vi.mocked(http.get).mockImplementation(async url=>({data:String(url).includes('preferences')?{revision:1,mode:'gentle'}:state()}))})
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
 it('does not read or write personal context from teacher preview',async()=>{
  const w=mount(CompanionPlanPanel,{props:{courseId:'c',preview:true}})
  expect(w.find('[data-testid="companion-plan-open"]').exists()).toBe(false)
  expect(http.get).not.toHaveBeenCalled();w.unmount()
 })
})
