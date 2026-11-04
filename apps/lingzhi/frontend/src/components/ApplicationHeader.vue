<template>
  <header class="app-header glass-panel-elevated" :class="{ 'is-contextual': contextual, 'is-library': library, 'has-library-center': library && !learning && centered, 'has-no-center': !centered }">
    <div class="app-header-start">
      <slot name="before-brand" />
      <ProductBrand v-if="showBrand" :surface="surface" />
      <div v-if="!learning" :id="contextId" class="route-header-context"><slot name="context" /></div>
    </div>
    <div v-if="!learning && centered" :id="centerId" class="app-header-center"><slot name="center" /></div>
    <div class="app-header-tools">
      <component :is="compactActions ? 'details' : 'div'" ref="actionsMenu" :class="compactActions ? 'app-header-menu' : 'app-header-inline-actions'" @keydown.esc="closeMenu(true)">
        <summary v-if="compactActions" :aria-label="activeLocale === 'zh' ? '更多阅读选项' : 'More reading options'"><MoreHorizontal :size="22" /></summary>
        <div class="app-header-menu-content">
          <div :id="learning ? undefined : actionsId" :class="learning ? 'header-actions' : 'route-header-actions'"><slot name="actions" /></div>
          <WorkspaceSwitcher :surface="surface" />
        </div>
      </component>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { MoreHorizontal } from 'lucide-vue-next'
import { activeLocale } from '../shared/i18n'
import ProductBrand from './ProductBrand.vue'
import WorkspaceSwitcher from './WorkspaceSwitcher.vue'
import type { ProductSurface } from '../shared/product-brand'
withDefaults(defineProps<{
  surface: ProductSurface
  compactActions?: boolean
  contextual?: boolean
  library?: boolean
  learning?: boolean
  showBrand?: boolean
  centered?: boolean
  contextId?: string
  centerId?: string
  actionsId?: string
}>(), { contextual: false, library: false, learning: false, showBrand: true, centered: true })
const actionsMenu = ref<HTMLElement | null>(null)
function closeMenu(focus = false) {
  if (actionsMenu.value?.tagName !== 'DETAILS') return
  const menu = actionsMenu.value as HTMLDetailsElement
  menu.open = false
  if (focus) actionsMenu.value.querySelector('summary')?.focus()
}
function dismissMenu(event: PointerEvent) {
  if (!actionsMenu.value?.contains(event.target as Node)) closeMenu()
}
onMounted(() => document.addEventListener('pointerdown', dismissMenu))
onBeforeUnmount(() => document.removeEventListener('pointerdown', dismissMenu))
</script>

<style>
.app-header-inline-actions, .app-header-inline-actions > .app-header-menu-content { display: contents; }
.app-header-menu > summary { display: flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; cursor: pointer; list-style: none; border-radius: 9px; }
.app-header-menu > summary::-webkit-details-marker { display: none; }
.app-header-menu[open] > summary { background: var(--lz-brand-soft); }
.app-header-menu > .app-header-menu-content { position: absolute; top: calc(100% + 6px); right: 0; width: min(320px, calc(100vw - 24px)); max-height: calc(100dvh - 90px); overflow: auto; display: flex; flex-direction: column; align-items: stretch; gap: 14px; padding: 16px; box-sizing: border-box; border: 1px solid var(--lz-border); border-radius: 12px; background: #fff; box-shadow: 0 12px 32px #26335026; }
.app-header-menu .route-header-actions { justify-self: stretch; }
.app-header-menu .workspace-switcher { align-self: flex-end; }
/* One header implementation for teacher and student workspaces. */
.app-header {
  position: relative;
  z-index: 80;
  min-width: 0;
  min-height: 60px;
  flex: none;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(480px, 660px) minmax(150px, 1fr);
  align-items: center;
  gap: 16px;
  padding: 0 17px;
  border: 1px solid rgba(255, 255, 255, 0.88);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,.96), rgba(250,250,255,.91));
  box-shadow: 0 8px 26px rgba(79,70,229,.08), inset 0 1px 0 rgba(255,255,255,.96);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.app-header.is-contextual {
  grid-template-columns: minmax(180px, 1fr) auto auto;
  gap: 12px;
}

