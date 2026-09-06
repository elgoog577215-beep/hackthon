<template>
  <OutlineFormPanel :flow="flow" :bound-course-id="boundCourseId" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import OutlineFormPanel, { type OutlineFormFlow } from '../components/outline-form/OutlineFormPanel.vue'

const route = useRoute()

const boundCourseId = computed(() => {
  const id = route.query.course_id
  if (id == null || id === '') return null
  return String(id)
})

const flow = computed<OutlineFormFlow>(() =>
  boundCourseId.value ? 'course-bound' : 'resource'
)
</script>
