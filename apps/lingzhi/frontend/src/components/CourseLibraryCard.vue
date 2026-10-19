<template>
  <article class="course-library-card">
    <div class="course-library-card__heading">
      <span class="course-library-card__mark" aria-hidden="true"><BookOpenText :size="22" /></span>
      <div class="course-library-card__identity">
        <h2>
          <slot name="title">{{ title }}</slot>
        </h2>
        <p v-if="origin" class="course-library-card__origin">{{ origin }}</p>
      </div>
    </div>
    <div v-if="$slots.default" class="course-library-card__body"><slot /></div>
    <footer v-if="$slots.actions" class="course-library-card__actions">
      <span v-if="$slots.summary" class="course-library-card__summary"><slot name="summary" /></span>
      <slot name="actions" />
    </footer>
    <slot name="details" />
  </article>
</template>

<script setup lang="ts">
import { BookOpenText } from "lucide-vue-next";
defineProps<{ courseId: string; title: string; origin?: string }>();
</script>

<style scoped>
.course-library-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 22px;
  border: 1px solid var(--lz-border);
  border-radius: var(--lz-radius-surface);
  background: var(--lz-surface, #fff);
  box-shadow: 0 2px 8px rgba(49, 46, 129, 0.02);
  transition: border-color .15s, box-shadow .15s;
}
.course-library-card:hover {
  border-color: #d5cdee;
  box-shadow: 0 5px 16px rgba(49, 46, 129, 0.04);
}
.course-library-card__heading {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-height: 60px;
}
.course-library-card__mark {
  flex: none; width: 40px; height: 40px; display: grid; place-items: center;
  border-radius: 10px; background: #f1efff; color: #7161e8;
}
.course-library-card__identity {
  min-width: 0;
  flex: 1;
}
.course-library-card__origin {
  margin: 4px 0 0;
  font-size: 15px;
  color: var(--lz-text-secondary);
}
h2 {
  margin: 0;
  color: var(--lz-text-strong);
  font-size: 18px;
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
.course-library-card__summary {
  flex: 1;
  color: var(--lz-text-secondary);
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
  justify-content: flex-end;
  gap: 12px;
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid #eceef4;
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
