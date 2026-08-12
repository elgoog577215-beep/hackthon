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
    path: '/teacher-course-space',
    name: 'teacher-course-space',
    component: () => import('../views/TeacherCourseSpaceView.vue')
  },
  {
    path: '/workspace-concept',
    name: 'workspace-concept',
    component: () => import('../views/WorkspacePortalConceptView.vue'),
    meta: { publicConcept: true }
  },
  {
    path: '/workspace-concept/modes',
    name: 'workspace-mode-lab',
    component: () => import('../views/WorkspaceModeLabView.vue'),
    meta: { publicConcept: true }
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
