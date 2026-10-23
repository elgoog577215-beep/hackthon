<template>
  <header class="companion-panel-header">
    <div class="companion-heading"><strong>{{ t('companionWorkspace.title', '灵知学伴') }}</strong></div>
    <div class="companion-header-actions">
      <details ref="menu" class="companion-session-menu" @keydown.esc.stop.prevent="closeMenu(true)" @focusout="leaveMenu">
        <summary :aria-label="t('studyDialogue.more')" :title="t('studyDialogue.more')"><MoreHorizontal :size="18" /></summary>
        <div>
          <button type="button" :disabled="busy" @click="closeMenu();emit('new')"><Plus :size="15" />{{ t('companionWorkspace.new', '新对话') }}</button>
          <button type="button" :aria-expanded="history" @click="closeMenu();emit('history')"><History :size="15" />{{ t('companionWorkspace.history', '历史') }}</button>
          <button type="button" @click="closeMenu();emit('mode')"><PanelRight :size="15" />{{ floating ? t('companionWorkspace.dock', '停靠右栏') : t('companionWorkspace.float', '切为浮窗') }}</button>
        </div>
      </details>
      <button type="button" :aria-label="t('companionWorkspace.minimize', '收起学伴')" @click="emit('close')"><Minus :size="16" /></button>
    </div>
    <span class="companion-perch" data-companion-perch aria-hidden="true"><img v-if="!livePet" :src="avatar" alt="" /></span>
  </header>
</template>
<script setup lang="ts">
import { History, Minus, MoreHorizontal, PanelRight, Plus } from 'lucide-vue-next'
import {ref} from 'vue'
import { t } from '../shared/i18n'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'
defineProps<{ floating?: boolean; history?: boolean; busy?: boolean; livePet?: boolean }>()
const emit = defineEmits<{ (e:'new'):void; (e:'history'):void; (e:'mode'):void; (e:'close'):void }>()
const avatar = resolvePublicAssetUrl('images/learning-companion.png', import.meta.env.BASE_URL)
const menu=ref<HTMLDetailsElement|null>(null)
function closeMenu(focus=false){if(menu.value){menu.value.open=false;if(focus)menu.value.querySelector('summary')?.focus()}}
function leaveMenu(event:FocusEvent){if(!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node|null))closeMenu()}
</script>
<style scoped>
.companion-panel-header { position:relative; display:flex; flex-direction:column; gap:8px; padding:10px 14px; border-bottom:1px solid #eee9f7; background:#fff; border-radius:18px 18px 0 0; flex:none; color:#30264e; }
.companion-heading { min-height:40px; padding-right:84px; display:flex; align-items:center; }.companion-heading strong { font-size:17px; font-weight:650; }
.companion-header-actions { display:flex; flex-wrap:wrap; gap:6px; }.companion-header-actions button { display:flex; align-items:center; justify-content:center; gap:5px; min-height:34px; padding:5px 8px; border:1px solid #e5ddf3; border-radius:8px; font-size:15px; background:#fff; color:#7655b1; cursor:pointer; }.companion-header-actions button:last-child { margin-left:auto; min-width:34px; }.companion-header-actions button:hover { background:#f5f0ff; }.companion-header-actions button:focus-visible { outline:2px solid #8561cc; outline-offset:2px; }.companion-header-actions button:disabled { opacity:.5; cursor:wait; }
.companion-perch { position:absolute; right:14px; top:10px; width:76px; height:40px; pointer-events:none; }.companion-perch img { width:40px; height:40px; object-fit:contain; }
.companion-panel-header{flex-direction:row;align-items:center;gap:8px;padding:10px 14px}
.companion-heading{flex:1;min-width:0;min-height:36px;padding-right:0}
.companion-header-actions{order:3;flex-wrap:nowrap;align-items:center}
.companion-perch{position:relative;right:auto;top:auto;width:76px;height:40px;flex:none;order:2}
.companion-session-menu{position:relative}
.companion-session-menu summary{display:grid;place-items:center;list-style:none;cursor:pointer;width:34px;height:34px;color:#5e5476;border-radius:8px}
.companion-session-menu summary::-webkit-details-marker{display:none}
.companion-session-menu summary:hover{background:#f5f0ff}
.companion-session-menu>div{position:absolute;right:0;top:calc(100% + 8px);z-index:10;display:grid;gap:4px;min-width:160px;padding:6px;background:white;border:1px solid #ded8ea;border-radius:10px;box-shadow:0 8px 24px #34224918}
.companion-header-actions .companion-session-menu button{justify-content:flex-start;white-space:nowrap;border:0;margin:0;width:100%}
.companion-session-menu summary:focus-visible{outline:2px solid #8561cc;outline-offset:2px}
</style>
