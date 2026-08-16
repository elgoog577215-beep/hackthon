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
    path: '/teacher/courses',
    name: 'teacher-course-library',
    component: () => import('../views/TeacherCourseLibraryView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/courses/new',
    name: 'teacher-course-create',
    component: () => import('../views/TeacherCourseCreateView.vue'),
    meta: { fullscreenConcept: true }
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
    path: '/workspace-concept/teacher-course-v1',
    name: 'teacher-course-production-concept',
    component: () => import('../views/TeacherCourseProductionConceptView.vue'),
    meta: { publicConcept: true, fullscreenConcept: true }
  },
  {
    path: '/course/:courseId',
    redirect: to => ({ name: 'learning', params: { courseId: to.params.courseId } })
  },
  {
    path: '/teacher/course/:courseId/overview',
    name: 'teacher-course-overview',
    component: () => import('../views/TeacherCourseOverviewView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/production',
    name: 'teacher-course-production',
    component: () => import('../views/TeacherCourseProductionView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/outline',
    name: 'teacher-course-outline',
    component: () => import('../views/TeacherCourseProductionView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/release',
    name: 'teacher-course-release',
    component: () => import('../views/TeacherCourseProductionView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/files',
    name: 'teacher-course-files',
    component: () => import('../views/TeacherCourseFilesView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/teaching-calendar',
    name: 'teacher-course-calendar',
    component: () => import('../views/TeacherCourseCalendarView.vue'),
    meta: { fullscreenConcept: true }
  },
  {
    path: '/teacher/course/:courseId/ppt',
    name: 'teacher-ppt-workspace',
    component: () => import('../views/PptWorkspaceView.vue'),
    meta: { fullscreenConcept: true, courseSurface: 'teacher' }
  },
  {
    path: '/teacher/teaching-calendar',
    name: 'teacher-teaching-calendar',
    component: () => import('../views/TeacherTeachingCalendarView.vue'),
    meta: { fullscreenConcept: true }
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
