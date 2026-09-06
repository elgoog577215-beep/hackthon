<template>
  <aside class="app-error-notice" :class="{ 'is-compact': compact }" role="alert">
    <span class="app-error-notice__icon" aria-hidden="true"><TriangleAlert :size="18" /></span>
    <div class="app-error-notice__content">
      <header>
        <strong>{{ presentation.title }}</strong>
        <button
          v-if="dismissible"
          type="button"
          :aria-label="t('appError.dismiss', '关闭这条错误')"
          @click="emit('dismiss')"
        >
          <X :size="15" />
        </button>
      </header>
      <p>{{ presentation.summary }}</p>
      <details v-if="presentation.technicalDetail">
        <summary>{{ t('appError.showTechnicalDetails', '查看技术详情') }}</summary>
        <pre><code>{{ presentation.technicalDetail }}</code></pre>
      </details>
      <div v-if="$slots.action" class="app-error-notice__action"><slot name="action" /></div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { TriangleAlert, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { AppErrorPresentation } from '../utils/app-error'

withDefaults(defineProps<{
  presentation: AppErrorPresentation
  compact?: boolean
  dismissible?: boolean
}>(), {
  compact: false,
  dismissible: false,
})

const emit = defineEmits<{ (event: 'dismiss'): void }>()
</script>

<style scoped>
.app-error-notice{min-width:0;display:grid;grid-template-columns:36px minmax(0,1fr);align-items:start;gap:11px;padding:13px 14px;border:1px solid #efc7bd;border-radius:12px;color:#7f1d1d;background:#fff8f6;box-shadow:0 12px 30px rgba(127,29,29,.12)}
.app-error-notice.is-compact{padding:11px 12px;border-radius:10px;box-shadow:none}
.app-error-notice__icon{width:36px;height:36px;display:grid;place-items:center;border-radius:9px;color:#b42318;background:#fee4e2}
.app-error-notice__content{min-width:0}
.app-error-notice header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.app-error-notice strong{min-width:0;color:#7a271a;font-size:13px;line-height:1.45;overflow-wrap:anywhere}
.app-error-notice header button{width:28px;height:28px;flex:none;display:grid;place-items:center;margin:-5px -5px 0 0;border:0;border-radius:7px;color:#9f5146;background:transparent;cursor:pointer}
.app-error-notice header button:hover{color:#7a271a;background:#fee4e2}
.app-error-notice header button:focus-visible{outline:2px solid #b42318;outline-offset:2px}
.app-error-notice p{margin:4px 0 0;color:#9f3a2d;font-size:12px;line-height:1.6;overflow-wrap:anywhere}
.app-error-notice details{margin-top:7px;color:#8f4a40;font-size:11px}
.app-error-notice summary{width:max-content;max-width:100%;cursor:pointer;font-weight:700}
.app-error-notice pre{max-height:180px;margin:7px 0 0;padding:9px 10px;overflow:auto;border:1px solid #f0d6d0;border-radius:8px;color:#5c2c25;background:#fff;font:11px/1.55 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.app-error-notice__action{display:flex;align-items:center;gap:8px;margin-top:10px}
.app-error-notice__action :deep(button){min-height:34px;padding:0 12px;border:1px solid #d92d20;border-radius:8px;color:#fff;background:#d92d20;font-size:12px;font-weight:750;cursor:pointer}
@media(prefers-reduced-motion:reduce){.app-error-notice *{scroll-behavior:auto!important}}
</style>
