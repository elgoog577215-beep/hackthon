<template>
  <RouterLink :to="to || identity.home" class="product-brand" :data-product-surface="surface" :aria-label="accessibleLabel || identity.title">
    <img class="product-brand-mark" :src="iconUrl" :alt="identity.name" width="38" height="38" />
    <span class="product-brand-copy"><strong>{{ identity.name }}</strong><small>{{ identity.role }}</small></span>
  </RouterLink>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { activeLocale } from '../shared/i18n'
import { productIdentity, type ProductSurface } from '../shared/product-brand'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'
const props = defineProps<{ surface: ProductSurface; to?: RouteLocationRaw; accessibleLabel?: string }>()
const identity = computed(() => productIdentity(props.surface, activeLocale.value))
const iconUrl = computed(() => resolvePublicAssetUrl(identity.value.icon, import.meta.env.BASE_URL))
</script>
<style scoped>
.product-brand{display:inline-flex;align-items:center;gap:9px;flex-shrink:0;text-decoration:none;border-radius:10px}.product-brand-mark{display:block;width:38px;height:38px;object-fit:contain;flex:none}.product-brand-copy{display:grid;gap:2px;white-space:nowrap}.product-brand-copy strong{font-size:20px;line-height:1.15;letter-spacing:.02em;font-weight:750;color:var(--lz-brand-strong)}.product-brand-copy small{font-size:15px;line-height:1.2;color:var(--lz-text-secondary)}.product-brand:focus-visible{outline:2px solid var(--lz-brand);outline-offset:3px}
</style>
