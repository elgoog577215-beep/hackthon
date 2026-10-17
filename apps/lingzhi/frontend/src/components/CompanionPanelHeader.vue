<template>
  <header class="companion-panel-header">
    <div class="companion-heading"><strong>{{ t('companionWorkspace.title', '灵知学伴') }}</strong></div>
    <div class="companion-header-actions">
      <button type="button" :disabled="busy" @click="emit('new')"><Plus :size="15" />{{ t('companionWorkspace.new', '新对话') }}</button>
      <button type="button" :aria-expanded="history" @click="emit('history')"><History :size="15" />{{ t('companionWorkspace.history', '历史') }}</button>
      <button type="button" @click="emit('mode')"><PanelRight :size="15" />{{ floating ? t('companionWorkspace.dock', '停靠右栏') : t('companionWorkspace.float', '切为浮窗') }}</button>
      <button type="button" :aria-label="t('companionWorkspace.minimize', '收起学伴')" @click="emit('close')"><Minus :size="16" /></button>
    </div>
  </header>
</template>
<script setup lang="ts">
import { History, Minus, PanelRight, Plus } from 'lucide-vue-next'
import { t } from '../shared/i18n'
defineProps<{ floating?: boolean; history?: boolean; busy?: boolean }>()
const emit = defineEmits<{ (e:'new'):void; (e:'history'):void; (e:'mode'):void; (e:'close'):void }>()
</script>
<style scoped>
.companion-panel-header { position:relative; display:flex; flex-direction:column; gap:8px; padding:10px 14px; border-bottom:1px solid #eee9f7; background:#fff; border-radius:18px 18px 0 0; flex:none; color:#30264e; }
.companion-heading { min-height:40px; display:flex; align-items:center; }.companion-heading strong { font-size:17px; font-weight:650; }
.companion-header-actions { display:flex; flex-wrap:wrap; gap:6px; }.companion-header-actions button { display:flex; align-items:center; justify-content:center; gap:5px; min-height:34px; padding:5px 8px; border:1px solid #e5ddf3; border-radius:8px; font-size:15px; background:#fff; color:#7655b1; cursor:pointer; }.companion-header-actions button:last-child { margin-left:auto; min-width:34px; }.companion-header-actions button:hover { background:#f5f0ff; }.companion-header-actions button:focus-visible { outline:2px solid #8561cc; outline-offset:2px; }.companion-header-actions button:disabled { opacity:.5; cursor:wait; }
</style>
