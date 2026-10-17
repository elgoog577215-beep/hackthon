<template>
  <ProductBrand surface="student" class="student-brand" :to="to" :accessible-label="accessibleLabel" />
</template>
<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import ProductBrand from './ProductBrand.vue'
defineProps<{ to?: RouteLocationRaw; accessibleLabel?: string }>()
</script>
