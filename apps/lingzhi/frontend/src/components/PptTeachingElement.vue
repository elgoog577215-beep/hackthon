<template>
  <pre v-if="element.kind === 'code'" class="ppt-teaching-code"><code>{{ element.text }}</code></pre>
  <figure v-else-if="element.kind === 'image'" class="ppt-teaching-image">
    <figcaption><MathText :content="element.text" /></figcaption>
    <p>{{ t('pptWorkspace.editor.imageInLayout') }}</p>
  </figure>
  <MathText v-else :tag="tag" :content="element.text" />
</template>

<script setup lang="ts">
import MathText from './MathText.vue'
import { t } from '../shared/i18n'
withDefaults(defineProps<{ element: { kind?: string; text: string }; tag?: string }>(), { tag: 'p' })
</script>

<style scoped>
.ppt-teaching-code{margin:0 0 16px;padding:16px;background:var(--lz-surface-muted,#f7f8fb);border-radius:6px;overflow:auto;white-space:pre;font:15px/1.7 monospace;color:inherit}
.ppt-teaching-image{margin:0 0 16px}.ppt-teaching-image p{margin:6px 0;color:var(--lz-text-secondary,#526078);font-size:15px}
</style>
