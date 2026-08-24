<template>
  <Teleport to="body">
    <TransitionGroup
      v-if="entries.length"
      tag="section"
      name="app-error-stack"
      class="app-error-center"
      :aria-label="t('appError.centerLabel', '异常反馈')"
    >
      <AppErrorNotice
        v-for="entry in entries"
        :key="entry.id"
        :presentation="entry.presentation"
        dismissible
        @dismiss="dismiss(entry.id)"
      />
    </TransitionGroup>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AppErrorNotice from './AppErrorNotice.vue'
import { t } from '../shared/i18n'
import { publishAppError, subscribeAppErrors, type AppErrorEvent } from '../utils/app-error'

const entries = ref<AppErrorEvent[]>([])
let unsubscribe: () => void = () => undefined

function receive(event: AppErrorEvent) {
  const duplicateIndex = entries.value.findIndex(item => item.signature === event.signature)
  const next = [...entries.value]
  if (duplicateIndex >= 0) next.splice(duplicateIndex, 1)
  next.unshift(event)
  entries.value = next.slice(0, 3)
}

function dismiss(id: string) {
  entries.value = entries.value.filter(entry => entry.id !== id)
}

function captureWindowError(event: ErrorEvent) {
  publishAppError(event.error || event.message, {
    title: t('appError.names.pageRuntime', '页面运行异常'),
    fallback: t('appError.reasons.pageRuntime', '页面运行时发生异常，请查看技术详情并刷新后重试。'),
  })
}

function captureUnhandledRejection(event: PromiseRejectionEvent) {
  if (event.reason && typeof event.reason === 'object' && event.reason.isAxiosError === true) return
  publishAppError(event.reason, {
    title: t('appError.names.pageRuntime', '页面运行异常'),
    fallback: t('appError.reasons.pageRuntime', '页面运行时发生异常，请查看技术详情并刷新后重试。'),
  })
}

onMounted(() => {
  unsubscribe = subscribeAppErrors(receive)
  window.addEventListener('error', captureWindowError)
  window.addEventListener('unhandledrejection', captureUnhandledRejection)
})
onBeforeUnmount(() => {
  unsubscribe()
  window.removeEventListener('error', captureWindowError)
  window.removeEventListener('unhandledrejection', captureUnhandledRejection)
})
</script>

<style scoped>
.app-error-center{position:fixed;z-index:3000;top:78px;right:18px;width:min(430px,calc(100vw - 36px));display:grid;gap:10px;pointer-events:none}
.app-error-center :deep(.app-error-notice){pointer-events:auto}
.app-error-stack-enter-active,.app-error-stack-leave-active{transition:opacity .18s ease,transform .18s ease}
.app-error-stack-enter-from,.app-error-stack-leave-to{opacity:0;transform:translateY(-8px)}
@media(prefers-reduced-motion:reduce){.app-error-stack-enter-active,.app-error-stack-leave-active{transition:none}}
</style>
