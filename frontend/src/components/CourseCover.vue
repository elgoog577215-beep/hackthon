<template>
  <span
    class="course-cover"
    :data-testid="`course-cover-${courseId}`"
    :data-cover-preset="preset"
    aria-hidden="true"
  >
    <img class="course-cover__book" :src="bookMaster" alt="" width="312" height="468" loading="lazy" />
    <component :is="artworkIcon" class="course-cover__art" :size="38" :stroke-width="2.25" aria-hidden="true" />
  </span>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Atom, BookMarked, BookOpen, Box, Grid3X3, Network } from 'lucide-vue-next'
import bookMaster from '../assets/course-covers/course-book-master.png'
import { courseCoverPreset, type CourseCoverPreset } from '../utils/course-presentation'

const props = defineProps<{
  courseId: string
  title: string
}>()

const artworkIcons: Record<CourseCoverPreset, Component> = {
  ai: Network,
  programming: Box,
  mathematics: Grid3X3,
  science: Atom,
  humanities: BookOpen,
  general: BookMarked,
}

const preset = computed(() => courseCoverPreset(props.title))
const artworkIcon = computed(() => artworkIcons[preset.value])
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

.course-cover__art {
  position: absolute;
  z-index: 1;
  top: 32%;
  left: 30%;
  width: 43%;
  height: 29%;
  display: block;
  color: #fff;
  filter: drop-shadow(0 2px 2px rgba(49, 46, 129, .18));
}

@media (max-width: 700px) {
  .course-cover { width: 72px; }
}
</style>
