<template>
  <section v-if="items.length || error" class="student-owned-courses" :aria-label="c('library')">
    <h3>{{ c('library') }}</h3>
    <RouterLink v-for="item in items" :key="item.id" :to="`/study/${encodeURIComponent(item.id)}`" :aria-current="materialId === item.id ? 'page' : undefined">
      <FileText :size="16" aria-hidden="true" />
      <span>{{ item.title }}<small>{{ c(item.purpose) }}</small></span>
    </RouterLink>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FileText } from 'lucide-vue-next'
import { studyApi, type StudySummary } from '../api/study'
import { studyCopy as c } from '../shared/study-copy'

const props = defineProps<{ userId: string; materialId?: string; materials?: StudySummary[] }>()
const loaded = ref<StudySummary[]>([]), error = ref(''), providedOwner = ref('')
const items = computed(() => {
  if (!props.userId) return []
  if (props.materials !== undefined) return providedOwner.value === props.userId ? props.materials : []
  return loaded.value
})
let controller: AbortController | undefined, sequence = 0
watch([() => props.userId, () => props.materials], async ([owner, provided], previous) => {
  const current = ++sequence
  controller?.abort()
  loaded.value = []; error.value = ''
  if (!owner) { providedOwner.value = ''; return }
  if (provided !== undefined) {
    providedOwner.value = owner !== previous?.[0] && provided === previous?.[1] ? '' : owner
    return
  }
  providedOwner.value = ''
  controller = new AbortController()
  try {
    const result = await studyApi.list(controller.signal)
    if (current === sequence) loaded.value = result
  } catch (cause) {
    if (current === sequence) error.value = cause instanceof Error ? cause.message : c('requestFailure')
  }
}, { immediate:true })
onBeforeUnmount(() => { sequence++; controller?.abort() })
</script>

<style scoped>
.student-owned-courses { min-height:0; max-height:260px; overflow:auto; border-top:1px solid var(--lz-border); padding:12px 8px; }
h3 { margin:0 8px 8px; font-size:15px; font-weight:600; color:var(--lz-text-secondary); }
a { display:flex; align-items:center; gap:8px; min-height:42px; padding:8px 10px; border-radius:var(--lz-radius-control); color:var(--lz-text); text-decoration:none; font-size:15px; }
a > svg { flex:none; color:var(--lz-brand); }
a > span { min-width:0; overflow-wrap:anywhere; }
small { display:block; margin-top:3px; font-size:13px; color:var(--lz-text-secondary); }
a:hover, a[aria-current="page"] { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
a:focus-visible { outline:2px solid var(--lz-brand); outline-offset:-2px; }
p { color:var(--lz-danger); font-size:15px; padding:0 8px; }
</style>
