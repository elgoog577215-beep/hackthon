import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import logger from '../utils/logger'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/courses'
  },
  {
    path: '/courses',
    name: 'course-library',
    component: () => import('../views/CourseLibraryView.vue')
  },
  {
    path: '/course/:courseId',
    redirect: to => ({ name: 'learning', params: { courseId: to.params.courseId } })
  },
  {
    path: '/course/:courseId/learn/:nodeId?',
    name: 'learning',
    component: () => import('../views/LearningView.vue')
  },
  {
    path: '/course/:courseId/ppt',
    name: 'ppt-workspace',
    component: () => import('../views/PptWorkspaceView.vue')
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/courses'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.onError((error) => {
    logger.error('Router Error:', error)
})

export default router
