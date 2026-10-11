<template>
  <div v-if="showMap" class="handout-reading-layout has-concept-map">
    <div class="handout-reading-body"><slot /></div>
    <slot name="aside" />
  </div>
  <slot v-else />
</template>
<script setup lang="ts">
defineProps<{ showMap: boolean }>()
</script>
