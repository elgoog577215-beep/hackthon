import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import http, { getLearnerIdentity } from '../utils/http'
import { createUuid } from '../utils/client-id'

export const useCompanionPreferencesStore = defineStore('companionPreferences', () => {
  const mode = ref<'gentle'|'on_request'>('gentle'), revision=ref(1), ready=ref(false), owner=ref(''), error=ref(false), busy=ref(false)
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
  return {mode,revision,ready,owner,error,busy,proactive,load,change}
})
