<template>
  <component :is="collapsible ? 'details' : 'div'" class="handout-contents" :class="{ 'handout-contents--collapsible': collapsible }" data-handout-print-exclude>
    <summary v-if="collapsible">{{ t('courseWorkbench.scriptDocument.readingContents', '目录') }}</summary>
    <nav :aria-label="t('courseWorkbench.scriptDocument.readingContents', '目录')">
      <a v-for="entry in entries" :key="entry.id" :href="`#${entry.id}`" :class="{ active: activeId === entry.id, 'handout-contents__child': entry.child }" :aria-current="activeId === entry.id ? 'location' : undefined" @click.prevent="navigate(entry.id)"><MathText :content="entry.title" /></a>
    </nav>
  </component>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MathText from './MathText.vue'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{ entries: { id: string; title: string; child?: boolean }[]; collapsible?: boolean }>(), { collapsible: false })
const emit = defineEmits<{ (event: 'navigate', id: string): void }>()
const activeId = ref('')
let animationFrame = 0
function navigate(id: string) {
  activeId.value = id
  document.getElementById(id)?.scrollIntoView?.({ behavior: 'instant', block: 'start' })
  emit('navigate', id)
}
function updatePosition() {
  const boundary = Math.min(160, window.innerHeight * .2)
  let current = props.entries[0]?.id || ''
  for (const entry of props.entries) {
    const node = document.getElementById(entry.id)
    if (node && node.getBoundingClientRect().top <= boundary) current = entry.id
  }
  activeId.value = current
}
function schedulePosition() {
  cancelAnimationFrame(animationFrame)
  animationFrame = requestAnimationFrame(updatePosition)
}
watch(() => props.entries, async () => {
  activeId.value = props.entries[0]?.id || ''
  await nextTick()
  updatePosition()
}, { immediate: true, deep: true })
onMounted(() => {
  // Capture nested reading-pane scrolls as well as the page. Reading position
  // remains UI state; course identities and order remain unchanged.
  window.addEventListener('scroll', schedulePosition, true)
  window.addEventListener('resize', schedulePosition)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', schedulePosition, true)
  window.removeEventListener('resize', schedulePosition)
  cancelAnimationFrame(animationFrame)
})
</script>

<style scoped>
.handout-contents{font:15px/1.65 var(--handout-sans);color:#526071}.handout-contents nav{display:grid;gap:3px}.handout-contents a{display:block;padding:7px 8px;border-left:2px solid transparent;color:inherit;text-decoration:none;overflow-wrap:anywhere}.handout-contents a:hover,.handout-contents a.active{background:#eae6f2;border-left-color:#6e4a9c;color:#523279}.handout-contents a.handout-contents__child{padding-left:20px;font-size:15px}.handout-contents a:focus-visible,.handout-contents summary:focus-visible{outline:3px solid #328dcc;outline-offset:3px}.handout-contents--collapsible{margin:0 0 26px;padding:12px 16px;border:1px solid #e1e5ec;background:#fafbfd}.handout-contents summary{cursor:pointer;color:#315e91;font-weight:650}.handout-contents[open] nav{margin-top:14px}@media print{.handout-contents{display:none}}
</style>
