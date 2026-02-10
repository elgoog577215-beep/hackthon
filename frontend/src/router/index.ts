import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/CourseView.vue')
  },
  {
    path: '/course/:courseId',
    name: 'course',
    component: () => import('../views/CourseView.vue')
  },
  // Catch-all route
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.onError((error) => {
    console.error('Router Error:', error)
    document.body.innerHTML += `<div style="color: red; padding: 20px; z-index: 9999; position: fixed; top: 50px; left: 0; background: white; border: 2px solid orange;">
        Router Error: ${error.message}
    </div>`
})

export default router
