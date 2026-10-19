<template>
  <ElCard class="course-library-card" shadow="hover" :body-style="{ padding: '22px', display: 'flex', flexDirection: 'column' }">
    <div class="course-library-card__heading">
      <span class="course-library-card__mark" aria-hidden="true"><BookOpenText :size="22" /></span>
      <div class="course-library-card__identity">
        <h2>
          <slot name="title">{{ title }}</slot>
        </h2>
      </div>
    </div>
    <slot />
    <footer v-if="$slots.actions" class="course-library-card__actions">
      <slot name="actions" />
    </footer>
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
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-height: 40px;
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
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid #e8edf4;
  font-size: 15px;
}
.course-library-card :deep(a:focus-visible),
.course-library-card :deep(button:focus-visible),
.course-library-card :deep(summary:focus-visible) {
  outline: 2px solid var(--lz-brand);
  outline-offset: 4px;
  border-radius: 4px;
}

</style>