.app-header.is-contextual .app-header-start { gap:12px; }

.app-header .app-header-start {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-header .route-header-context {
  min-width: 0;
  flex: 1;
}

.app-header .app-header-center { min-width:0; width:100%; justify-self:center; }
.app-header .app-header-tools { min-width:0; grid-column:3; justify-self:end; display:flex; align-items:center; gap:12px; }
.app-header .route-header-actions { min-width:0; grid-column:3; justify-self:end; }
.app-header.is-library { grid-template-columns:minmax(0,1fr) auto minmax(max-content,1fr); }
.app-header.is-library .route-header-actions { display:flex; align-items:center; gap:10px; }

.app-header .header-actions { position:relative; grid-column:3; justify-self:end; display:flex; align-items:center; justify-content:flex-end; gap:5px; padding-left:13px; }
.app-header .header-actions::before { content:""; position:absolute; left:0; width:1px; height:26px; background:linear-gradient(180deg,transparent,#dbe3ef,transparent); }

@media (max-width: 900px) {
  .app-header { grid-template-columns: auto minmax(180px, 1fr) auto; gap: 8px; padding: 0 10px; }
  .app-header.is-contextual { grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); }
}

@media (max-width: 1280px) {
  .app-header.is-contextual:lang(en) {
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:58px 44px;
    gap:0 8px;
    padding:0 10px;
  }
  .app-header.is-contextual:lang(en) .app-header-start { grid-column:1; grid-row:1; }
  .app-header.is-contextual:lang(en) .app-header-center {
    grid-column:1/-1;
    grid-row:2;
    align-self:stretch;
    display:flex;
    align-items:center;
    justify-content:center;
    border-top:1px solid var(--lz-border);
  }
  .app-header.is-contextual:lang(en) .app-header-tools { grid-column:2; grid-row:1; }
}

@media (max-width: 1100px) {
  .app-header.is-contextual {
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:58px 44px;
    gap:0 8px;
    padding:0 10px;
  }
  .app-header.is-contextual .app-header-start { grid-column:1; grid-row:1; }
  .app-header.is-contextual .app-header-center {
    grid-column:1/-1;
    grid-row:2;
    align-self:stretch;
    display:flex;
    align-items:center;
    justify-content:center;
    border-top:1px solid var(--lz-border);
  }
  .app-header.is-contextual .app-header-tools { grid-column:2; grid-row:1; }
}

@media (max-width: 600px) {
  .app-header { border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
  .app-header { grid-template-columns: auto minmax(70px, 1fr) auto; min-height:60px; }
  .app-header.is-library.has-library-center {
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:58px 44px;
    gap:0 8px;
    min-height:104px;
    padding:0 10px;
  }
  .app-header.is-library.has-library-center > .app-header-start { grid-column:1; grid-row:1; }
  .app-header.is-library.has-library-center > .app-header-center {
    grid-column:1/-1;
    grid-row:2;
    align-self:stretch;
    display:flex;
    align-items:center;
    justify-content:flex-start;
    border-top:1px solid var(--lz-border);
  }
  .app-header.is-library.has-library-center > .app-header-tools { grid-column:2; grid-row:1; gap:6px; }
  .app-header .route-header-actions,
.app-header .header-actions { grid-column:3; grid-row:1; }
  .app-header .header-actions .header-icon-button:nth-of-type(1),
.app-header .header-actions .el-popover__reference-wrapper,
.app-header .header-actions .el-dropdown { display: none; }
}
.app-header.has-no-center { grid-template-columns: minmax(0, 1fr) auto; }
.app-header.has-no-center > .app-header-tools { grid-column: 2; }
</style>
