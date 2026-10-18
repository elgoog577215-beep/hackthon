<template>
  <RouterLink v-if="!disabled" class="student-create-course" to="/study?create=1">
    <Plus :size="17" aria-hidden="true" />{{ c('create') }}
  </RouterLink>
  <button v-else class="student-create-course" type="button" disabled>
    <Plus :size="17" aria-hidden="true" />{{ c('create') }}
  </button>
</template>

<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
import { studyCopy as c } from '../shared/study-copy'

defineProps<{ disabled?: boolean }>()
</script>

<style scoped>
.student-create-course {
  display:flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  min-height:var(--lz-control-height, 38px);
  padding:8px 14px;
  border:1px solid var(--lz-action-primary-border);
  border-radius:var(--lz-radius-control);
  background:var(--lz-action-primary-bg);
  color:var(--lz-action-primary-text);
  font:inherit;
  font-size:15px;
  font-weight:600;
  text-decoration:none;
}
.student-create-course:hover { background:var(--lz-action-primary-hover); }
.student-create-course:focus-visible { outline:2px solid var(--lz-action-focus); outline-offset:2px; }
.student-create-course:disabled {
  color:var(--lz-action-disabled-text);
  background:var(--lz-action-disabled-bg);
  border-color:var(--lz-action-border);
}
</style>
