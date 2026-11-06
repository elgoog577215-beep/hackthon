<template>
  <ElCard class="course-library-card" shadow="never">
    <div class="course-library-card__heading">
      <span class="course-library-card__mark" aria-hidden="true">
        <BookOpenText :size="18" />
      </span>
      <div class="course-library-card__identity">
        <h2><slot name="title">{{ title }}</slot></h2>
      </div>
      <div class="course-library-card__menu">
        <slot name="menu" />
      </div>
    </div>
    <div class="course-library-card__footer">
      <div class="course-library-card__meta"><slot /></div>
      <div class="course-library-card__actions"><slot name="actions" /></div>
    </div>
    <slot name="details" />
  </ElCard>
</template>

<script setup lang="ts">
import { ElCard } from "element-plus";
import { BookOpenText } from "lucide-vue-next";

defineProps<{ courseId: string; title: string }>();
</script>

<style scoped>
.course-library-card {
  position: relative;
  width: 100%;
  height: 112px;
  min-width: 0;
  overflow: visible;
  box-sizing: border-box;
  border: 1px solid var(--lz-border);
  border-radius: var(--radius-md, 12px);
  background: #fff;
  box-shadow: none;
  transition: border-color 140ms ease;
}

.course-library-card:hover {
  border-color: var(--lz-border-strong);
}

.course-library-card:focus-within {
  z-index: 5;
}

.course-library-card :deep(.el-card__body) {
  position: relative;
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: minmax(0, 1fr) 28px;
  gap: 8px;
  box-sizing: border-box;
  overflow: visible;
  padding: 12px 14px;
  border-radius: inherit;
}

.course-library-card__heading {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) 32px;
  align-items: start;
  gap: 8px;
}

.course-library-card__mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  margin-top: 2px;
  border-radius: var(--radius-sm, 8px);
  background: var(--lz-brand-soft);
  color: var(--lz-brand-strong);
}

.course-library-card__identity {
  min-width: 0;
  max-height: 2.8em;
  overflow: hidden;
}

h2 {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  color: var(--lz-text-strong);
  font-size: var(--text-base, 16px);
  font-weight: var(--font-semibold, 600);
  line-height: 1.4;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

h2 :deep(a),
h2 :deep(button) {
  display: -webkit-box;
  overflow: hidden;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: start;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

h2 :deep(a:hover),
h2 :deep(button:hover) {
  color: var(--lz-brand-strong);
}

.course-library-card__menu,
.course-library-card__actions {
  min-width: 0;
  display: flex;
  align-items: center;
}

.course-library-card__menu {
  justify-content: flex-end;
}

.course-library-card__footer {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.course-library-card__meta {
  min-width: 0;
  overflow: hidden;
  color: var(--lz-text-secondary);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-library-card :deep(.course-start) {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 2px;
  border: 0;
  border-radius: var(--radius-sm, 8px);
  background: transparent;
  color: var(--lz-brand-strong);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
  text-decoration: none;
  white-space: nowrap;
}

.course-library-card :deep(.course-start:hover) {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.course-library-card :deep(.course-actions-menu) {
  position: relative;
  display: flex;
  flex: none;
}

.course-library-card :deep(.course-actions-menu > summary) {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-xs, 4px);
  color: var(--lz-text-secondary);
  cursor: pointer;
  list-style: none;
}

.course-library-card :deep(.course-actions-menu > summary::-webkit-details-marker) {
  display: none;
}

.course-library-card :deep(.course-actions-menu > summary:hover),
.course-library-card :deep(.course-actions-menu[open] > summary) {
  background: var(--lz-surface-subtle);
  color: var(--lz-text-strong);
}

.course-library-card :deep(.course-actions-menu__panel) {
  position: absolute;
  z-index: 12;
  top: calc(100% + 4px);
  right: 0;
  width: max-content;
  min-width: 176px;
  max-width: min(250px, calc(100vw - 56px));
  max-height: min(60vh, 360px);
  overflow: auto;
  padding: 4px;
  border: 1px solid var(--lz-border);
  border-radius: var(--radius-sm, 8px);
  background: #fff;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.1);
}

.course-library-card :deep(.course-actions-menu__panel button) {
  width: 100%;
  min-height: 40px;
  display: block;
  padding: 8px 10px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: var(--lz-text);
  font: inherit;
  font-size: 14px;
  line-height: 1.35;
  text-align: start;
  cursor: pointer;
}

.course-library-card :deep(.course-actions-menu__panel button:hover:not(:disabled)) {
  background: var(--lz-brand-soft);
  color: var(--lz-brand-strong);
}

.course-library-card :deep(.course-actions-menu__panel button:disabled) {
  color: var(--lz-text-muted);
  cursor: not-allowed;
}

.course-library-card :deep(.course-card-panel) {
  position: absolute;
  z-index: 11;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: min(60vh, 380px);
  overflow: auto;
  box-sizing: border-box;
  border: 1px solid var(--lz-border);
  border-radius: var(--radius-sm, 8px);
  background: #fff;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.1);
}

.course-library-card :deep(a:focus-visible),
.course-library-card :deep(button:focus-visible),
.course-library-card :deep(summary:focus-visible) {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .course-library-card {
    height: 124px;
  }

  .course-library-card :deep(.el-card__body) {
    grid-template-rows: minmax(0, 1fr) 44px;
    padding: 12px 14px;
  }

  .course-library-card__heading {
    grid-template-columns: 32px minmax(0, 1fr) 40px;
    gap: 8px;
  }

  .course-library-card :deep(.course-start) {
    min-height: 44px;
    padding-inline: 4px;
  }

  .course-library-card :deep(.course-actions-menu > summary) {
    width: 40px;
    height: 44px;
  }
}
</style>
