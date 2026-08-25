<template>
  <nav
    class="compact-pagination"
    :aria-label="label"
    :data-testid="`${testIdPrefix}-pagination`"
  >
    <span class="compact-pagination__range">{{ rangeText }}</span>
    <div class="compact-pagination__controls">
      <button
        type="button"
        :aria-label="previousLabel"
        :title="previousLabel"
        :data-testid="`${testIdPrefix}-page-prev`"
        :disabled="page <= 1"
        @click="changePage(page - 1)"
      >
        <ChevronLeft :size="16" />
      </button>
      <label class="compact-pagination__page">
        <span class="visually-hidden">{{ pageSelectLabel }}</span>
        <select
          :value="page"
          :aria-label="pageSelectLabel"
          :data-testid="`${testIdPrefix}-page-select`"
          @change="selectPage"
        >
          <option v-for="targetPage in pageCount" :key="targetPage" :value="targetPage">
            {{ targetPage }}
          </option>
        </select>
        <span aria-hidden="true">/ {{ pageCount }}</span>
      </label>
      <button
        type="button"
        :aria-label="nextLabel"
        :title="nextLabel"
        :data-testid="`${testIdPrefix}-page-next`"
        :disabled="page >= pageCount"
        @click="changePage(page + 1)"
      >
        <ChevronRight :size="16" />
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps<{
  page: number
  pageCount: number
  rangeText: string
  label: string
  previousLabel: string
  nextLabel: string
  pageSelectLabel: string
  testIdPrefix: string
}>()

const emit = defineEmits<{
  'update:page': [page: number]
}>()

function changePage(page: number) {
  emit('update:page', Math.min(props.pageCount, Math.max(1, page)))
}

function selectPage(event: Event) {
  changePage(Number((event.target as HTMLSelectElement).value))
}
</script>

<style scoped>
.compact-pagination {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  color: #7c8798;
  background: #fff;
  font-size: 11px;
}

.compact-pagination__range {
  white-space: nowrap;
}

.compact-pagination__controls {
  display: inline-flex;
  align-items: center;
  border: 1px solid #dfe4ec;
  border-radius: 8px;
  background: #fff;
}

.compact-pagination__controls button {
  width: 34px;
  height: 32px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  color: #536174;
  background: transparent;
  cursor: pointer;
}

.compact-pagination__controls button:first-child {
  border-right: 1px solid #e7ebf1;
}

.compact-pagination__controls button:last-child {
  border-left: 1px solid #e7ebf1;
}

.compact-pagination__controls button:hover:not(:disabled) {
  color: #4338ca;
  background: #f6f6ff;
}

.compact-pagination__controls button:disabled {
  color: #c4cad4;
  cursor: not-allowed;
}

.compact-pagination__controls button:focus-visible,
.compact-pagination__page select:focus-visible {
  position: relative;
  z-index: 1;
  outline: 2px solid #6366f1;
  outline-offset: 1px;
}

.compact-pagination__page {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 9px;
  color: #8a94a5;
  white-space: nowrap;
}

.compact-pagination__page select {
  min-width: 26px;
  height: 30px;
  padding: 0 2px;
  border: 0;
  outline: 0;
  appearance: none;
  color: #263147;
  background: transparent;
  font: inherit;
  font-weight: 720;
  text-align: center;
  cursor: pointer;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
