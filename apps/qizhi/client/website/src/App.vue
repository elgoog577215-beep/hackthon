<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Navbar from './components/layout/Navbar.vue'
import RouteSlideView from './components/layout/RouteSlideView.vue'
import DialogConsoleTestHost from './dev/DialogConsoleTestHost.vue'
import { chatMessagesScrollToTop } from './utils/chatPageScroll'

const route = useRoute()
const shouldShowBackToTop = computed(() => route.path !== '/')
/** 智能对话：锁定视口高度，消息区内部滚动，避免整页被长对话撑出空白 */
const isFillLayout = computed(() => route.path === '/chat')
const isDev = import.meta.env.DEV
const dialogTestRef = ref<InstanceType<typeof DialogConsoleTestHost> | null>(null)

// 路由守卫拒绝学生访问教师专属页面时，会 dispatch 'rbac:denied'；这里弹 3s toast
const rbacToast = ref<string>('')
let rbacToastTimer: number | null = null
function showRbacToast(msg: string) {
  rbacToast.value = msg
  if (rbacToastTimer != null) window.clearTimeout(rbacToastTimer)
  rbacToastTimer = window.setTimeout(() => {
    rbacToast.value = ''
    rbacToastTimer = null
  }, 3000)
}
function handleRbacDenied() {
  showRbacToast('该功能仅对教师开放')
}

function scrollToTop() {
  if (route.path === '/chat') {
    chatMessagesScrollToTop({ smooth: true })
    return
  }
  window.scrollTo({ top: 0, left: 0, behavior: 'smooth' })
}

/** 临时：开发环境 console 测试弹窗，无需登录 */
onMounted(() => {
  window.addEventListener('rbac:denied', handleRbacDenied as EventListener)
  if (!isDev) return
  ;(window as any).testAlertDialog = () => dialogTestRef.value?.openAlert()
  ;(window as any).testMessageDialog = () => dialogTestRef.value?.openMessage()
  console.info(
    '[dialog-test] 已注册（无需登录）：testAlertDialog() / testMessageDialog()'
  )
})

onUnmounted(() => {
  window.removeEventListener('rbac:denied', handleRbacDenied as EventListener)
  if (rbacToastTimer != null) {
    window.clearTimeout(rbacToastTimer)
    rbacToastTimer = null
  }
  delete (window as any).testAlertDialog
  delete (window as any).testMessageDialog
})
</script>

<template>
  <div class="app-container" :class="{ 'app-container--fill': isFillLayout }">
    <Navbar />
    <div class="route-slide-host" :class="{ 'route-slide-host--fill': isFillLayout }">
      <RouteSlideView />
    </div>
    <button
      v-if="shouldShowBackToTop"
      type="button"
      class="back-to-top"
      aria-label="返回顶部"
      title="返回顶部"
      @click="scrollToTop"
    >
      <svg class="back-to-top-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M12 19V5M12 5l-7 7M12 5l7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="back-to-top-text">返回顶部</span>
    </button>
    <!-- 临时：开发环境弹窗 console 测试宿主 -->
    <DialogConsoleTestHost v-if="isDev" ref="dialogTestRef" />
    <!-- RBAC 拒绝访问提示（学生访问教师专属页时由 router.beforeEach 触发） -->
    <Transition name="rbac-toast">
      <div v-if="rbacToast" class="rbac-toast" role="status">{{ rbacToast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.app-container {
  width: 100%;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-container--fill {
  height: 100dvh;
  max-height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

.app-container--fill :deep(> .navbar) {
  flex-shrink: 0;
}

.route-slide-host--fill {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 对话页根节点占满导航栏以下区域（flex 子项须 min-height:0 才能内部滚动） */
.app-container--fill .route-slide-host--fill :deep(.chat-view) {
  flex: 1 1 0;
  min-height: 0;
  height: auto;
  max-height: none;
}

.back-to-top {
  position: fixed;
  right: max(16px, env(safe-area-inset-right, 0px));
  bottom: max(24px, env(safe-area-inset-bottom, 0px) + 16px);
  z-index: 99;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.95);
  color: #333;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: background-color 0.2s, box-shadow 0.2s, transform 0.05s;
}
.back-to-top:hover {
  background: #fff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14), 0 0 0 1px rgba(91, 141, 238, 0.25);
  color: #5b8dee;
}
.back-to-top:active {
  transform: scale(0.98);
}
.back-to-top:focus-visible {
  outline: 2px solid rgba(91, 141, 238, 0.6);
  outline-offset: 2px;
}
.back-to-top-icon {
  flex-shrink: 0;
}

@media (max-width: 480px) {
  .back-to-top-text {
    display: none;
  }
  .back-to-top {
    width: 48px;
    height: 48px;
    padding: 0;
    justify-content: center;
    border-radius: 50%;
  }
}

/* 移动端整体隐藏返回顶部按钮：触屏端常规用系统手势或滑动，悬浮按钮容易
   挡住聊天输入区/页面底部的操作元素 */
@media (max-width: 640px) {
  .back-to-top {
    display: none !important;
  }
}

.rbac-toast {
  position: fixed;
  top: 88px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1200;
  padding: 10px 18px;
  background: rgba(26, 37, 64, 0.92);
  color: #fff;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 6px 20px rgba(15, 28, 58, 0.18);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  pointer-events: none;
}

.rbac-toast-enter-active,
.rbac-toast-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.rbac-toast-enter-from,
.rbac-toast-leave-to {
  opacity: 0;
  transform: translate(-50%, -10px);
}
</style>
