<template><PptProjectWorkspace ref="workspace" :key="String(route.params.courseId)" :course-id="String(route.params.courseId)" :initial-lesson-id="String(route.query.lessonId || '')" /></template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import PptProjectWorkspace from '../components/PptProjectWorkspace.vue'
const route = useRoute()
const workspace = ref<InstanceType<typeof PptProjectWorkspace> | null>(null)
onBeforeRouteLeave(() => workspace.value?.prepareToLeave() ?? true)
onBeforeRouteUpdate(() => workspace.value?.prepareToLeave() ?? true)
</script>
