<template>
  <span
    class="course-cover"
    :data-testid="`course-cover-${courseId}`"
    :data-cover-preset="preset"
    aria-hidden="true"
  >
    <img class="course-cover__book" :src="bookMaster" alt="" width="312" height="468" loading="lazy" />
    <span class="course-cover__artwork">
      <span class="course-cover__pattern"></span>
      <component :is="artwork.symbol" class="course-cover__symbol" :size="30" :stroke-width="2.2" />
      <component :is="artwork.detail" class="course-cover__detail" :size="13" :stroke-width="2.1" />
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import {
  Atom,
  BookOpenCheck,
  Bookmark,
  BrainCircuit,
  CircuitBoard,
  Code2,
  Cog,
  FlaskConical,
  Grid3X3,
  HeartPulse,
  MessagesSquare,
  Network,
  Quote,
  Sigma,
  SquareTerminal,
  Stethoscope,
} from 'lucide-vue-next'
import bookMaster from '../assets/course-covers/course-book-master.png'
import { courseCoverPreset, type CourseCoverPreset } from '../utils/course-presentation'

const props = defineProps<{
  courseId: string
  title: string
}>()

interface CoverArtwork {
  symbol: Component
  detail: Component
}

const coverArtwork: Record<CourseCoverPreset, CoverArtwork> = {
  ai: { symbol: BrainCircuit, detail: Network },
  programming: { symbol: Code2, detail: SquareTerminal },
  mathematics: { symbol: Sigma, detail: Grid3X3 },
  medicine: { symbol: HeartPulse, detail: Stethoscope },
  engineering: { symbol: Cog, detail: CircuitBoard },
  science: { symbol: Atom, detail: FlaskConical },
  humanities: { symbol: MessagesSquare, detail: Quote },
  general: { symbol: BookOpenCheck, detail: Bookmark },
}

const preset = computed(() => courseCoverPreset(props.title))
const artwork = computed(() => coverArtwork[preset.value])
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

.course-cover__artwork {
  position: absolute;
  z-index: 1;
  top: 20%;
  left: 23%;
  width: 58%;
  height: 58%;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, .42);
  border-radius: 7px 5px 5px 7px;
  color: var(--cover-ink, #fff);
  background: linear-gradient(155deg, var(--cover-top), var(--cover-bottom));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .28), 0 5px 12px rgba(30, 27, 75, .2);
}

.course-cover__pattern {
  position: absolute;
  inset: 0;
  display: block;
  opacity: .38;
}

.course-cover__symbol {
  position: absolute;
  z-index: 1;
  top: 13px;
  left: 50%;
  width: 30px;
  height: 30px;
  transform: translateX(-50%);
  filter: drop-shadow(0 2px 3px rgba(15, 23, 42, .24));
}

.course-cover__detail {
  position: absolute;
  z-index: 2;
  right: 5px;
  bottom: 5px;
  width: 13px;
  height: 13px;
  padding: 2px;
  border: 1px solid rgba(255, 255, 255, .38);
  border-radius: 50%;
  background: rgba(15, 23, 42, .24);
  box-sizing: content-box;
}

.course-cover[data-cover-preset='ai'] { --cover-top:#2563eb; --cover-bottom:#164e63; --cover-ink:#cffafe; }
.course-cover[data-cover-preset='programming'] { --cover-top:#0f766e; --cover-bottom:#134e4a; --cover-ink:#ccfbf1; }
.course-cover[data-cover-preset='mathematics'] { --cover-top:#7c3aed; --cover-bottom:#4c1d95; --cover-ink:#ede9fe; }
.course-cover[data-cover-preset='medicine'] { --cover-top:#e11d48; --cover-bottom:#881337; --cover-ink:#fff1f2; }
.course-cover[data-cover-preset='engineering'] { --cover-top:#ea580c; --cover-bottom:#7c2d12; --cover-ink:#ffedd5; }
.course-cover[data-cover-preset='science'] { --cover-top:#0891b2; --cover-bottom:#155e75; --cover-ink:#cffafe; }
.course-cover[data-cover-preset='humanities'] { --cover-top:#ca8a04; --cover-bottom:#713f12; --cover-ink:#fef9c3; }
.course-cover[data-cover-preset='general'] { --cover-top:#64748b; --cover-bottom:#334155; --cover-ink:#f8fafc; }

.course-cover[data-cover-preset='ai'] .course-cover__pattern,
.course-cover[data-cover-preset='engineering'] .course-cover__pattern {
  background-image: radial-gradient(circle, currentColor 1px, transparent 1.5px);
  background-size: 10px 10px;
}

.course-cover[data-cover-preset='programming'] .course-cover__pattern,
.course-cover[data-cover-preset='humanities'] .course-cover__pattern {
  background-image: repeating-linear-gradient(to bottom, transparent 0 8px, currentColor 8px 9px);
}

.course-cover[data-cover-preset='mathematics'] .course-cover__pattern {
  background-image: linear-gradient(currentColor 1px, transparent 1px), linear-gradient(90deg, currentColor 1px, transparent 1px);
  background-size: 12px 12px;
}

.course-cover[data-cover-preset='medicine'] .course-cover__pattern {
  background: linear-gradient(90deg, transparent 42%, currentColor 42% 58%, transparent 58%), linear-gradient(transparent 42%, currentColor 42% 58%, transparent 58%);
  transform: scale(.38);
}

.course-cover[data-cover-preset='science'] .course-cover__pattern {
  background: radial-gradient(circle at 48% 44%, transparent 0 14px, currentColor 15px, transparent 16px 100%);
}

.course-cover[data-cover-preset='general'] .course-cover__pattern {
  background-image: repeating-linear-gradient(135deg, transparent 0 10px, currentColor 10px 11px);
}

@media (max-width: 700px) {
  .course-cover { width: 72px; }
}
</style>
