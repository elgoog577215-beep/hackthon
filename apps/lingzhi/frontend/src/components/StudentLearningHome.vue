<template>
  <StudentCourseLibrary
    ref="library"
    :user-id="userId"
    :materials="materials"
    :refreshing="refreshing"
    @refresh="emit('refresh')"
    :initial-filter="initialFilter"
    unified
    @source="emit('source', $event)"
    @create="emit('create', $event)"
    @filter="emit('filter', $event)"
  />
</template>
<script setup lang="ts">
import { ref } from "vue";
import type { StudyPurpose, StudySource, StudySummary } from "../api/study";
import StudentCourseLibrary from "./StudentCourseLibrary.vue";
defineProps<{
  userId: string;
  refreshing?: boolean;
  materials: StudySummary[];
  initialFilter?: "all" | "teacher" | "owned";
}>();
const emit = defineEmits<{
  create: [purpose: StudyPurpose];
  refresh: [];
  source: [source: StudySource];
  filter: [value: "all" | "teacher" | "owned"];
}>();
const library = ref<InstanceType<typeof StudentCourseLibrary> | null>(null);
defineExpose({ reload: () => library.value?.reload() });
</script>
