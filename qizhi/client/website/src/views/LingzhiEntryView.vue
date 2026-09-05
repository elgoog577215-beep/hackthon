<template>
  <main class="lingzhi-entry" aria-live="polite">
    <div class="lingzhi-entry-spinner" aria-hidden="true"></div>
    <p>正在进入新版课程…</p>
  </main>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

const configuredTarget = String(import.meta.env.VITE_LINGZHI_COURSES_URL || '').trim()
const safeTarget = /^(?:https?:\/\/|\/(?!\/))/i.test(configuredTarget)
  ? configuredTarget
  : ''
const target = safeTarget || (import.meta.env.DEV
  ? 'http://127.0.0.1:5173/courses'
  : '/lingzhi/courses')

onMounted(() => {
  window.location.replace(target)
})
</script>

<style scoped>
.lingzhi-entry {
  min-height: 60vh;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 12px;
  color: #475569;
}

.lingzhi-entry-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #dbeafe;
  border-top-color: #4f46e5;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .lingzhi-entry-spinner { animation: none; }
}
</style>
