<template>
  <div class="aid-toolbar">
    <template v-if="!searching">
      <span class="aid-scope-label">{{ c(scope === 'current' ? 'referenceCurrent' : 'referenceAllCourse') }}</span>
      <button class="aid-scope-toggle" :aria-label="c('referenceScope')" :aria-pressed="scope === 'all'" @click="emit('update:scope', scope === 'all' ? 'current' : 'all')">{{ c(scope === 'current' ? 'referenceOverview' : 'referenceCurrent') }}</button>
    </template>
    <input v-else ref="input" :value="query" type="search" :placeholder="placeholder" :aria-label="placeholder" @input="emit('update:query', ($event.target as HTMLInputElement).value)" @keydown.esc.stop="closeSearch" />
    <button ref="searchButton" class="aid-search-toggle" :aria-label="searching ? c('closeSearch') : placeholder" :aria-expanded="searching" @click="toggleSearch"><X v-if="searching" :size="17" /><Search v-else :size="17" /></button>
  </div>
</template>
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Search, X } from 'lucide-vue-next'
import { studyCopy as c } from '../shared/study-copy'
defineProps<{ scope: 'current' | 'all'; query: string; placeholder: string }>()
const emit = defineEmits<{ 'update:scope': [value: 'current' | 'all']; 'update:query': [value: string] }>()
const searching = ref(false), input = ref<HTMLInputElement | null>(null), searchButton = ref<HTMLButtonElement | null>(null)
async function closeSearch() { searching.value = false; emit('update:query', ''); await nextTick(); searchButton.value?.focus() }
async function toggleSearch() { if (searching.value) return closeSearch(); searching.value = true; await nextTick(); input.value?.focus() }
</script>
<style scoped>
.aid-toolbar { display:flex; align-items:center; gap:8px; flex:none; min-width:0; padding:6px 12px; border-bottom:1px solid #eceff4; background:#fff; font:13px/1.4 var(--study-ui-font); }
.aid-scope-label { flex:1; min-width:0; color:#657080; }
.aid-toolbar button { display:inline-flex; align-items:center; justify-content:center; flex:none; height:32px; padding:0 10px; font:inherit; color:#6e4a9c; border:1px solid #dcd6e7; border-radius:7px; background:#fff; cursor:pointer; }
.aid-toolbar .aid-search-toggle { width:32px; padding:0; color:#5b6474; border-color:transparent; }
.aid-toolbar button:hover { background:#f3effa; }
.aid-toolbar input { flex:1; box-sizing:border-box; width:0; min-width:0; height:32px; padding:0 8px; border:1px solid #dcd6e7; border-radius:7px; font:16px/1.4 var(--study-ui-font); color:#343c50; background:#fff; }
.aid-toolbar :focus-visible { outline:2px solid #8875b2; outline-offset:2px; }
</style>
