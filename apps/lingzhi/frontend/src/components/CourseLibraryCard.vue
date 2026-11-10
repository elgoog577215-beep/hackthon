<template>
  <article class="course-library-card">
    <div class="course-library-card__heading">
      <span class="course-library-card__mark" aria-hidden="true"><BookOpenText :size="22" /></span>
      <div class="course-library-card__identity">
        <h2>
          <slot name="title">{{ title }}</slot>
        </h2>
      </div>
    </div>
    <div v-if="$slots.default" class="course-library-card__summary"><slot /></div>
    <footer v-if="$slots.actions" class="course-library-card__actions">
      <slot name="actions" />
    </footer>
    <div v-if="$slots.details" class="course-library-card__details"><slot name="details" /></div>
  </article>
</template>

<script setup lang="ts">
import { BookOpenText } from "lucide-vue-next";
defineProps<{ courseId: string; title: string }>();
</script>

<style scoped>
.course-library-card {
  min-width: 0; display: grid; grid-template-columns: minmax(200px, 1fr) minmax(160px, .65fr) auto;
  align-items: center; column-gap: 24px; padding: 18px 22px;
  background: var(--lz-surface); border-bottom: 1px solid var(--lz-border);
}
.course-library-card:last-child { border-bottom: 0; }
.course-library-card:hover { background: var(--lz-surface-subtle); }
.course-library-card__summary { min-width: 0; font-size: 15px; }
.course-library-card__summary :deep(p) { margin: 0; }
.course-library-card__details { grid-column: 1 / -1; }
.course-library-card__heading {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
}
.course-library-card__mark {
  flex: none; width: 40px; height: 40px; display: grid; place-items: center;
  border-radius: 8px; background: var(--lz-brand-soft); color: var(--lz-brand-strong);
}
.course-library-card__identity {
  min-width: 0;
  flex: 1;
}
h2 {
  margin: 0;
  color: var(--lz-text-strong);
  font-size: 16px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
h2 :deep(a),
h2 :deep(button) {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
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
.course-library-card__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  margin: 0;
  padding: 0;
  grid-column: 3;
  font-size: 15px;
}
.course-library-card :deep(a:focus-visible),
.course-library-card :deep(button:focus-visible),
.course-library-card :deep(summary:focus-visible) {
  outline: 2px solid var(--lz-brand);
  outline-offset: 4px;
  border-radius: 4px;
}

@media (max-width: 760px) {
  .course-library-card { grid-template-columns: minmax(0, 1fr) auto; gap: 10px 12px; padding: 16px; }
  .course-library-card__heading { grid-column: 1; }
  .course-library-card__summary { grid-column: 1; padding-left: 52px; }
  .course-library-card__actions { grid-column: 2; grid-row: 1 / 3; }
}
@media (max-width: 480px) {
  .course-library-card { grid-template-columns: minmax(0, 1fr); gap: 10px; }
  .course-library-card__heading,
  .course-library-card__summary,
  .course-library-card__actions,
  .course-library-card__details { grid-column: 1; grid-row: auto; }
  .course-library-card__actions { flex-direction: column; align-items: stretch; gap: 8px; }
  .course-library-card__actions :deep(.course-start),
  .course-library-card__actions :deep(.course-update-action) { width: 100%; min-height: 46px; justify-content: center; }
  .course-library-card__actions :deep(.el-button:not(.is-text):not(.is-link):not(.el-button--small)) { min-height: 44px; }
}
</style>
