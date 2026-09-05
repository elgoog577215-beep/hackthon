<template>
  <span
    class="course-cover"
    :class="{ 'course-cover--glyph': variant === 'glyph' }"
    :data-testid="`course-cover-${courseId}`"
    :data-cover-preset="preset"
    aria-hidden="true"
  >
    <BookOpenText v-if="variant === 'glyph'" class="course-cover__glyph" :size="24" :stroke-width="1.8" />
    <img v-else class="course-cover__book" :src="bookTexture" alt="" width="312" height="468" loading="lazy" />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BookOpenText } from 'lucide-vue-next'
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
  variant?: 'book' | 'glyph'
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

.course-cover--glyph {
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 14px;
  color: #4f46e5;
  background: #eef2ff;
}

.course-cover--glyph[data-cover-preset='programming'] { color:#0f766e; background:#ecfdf5; }
.course-cover--glyph[data-cover-preset='mathematics'] { color:#6d28d9; background:#f5f3ff; }
.course-cover--glyph[data-cover-preset='medicine'] { color:#be123c; background:#fff1f2; }
.course-cover--glyph[data-cover-preset='engineering'] { color:#0369a1; background:#f0f9ff; }
.course-cover--glyph[data-cover-preset='science'] { color:#1d4ed8; background:#eff6ff; }
.course-cover--glyph[data-cover-preset='humanities'] { color:#b45309; background:#fffbeb; }
.course-cover--glyph[data-cover-preset='general'] { color:#475569; background:#f1f5f9; }
.course-cover__glyph { display:block; }

@media (max-width: 700px) {
  .course-cover { width: var(--course-cover-width, 68px); }
}
</style>
