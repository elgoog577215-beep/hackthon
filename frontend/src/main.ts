import { createApp } from 'vue'
import './style.css'
import './styles/design-system.css'
import './styles/learning-shell.css'
import './styles/resource-workspace.css'
import App from './App.vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import { createPinia } from 'pinia'
import router from './router'
import logger from './utils/logger'
import { initializeI18n } from './shared/i18n'
import {
  getActiveRequestIdentity,
  withApiBase,
} from './utils/http'
import {
  initializeUsageTracking,
  trackClientError,
  trackPageView,
  type UsageSurface,
} from './utils/usage-tracker'

const usageSurface = (route: typeof router.currentRoute.value): UsageSurface => (
  route.meta.identityScope === 'teacher' || route.query.teacherPreview === '1'
    ? 'teacher'
    : 'learner'
)

const currentUsageContext = () => {
  const route = router.currentRoute.value
  return {
    surface: usageSurface(route),
    routeName: typeof route.name === 'string' ? route.name : undefined,
    courseId: typeof route.params.courseId === 'string' ? route.params.courseId : undefined,
  }
}

const bootstrap = async () => {
  await initializeI18n()

  try {
    const app = createApp(App)
    const pinia = createPinia()

    initializeUsageTracking({
      endpoint: withApiBase('/api/usage-events/batch'),
      identityProvider: getActiveRequestIdentity,
      contextProvider: currentUsageContext,
    })
    let initialNavigation = true
    router.afterEach((to) => {
      const context = {
        userId: getActiveRequestIdentity(),
        surface: usageSurface(to),
        routeName: typeof to.name === 'string' ? to.name : undefined,
        courseId: typeof to.params.courseId === 'string' ? to.params.courseId : undefined,
      }
      trackPageView(context, initialNavigation ? 'initial' : 'route')
      initialNavigation = false
    })

    app.use(ElementPlus)
    app.use(pinia)
    app.use(router)

    app.mount('#app')
  } catch (e) {
    trackClientError('router_error')
    logger.error('App Mount Error:', e)
  }
}

void bootstrap()
