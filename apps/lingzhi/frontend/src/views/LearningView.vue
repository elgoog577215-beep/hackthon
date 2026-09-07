<template>
  <LearnerCourseView />
</template>
<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
// Both views share the original UI; preview I/O is isolated in existing stores.
const LearnerCourseView = defineAsyncComponent(() => import('./LearnerCourseView.vue'))
</script>
