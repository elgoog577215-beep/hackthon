<template>
  <ElCard class="course-library-card" shadow="hover" :body-style="{ padding: '18px', display: 'flex', flexDirection: 'column' }">
    <div class="course-library-card__heading">
      <span class="course-library-card__mark" aria-hidden="true"><BookOpenText :size="22" /></span>
      <div class="course-library-card__identity">
        <h2>
          <slot name="title">{{ title }}</slot>
        </h2>
      </div>
      <div v-if="$slots.actions" class="course-library-card__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
    <slot name="details" />
  </ElCard>
</template>

<script setup lang="ts">
import { ElCard } from "element-plus";
import { BookOpenText } from "lucide-vue-next";
defineProps<{ courseId: string; title: string }>();
</script>

<style scoped>
.course-library-card { min-width: 0; }
.course-library-card__heading {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 44px;
}
.course-library-card__mark {
  flex: none; width: 40px; height: 40px; display: grid; place-items: center;
  border-radius: 8px; background: #eef2ff; color: #4f46e5;
}
.course-library-card__identity {
  min-width: 0;
  flex: 1;
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
.course-library-card__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
}
.course-library-card :deep(.course-start) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--lz-action-primary-border);
  border-radius: var(--lz-radius-control);
  background: var(--lz-action-primary-bg);
  color: var(--lz-action-primary-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
  text-decoration: none;
  white-space: nowrap;
}
.course-library-card :deep(.course-start:hover) {
  background: var(--lz-action-primary-hover);
  color: var(--lz-action-primary-text);
}
@media (max-width: 430px) {
  .course-library-card__heading { grid-template-columns: 36px minmax(0, 1fr) auto; gap: 9px; }
  .course-library-card__mark { width: 36px; height: 36px; }
  h2 { font-size: 17px; }
  .course-library-card :deep(.course-start) { min-height: 44px; padding: 0 10px; font-size: 13px; }
}
@media (max-width: 380px) {
  .course-library-card__heading { grid-template-columns: 36px minmax(0, 1fr); align-items: start; row-gap: 8px; }
  .course-library-card__actions { grid-column: 2; justify-content: flex-start; }
}
.course-library-card :deep(a:focus-visible),
.course-library-card :deep(button:focus-visible),
.course-library-card :deep(summary:focus-visible) {
  outline: 2px solid var(--lz-brand);
  outline-offset: 4px;
  border-radius: 4px;
}

</style>
