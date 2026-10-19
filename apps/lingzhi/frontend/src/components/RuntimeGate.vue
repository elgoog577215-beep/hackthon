<template>
  <div v-if="RUNTIME_ID && ready" class="runtime-badge" role="status">{{ t('runtime.isolated') }}</div>
  <slot v-if="ready" />
  <section v-else class="runtime-block" :role="error ? 'alert' : 'status'">
    <p>{{ error || t('runtime.checking') }}</p>
    <button v-if="error" type="button" @click="reload">{{ t('runtime.reload') }}</button>
  </section>
</template>
<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {RUNTIME_ID,verifyRuntime} from '../utils/runtime-identity'
import {t} from '../shared/i18n'
const ready=ref(!RUNTIME_ID)
const error=ref('')
onMounted(async()=>{
  if (!RUNTIME_ID) return
  try {await verifyRuntime();ready.value=true}
  catch(e) {error.value=e instanceof Error ? e.message : t('runtime.mismatch')}
})
function reload(){window.location.reload()}
</script>
<style scoped>
.runtime-badge{position:fixed;bottom:12px;left:12px;z-index:9000;border:1px solid #d4c6ed;border-radius:9px;background:#f3edff;color:#574077;padding:7px 12px;font:600 14px/1.5 sans-serif;box-shadow:0 2px 10px #48346a12}.runtime-block{margin:48px auto;padding:24px;max-width:640px;font-size:16px;line-height:1.7;color:#674a72;background:#faf7ff;border:1px solid #ded2eb;border-radius:12px}.runtime-block button{font:inherit;padding:8px 16px;background:#fff;border:1px solid #c6b5dc;border-radius:8px;color:inherit;cursor:pointer}
</style>
