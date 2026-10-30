<template>
  <header class="app-header glass-panel-elevated" :class="{ 'is-contextual': contextual, 'is-library': library, 'has-no-center': !centered }">
    <div class="app-header-start">
      <slot name="before-brand" />
      <ProductBrand v-if="showBrand" :surface="surface" />
      <div v-if="!learning" :id="contextId" class="route-header-context"><slot name="context" /></div>
    </div>
    <div v-if="!learning && centered" :id="centerId" class="app-header-center"><slot name="center" /></div>
    <div class="app-header-tools">
      <div :id="learning ? undefined : actionsId" :class="learning ? 'header-actions' : 'route-header-actions'"><slot name="actions" /></div>
      <WorkspaceSwitcher :surface="surface" />
    </div>
  </header>
</template>

<script setup lang="ts">
import ProductBrand from './ProductBrand.vue'
import WorkspaceSwitcher from './WorkspaceSwitcher.vue'
import type { ProductSurface } from '../shared/product-brand'
withDefaults(defineProps<{
  surface: ProductSurface
  contextual?: boolean
  library?: boolean
  learning?: boolean
  showBrand?: boolean
  centered?: boolean
  contextId?: string
  centerId?: string
  actionsId?: string
}>(), { contextual: false, library: false, learning: false, showBrand: true, centered: true })
</script>

<style>
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
  .app-header .route-header-actions,
.app-header .header-actions { grid-column:3; grid-row:1; }
  .app-header .header-actions .header-icon-button:nth-of-type(1),
.app-header .header-actions .el-popover__reference-wrapper,
.app-header .header-actions .el-dropdown { display: none; }
}
.app-header.has-no-center { grid-template-columns: minmax(0, 1fr) auto; }
.app-header.has-no-center > .app-header-tools { grid-column: 2; }
</style>
