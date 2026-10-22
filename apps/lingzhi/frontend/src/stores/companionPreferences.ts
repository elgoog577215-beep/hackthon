import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import http, { getLearnerIdentity } from '../utils/http'
import { createUuid } from '../utils/client-id'

export const useCompanionPreferencesStore = defineStore('companionPreferences', () => {
  const mode = ref<'gentle'|'on_request'>('gentle'), revision=ref(1), ready=ref(false), owner=ref(''), error=ref(false), busy=ref(false)
  const suppressions=ref<Record<string,string[]>>({}), suppressionError=ref(false)
  let sequence=0, pending:Promise<void>|null=null
  const proactive=computed(()=>ready.value && owner.value===getLearnerIdentity() && mode.value==='gentle')
  async function load(force=false) {
    const actor=getLearnerIdentity()
    if(!force && ready.value && actor===owner.value) return
    if(pending && actor===owner.value && !force) return pending
    const token=++sequence;owner.value=actor;ready.value=false;error.value=false
    const request=(async()=>{try {
      const {data}=await http.get('/api/study/companion/preferences')
      if(token!==sequence || actor!==getLearnerIdentity())return
      if(!['gentle','on_request'].includes(data?.mode) || !Number.isInteger(data?.revision))throw Error('invalid preference')
      mode.value=data.mode;revision.value=data.revision;ready.value=true
    }catch {if(token===sequence)error.value=true}finally{if(token===sequence)pending=null}})()
    pending=request;return request
  }
  async function change(next:'gentle'|'on_request') {
    if(busy.value)return
    if(!ready.value)await load()
    if(!ready.value)throw Error('Preference unavailable')
    const actor=getLearnerIdentity();busy.value=true
    try {
      const {data}=await http.patch('/api/study/companion/preferences',{mode:next,expected_revision:revision.value,request_id:createUuid()})
      if(actor!==getLearnerIdentity())return
      mode.value=data.mode;revision.value=data.revision;ready.value=true
    }catch(e){await load(true);throw e}finally{busy.value=false}
  }
  async function loadSuppressions(course:string){const actor=getLearnerIdentity();try{const {data}=await http.get(`/api/courses/${encodeURIComponent(course)}/learning-records/companion/suppressions`);if(actor!==getLearnerIdentity())return;suppressions.value={...suppressions.value,[course]:Array.isArray(data)?data.filter(s=>s.mode==='never'||s.mode==='not_now').map(s=>s.suppression_key):[]}}catch{suppressionError.value=true}}
  async function suppress(course:string,key:string,choice:'not_now'|'never'){suppressions.value={...suppressions.value,[course]:[...(suppressions.value[course]||[]),key]};try{await http.post(`/api/courses/${encodeURIComponent(course)}/learning-records/companion/suppressions`,{key,mode:choice});suppressionError.value=false}catch{suppressionError.value=true}}
  return {mode,revision,ready,owner,error,busy,proactive,suppressions,suppressionError,load,change,loadSuppressions,suppress}
})
