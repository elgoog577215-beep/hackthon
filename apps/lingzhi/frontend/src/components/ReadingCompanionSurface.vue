<template>
  <Teleport :to="inline ? anchor! : fullTarget || 'body'" :disabled="!inline && !fullTarget">
    <section v-show="visible" class="reading-companion-surface" :class="{ 'is-inline': inline, 'is-collapsed': collapsed && inline }" :aria-label="t('readingCompanion.title')">
      <header v-if="usableAnchor && (!minimal || !inline)" class="reading-companion-toolbar">
        <span><Sparkles :size="16" />{{ t('readingCompanion.title') }}</span>
        <template v-if="inline">
          <button v-if="collapsed" type="button" data-testid="companion-reopen" @click="collapsed = false">{{ t('readingCompanion.reopen') }}</button>
          <button v-else type="button" data-testid="companion-collapse" @click="collapsed = true">{{ t('readingCompanion.collapse') }}</button>
        </template>
        <button v-else type="button" data-testid="companion-return-inline" @click="move(true)"><CornerDownLeft :size="15" />{{ t('readingCompanion.return') }}</button>
      </header>
      <div v-show="!inline || !collapsed" class="reading-companion-content"><slot :inline="inline" :expand="() => move(false)" /></div>
      <footer v-if="!minimal && inline && !collapsed" class="reading-companion-more"><span>{{t('readingCompanion.moreHint')}}</span><button type="button" data-testid="companion-expand" @click="move(false)">{{t('readingCompanion.expand')}}<Maximize2 :size="15" /></button></footer>
    </section>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { CornerDownLeft, Maximize2, Sparkles } from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  anchor?: HTMLElement | null
  fullTarget?: string
  visible?: boolean
  minimal?: boolean
}>(), { anchor: null, fullTarget: '', visible: true })
const emit = defineEmits<{ presentationChange: [inline: boolean] }>()
const connected = ref(false), expanded = ref(false), collapsed = ref(false)
const usableAnchor = computed(() => Boolean(props.anchor && connected.value))
const inline = computed(() => usableAnchor.value && !expanded.value)
function checkAnchor() { connected.value = Boolean(props.anchor?.isConnected) }
watch(() => props.anchor, () => { checkAnchor(); expanded.value = false; collapsed.value = false }, { immediate: true })
watch(inline, value => emit('presentationChange', value), { immediate: true })

async function move(toInline: boolean) {
  checkAnchor()
  const scroller = props.anchor?.closest<HTMLElement>('#content-scroll-container, .study-document-scroll, [data-reading-scroll]')
  const scrollTop = scroller?.scrollTop
  expanded.value = !toInline
  collapsed.value = false
  await nextTick()
  if (scroller?.isConnected && scrollTop !== undefined) scroller.scrollTop = scrollTop
}
// A source rerender can remove the teleport target without changing its ref.
// Move the existing component to its full surface; never recreate its session.
let observer: MutationObserver | undefined
onMounted(() => {
  checkAnchor()
  observer = new MutationObserver(checkAnchor)
  observer.observe(document.body, { childList: true, subtree: true })
})
onUnmounted(() => observer?.disconnect())
defineExpose({ expand: () => move(false) })
</script>

<style scoped>
.reading-companion-surface{display:flex;flex-direction:column;flex:1;min-height:0;min-width:0;height:100%}
.reading-companion-content{display:flex;flex-direction:column;flex:1;min-height:0;min-width:0}
.reading-companion-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid #e4dff0;color:var(--lz-text-secondary,#66557b);font-size:15px;background:#f8f6fc}
.reading-companion-toolbar>span{display:flex;align-items:center;gap:6px;margin-right:auto;font-weight:650}
.reading-companion-toolbar button{display:inline-flex;align-items:center;gap:5px;min-height:32px;border:0;border-radius:7px;padding:4px 8px;background:transparent;color:inherit;font:inherit;cursor:pointer}
.reading-companion-toolbar button:hover{background:#eee9f8}
.reading-companion-toolbar button:focus-visible{outline:2px solid #8b75c4;outline-offset:2px}
.reading-companion-surface.is-inline{height:auto;max-height:none;margin:12px 0 20px;border:1px solid #d7dbea;border-radius:10px;overflow:visible;background:white;box-shadow:0 3px 12px rgba(48,55,80,.04)}
.is-inline .reading-companion-toolbar{border-radius:10px 10px 0 0;padding:7px 12px;background:#f7f8fc;color:#3e4c65;font-size:15px}
.reading-companion-more{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:9px 16px;border-top:1px solid #e4e7ef;font-size:14px;color:#58657a;background:#fafbfe;border-radius:0 0 10px 10px}
.reading-companion-more button{display:inline-flex;align-items:center;gap:6px;border:0;background:transparent;color:#5145aa;font:inherit;font-size:15px;font-weight:600;cursor:pointer;padding:5px 0}
.reading-companion-surface.is-collapsed{height:auto;max-height:none}
.is-inline .reading-companion-content{flex:none;overflow:visible}
.is-inline :deep(.ai-teacher-panel),.is-inline :deep(.ai-teacher-surface){width:100%;height:auto;max-height:none;min-height:0;flex:none;border:0;border-radius:0;box-shadow:none;overflow:visible}
.is-inline :deep(.personal-assistant){width:100%;height:auto;border:0}
</style>
