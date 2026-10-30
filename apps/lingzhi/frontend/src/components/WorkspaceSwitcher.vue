<template>
  <UiSegmentedControl
    v-if="canOpenTeacher"
    class="workspace-switcher"
    :model-value="surface"
    :options="options"
    :accessibility-label="t('app.switchWorkspace', '切换工作空间')"
    @update:model-value="switchWorkspace"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import UiSegmentedControl from './UiSegmentedControl.vue'
import { activeLocale, t } from '../shared/i18n'
import { productIdentity, type ProductSurface } from '../shared/product-brand'
import { configuredStudyPortal, configuredTeacherPortal } from '../shared/study-portal'

defineProps<{ surface: ProductSurface }>()
const router = useRouter()
const teacherPortal = configuredTeacherPortal(import.meta.env.VITE_TEACHER_APP_URL)
const studentPortal = configuredStudyPortal(import.meta.env.VITE_STUDY_APP_URL)
// A student-only deployment cannot serve teacher routes without a peer URL.
const canOpenTeacher = import.meta.env.VITE_APP_SURFACE !== 'student'
  || (!!teacherPortal && !teacherPortal.startsWith('/'))
const options = computed(() => (['teacher', 'student'] as const).map(surface => ({
  value: surface,
  label: productIdentity(surface, activeLocale.value).role,
})))

function switchWorkspace(surface: string) {
  const target = surface === 'teacher' ? teacherPortal || '/courses' : studentPortal || '/study'
  if (target.startsWith('/')) void router.push(target)
  else window.location.assign(target)
}
</script>

<style scoped>
.workspace-switcher {
  --ui-segment-font-size: 15px;
  flex: none;
}
</style>
