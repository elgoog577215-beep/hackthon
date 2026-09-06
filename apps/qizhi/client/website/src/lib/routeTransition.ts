import { computed, ref } from 'vue'
import type { Router } from 'vue-router'

/** 横向滑动：前进（新页从右入）/ 后退（新页从左入） */
export type RouteSlideDirection = 'forward' | 'back'

/** slide：Tab 位移动画；fade：整页刷新式淡入（首页、鉴权、跨模块等） */
export type RouteTransitionMode = 'slide' | 'fade'

export const routeSlideDirection = ref<RouteSlideDirection>('forward')
export const routeTransitionMode = ref<RouteTransitionMode>('slide')

export const routeSlideTransitionName = computed(() =>
  routeTransitionMode.value === 'fade' ? 'fade-page' : routeSlideDirection.value === 'forward' ? 'slide-left' : 'slide-right',
)

let lastHistoryPosition =
  typeof window !== 'undefined' ? ((history.state?.position as number | undefined) ?? 0) : 0

/** 与 Navbar 主导航从左到右顺序一致，用于判断 Tab 切换方向 */
const NAV_TAB_PREFIXES: { prefix: string; order: number }[] = [
  // 资源工作台/大纲表单已并入「我的课程」族系（同一 Tab order）
  { prefix: '/my-courses', order: 1 },
  { prefix: '/newcourse-form', order: 1 },
  { prefix: '/course/', order: 1 },
  { prefix: '/resource/', order: 1 },
  { prefix: '/outline-form', order: 1 },
  { prefix: '/resource/generate', order: 1 },
  { prefix: '/ppt-generate', order: 1 },
  { prefix: '/chat', order: 2 },
  { prefix: '/resource-analysis', order: 3 },
]

const ADMIN_TAB_PREFIXES: { prefix: string; order: number }[] = [
  { prefix: '/admin/dashboard', order: 0 },
  { prefix: '/admin/agents', order: 1 },
  { prefix: '/admin/users', order: 2 },
  { prefix: '/admin/feedbacks', order: 3 },
  { prefix: '/admin/audit-logs', order: 4 },
]

function matchTabOrder(path: string, table: { prefix: string; order: number }[]): number | null {
  for (const { prefix, order } of table) {
    if (path === prefix || path.startsWith(prefix)) return order
  }
  return null
}

function isFadeRoute(path: string): boolean {
  if (path === '/' || path.startsWith('/auth')) return true
  if (path.startsWith('/essay-check')) return true
  if (path.startsWith('/smart-classroom-video-analysis')) return true
  return false
}

/** 同一大 Tab 内从列表进入详情 */
function isDrillDown(from: string, to: string): boolean {
  if ((from === '/my-courses' || from.startsWith('/course/')) && (to.startsWith('/resource/') || to === '/outline-form')) return true
  if (from === '/my-courses' && (to.startsWith('/course/') || to === '/newcourse-form')) return true
  if (from === '/resource-analysis' && to.startsWith('/resource-analysis/') && to !== '/resource-analysis') {
    return true
  }
  if (from.startsWith('/course/') && to.startsWith('/course/') && to.length > from.length) return true
  return false
}

function isDrillUp(from: string, to: string): boolean {
  if ((to === '/my-courses' || to.startsWith('/course/')) && from.startsWith('/resource/')) return true
  if (to === '/outline-form' && from.startsWith('/resource/')) return true
  if (to === '/my-courses' && (from.startsWith('/course/') || from === '/newcourse-form')) return true
  if (to === '/resource-analysis' && from.startsWith('/resource-analysis/')) return true
  if (from.startsWith('/course/') && to.startsWith('/course/') && to.length < from.length) return true
  return false
}

type HistoryDelta = 'forward' | 'back' | 'same'

function resolveTransition(
  fromPath: string,
  toPath: string,
  historyDelta: HistoryDelta,
): { mode: RouteTransitionMode; direction: RouteSlideDirection } {
  if (fromPath === toPath) {
    return { mode: 'fade', direction: 'forward' }
  }

  if (isFadeRoute(fromPath) || isFadeRoute(toPath)) {
    return { mode: 'fade', direction: 'forward' }
  }

  const fromAdmin = fromPath.startsWith('/admin')
  const toAdmin = toPath.startsWith('/admin')
  if (fromAdmin || toAdmin) {
    if (fromAdmin && toAdmin) {
      const fromOrder = matchTabOrder(fromPath, ADMIN_TAB_PREFIXES)
      const toOrder = matchTabOrder(toPath, ADMIN_TAB_PREFIXES)
      if (fromOrder != null && toOrder != null && fromOrder !== toOrder) {
        return {
          mode: 'slide',
          direction: toOrder > fromOrder ? 'forward' : 'back',
        }
      }
    }
    return { mode: 'fade', direction: 'forward' }
  }

  if (isDrillDown(fromPath, toPath)) {
    return { mode: 'slide', direction: 'forward' }
  }
  if (isDrillUp(fromPath, toPath)) {
    return { mode: 'slide', direction: 'back' }
  }

  const fromOrder = matchTabOrder(fromPath, NAV_TAB_PREFIXES)
  const toOrder = matchTabOrder(toPath, NAV_TAB_PREFIXES)

  if (fromOrder != null && toOrder != null) {
    if (fromOrder !== toOrder) {
      return {
        mode: 'slide',
        direction: toOrder > fromOrder ? 'forward' : 'back',
      }
    }
    // 同 Tab 族系内横向切换（如不同资源 id）用淡入，避免每次都全屏横滑
    return { mode: 'fade', direction: 'forward' }
  }

  if (historyDelta === 'back') {
    return { mode: 'slide', direction: 'back' }
  }
  if (historyDelta === 'forward') {
    return { mode: 'slide', direction: 'forward' }
  }

  return { mode: 'fade', direction: 'forward' }
}

/** 根据 history 与主导航 Tab 关系决定页面切换动画 */
export function installRouteSlideTransition(router: Router) {
  router.afterEach((to, from) => {
    const toPos = (history.state?.position as number | undefined) ?? lastHistoryPosition

    if (from.name != null && to.path !== from.path) {
      let historyDelta: HistoryDelta = 'same'
      if (toPos > lastHistoryPosition) historyDelta = 'forward'
      else if (toPos < lastHistoryPosition) historyDelta = 'back'

      const { mode, direction } = resolveTransition(from.path, to.path, historyDelta)
      routeTransitionMode.value = mode
      routeSlideDirection.value = direction
    }

    lastHistoryPosition = toPos
  })
}
