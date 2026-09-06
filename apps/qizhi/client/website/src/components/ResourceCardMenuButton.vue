<template>
  <button
    type="button"
    class="card-menu-btn"
    title="更多操作"
    aria-label="更多操作"
    @click.stop="$emit('click')"
  >
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="6" r="1.75" fill="currentColor" />
      <circle cx="12" cy="12" r="1.75" fill="currentColor" />
      <circle cx="12" cy="18" r="1.75" fill="currentColor" />
    </svg>
  </button>
</template>

<script setup lang="ts">
defineEmits<{ (e: 'click'): void }>()
</script>
