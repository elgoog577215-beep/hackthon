<template>
  <header class="companion-panel-header">
    <div class="companion-heading"><strong>{{ t('companionWorkspace.title', '灵知学伴') }}</strong>
      <button type="button" class="companion-close" :aria-label="t('companionWorkspace.minimize', '收起学伴')" @click="emit('close')"><Minus :size="16" /></button>
    </div>
    <div class="companion-header-actions">
      <button type="button" :disabled="busy" @click="emit('new')"><Plus :size="15" />{{ t('companionWorkspace.new', '新对话') }}</button>
      <button type="button" :aria-expanded="history" @click="emit('history')"><History :size="15" />{{ t('companionWorkspace.history', '历史') }}</button>
      <button type="button" @click="emit('mode')"><PanelRight :size="15" />{{ floating ? t('companionWorkspace.dock', '停靠右栏') : t('companionWorkspace.float', '切为浮窗') }}</button>
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
.companion-panel-header {
  display:flex;
  flex:none;
  flex-direction:column;
  gap:8px;
  padding:10px 14px;
  border-bottom:1px solid var(--lz-border);
  border-radius:var(--lz-radius-surface) var(--lz-radius-surface) 0 0;
  background:#fff;
  color:var(--lz-text-strong);
}
.companion-heading {
  display:flex;
  align-items:center;
  justify-content:space-between;
  min-height:var(--lz-control-height);
  gap:8px;
}
.companion-heading strong { font-size:17px; font-weight:650; }
.companion-header-actions { display:flex; flex-wrap:wrap; gap:6px; }
.companion-header-actions button,
.companion-close {
  display:flex;
  align-items:center;
  justify-content:center;
  min-height:var(--lz-control-height);
  gap:5px;
  padding:5px 8px;
  border:1px solid var(--lz-border);
  border-radius:var(--lz-radius-control);
  background:#fff;
  color:var(--lz-text);
  font-size:15px;
  cursor:pointer;
}
.companion-close { min-width:var(--lz-control-height); padding:0; }
.companion-header-actions button:hover,
.companion-close:hover { background:var(--lz-brand-soft); }
.companion-header-actions button:focus-visible,
.companion-close:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.companion-header-actions button:disabled { opacity:.5; cursor:wait; }
</style>
