<template>
  <TeacherCoursePreview v-if="teacherPreview" />
  <LearnerCourseView v-else />
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const teacherPreview = computed(() => String(route.query.teacherPreview || '') === '1')
// The learner module is not even imported on a teacher trial. Its setup and
// persistent learning stores cannot run on this surface.
const LearnerCourseView = defineAsyncComponent(() => import('./LearnerCourseView.vue'))
const TeacherCoursePreview = defineAsyncComponent(() => import('./TeacherCoursePreview.vue'))
</script>
