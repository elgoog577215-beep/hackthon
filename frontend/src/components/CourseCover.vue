<template>
  <span
    class="course-cover"
    :data-testid="`course-cover-${courseId}`"
    :data-cover-preset="preset"
    aria-hidden="true"
  >
    <img class="course-cover__book" :src="bookTexture" alt="" width="312" height="468" loading="lazy" />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import bookAi from '../assets/course-covers/course-book-ai.png'
import bookEngineering from '../assets/course-covers/course-book-engineering.png'
import bookGeneral from '../assets/course-covers/course-book-general.png'
import bookHumanities from '../assets/course-covers/course-book-humanities.png'
import bookMathematics from '../assets/course-covers/course-book-mathematics.png'
import bookMedicine from '../assets/course-covers/course-book-medicine.png'
import bookProgramming from '../assets/course-covers/course-book-programming.png'
import bookScience from '../assets/course-covers/course-book-science.png'
import { courseCoverPreset, type CourseCoverPreset } from '../utils/course-presentation'

const props = defineProps<{
  courseId: string
  title: string
}>()

const bookTextures: Record<CourseCoverPreset, string> = {
  ai: bookAi,
  programming: bookProgramming,
  mathematics: bookMathematics,
  medicine: bookMedicine,
  engineering: bookEngineering,
  science: bookScience,
  humanities: bookHumanities,
  general: bookGeneral,
}

const preset = computed(() => courseCoverPreset(props.title))
const bookTexture = computed(() => bookTextures[preset.value])
</script>

<style scoped>
.course-cover {
  position: relative;
  width: var(--course-cover-width, 78px);
  aspect-ratio: 2 / 3;
  display: block;
  flex: 0 0 auto;
  overflow: visible;
}

.course-cover__book {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  filter: drop-shadow(0 11px 16px rgba(49, 46, 129, .24));
}

@media (max-width: 700px) {
  .course-cover { width: 72px; }
}
</style>
