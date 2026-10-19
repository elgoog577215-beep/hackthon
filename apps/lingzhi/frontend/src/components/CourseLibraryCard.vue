<template>
  <article class="course-library-card">
    <div class="course-library-card__heading">
      <CourseCover :course-id="courseId" :title="title" />
      <div class="course-library-card__identity">
        <p v-if="origin" class="course-library-card__origin">{{ origin }}</p>
        <h2>
          <slot name="title">{{ title }}</slot>
        </h2>
        <slot name="summary" />
      </div>
    </div>
    <div v-if="$slots.default" class="course-library-card__body"><slot /></div>
    <footer v-if="$slots.actions" class="course-library-card__actions">
      <slot name="actions" />
    </footer>
    <slot name="details" />
  </article>
</template>

<script setup lang="ts">
import CourseCover from "./CourseCover.vue";
defineProps<{ courseId: string; title: string; origin?: string }>();
</script>

<style scoped>
.course-library-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 24px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-surface);
  background: var(--lz-surface, #fff);
  box-shadow: 0 3px 14px rgba(49, 46, 129, 0.035);
}
.course-library-card__heading {
  display: flex;
  align-items: center;
  gap: 22px;
  min-height: 126px;
  --course-cover-width: 72px;
}
.course-library-card__identity {
  min-width: 0;
  flex: 1;
}
.course-library-card__origin {
  margin: 0 0 9px;
  font-size: 15px;
  color: var(--lz-text-secondary);
}
h2 {
  margin: 0 0 10px;
  color: var(--lz-text-strong);
  font-size: 20px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
h2 :deep(a),
h2 :deep(button) {
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: start;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
}
h2 :deep(a:hover),
h2 :deep(button:hover) {
  color: var(--lz-brand-strong);
}
.course-library-card__body {
  margin-top: 18px;
  font-size: 15px;
  line-height: 1.7;
  color: var(--lz-text-secondary);
}
.course-library-card__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: auto;
  padding-top: 22px;
  font-size: 15px;
}
.course-library-card :deep(a:focus-visible),
.course-library-card :deep(button:focus-visible),
.course-library-card :deep(summary:focus-visible) {
  outline: 2px solid var(--lz-brand);
  outline-offset: 4px;
  border-radius: 4px;
}
@media (max-width: 1100px) {
  .course-library-card {
    padding: 20px;
  }
}
</style>
